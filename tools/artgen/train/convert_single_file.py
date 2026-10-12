#!/usr/bin/env python
"""Convert an SDXL single-file checkpoint to a diffusers folder (offline, fp16 weights).

  convert_single_file.py ~/Downloads/waiIllustriousSDXL_v170.safetensors ~/.cache/artgen/wai_v17_diffusers

The single file is only read. The config comes from the SDXL base repo in the HF cache.
"""
import os, sys
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import torch
from diffusers import StableDiffusionXLPipeline

src, dst = (os.path.expanduser(a) for a in sys.argv[1:3])
tmp = dst.rstrip("/") + ".tmp"
pipe = StableDiffusionXLPipeline.from_single_file(src, local_files_only=True, torch_dtype=torch.float16)
pipe.save_pretrained(tmp, safe_serialization=True)
os.rename(tmp, dst)
print(dst)
