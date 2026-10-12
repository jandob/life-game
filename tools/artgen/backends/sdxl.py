"""SDXL-family single-file checkpoints (Illustrious, WAI, Pony, SDXL base) with diffusers.

One backend, many models: pick one with ``--opt model=<key>`` (keys live in
``models.json``: ``illustrious_v1``, ``wai_v17``, ``cyberrealistic_pony_v18``,
``sdxl_base``). Checkpoints are read from where they are (the HF cache or a local
path such as ``~/Downloads``); nothing is copied or modified.

Options (``--opt k=v``)
  model        registry key (default illustrious_v1). Load-time.
  loras        ``name`` or ``name:scale`` list, comma separated, e.g. ``pixel_art_xl:1.0``.
               Names come from ``models.json`` ``loras`` or are paths to .safetensors.
               A LoRA with a ``trigger`` gets it prepended to the prompt.
  rating       safe (default) | questionable | explicit. Mapped to the family's tag
               (Pony: rating_safe/... ; Illustrious/WAI: general / sensitive / nsfw, explicit).
               ``safe`` also adds "nsfw, nude, naked, nipples, topless, ..." to the negative;
               the other ratings do not.
  quality      override the family's quality prefix (``quality=`` empty disables it).
  steps, guidance, sampler (euler_a | dpmpp_2m_karras | dpmpp_sde_karras), clip_skip
  ref          reference image(s) via IP-Adapter Plus (``--ref FILE``); ``ip_scale`` (0.6).
  pose         skeleton PNG (see ``artgen.py pose``) via the OpenPose ControlNet;
               ``pose_scale`` (0.8), ``pose_end`` (0.8 = release the control at 80 % of the steps).
  feather      refine only: blur radius (px, default 6) of the mask edge when the original is pasted back.
  negative_extra  appended to the family's default negative (``--negative`` replaces it; the
               rating=safe terms are still added to it).

Prompt conventions per family (applied by ``apply_template``; ``--raw-prompt`` skips them)
  pony          ``score_9, score_8_up, score_7_up, <rating_*>, <trigger>, <prompt>, <background>``
                negative: ``score_6, score_5, score_4, ...``. Clip skip 2 is diffusers' default
                for SDXL (penultimate layer), so ``clip_skip`` stays unset.
  illustrious   ``masterpiece, best quality, amazing quality, very aesthetic, absurdres, newest,
                <rating>, <trigger>, <prompt>, <background>``. Danbooru tags plus plain English.
                Negative adds ``child, loli, shota, young`` because these checkpoints skew young.
  sdxl          plain English, no tags, no quality prefix.

fp16 on MPS needs the fp16-fix VAE (``madebyollin/sdxl-vae-fp16-fix``), which this
backend always loads; the stock SDXL VAE gives black images in fp16.
"""
from __future__ import annotations

import gc
import os
import time
from typing import Any

from PIL import Image

from .base import Backend, BackendInfo
from ._common import MemTracker, hf_file, hf_snapshot, load_registry, resolve

RATINGS = {
    "pony": {"safe": "rating_safe", "questionable": "rating_questionable", "explicit": "rating_explicit"},
    "illustrious": {"safe": "general", "questionable": "sensitive", "explicit": "nsfw, explicit"},
    "sdxl": {},
}
FAMILIES = {
    "pony": {
        "quality": "score_9, score_8_up, score_7_up",
        "negative": ("score_6, score_5, score_4, lowres, worst quality, low quality, bad anatomy, bad hands, "
                     "extra fingers, missing fingers, jpeg artifacts, signature, watermark, text, blurry"),
        "background": "simple background",
    },
    "illustrious": {
        "quality": "masterpiece, best quality, amazing quality, very aesthetic, absurdres, newest",
        "negative": ("lowres, worst quality, low quality, bad quality, bad anatomy, bad hands, extra fingers, "
                     "jpeg artifacts, signature, watermark, username, text, blurry, child, loli, shota, young"),
        "background": "simple background",
    },
    "sdxl": {
        "quality": "",
        "negative": "lowres, blurry, low quality, deformed, bad anatomy, jpeg artifacts, watermark, text, signature",
        "background": "",
    },
}


