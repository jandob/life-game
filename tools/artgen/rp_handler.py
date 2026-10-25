"""RunPod Serverless worker (repo root so RunPod's GitHub deploy finds the handler; image: remote/runpod/Dockerfile): Qwen-Image 2.1 (base, 40 steps, true CFG) for artgen's remote runner.

Input  (``job["input"]``): an artgen ``JobSpec`` as JSON (see ``runner.py``): prompt, negative, refs
       ([{sha256, png_bytes(base64)}], Picture 1, 2, ...), seed, n, width, height, steps, true_cfg,
       opts (``ref_res``).
Output: ``{"images": [{"png_base64": ..., "meta": {...}}, ...]}``; image i uses seed + i.

The weights come from the endpoint's model cache (one cached model per endpoint: set the endpoint's
Model to ``Qwen/Qwen-Image-2.1``); RunPod mounts it as a Hugging Face cache under
``/runpod-volume/huggingface-cache/hub``. Without the cache (local test) it downloads to HF_HOME.
"""
from __future__ import annotations

import base64
import glob
import hashlib
import io
import os
import time

import runpod
import torch
from diffusers import QwenImage21Pipeline
from PIL import Image

MODEL_REPO = os.environ.get("MODEL_REPO", "Qwen/Qwen-Image-2.1")
CACHE_HUB = os.environ.get("RUNPOD_HF_CACHE", "/runpod-volume/huggingface-cache/hub")
# Defaults of the "base" variant (same values as artgen's backends/qwen_image21.py PROFILES["base"]).
DEFAULTS = {"steps": 40, "true_cfg": 4.0, "negative": "low quality, blurry, deformed, text, watermark"}


def model_path() -> str:
    """Snapshot dir of MODEL_REPO in the RunPod model cache, else a regular HF download (local tests)."""
    snaps = sorted(glob.glob(os.path.join(CACHE_HUB, f"models--{MODEL_REPO.replace('/', '--')}", "snapshots", "*")))
    if snaps:
        return snaps[-1]
    from huggingface_hub import snapshot_download
    return snapshot_download(MODEL_REPO)


t0 = time.perf_counter()
PATH = model_path()
PIPE = QwenImage21Pipeline.from_pretrained(PATH, torch_dtype=torch.bfloat16).to("cuda")
PIPE.set_progress_bar_config(disable=True)
LOAD_S = round(time.perf_counter() - t0, 1)
GPU = torch.cuda.get_device_name(0)
print(f"loaded {MODEL_REPO} from {PATH} in {LOAD_S}s on {GPU}", flush=True)


def decode_refs(refs: list[dict]) -> list[Image.Image]:
    out = []
    for r in refs or []:
        data = base64.b64decode(r["png_bytes"])
        if r.get("sha256") and hashlib.sha256(data).hexdigest() != r["sha256"]:
            raise ValueError(f"reference sha256 mismatch ({r['sha256'][:12]}...)")
        out.append(Image.open(io.BytesIO(data)).convert("RGBA"))
    return out


def handler(job: dict) -> dict:
    inp = job["input"]
    if inp.get("variant") not in (None, "base"):
        return {"error": f"this endpoint serves the base variant only, got {inp.get('variant')!r}"}
    refs = decode_refs(inp.get("refs"))
    opts = inp.get("opts") or {}
    steps = int(inp.get("steps") or DEFAULTS["steps"])
    cfg = float(inp.get("true_cfg") or DEFAULTS["true_cfg"])
    negative = inp.get("negative") or DEFAULTS["negative"]
    width, height = int(inp.get("width") or 1024), int(inp.get("height") or 1024)
    seed, n = int(inp.get("seed") or 0), int(inp.get("n") or 1)
    kw = dict(prompt=inp["prompt"], negative_prompt=negative, true_cfg_scale=cfg, num_inference_steps=steps,
              width=width, height=height)
    if inp.get("sigmas"):
        kw["sigmas"] = [float(s) for s in inp["sigmas"]]
    if refs:
        kw["image"] = refs
        kw["output_resolution"] = int(opts.get("ref_res") or 1024)
    images = []
    for i in range(n):
        t1 = time.perf_counter()
        with torch.no_grad():
            img = PIPE(generator=torch.Generator("cpu").manual_seed(seed + i), **kw).images[0]
        torch.cuda.synchronize()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        images.append({"png_base64": base64.b64encode(buf.getvalue()).decode(),
                       "meta": {"seed": seed + i, "size": list(img.size), "steps": steps, "true_cfg": cfg,
                                "negative": negative, "ref_res": kw.get("output_resolution"), "refs": len(refs),
                                "model": MODEL_REPO, "snapshot": os.path.basename(PATH), "gpu": GPU,
                                "image_s": round(time.perf_counter() - t1, 1), "load_s": LOAD_S,
                                "peak_cuda_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2)}})
    return {"images": images}


runpod.serverless.start({"handler": handler})
