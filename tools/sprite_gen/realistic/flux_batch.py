"""Run many FLUX klein jobs with one model load.

Usage (from tools/artgen):
    .venv/bin/python out/sam_art/flux_batch.py JOBS.json

JOBS.json: {"defaults": {...}, "jobs": [{"name", "out", "prompt", "ref": [...], "seed", "n", "width", "height"}]}
Every image gets the usual artgen PNG + JSON sidecar (via artgen.generate_images).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import artgen  # noqa: E402
from backends import get_backend  # noqa: E402

spec = json.loads(Path(sys.argv[1]).read_text())
d = spec.get("defaults", {})
b = get_backend("flux2_klein_pixel_lora")
opts = {k: v for k, v in b.info.defaults.items() if v is not None}
opts.update(d.get("opts", {}))
t0 = time.perf_counter()
b.load(**{k: v for k, v in opts.items() if k in b.load_keys})
print(f"load {time.perf_counter() - t0:.1f}s", flush=True)
gen_base = {k: v for k, v in opts.items() if k not in b.load_keys}
suffix = d.get("suffix", "")
for job in spec["jobs"]:
    gen = dict(gen_base)
    if job.get("ref"):
        gen["ref"] = job["ref"]
    else:
        gen.pop("ref", None)
    t1 = time.perf_counter()
    paths = artgen.generate_images(
        b, job["prompt"] + suffix, raw_prompt=False, seed=job.get("seed", d.get("seed", 11)),
        n=job.get("n", d.get("n", 1)), width=job.get("width", d.get("width", 576)),
        height=job.get("height", d.get("height", 1024)), negative=None, opts=gen,
        out_dir=Path(job.get("out", d.get("out"))), stem=job["name"])
    print(f"{job['name']}: {time.perf_counter() - t1:.1f}s -> {[str(p) for p in paths]}", flush=True)
print(f"total {time.perf_counter() - t0:.1f}s")
