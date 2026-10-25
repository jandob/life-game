"""Qwen-Image 2.1 (Turbo) with a GGUF transformer on MPS.

Components:

* transformer: ``abenzerps/Qwen-Image-2.1-Turbo-Quantized`` Q8_0 GGUF (7.6 GB), loaded with
  ``QwenImage21Transformer2DModel.from_single_file``; ``_gguf.fix_non_linear`` repairs a diffusers bug.
* VAE ``AutoencoderKLQwenImage21`` (fp32, bf16 with reference images), always tiled: an untiled
  1024 px decode peaks at 28 GB and swaps.
* scheduler, processor, configs and the Turbo 8-step ``sample_sigmas`` from ``Qwen/Qwen-Image-2.1-Turbo``.
* text encoder ``Qwen3VLForConditionalGeneration`` (17.5 GB bf16 on CPU). It runs ONLY in the separate
  process ``python -m backends.qwen_encode`` and is never resident together with the transformer.
  Encodings are cached on disk (``_enc_cache``, namespace ``qwen21``), so extra seeds and repeat runs
  skip the 20 s - 6 min encode.

The embeddings reach the pipeline by replacing ``pipe.encode_prompt``; ``check_pipeline_api`` fails at
load time if the pinned diffusers commit changed the relevant signatures.
"""
from __future__ import annotations

import gc
import inspect
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image

from . import _enc_cache
from .base import Backend, BackendInfo
from ._common import MemTracker, hf_file, hf_snapshot, load_registry

NAMESPACE = "qwen21"
PINNED_DIFFUSERS = "85c9fa4caee33d1c5b473395784471d2d7957c1b"   # github.com/huggingface/diffusers
TEMPLATE = ("Pixel art sprite of {prompt}, 16-bit video game asset, crisp hard-edged pixels, "
            "flat colours, {background}.")
RGBA_TEMPLATE = ("This is an RGBA image with transparency. Pixel art sprite of {prompt}, 16-bit video "
                 "game asset, crisp hard-edged pixels, flat colours. The image has alpha channel and "
                 "the background is transparent.")
ENCODE_PARAMS = ("prompt", "image", "device", "num_images_per_prompt", "prompt_embeds",
                 "prompt_embeds_mask", "image_pad_mask")

# Variant profiles (local). The 40-step base model with real CFG is the separate backend
# runpod_qwen_image21 (RunPod Serverless).
PROFILES = {
    "turbo": {"steps": 8, "true_cfg": 1.0, "negative": None},
}


def check_pipeline_api(pipe_cls) -> None:
    """Fail loudly if the installed diffusers no longer matches what this backend relies on."""
    problems = []
    enc = set(inspect.signature(pipe_cls.encode_prompt).parameters)
    problems += [f"encode_prompt lacks {p!r}" for p in ENCODE_PARAMS if p not in enc]
    if "output_resolution" not in inspect.signature(pipe_cls.__call__).parameters:
        problems.append("__call__ lacks 'output_resolution'")
    if "sample_sigmas" not in inspect.signature(pipe_cls.__init__).parameters:
        problems.append("__init__ lacks 'sample_sigmas'")
    if problems:
        raise RuntimeError(
            "QwenImage21Pipeline API changed (" + "; ".join(problems) + "). artgen is pinned to diffusers "
            f"commit {PINNED_DIFFUSERS}: pip install git+https://github.com/huggingface/diffusers@{PINNED_DIFFUSERS}")


def diffusers_version() -> dict:
    import importlib.metadata as md
    import diffusers
    out = {"version": diffusers.__version__, "commit": None}
    try:
        du = json.loads(md.distribution("diffusers").read_text("direct_url.json") or "{}")
        out["commit"] = du.get("vcs_info", {}).get("commit_id")
    except Exception:  # noqa: BLE001
        pass
    return out


def snapshot_revision(path: str) -> str:
    """Commit hash of an HF snapshot dir (its directory name)."""
    return Path(path).resolve().name


