"""Qwen-Image 2.1 base (40 steps, true CFG) on a RunPod Serverless endpoint.

One remote backend = one endpoint = one model: the endpoint runs the worker in ``rp_handler.py``
(image ``remote/runpod/Dockerfile``) with ``Qwen/Qwen-Image-2.1`` in its model cache. Nothing is loaded
locally; each ``generate`` call is one RunPod job, image i uses seed + i.

Config: the ``runpod_qwen_image21`` entry in ``models.json`` (model, ``endpoint_env``, defaults);
environment: ``RUNPOD_API_KEY`` and the endpoint id in ``endpoint_env`` (``ARTGEN_RUNPOD_ENDPOINT``).
Prompts: like ``qwen_image21`` (sprite template without refs; with refs the prompt is sent verbatim).
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import time
from pathlib import Path
from typing import Any

from PIL import Image

from . import _runpod
from ._common import load_registry
from .base import Backend, BackendInfo
from .qwen_image21 import TEMPLATE


class RunpodQwenImage21(Backend):
    info = BackendInfo(
        name="runpod_qwen_image21",
        description="Qwen-Image 2.1 base (40 steps, true CFG 4.0) on RunPod Serverless (remote, billed per second)",
        models=["Qwen/Qwen-Image-2.1"],
        licence="Qwen Research licence (qwen-research, see the model card)",
        local=False,
        caps=frozenset({"refs", "edit", "sheet"}),
        defaults={"background": "plain flat white background"},
        prompt_template=TEMPLATE,
        default_size=(1024, 1024),
    )
    load_keys = frozenset()
    passthrough_opts = frozenset({"ref"})
    template_flags = frozenset({"ref"})

    def __init__(self) -> None:
        self.cfg: dict = {}
        self.endpoint = None
        self._stats: dict[str, Any] = {}

    def apply_template(self, subject: str, **fields) -> str:
        if fields.get("ref"):
            return subject      # with references --prompt is sent verbatim ("Picture 1/2/3 ...")
        return super().apply_template(subject, **fields)

    def load(self, **_ignored) -> None:
        self.cfg = load_registry()["runpod_qwen_image21"]
        env = self.cfg["endpoint_env"]
        self.endpoint = os.environ.get(env)
        if not self.endpoint:
            raise SystemExit(f"runpod_qwen_image21: set {env} to the RunPod endpoint id (and RUNPOD_API_KEY)")
        _runpod.api_key()

    def generate(self, prompt, negative=None, width=1024, height=1024, seed=0, n=1, ref=None, ref_res=None,
                 steps=None, true_cfg=None, sigmas=None, **_ignored) -> list[Image.Image]:
        if not self.endpoint:
            self.load()
        d = self.cfg.get("defaults", {})
        refs = []
        for p in ref or []:
            data = Path(p).read_bytes()
            refs.append({"sha256": hashlib.sha256(data).hexdigest(), "png_bytes": base64.b64encode(data).decode()})
        payload = {"prompt": prompt, "negative": negative or d.get("negative"), "refs": refs,
                   "seed": int(seed), "n": int(n), "width": int(width), "height": int(height),
                   "steps": int(steps or d.get("steps", 40)), "true_cfg": float(true_cfg or d.get("true_cfg", 4.0)),
                   "sigmas": sigmas, "opts": {"ref_res": int(ref_res)} if (ref_res and refs) else {}}
        t0 = time.perf_counter()
        out, job = _runpod.run(payload, self.endpoint, timeout_s=float(self.cfg.get("timeout_s", 1800)))
        items = out.get("images") or []
        if len(items) != n:
            raise RuntimeError(f"runpod: expected {n} images, got {len(items)}")
        imgs = [Image.open(io.BytesIO(base64.b64decode(it["png_base64"]))).convert("RGBA") for it in items]
        self._stats = {"remote": [it.get("meta", {}) for it in items], "runpod": job,
                       "model": self.cfg.get("model"), "steps": payload["steps"], "true_cfg": payload["true_cfg"],
                       "negative": payload["negative"], "refs": len(refs), "ref_res": payload["opts"].get("ref_res"),
                       "call_s": round(time.perf_counter() - t0, 1),
                       "last_image_s": [it.get("meta", {}).get("image_s") for it in items]}
        return imgs

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)