# Added to the negative when rating is "safe" (the default). Pony in particular paints nude
# women into scenes (even a sofa-only prompt) unless these are suppressed.
SAFE_NEGATIVE = "nsfw, nude, naked, nipples, topless, bottomless, nudity, cleavage, sexual"


def parse_loras(spec) -> list[tuple[str, float | None]]:
    """``"a:0.8,b"`` or ``["a:0.8"]`` -> [("a", 0.8), ("b", None)]."""
    if not spec:
        return []
    items = spec if isinstance(spec, (list, tuple)) else str(spec).split(",")
    out = []
    for it in items:
        it = str(it).strip()
        if not it:
            continue
        name, sep, sc = it.rpartition(":")
        if sep and sc.replace(".", "", 1).replace("-", "", 1).isdigit():
            out.append((name, float(sc)))
        else:
            out.append((it, None))
    return out


class Sdxl(Backend):
    info = BackendInfo(
        name="sdxl",
        description=("SDXL single-file checkpoints (Illustrious v1, WAI v17, CyberRealistic Pony v18, SDXL base) "
                     "+ optional LoRAs, IP-Adapter ref, OpenPose ControlNet, inpaint; local MPS fp16"),
        models=["OnomaAIResearch/Illustrious-XL-v1.0", "waiIllustriousSDXL_v170 (local file)",
                "cyberdelia/CyberRealisticPony V18.0 F16", "sd_xl_base_1.0 (local file)",
                "nerijs/pixel-art-xl", "madebyollin/sdxl-vae-fp16-fix",
                "ip-adapter-plus_sdxl_vit-h + CLIP-ViT-H-14 (local files)",
                "xinsir/controlnet-openpose-sdxl-1.0"],
        licence="per model, see models.json (RAIL++-M / FAIPL; outputs are not restricted)",
        local=True,
        defaults={"model": "illustrious_v1", "rating": "safe", "ip_scale": 0.6,
                  "pose_scale": 0.8, "pose_end": 0.8},
        prompt_template="{quality}, {rating}, {trigger}, {prompt}, {background}",
    )
    load_keys = frozenset({"model"})
    passthrough_opts = frozenset({"ref", "loras", "sampler", "pose", "negative_extra", "model", "rating"})
    inpaint_keys = ("steps", "guidance", "sampler", "loras", "negative_extra", "model", "rating")
    refine_keys = inpaint_keys + ("pose_scale", "pose_end", "feather")

    def __init__(self) -> None:
        self.pipe = None
        self.torch = None
        self.device = None
        self.model_name = None
        self.reg = None
        self._stats: dict[str, Any] = {}
        self._loaded_loras: dict[str, str] = {}   # adapter name -> file
        self._ip_loaded = False
        self._cn = None
        self._cn_pipe = None
        self._inp_pipe = None
        self._refine_pipes: dict[str, Any] = {}   # img2img / controlnet variants used by refine()
        self._sampler = None

    # ------------------------------------------------------------------ load
    def load(self, model: str = "illustrious_v1", **_ignored) -> None:
        import torch
        from diffusers import AutoencoderKL, StableDiffusionXLPipeline
        if self.pipe is not None and model == self.model_name:
            return
        if self.pipe is not None:
            self.unload()
        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.reg = load_registry()
        if model not in self.reg["models"]:
            raise SystemExit(f"unknown sdxl model {model!r}; known: {', '.join(self.reg['models'])}")
        entry = self.reg["models"][model]
        t0 = time.perf_counter()
        ckpt = resolve(entry)
        vae = AutoencoderKL.from_pretrained(self.reg["vae"]["hf_repo"], torch_dtype=torch.float16,
                                            local_files_only=self._have_local(self.reg["vae"]["hf_repo"]))
        kw = dict(torch_dtype=torch.float16, vae=vae, use_safetensors=True)
        try:
            pipe = StableDiffusionXLPipeline.from_single_file(ckpt, local_files_only=True, **kw)
        except Exception:  # noqa: BLE001  (first run: fetches the small SDXL config/tokenizer files)
            pipe = StableDiffusionXLPipeline.from_single_file(ckpt, **kw)
        pipe.to(self.device)
        pipe.set_progress_bar_config(disable=True)
        self.pipe, self.model_name, self.entry = pipe, model, entry
        self.family = entry["family"]
        self._sampler = None
        self.mem = MemTracker(torch, self.device, self._stats)
        self._stats.update(load_s=round(time.perf_counter() - t0, 1), device=self.device, model=model,
                           checkpoint=ckpt)
        self.mem("peak_mps_driver_gb")

    @staticmethod
    def _have_local(repo: str) -> bool:
        from huggingface_hub import try_to_load_from_cache
        return isinstance(try_to_load_from_cache(repo, "config.json"), str)

    # -------------------------------------------------------------- template
    def _family_of(self, model: str | None) -> str:
        reg = self.reg or load_registry()
        return reg["models"][model or self.info.defaults["model"]]["family"]

    def apply_template(self, subject: str, **fields) -> str:
        model = fields.get("model") or self.model_name or self.info.defaults["model"]
        reg = self.reg or load_registry()
        fam = reg["models"][model]["family"]
        f = FAMILIES[fam]
        quality = fields["quality"] if "quality" in fields else f["quality"]
        rating = fields.get("rating", "safe")
        rating = RATINGS[fam].get(rating, rating) if fam != "sdxl" else ""
        triggers = []
        for name, _ in parse_loras(fields.get("loras")):
            t = reg["loras"].get(name, {}).get("trigger")
            if t:
                triggers.append(t)
        bg = fields["background"] if "background" in fields else f["background"]
        parts = [quality, rating, ", ".join(triggers), subject, bg]
        return ", ".join(p for p in parts if p)

    def default_negative(self, model: str | None = None) -> str:
        return FAMILIES[self._family_of(model)]["negative"]

    def apply_inpaint_template(self, subject: str) -> str:
        return self.apply_template(subject, background="")

    def _negative(self, negative: str | None, extra: str | None, rating: str | None) -> str:
        """``negative`` replaces the family default; the safe-rating terms are always added for rating=safe
        (also to a custom negative: ``rating=questionable|explicit`` turns that off)."""
        neg = negative if negative is not None else FAMILIES[self.family]["negative"]
        if extra:
            neg = f"{neg}, {extra}"
        if (rating or "safe") == "safe" and self.family != "sdxl":
            neg = f"{neg}, {SAFE_NEGATIVE}"
        return neg

    # -------------------------------------------------------------- samplers
    def _set_sampler(self, name: str) -> None:
        if name == self._sampler:
            return
        from diffusers import DPMSolverMultistepScheduler, EulerAncestralDiscreteScheduler
        cfg = self.pipe.scheduler.config
        if name == "euler_a":
            s = EulerAncestralDiscreteScheduler.from_config(cfg)
        elif name == "dpmpp_2m_karras":
            s = DPMSolverMultistepScheduler.from_config(cfg, use_karras_sigmas=True)
        elif name == "dpmpp_sde_karras":
            s = DPMSolverMultistepScheduler.from_config(cfg, use_karras_sigmas=True,
                                                        algorithm_type="sde-dpmsolver++")
        else:
            raise ValueError(f"unknown sampler {name!r}")
        self.pipe.scheduler = s
        for p in self._other_pipes():
            p.scheduler = s
        self._sampler = name

    def _other_pipes(self) -> list:
        return [p for p in (self._cn_pipe, self._inp_pipe, *self._refine_pipes.values()) if p is not None]

    # ----------------------------------------------------------------- loras
    def _apply_loras(self, spec) -> None:
        wanted = parse_loras(spec)
        pipe = self.pipe
        names, weights = [], []
        for name, scale in wanted:
            reg_entry = self.reg["loras"].get(name)
            path = resolve(reg_entry) if reg_entry else os.path.expanduser(name)
            if not os.path.isfile(path):
                raise FileNotFoundError(f"LoRA {name!r} not found ({path})")
            ad = os.path.basename(name).replace(".", "_").replace("-", "_")
            if ad not in self._loaded_loras:
                pipe.load_lora_weights(os.path.dirname(path), weight_name=os.path.basename(path),
                                       adapter_name=ad)
                self._loaded_loras[ad] = path
            names.append(ad)
            weights.append(scale if scale is not None else (reg_entry or {}).get("scale", 1.0))
        if names:
            pipe.set_adapters(names, adapter_weights=weights)
        elif self._loaded_loras:
            pipe.set_adapters(list(self._loaded_loras), adapter_weights=[0.0] * len(self._loaded_loras))

    # ------------------------------------------------------------ ip-adapter
    def _ensure_ip(self) -> None:
        if self._ip_loaded:
            return
        import json
        import torch
        from safetensors.torch import load_file
        from transformers import CLIPImageProcessor, CLIPVisionConfig, CLIPVisionModelWithProjection
        cfg = self.reg["ip_adapter"]
        if self.pipe.image_encoder is None:
            cfg_path = hf_file(*cfg["image_encoder_config"])
            enc_cfg = CLIPVisionConfig.from_dict(json.load(open(cfg_path)))
            prev = torch.get_default_dtype()
            torch.set_default_dtype(torch.float16)
            try:
                enc = CLIPVisionModelWithProjection(enc_cfg)
            finally:
                torch.set_default_dtype(prev)
            sd = load_file(os.path.expanduser(cfg["image_encoder"]))
            missing, unexpected = enc.load_state_dict(sd, strict=False)
            bad = [k for k in missing if "position_ids" not in k]
            unexpected = [k for k in unexpected if "position_ids" not in k]
            if bad or unexpected:
                raise RuntimeError(f"CLIP image encoder mismatch: {bad[:3]} {unexpected[:3]}")
            enc = enc.eval().to(self.device)
            self.pipe.register_modules(image_encoder=enc, feature_extractor=CLIPImageProcessor())
        for other in self._other_pipes():   # pipelines built earlier hold a stale None
            if other is not None:
                other.register_modules(image_encoder=self.pipe.image_encoder,
                                       feature_extractor=self.pipe.feature_extractor)
        p = os.path.expanduser(cfg["path"])
        self.pipe.load_ip_adapter(os.path.dirname(p), subfolder="", weight_name=os.path.basename(p),
                                  image_encoder_folder=None)
        self._ip_loaded = True

    def _drop_ip(self) -> None:
        if self._ip_loaded:
            self.pipe.unload_ip_adapter()
            self._ip_loaded = False

    # -------------------------------------------------------------- controlnet
    def _ensure_controlnet(self):
        if self._cn_pipe is None:
            from diffusers import ControlNetModel, StableDiffusionXLControlNetPipeline
            repo = self.reg["controlnet"]["openpose"]["hf_repo"]
            if self._cn is None:
                self._cn = ControlNetModel.from_pretrained(repo, torch_dtype=self.torch.float16,
                                                           local_files_only=True).to(self.device)
            self._cn_pipe = StableDiffusionXLControlNetPipeline(**self.pipe.components, controlnet=self._cn)
            self._cn_pipe.set_progress_bar_config(disable=True)
        return self._cn_pipe

    # ------------------------------------------------------- long prompts
    def _chunk_embeds(self, text: str, n_chunks: int | None = None):
        """Encode ``text`` in 75-token chunks (the A1111 scheme) so prompts may exceed CLIP's 77 tokens.

        Returns (embeds [1, 77*chunks, 2048], pooled [1, 1280]). For prompts of 75 tokens or
        fewer this equals diffusers' own ``encode_prompt`` output (checked in test_backends.py).
        """
        torch = self.torch
        pipe = self.pipe
        parts, pooled = [], None
        for ti, (tok, enc) in enumerate(((pipe.tokenizer, pipe.text_encoder),
                                         (pipe.tokenizer_2, pipe.text_encoder_2))):
            ids = tok(text, truncation=False, add_special_tokens=False).input_ids
            chunks = [ids[i:i + 75] for i in range(0, len(ids), 75)] or [[]]
            chunks += [[]] * ((n_chunks or len(chunks)) - len(chunks))
            hs = []
            for k, c in enumerate(chunks):
                x = [tok.bos_token_id] + c + [tok.eos_token_id] + [tok.pad_token_id] * (75 - len(c))
                out = enc(torch.tensor([x], device=self.device), output_hidden_states=True)
                hs.append(out.hidden_states[-2])
                if ti == 1 and k == 0:
                    pooled = out[0]
            parts.append(torch.cat(hs, dim=1))
        return torch.cat(parts, dim=-1), pooled

    def _n_chunks(self, text: str) -> int:
        n = len(self.pipe.tokenizer(text, truncation=False, add_special_tokens=False).input_ids)
        n2 = len(self.pipe.tokenizer_2(text, truncation=False, add_special_tokens=False).input_ids)
        return max(1, -(-max(n, n2) // 75))

    def encode_pair(self, prompt: str, negative: str):
        """(prompt_embeds, negative_embeds, pooled, negative_pooled) with equal chunk counts."""
        n = max(self._n_chunks(prompt), self._n_chunks(negative))
        with self.torch.no_grad():
            pe, pp = self._chunk_embeds(prompt, n)
            ne, np_ = self._chunk_embeds(negative, n)
        return pe, ne, pp, np_

    # -------------------------------------------------------------- generate
    def generate(self, prompt, negative=None, width=1024, height=1024, seed=0, n=1,
                 steps: int | None = None, guidance: float | None = None, sampler: str | None = None,
                 loras=None, ref=None, ip_scale: float = 0.6, pose=None, pose_scale: float = 0.8,
                 pose_end: float = 0.8, negative_extra: str | None = None, clip_skip: int | None = None,
                 model: str | None = None, rating: str = "safe", **_ignored) -> list[Image.Image]:
        if self.pipe is None or (model and model != self.model_name):
            self.load(model=model or self.info.defaults["model"])
        torch = self.torch
        d = self.entry["defaults"]
        steps = int(steps if steps is not None else d["steps"])
        guidance = float(guidance if guidance is not None else d["guidance"])
        self._set_sampler(sampler or d["sampler"])
        self._apply_loras(loras)
        negative = self._negative(negative, negative_extra, rating)
        refs = None
        if ref:
            paths = ref if isinstance(ref, (list, tuple)) else [ref]
            refs = [Image.open(p).convert("RGB") for p in paths]
            self._ensure_ip()
            self.pipe.set_ip_adapter_scale(float(ip_scale))
        else:
            self._drop_ip()
        pipe = self.pipe
        kw: dict[str, Any] = {}
        if pose:
            pipe = self._ensure_controlnet()
            kw.update(image=Image.open(pose).convert("RGB").resize((width, height)),
                      controlnet_conditioning_scale=float(pose_scale),
                      control_guidance_end=float(pose_end))
        if refs:
            kw["ip_adapter_image"] = refs[0] if len(refs) == 1 else refs
        if clip_skip is None:
            pe, ne, pp, np_ = self.encode_pair(prompt, negative)
            kw.update(prompt_embeds=pe, negative_prompt_embeds=ne, pooled_prompt_embeds=pp,
                      negative_pooled_prompt_embeds=np_)
        else:   # explicit clip_skip: let diffusers encode (truncates at 77 tokens)
            kw.update(prompt=prompt, negative_prompt=negative, clip_skip=int(clip_skip))
        out, times = [], []
        for i in range(n):
            g = torch.Generator("cpu").manual_seed(int(seed) + i)
            t1 = time.perf_counter()
            with torch.no_grad():
                img = pipe(width=width, height=height,
                           num_inference_steps=steps, guidance_scale=guidance, generator=g,
                           callback_on_step_end=lambda p, k, t, kw_: (self.mem(), kw_)[1], **kw).images[0]
            if self.device == "mps":
                torch.mps.synchronize()
            times.append(time.perf_counter() - t1)
            self.mem()
            out.append(img)
        self._stats["last_image_s"] = [round(x, 2) for x in times]
        self._stats["steps"] = steps
        return out

    # --------------------------------------------------------------- inpaint
    def inpaint(self, prompt: str, image: Image.Image, mask: Image.Image, seed: int = 0, n: int = 1,
                strength: float = 0.75, steps: int | None = None, guidance: float | None = None,
                sampler: str | None = None, loras=None, negative: str | None = None,
                negative_extra: str | None = None, model: str | None = None, ref=None,
                rating: str = "safe", **_ignored) -> list[Image.Image]:
        """Masked img2img with ``StableDiffusionXLInpaintPipeline`` (shares the loaded weights).

        White mask = repaint. Sides must be multiples of 8. ``ref`` is ignored (use generate()).
        """
        if self.pipe is None or (model and model != self.model_name):
            self.load(model=model or self.info.defaults["model"])
        from diffusers import StableDiffusionXLInpaintPipeline
        torch = self.torch
        if image.width % 8 or image.height % 8:
            raise ValueError(f"canvas {image.size} must be a multiple of 8")
        if mask.size != image.size:
            raise ValueError(f"mask {mask.size} does not match canvas {image.size}")
        d = self.entry["defaults"]
        steps = int(steps if steps is not None else d["steps"])
        guidance = float(guidance if guidance is not None else d["guidance"])
        self._drop_ip()
        self._apply_loras(loras)
        if self._inp_pipe is None:
            self._inp_pipe = StableDiffusionXLInpaintPipeline(**self.pipe.components)
            self._inp_pipe.set_progress_bar_config(disable=True)
        self._set_sampler(sampler or d["sampler"])
        negative = self._negative(negative, negative_extra, rating)
        pe, ne, pp, np_ = self.encode_pair(prompt, negative)
        out, times = [], []
        for i in range(n):
            g = torch.Generator("cpu").manual_seed(int(seed) + i)
            t1 = time.perf_counter()
            with torch.no_grad():
                img = self._inp_pipe(prompt_embeds=pe, negative_prompt_embeds=ne, pooled_prompt_embeds=pp,
                                     negative_pooled_prompt_embeds=np_, image=image.convert("RGB"),
                                     mask_image=mask.convert("L"), width=image.width, height=image.height,
                                     strength=strength, num_inference_steps=steps, guidance_scale=guidance,
                                     generator=g).images[0]
            if self.device == "mps":
                torch.mps.synchronize()
            times.append(time.perf_counter() - t1)
            self.mem()
            out.append(img)
        self._stats["last_image_s"] = [round(x, 2) for x in times]
        return out

    # ---------------------------------------------------------------- refine
    def _refine_pipe(self, masked: bool, posed: bool):
        """Img2Img / Inpaint pipeline (optionally with the OpenPose ControlNet) sharing the loaded weights."""
        import diffusers
        key = ("inpaint" if masked else "img2img") + ("_cn" if posed else "")
        if key not in self._refine_pipes:
            name = {"img2img": "StableDiffusionXLImg2ImgPipeline",
                    "inpaint": "StableDiffusionXLInpaintPipeline",
                    "img2img_cn": "StableDiffusionXLControlNetImg2ImgPipeline",
                    "inpaint_cn": "StableDiffusionXLControlNetInpaintPipeline"}[key]
            extra = {}
            if posed:
                self._ensure_controlnet()
                extra["controlnet"] = self._cn
            p = getattr(diffusers, name)(**self.pipe.components, **extra)
            p.set_progress_bar_config(disable=True)
            self._refine_pipes[key] = p
        return self._refine_pipes[key]

    def refine(self, prompt: str, image: Image.Image, mask: Image.Image | None = None, seed: int = 0,
               n: int = 1, strength: float = 0.5, steps: int | None = None, guidance: float | None = None,
               sampler: str | None = None, loras=None, negative: str | None = None,
               negative_extra: str | None = None, model: str | None = None, rating: str = "safe",
               pose=None, pose_scale: float = 0.8, pose_end: float = 0.8, feather: float = 6.0,
               **_ignored) -> list[Image.Image]:
        """Repaint ``image`` with this model: img2img at ``strength`` (0 keeps it, 1 ignores it).

        Without ``mask`` the whole image goes through ``StableDiffusionXLImg2ImgPipeline``. With a mask
        (white = repaint) it goes through the inpaint pipeline, and the original pixels are pasted back
        outside the mask (edge softened by ``feather`` px) so protected faces stay byte-identical apart from
        that edge. ``pose`` adds the OpenPose ControlNet. Sides not divisible by 8 are resized to the
        nearest multiple of 8 (the result has that size).
        """
        if self.pipe is None or (model and model != self.model_name):
            self.load(model=model or self.info.defaults["model"])
        torch = self.torch
        w, h = (max(8, round(v / 8) * 8) for v in image.size)
        image = image.convert("RGB")
        if (w, h) != image.size:
            image = image.resize((w, h), Image.LANCZOS)
        if mask is not None:
            mask = mask.convert("L")
            if mask.size != (w, h):
                mask = mask.resize((w, h), Image.LANCZOS)
        d = self.entry["defaults"]
        steps = int(steps if steps is not None else d["steps"])
        guidance = float(guidance if guidance is not None else d["guidance"])
        self._drop_ip()
        self._apply_loras(loras)
        pipe = self._refine_pipe(mask is not None, bool(pose))
        self._set_sampler(sampler or d["sampler"])
        negative = self._negative(negative, negative_extra, rating)
        pe, ne, pp, np_ = self.encode_pair(prompt, negative)
        kw: dict[str, Any] = dict(prompt_embeds=pe, negative_prompt_embeds=ne, pooled_prompt_embeds=pp,
                                  negative_pooled_prompt_embeds=np_, strength=float(strength),
                                  num_inference_steps=steps, guidance_scale=guidance)
        if mask is not None:
            kw.update(image=image, mask_image=mask, width=w, height=h)
        else:
            kw.update(image=image)
        if pose:
            ctl = Image.open(pose).convert("RGB").resize((w, h))
            kw.update(controlnet_conditioning_scale=float(pose_scale), control_guidance_end=float(pose_end))
            kw["control_image"] = ctl
        paste = None
        if mask is not None and feather > 0:
            from PIL import ImageFilter
            paste = mask.filter(ImageFilter.GaussianBlur(float(feather)))
        out, times = [], []
        for i in range(n):
            g = torch.Generator("cpu").manual_seed(int(seed) + i)
            t1 = time.perf_counter()
            with torch.no_grad():
                img = pipe(generator=g, **kw).images[0]
            if self.device == "mps":
                torch.mps.synchronize()
            times.append(time.perf_counter() - t1)
            self.mem()
            if mask is not None:
                img = Image.composite(img, image, paste or mask)
            out.append(img)
        self._stats["last_image_s"] = [round(x, 2) for x in times]
        self._stats["steps"] = steps
        return out

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def unload(self) -> None:
        self.pipe = self._cn_pipe = self._inp_pipe = self._cn = None
        self._refine_pipes = {}
        self._loaded_loras, self._ip_loaded, self._sampler = {}, False, None
        gc.collect()
        try:
            self.torch.mps.empty_cache()
        except Exception:  # noqa: BLE001
            pass