def lfs_sha256(path: str) -> str | None:
    """sha256 of a cached LFS file: the repo blob name in the HF cache IS the sha256.

    Follow only the snapshot link (snapshots/<rev>/file -> ../../blobs/<sha256>): newer caches link
    that blob on into a global content store whose names are not the file's sha256.
    """
    name = Path(os.readlink(path)).name if os.path.islink(path) else Path(path).name
    return name if re.fullmatch(r"[0-9a-f]{64}", name) else None


def file_sha256(path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def condition_image(img: Image.Image, res: int) -> Image.Image:
    """Same resize as QwenImage21Pipeline.__call__ step 1, so encoded vision tokens match what
    the pipeline feeds the transformer. Used for the encode key and the encode itself."""
    from diffusers.image_processor import VaeImageProcessor
    from diffusers.pipelines.qwenimage21.pipeline_qwenimage21 import calculate_dimensions
    img = img.convert("RGBA")
    w, h, _ = calculate_dimensions(res * res, img.width / img.height)
    return VaeImageProcessor(vae_scale_factor=16, vae_latent_channels=64).resize(img, width=w, height=h)


def set_vae_dtype(vae, torch, with_refs: bool) -> str:
    """fp32 normally; bf16 when reference images reach the VAE (prepare_latents uses the transformer dtype)."""
    vae.to(torch.bfloat16 if with_refs else torch.float32)
    return "bf16" if with_refs else "fp32"


class QwenImage21(Backend):
    info = BackendInfo(
        name="qwen_image21",
        description="Qwen-Image 2.1 Turbo (8 saved sigmas, no CFG), Q8_0 GGUF transformer, local MPS; "
                    "text encoder in a separate process with an on-disk encoding cache",
        models=["Qwen/Qwen-Image-2.1-Turbo", "abenzerps/Qwen-Image-2.1-Turbo-Quantized (Q8_0 GGUF)"],
        licence="Qwen Research licence (qwen-research, see the model card); GGUF conversion by abenzerps, same licence",
        local=True,
        caps=frozenset({"refs", "edit", "sheet", "rgba"}),
        defaults={"variant": "turbo", "background": "plain flat white background", "rgba": 0},
        prompt_template=TEMPLATE,
        default_size=(1024, 1024),
    )
    load_keys = frozenset({"variant"})
    passthrough_opts = frozenset({"ref", "rgba"})
    template_flags = frozenset({"rgba", "ref"})   # non-string opts that apply_template also needs

    def __init__(self) -> None:
        self.torch = None
        self.device = None
        self.pipe = None
        self.vae = None
        self.sched = None
        self.processor = None
        self.cfg = None
        self.profile = None
        self._stats: dict[str, Any] = {}

    # ---------------------------------------------------------------- prompt
    def apply_template(self, subject: str, **fields) -> str:
        if fields.get("ref"):
            return subject      # with references --prompt is sent verbatim ("Picture 1/2/3 ..."): no sprite template
        if fields.get("rgba"):
            return RGBA_TEMPLATE.format(prompt=subject)
        return super().apply_template(subject, **fields)

    # ------------------------------------------------------------------ load
    def load(self, variant: str = "turbo", **_ignored) -> None:
        """Light: scheduler, processor, VAE (no transformer, no text encoder)."""
        if variant not in PROFILES:
            raise ValueError(f"unknown variant {variant!r}; known: {', '.join(PROFILES)} "
                             "(the 40-step base model is the backend runpod_qwen_image21)")
        import torch
        from diffusers import (AutoencoderKLQwenImage21, FlowMatchEulerDiscreteScheduler, QwenImage21Pipeline)
        from transformers import Qwen3VLProcessor
        check_pipeline_api(QwenImage21Pipeline)
        t0 = time.perf_counter()
        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.profile = dict(PROFILES[variant], name=variant)
        self.cfg = load_registry()["qwen_image21"]
        self.snap = hf_snapshot(self.cfg["config_repo"], ["*.json", "*.jinja", "*.txt", "vae/*", "processor/*"])
        self.encoder_id = f"{self.cfg['config_repo']}@{snapshot_revision(self.snap)}"
        self.sample_sigmas = json.loads(Path(self.snap, "model_index.json").read_text()).get("sample_sigmas")
        self.sched = FlowMatchEulerDiscreteScheduler.from_pretrained(self.snap, subfolder="scheduler")
        self.processor = Qwen3VLProcessor.from_pretrained(os.path.join(self.snap, "processor"))
        self.vae = AutoencoderKLQwenImage21.from_pretrained(self.snap, subfolder="vae", torch_dtype=torch.float32)
        # Untiled fp32 decode at 1024 px peaks at 28 GB on MPS (swap on 24 GB); tiled peaks near 10 GB.
        self.vae.enable_tiling()
        self.mem = MemTracker(torch, self.device, self._stats)
        self._stats.update(
            load_s=round(time.perf_counter() - t0, 1), device=self.device, variant=variant,
            diffusers=diffusers_version(), encoder_id=self.encoder_id,
            vae={"tiling": True, "dtype": "fp32"}, true_cfg=self.profile["true_cfg"])

    def _load_pipe(self, with_refs: bool = False):
        if self.pipe is not None:
            return self.pipe
        torch = self.torch
        from diffusers import GGUFQuantizationConfig, QwenImage21Pipeline, QwenImage21Transformer2DModel
        from ._gguf import fix_non_linear
        t0 = time.perf_counter()
        gguf_path = hf_file(self.cfg["gguf_repo"], self.cfg["gguf_file"])
        tr = QwenImage21Transformer2DModel.from_single_file(
            gguf_path, quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
            config=self.snap, subfolder="transformer", torch_dtype=torch.bfloat16)
        fixed = fix_non_linear(tr)
        pipe = QwenImage21Pipeline(scheduler=self.sched, vae=self.vae, text_encoder=None,
                                   processor=self.processor, transformer=tr,
                                   sample_sigmas=self.sample_sigmas)
        pipe.to(self.device)
        vae_dtype = set_vae_dtype(pipe.vae, torch, with_refs)
        pipe.vae.enable_tiling()
        pipe.set_progress_bar_config(disable=True)
        self.pipe = pipe
        self._stats.update(
            transformer_load_s=round(time.perf_counter() - t0, 1), gguf_fixed=len(fixed),
            gguf={"repo": self.cfg["gguf_repo"], "file": self.cfg["gguf_file"], "sha256": lfs_sha256(gguf_path)},
            vae={"tiling": True, "dtype": vae_dtype})
        self.mem()
        return pipe

    def _drop_pipe(self) -> None:
        self.pipe = None
        gc.collect()
        if self.device == "mps":
            self.torch.mps.empty_cache()

    # ---------------------------------------------------------------- encode
    def _jobs_missing(self, jobs: list[dict]) -> list[dict]:
        todo, seen = [], set()
        for j in jobs:
            conds = [condition_image(Image.open(p), j["ref_res"]) for p in j.get("ref_paths") or []]
            k = _enc_cache.key(j["prompt"], conds, j["ref_res"], self.encoder_id)
            if k not in seen and _enc_cache.get(k, NAMESPACE) is None:
                todo.append(j)
            seen.add(k)
        return todo

    def _run_encoder(self, jobs: list[dict]) -> None:
        """Encode in a child process (stdout routed to stderr: callers parse our stdout)."""
        import tempfile
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as td:
            jf = Path(td) / "jobs.json"
            jf.write_text(json.dumps(jobs))
            subprocess.run([sys.executable, "-m", "backends.qwen_encode", str(jf)],
                           cwd=str(Path(__file__).resolve().parent.parent), stdout=sys.stderr, check=True)
        self._stats["last_encode_s"] = round(time.perf_counter() - t0, 1)
        self._stats["encode_runs"] = self._stats.get("encode_runs", 0) + 1

    def precompute(self, prompts: list[str], refs: list[str] | None = None, ref_res: int = 512) -> None:
        if self.sched is None:
            self.load()
        todo = self._jobs_missing([{"prompt": p, "ref_paths": list(refs or []), "ref_res": ref_res}
                                   for p in dict.fromkeys(prompts)])
        if not todo:
            return
        self._drop_pipe()      # never hold transformer and text encoder together
        self._run_encoder(todo)

    # -------------------------------------------------------------- generate
    def generate(self, prompt, negative=None, width=1024, height=1024, seed=0, n=1,
                 sigmas: list | None = None, ref=None, ref_res: int = 512,
                 true_cfg: float | None = None, **_ignored) -> list[Image.Image]:
        """``ref``: reference image paths (Picture 1, 2, ...); with refs the prompt is used verbatim
        (see apply_template). ``ref_res``: side the refs are resized to (encode and pipeline alike);
        independent of width/height."""
        if self.sched is None:
            self.load()
        ref = [ref] if isinstance(ref, str) else list(ref or [])
        ref_res = int(ref_res)
        if width % 16 or height % 16:
            raise ValueError("width and height must be multiples of 16")
        torch = self.torch
        if true_cfg is not None and float(true_cfg) != self.profile["true_cfg"]:
            raise NotImplementedError("true_cfg != profile value is not supported locally (use runpod_qwen_image21)")
        self._stats.pop("last_encode_s", None)
        ref_imgs = [Image.open(p).convert("RGBA") for p in ref]
        conds = [condition_image(im, ref_res) for im in ref_imgs]
        key = _enc_cache.key(prompt, conds, ref_res, self.encoder_id)
        enc = _enc_cache.get(key, NAMESPACE)
        encoded_now = enc is None
        if enc is None:
            self.precompute([prompt], ref, ref_res)
            enc = _enc_cache.get(key, NAMESPACE)
            if enc is None:
                raise RuntimeError("encoder process finished but the encoding is not in the cache")
        pipe = self._load_pipe(with_refs=bool(ref))
        vae_dtype = set_vae_dtype(pipe.vae, torch, bool(ref))
        self._check_return_arity(enc)
        enc = tuple(None if t is None else t.to(self.device) for t in enc)
        pipe.encode_prompt = lambda **kw: enc     # the pipeline has no text encoder
        used = [float(s) for s in sigmas] if sigmas else list(self.sample_sigmas)
        kw: dict[str, Any] = dict(width=width, height=height, true_cfg_scale=self.profile["true_cfg"],
                                  callback_on_step_end=lambda p, i, t, k: (self.mem(), k)[1])
        if ref:
            kw.update(image=ref_imgs, output_resolution=ref_res)   # the pipeline resizes them like condition_image
        if sigmas:
            kw["sigmas"] = used
        else:
            kw["num_inference_steps"] = len(used)
        out, times = [], []
        for i in range(n):
            g = torch.Generator("cpu").manual_seed(int(seed) + i)
            t1 = time.perf_counter()
            with torch.no_grad():
                img = pipe(prompt=prompt, generator=g, **kw).images[0]
            if self.device == "mps":
                torch.mps.synchronize()
            times.append(time.perf_counter() - t1)
            self.mem()
            out.append(img.convert("RGBA"))
        self._stats.update(last_image_s=[round(x, 2) for x in times], sigmas=used, steps=len(used),
                           enc_key=key, enc_cache_hit=not encoded_now, ref_res=ref_res,
                           refs=[{"path": str(p), "sha256": file_sha256(p)} for p in ref],
                           prompt_mode="verbatim (refs given)" if ref else "template",
                           vae={"tiling": True, "dtype": vae_dtype},
                           peak_mps_gb=self._stats.get("peak_mps_gen_gb"))
        return out

    @staticmethod
    def _check_return_arity(enc) -> None:
        if len(enc) != 3:
            raise RuntimeError(f"cached encoding has {len(enc)} items, expected (embeds, mask, image_pad_mask)")

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def unload(self) -> None:
        self.vae = None
        self._drop_pipe()
