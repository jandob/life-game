"""Z-Image-Turbo (Tongyi-MAI, Apache-2.0) built from the ComfyUI single files.

Components (all read-only, paths in ``models.json``):

* transformer: ``z_image_turbo_bf16.safetensors`` (6.15 B params, 12.3 GB bf16),
  loaded with ``ZImageTransformer2DModel.from_single_file`` (diffusers converts the keys).
* text encoder: ``qwen_3_4b.safetensors`` -> ``transformers.Qwen3Model`` (8 GB bf16).
* VAE: ``ae.safetensors`` (FLUX-style 16-channel VAE, fp32) -> ``AutoencoderKL.from_single_file``.
* configs and tokenizer: a few kB of JSON from ``Tongyi-MAI/Z-Image-Turbo`` and
  the tokenizer already cached from ``Tongyi-MAI/Z-Image``. No weights are downloaded.

Memory (24 GB machine): text encoder and transformer together would be about
20 GB, so they are never resident at the same time. A prompt is encoded first
(text encoder loaded, used, dropped), then the transformer is loaded to MPS.
Encoded prompts are cached; ``precompute()`` encodes a whole list in one go.

Model card settings: 8 steps (9 scheduler steps), guidance 0 (negative prompts are
ignored). The prompt is natural language (it was trained with long, descriptive
prompts); there is no tag syntax, no LoRA support in this backend.
"""
from __future__ import annotations

import gc
import time
from typing import Any

from PIL import Image

from .base import Backend, BackendInfo
from ._common import MemTracker, hf_snapshot, load_registry
import os


