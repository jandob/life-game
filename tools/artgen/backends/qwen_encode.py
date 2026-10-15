"""Text-encoder worker for qwen_image21: fills the encoding cache and exits.

    python -m backends.qwen_encode JOBFILE        (run from tools/artgen)

JOBFILE is a JSON list of ``{"prompt": str, "ref_paths": [str], "ref_res": int}``. Runs in its own
process so the 17.5 GB Qwen3-VL (bf16, CPU) never shares memory with the transformer. Everything it
prints goes to stderr: callers (scenekit) parse artgen's stdout.
"""
from __future__ import annotations

import json
import os
import sys
import time


def main(argv: list[str]) -> int:
    real_stdout, sys.stdout = sys.stdout, sys.stderr     # stdout is reserved for callers
    if len(argv) != 1:
        print("usage: python -m backends.qwen_encode JOBFILE", file=sys.stderr)
        return 2
    jobs = json.loads(open(argv[0]).read())
    import torch
    from PIL import Image
    from diffusers import QwenImage21Pipeline
    from transformers import Qwen3VLForConditionalGeneration, Qwen3VLProcessor
    from . import _enc_cache
    from ._common import hf_snapshot, load_registry
    from .qwen_image21 import NAMESPACE, check_pipeline_api, condition_image, snapshot_revision

    check_pipeline_api(QwenImage21Pipeline)
    repo = load_registry()["qwen_image21"]["config_repo"]
    root = hf_snapshot(repo, ["*.json", "*.jinja", "text_encoder/*", "processor/*"])
    encoder_id = f"{repo}@{snapshot_revision(root)}"
    todo = []
    for j in jobs:
        conds = [condition_image(Image.open(p), j["ref_res"]) for p in j.get("ref_paths") or []]
        k = _enc_cache.key(j["prompt"], conds, j["ref_res"], encoder_id)
        if _enc_cache.get(k, NAMESPACE) is None and k not in [t[0] for t in todo]:
            todo.append((k, j, conds))
    if not todo:
        print(json.dumps({"encoded": 0, "cached": len(jobs)}))
        return 0
    t0 = time.perf_counter()
    proc = Qwen3VLProcessor.from_pretrained(os.path.join(root, "processor"))
    te = Qwen3VLForConditionalGeneration.from_pretrained(
        os.path.join(root, "text_encoder"), dtype=torch.bfloat16, device_map="cpu").eval()
    helper = QwenImage21Pipeline(scheduler=None, vae=None, text_encoder=te, processor=proc, transformer=None)
    print(json.dumps({"te_load_s": round(time.perf_counter() - t0, 1)}))
    for k, j, conds in todo:
        t1 = time.perf_counter()
        with torch.no_grad():
            enc = helper.encode_prompt(j["prompt"], image=conds or None, device="cpu")
        _enc_cache.put(k, enc, NAMESPACE)
        print(json.dumps({"encoded_s": round(time.perf_counter() - t1, 1), "key": k[:12]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
