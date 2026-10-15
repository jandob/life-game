#!/bin/bash
# FLUX klein: side and back views with the chosen front as reference (one process per call, sequential)
cd /Users/janosch/repos/life-game/tools/artgen
P=.venv/bin/python
S3="anime style pixel art, thick dark outlines, flat cel shading with two tones"
BG='background=plain flat white background'
gen() { # name ref prompt
  /usr/bin/time -p $P artgen.py generate --backend flux2_klein_pixel_lora --opt lora_scale=1.0 --opt "$BG" \
    --ref "$2" --width 576 --height 1024 --seed 11 --n 2 --out out/sam_art/views --name "$1" --prompt "$3, $S3"
}
SAM="the same young woman from the reference image, adult, same blonde hair, same teal zip-up track jacket with white stripes, same white top, same black leggings, same white sneakers, fully clothed"
PL="the same man from the reference image, adult, same messy brown hair, same green hoodie, same dark blue jeans, same brown sneakers, fully clothed"
gen sam_side "out/sam_art/front/sam_front_s13.png" "$SAM, standing, side view facing right, full body profile"
gen sam_back "out/sam_art/front/sam_front_s13.png" "$SAM, standing, back view seen from behind, full body"
gen sam_frontflux "out/sam_art/front/sam_front_s13.png" "$SAM, standing, front view facing the viewer, full body"
gen player_side "out/sam_art/front/player_front_s12.png" "$PL, standing, side view facing right, full body profile"
gen player_back "out/sam_art/front/player_front_s12.png" "$PL, standing, back view seen from behind, full body"