class ZImageTurbo(Backend):
    info = BackendInfo(
        name="z_image_turbo",
        description="Z-Image-Turbo (8 steps, guidance 0) from the ComfyUI single files, local MPS",
        models=["Tongyi-MAI/Z-Image-Turbo (single files: transformer bf16, qwen_3_4b, ae)"],
        licence="Apache-2.0",
        local=True,
        defaults={"steps": 8, "guidance": 0.0, "dtype": "bf16",
                  "style": "", "background": "plain flat white background"},
        prompt_template="{style}{prompt}, {background}",
    )
    load_keys = frozenset({"dtype"})

    def __init__(self) -> None:
        self.torch = None
        self.device = None
        self.transformer = None
        self.vae = None
        self.tokenizer = None
        self.cfg = None
        self._stats: dict[str, Any] = {}
        self._cache: dict[str, Any] = {}

    # ------------------------------------------------------------------ load
    def load(self, dtype: str = "bf16", **_ignored) -> None:
        import torch
        from transformers import AutoTokenizer
        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.dtype = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[dtype]
        self.cfg = load_registry()["z_image_turbo"]
        t0 = time.perf_counter()
        self.snap = hf_snapshot(self.cfg["config_repo"], [
            "model_index.json", "scheduler/*.json", "text_encoder/config.json",
            "transformer/config.json", "vae/config.json"])
        tok_snap = hf_snapshot(self.cfg["tokenizer_repo"], ["tokenizer/*.json", "tokenizer/*.txt"])
        self.tokenizer = AutoTokenizer.from_pretrained(os.path.join(tok_snap, "tokenizer"))
        from diffusers import AutoencoderKL, FlowMatchEulerDiscreteScheduler
        self.scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(self.snap, subfolder="scheduler")
        # VAE stays fp32 (small, avoids bf16 colour banding); it lives on the GPU.
        self.vae = AutoencoderKL.from_single_file(
            os.path.expanduser(self.cfg["vae"]), config=self.snap, subfolder="vae",
            torch_dtype=torch.float32).to(self.device)
        self.mem = MemTracker(torch, self.device, self._stats)
        self._stats.update(load_s=round(time.perf_counter() - t0, 1), device=self.device, dtype=dtype)
        self.mem("peak_mps_driver_gb")

    def _load_transformer(self):
        if self.transformer is None:
            from diffusers import ZImageTransformer2DModel
            t0 = time.perf_counter()
            tr = ZImageTransformer2DModel.from_single_file(
                os.path.expanduser(self.cfg["transformer"]), config=self.snap,
                subfolder="transformer", torch_dtype=self.dtype)
            self.transformer = tr.to(self.device)
            self._stats["transformer_load_s"] = round(time.perf_counter() - t0, 1)
        return self.transformer

    def _drop_transformer(self) -> None:
        self.transformer = None
        self._free()

    def _free(self) -> None:
        gc.collect()
        if self.device == "mps":
            self.torch.mps.empty_cache()

    # ---------------------------------------------------------------- encode
    def _load_text_encoder(self):
        from safetensors.torch import load_file
        from transformers import Qwen3Config, Qwen3Model
        torch = self.torch
        cfg = Qwen3Config.from_pretrained(os.path.join(self.snap, "text_encoder"))
        cfg.torch_dtype = self.dtype
        # Build on CPU in the target dtype (a meta-device build would leave the
        # rotary inv_freq buffer uninitialised), then overwrite with the file's weights.
        prev = torch.get_default_dtype()
        torch.set_default_dtype(self.dtype)
        try:
            te = Qwen3Model(cfg)
        finally:
            torch.set_default_dtype(prev)
        sd = {k.removeprefix("model."): v for k, v in
              load_file(os.path.expanduser(self.cfg["text_encoder"])).items()}
        missing, unexpected = te.load_state_dict(sd, strict=False)
        missing = [k for k in missing if "rotary" not in k]
        if missing or unexpected:
            raise RuntimeError(f"text encoder mismatch: missing={missing[:3]} unexpected={unexpected[:3]}")
        return te.eval().to(self.device)

    def precompute(self, prompts: list[str]) -> None:
        todo = [p for p in dict.fromkeys(prompts) if p not in self._cache]
        if not todo:
            return
        from diffusers import ZImagePipeline
        if self.tokenizer is None:
            self.load()
        self._drop_transformer()          # never hold transformer and text encoder together
        t0 = time.perf_counter()
        te = self._load_text_encoder()
        helper = ZImagePipeline(scheduler=self.scheduler, vae=None, text_encoder=te,
                                tokenizer=self.tokenizer, transformer=None)
        with self.torch.no_grad():
            for p in todo:
                emb, _ = helper.encode_prompt(p, device=self.device, do_classifier_free_guidance=False)
                self._cache[p] = [e.to("cpu") for e in emb]
        self.mem()
        del helper, te
        self._free()
        self._stats["last_encode_s"] = round(time.perf_counter() - t0, 2)

    # -------------------------------------------------------------- generate
    def generate(self, prompt, negative=None, width=1024, height=1024, seed=0, n=1,
                 steps: int = 8, guidance: float = 0.0, **_ignored) -> list[Image.Image]:
        if self.tokenizer is None:
            self.load()
        from diffusers import ZImagePipeline
        torch = self.torch
        if width % 16 or height % 16:
            raise ValueError("width and height must be multiples of 16")
        self.precompute([prompt])
        embeds = [e.to(self.device) for e in self._cache[prompt]]
        tr = self._load_transformer()
        pipe = ZImagePipeline(scheduler=self.scheduler, vae=self.vae, text_encoder=None,
                              tokenizer=self.tokenizer, transformer=tr)
        pipe.set_progress_bar_config(disable=True)
        out, times = [], []
        for i in range(n):
            g = torch.Generator("cpu").manual_seed(int(seed) + i)
            t1 = time.perf_counter()
            with torch.no_grad():
                img = pipe(prompt_embeds=embeds, width=width, height=height,
                           num_inference_steps=steps, guidance_scale=guidance, generator=g,
                           callback_on_step_end=lambda p, k, t, kw: (self.mem(), kw)[1]).images[0]
            if self.device == "mps":
                torch.mps.synchronize()
            times.append(time.perf_counter() - t1)
            self.mem()
            out.append(img)
        self._stats["last_image_s"] = [round(x, 2) for x in times]
        return out

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def unload(self) -> None:
        self.transformer = None
        self.vae = None
        self._free()
