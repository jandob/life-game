#!/bin/bash
# HISTORICAL RECORD: this is how Samantha's first front was made. It no longer runs: the sdxl backend
# (and its LoRAs/cast) was removed by the OpenSpec change artgen-qwen-image (2026-10-16).
cd /Users/janosch/repos/life-game/tools/artgen
P=.venv/bin/python
SUF="anime style pixel art, thick dark outlines, flat cel shading with two tones"
time $P artgen.py generate --backend sdxl --opt model=wai_v17 --opt loras=pixel_art_xl:0.8 \
  --opt background="simple background, white background" --width 768 --height 1152 --seed 11 --n 4 \
  --out out/sam_art/front --name sam_front \
  --prompt "1girl, solo, adult woman, 25 years old, athletic, slim, blonde hair, shoulder-length hair, loose hair, side-swept bangs, blue eyes, confident smirk, teal zip-up track jacket, white sports top, black leggings, white sneakers, fully clothed, standing, arms at sides, facing viewer, front view, full body, $SUF"
time $P artgen.py generate --backend sdxl --opt model=wai_v17 --opt loras=pixel_art_xl:0.8 \
  --opt background="simple background, white background" --width 768 --height 1152 --seed 11 --n 4 \
  --out out/sam_art/front --name player_front \
  --prompt "1boy, solo, male focus, adult, slender, slim build, brown hair, short messy hair, green eyes, calm neutral expression, olive green hoodie, dark blue jeans, brown sneakers, fully clothed, standing, arms at sides, facing viewer, front view, full body, $SUF"
