"""FLUX.2 [klein] 4B + Limbicnation/pixel-art-lora, run locally with diffusers.

* 4-step distilled model, guidance 1.0 (negative prompts are ignored).
* Trained at 512x512; other sizes work but drift from the LoRA's style.
* Klein accepts reference images (``ref`` option). They are passed as the
  pipeline's ``image`` argument, which is FLUX.2's multi-reference
  conditioning. Use it to keep a character consistent across directions.

Memory on a 24 GB Apple Silicon machine (bf16): transformer about 7.8 GB,
Qwen3 text encoder about 8 GB, VAE 0.2 GB. ``offload`` picks how to fit:

* ``none``: everything on MPS (fastest, about 16 GB resident).
* ``free_te``: text encoder on MPS only while encoding a prompt, then moved
  back to CPU. Lower peak on the GPU side, slower per prompt.
* ``te_cpu``: text encoder stays on CPU (slow encode, smallest GPU use).
"""
from __future__ import annotations

import gc
import time
from typing import Any

from PIL import Image

from .base import Backend, BackendInfo

BASE = "black-forest-labs/FLUX.2-klein-4B"
LORA = "Limbicnation/pixel-art-lora"
LORA_FILE = "pytorch_lora_weights.safetensors"


class Flux2KleinPixelLora(Backend):
    info = BackendInfo(
        name="flux2_klein_pixel_lora",
        description="FLUX.2 klein 4B (distilled, 4 steps) + pixel-art LoRA, local MPS",
        models=[BASE, LORA],
        licence="Apache-2.0 (base model and LoRA; LoRA trained on CC0 data)",
        local=True,
        defaults={"steps": 4, "guidance": 1.0, "lora_scale": 1.0,
                  "offload": "free_te", "dtype": "bf16", "ref": None,
                  "background": "transparent background"},
        prompt_template="pixel art sprite, {prompt}, game asset, {background}",
    )
    # Used by inpaint(): scene tiles, not sprites on a transparent background.
    inpaint_template = ("pixel art, {prompt}, top-down 3/4 view video game map, 16-bit tiles, "
                        "flat colours, crisp pixels")

    def __init__(self) -> None:
        self.pipe = None
        self.device = None
        self._stats: dict[str, Any] = {}
        self._offload = None
        self._lora_scale = None
        self._peft_scaling = 1.0
        self._embed_cache: dict = {}
        self._in_gen = False

    # ------------------------------------------------------------------ load
    def load(self, offload: str = "free_te", dtype: str = "bf16", **_ignored) -> None:
        import torch
        from diffusers import Flux2KleinPipeline

        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        td = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[dtype]
        t0 = time.perf_counter()
        # Prefer the local HF cache; only touch the network if files are missing.
        try:
            pipe = Flux2KleinPipeline.from_pretrained(BASE, dtype=td, local_files_only=True)
        except OSError:
            pipe = Flux2KleinPipeline.from_pretrained(BASE, dtype=td)
        try:
            pipe.load_lora_weights(LORA, weight_name=LORA_FILE, adapter_name="pixel",
                                   local_files_only=True)
        except (OSError, ValueError):
            pipe.load_lora_weights(LORA, weight_name=LORA_FILE, adapter_name="pixel")
        self._peft_scaling = next(
            m.scaling["pixel"] for m in pipe.transformer.modules()
            if isinstance(getattr(m, "scaling", None), dict) and "pixel" in m.scaling)
        if offload == "none":
            pipe.to(self.device)
        else:
            pipe.transformer.to(self.device)
            pipe.vae.to(self.device)
            pipe.text_encoder.to("cpu")
        pipe.set_progress_bar_config(disable=True)
        self.pipe = pipe
        self._offload = offload
        self._stats["load_s"] = round(time.perf_counter() - t0, 1)
        self._stats["device"] = self.device
        self._stats["dtype"] = dtype
        self._stats["offload"] = offload
        self._track_mem()

    # --------------------------------------------------------------- helpers
    def _track_mem(self) -> None:
        torch = self.torch
        if self.device == "mps":
            drv = torch.mps.driver_allocated_memory() / 2**30
            self._stats["peak_mps_driver_gb"] = round(
                max(self._stats.get("peak_mps_driver_gb", 0.0), drv), 2)
            if self._in_gen:
                self._stats["peak_mps_gen_gb"] = round(
                    max(self._stats.get("peak_mps_gen_gb", 0.0), drv), 2)
        try:
            import resource
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30  # bytes on macOS
            self._stats["peak_rss_gb"] = round(rss, 2)
        except Exception:
            pass

    def _set_lora_scale(self, scale: float) -> None:
        """``scale`` multiplies the raw LoRA delta (B @ A).

        The LoRA was saved with ``use_rslora`` (alpha 128, rank 64), so peft
        multiplies by alpha / sqrt(r) = 16. At 16x the output is black or
        noise on MPS and CPU alike, so we divide that factor out: scale 1.0
        here means "B @ A added once", which is what gives clean results.
        """
        if scale != self._lora_scale:
            if scale == 0:
                self.pipe.disable_lora()
            else:
                self.pipe.enable_lora()
                self.pipe.set_adapters(["pixel"], adapter_weights=[scale / self._peft_scaling])
            self._lora_scale = scale

    def precompute(self, prompts: list[str]) -> None:
        """Encode all prompts up front, then free the text encoder from MPS.

        After this, generate() only needs the transformer and VAE (about 8 GB)
        for these prompts. Unknown prompts still work: the encoder is moved
        back on demand.
        """
        for p in prompts:
            if p not in self._embed_cache:
                self._embed_cache[p] = self._encode(p)
        if self.device == "mps":
            self.pipe.text_encoder.to("cpu")
            self._offload = "free_te" if self._offload == "none" else self._offload
            gc.collect()
            self.torch.mps.empty_cache()

    def _encode(self, prompt: str):
        if prompt in self._embed_cache:
            return self._embed_cache[prompt]
        pipe, torch = self.pipe, self.torch
        if self._offload == "free_te":
            pipe.text_encoder.to(self.device)
            dev = self.device
        elif self._offload == "te_cpu":
            dev = "cpu"
        else:
            dev = self.device
        with torch.no_grad():
            embeds, _ids = pipe.encode_prompt(prompt=prompt, device=dev)
        self._track_mem()
        if self._offload == "free_te":
            pipe.text_encoder.to("cpu")
            gc.collect()
            torch.mps.empty_cache() if self.device == "mps" else None
        return embeds.to(self.device)

    # -------------------------------------------------------------- generate
    def generate(self, prompt, negative=None, width=512, height=512, seed=0, n=1,
                 steps: int = 4, guidance: float = 1.0, lora_scale: float = 1.0,
                 ref=None, **_ignored) -> list[Image.Image]:
        if self.pipe is None:
            self.load()
        torch = self.torch
        self._set_lora_scale(float(lora_scale))
        refs = None
        if ref:
            paths = ref if isinstance(ref, (list, tuple)) else [ref]
            refs = [Image.open(p).convert("RGB") for p in paths]

        t0 = time.perf_counter()
        embeds = self._encode(prompt)
        t_enc = time.perf_counter() - t0

        def cb(pipe, i, t, kw):
            self._track_mem()
            return kw

        self._in_gen = True

        out, times = [], []
        for i in range(n):
            g = torch.Generator("cpu").manual_seed(int(seed) + i)
            t1 = time.perf_counter()
            kwargs = dict(prompt_embeds=embeds, width=width, height=height,
                          num_inference_steps=steps, guidance_scale=guidance,
                          generator=g, callback_on_step_end=cb)
            if refs:
                kwargs["image"] = refs if len(refs) > 1 else refs[0]
            with torch.no_grad():
                img = self.pipe(**kwargs).images[0]
            if self.device == "mps":
                torch.mps.synchronize()
            times.append(time.perf_counter() - t1)
            self._track_mem()
            out.append(img)
        self._in_gen = False
        self._stats["last_encode_s"] = round(t_enc, 2)
        self._stats["last_image_s"] = [round(x, 2) for x in times]
        return out

    # --------------------------------------------------------------- inpaint
    def apply_inpaint_template(self, subject: str, **_fields) -> str:
        return self.inpaint_template.format(prompt=subject)

    def _inpaint_pipe(self):
        """Flux2KleinInpaintPipeline sharing every component (and the LoRA) with the text pipeline."""
        if getattr(self, "_ipipe", None) is None:
            from diffusers import Flux2KleinInpaintPipeline
            self._ipipe = Flux2KleinInpaintPipeline(**self.pipe.components,
                                                    is_distilled=bool(self.pipe.config.is_distilled))
            self._ipipe.set_progress_bar_config(disable=True)
        return self._ipipe

    def inpaint(self, prompt: str, image: Image.Image, mask: Image.Image, seed: int = 0, n: int = 1,
                strength: float = 0.75, steps: int = 4, guidance: float = 1.0, lora_scale: float = 1.0,
                ref=None, **_ignored) -> list[Image.Image]:
        """Masked img2img: white mask pixels are repainted from ``image`` at ``strength``; black ones are kept.

        ``image`` is also given to the transformer as a conditioning image, so the model sees the whole canvas.
        Width and height must be multiples of 16. Image i uses seed + i. ``ref``: reference image path(s).
        """
        if self.pipe is None:
            self.load()
        torch = self.torch
        if image.width % 16 or image.height % 16:
            raise ValueError(f"canvas {image.size} must be a multiple of 16")
        if mask.size != image.size:
            raise ValueError(f"mask {mask.size} does not match canvas {image.size}")
        self._set_lora_scale(float(lora_scale))
        ipipe = self._inpaint_pipe()
        refs = None
        if ref:
            paths = ref if isinstance(ref, (list, tuple)) else [ref]
            refs = [Image.open(p).convert("RGB") for p in paths]
            refs = [r.resize(refs[0].size, Image.NEAREST) if r.size != refs[0].size else r for r in refs]
        t0 = time.perf_counter()
        embeds = self._encode(prompt)   # moves the text encoder back to CPU afterwards (free_te)
        t_enc = time.perf_counter() - t0
        self._in_gen = True
        out, times = [], []
        for i in range(n):
            g = torch.Generator("cpu").manual_seed(int(seed) + i)
            t1 = time.perf_counter()
            kwargs = dict(prompt_embeds=embeds, image=image.convert("RGB"), mask_image=mask.convert("L"),
                          height=image.height, width=image.width, strength=strength,
                          num_inference_steps=steps, guidance_scale=guidance, generator=g,
                          callback_on_step_end=lambda p, k, t, kw: (self._track_mem(), kw)[1])
            if refs:
                kwargs["image_reference"] = refs if len(refs) > 1 else refs[0]
            with torch.no_grad():
                img = ipipe(**kwargs).images[0]
            if self.device == "mps":
                torch.mps.synchronize()
            times.append(time.perf_counter() - t1)
            self._track_mem()
            out.append(img)
        self._in_gen = False
        self._stats["last_encode_s"] = round(t_enc, 2)
        self._stats["last_image_s"] = [round(x, 2) for x in times]
        return out

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def unload(self) -> None:
        self.pipe = None
        gc.collect()
        try:
            self.torch.mps.empty_cache()
        except Exception:
            pass
