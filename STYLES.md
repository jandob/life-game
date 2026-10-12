# Style recipes per backend

Ready-to-run `artgen.py generate` templates for the three styles. Replace `<SCENE>` with the subject
(keep it fully described: who, clothes, pose, view). Run from `tools/artgen` with `.venv/bin/python`.
Measured on the M5 (24 GB): SDXL 768x1152 about 45-60 s per image (28 steps, peak 13 GB MPS);
Z-Image-Turbo about 100 s per image including the text-encoder reload (peak 18-22 GB); FLUX 5-11 s.

Assessment from `scratchpad/backends` (one man + one sofa, clothed): see the end of this file.
`--n 4` gives 4 seeds. Post-process with the `post` lines at the bottom.

Notes valid for all SDXL lines: tag models (Illustrious, WAI, Pony) like Danbooru tags
(`1boy, solo, adult, ...`); put `adult` / `mature male` in character prompts, because they skew young. `rating=safe` (default)
adds nudity terms to the negative; for explicit tests use `--opt rating=explicit`. Pony adds a person to almost
any sofa/furniture prompt, so give Pony props a human negative and check each image.

## S2 realistic hi-res pixel

| Backend | Command |
|---|---|
| FLUX (reference) | ` .venv/bin/python artgen.py generate --backend flux2_klein_pixel_lora --opt lora_scale=0.5 --opt background="plain flat dark navy background" --prompt "<SCENE>, detailed hi-res pixel art, realistic anatomy, sculpted form shading, crisp specular highlights, limited palette" --width 576 --height 1024 --seed 11 --n 4 --out out/s2` |
| sdxl wai_v17 (recommended SDXL) | ` .venv/bin/python artgen.py generate --backend sdxl --opt model=wai_v17 --opt loras=pixel_art_xl:0.5 --opt background="simple background, dark blue background" --prompt "<SCENE as tags>, detailed hi-res pixel art, sculpted form shading, crisp specular highlights, limited palette" --width 768 --height 1152 --seed 11 --n 4 --out out/s2` |
| sdxl illustrious_v1 | same with ` .venv/bin/python artgen.py generate --backend sdxl --opt model=illustrious_v1` (cleaner licence, a bit flatter) |
| sdxl cyberrealistic_pony_v18 | ` .venv/bin/python artgen.py generate ... --opt model=cyberrealistic_pony_v18 --opt loras=pixel_art_xl:1.0 ...` Gives photographs with pixelated details, not pixel art. Use only for realistic reference or `--ref`/pose experiments. |
| sdxl sdxl_base | ` .venv/bin/python artgen.py generate ... --opt model=sdxl_base --opt loras=pixel_art_xl:0.5 --prompt "<SCENE in plain English>, detailed hi-res pixel art, ..."` (best pure pixel look, no rating/quality tags, anatomy is plain) |
| z_image_turbo | ` .venv/bin/python artgen.py generate --backend z_image_turbo --opt style="detailed hi-res pixel art with sculpted shading and a limited palette. " --opt background="plain flat dark navy background" --prompt "<SCENE in plain English>" --width 768 --height 1152 --seed 11 --out out/s2` Comes out as a 3D-render look, not pixels; quantise with `post --grid 4`. |

## S3 anime-leaning pixel, thick outlines

| Backend | Command |
|---|---|
| FLUX (reference) | `artgen.py generate --backend flux2_klein_pixel_lora --opt lora_scale=1.0 --opt background="plain flat white background" --prompt "<SCENE>, anime style pixel art, thick dark outlines, flat cel shading with two tones" --width 576 --height 1024 --seed 11 --n 4 --out out/s3` |
| sdxl illustrious_v1 (recommended) | `artgen.py generate --backend sdxl --opt model=illustrious_v1 --opt loras=pixel_art_xl:0.8 --opt background="simple background, white background" --prompt "<SCENE as tags>, anime style pixel art, thick dark outlines, flat cel shading with two tones" --width 768 --height 1152 --seed 11 --n 4 --out out/s3` (LoRA 0.5-1.0 all work; lower keeps more detail) |
| sdxl wai_v17 | same with `model=wai_v17` (more detailed and realistic proportions) |
| sdxl sdxl_base | `--opt model=sdxl_base --opt loras=pixel_art_xl:0.8`, plain-English prompt. Closest to a classic sprite. |
| sdxl cyberrealistic_pony_v18 | not recommended (LoRA barely changes the photoreal look) |
| z_image_turbo | `--backend z_image_turbo --opt style="anime style pixel art with thick dark outlines and flat two-tone cel shading. " --prompt "<SCENE>"`. Clean anime illustration, not pixel art. |

## S4 flat vector / cel

No pixel LoRA (omit `loras`).

| Backend | Command |
|---|---|
| FLUX | `artgen.py generate --backend flux2_klein_pixel_lora --opt lora_scale=0 --opt background="plain flat white background" --prompt "<SCENE>, flat vector illustration, clean dark line art, two-tone cel shading, flat colours, modern character design" --width 576 --height 1024 --seed 11 --n 4 --out out/s4` |
| sdxl illustrious_v1 / wai_v17 | `artgen.py generate --backend sdxl --opt model=wai_v17 --opt background="simple background, white background" --prompt "<SCENE as tags>, flat vector illustration, clean dark line art, two-tone cel shading, flat colours" --width 768 --height 1152 --seed 11 --n 4 --out out/s4` (add `--opt negative_extra="3d, realistic, gradient"` if shading gets soft) |
| sdxl sdxl_base | same with `model=sdxl_base`, plain English. Good, with a cast shadow. |
| sdxl cyberrealistic_pony_v18 | not suitable (photo) |
| z_image_turbo (recommended) | `artgen.py generate --backend z_image_turbo --opt style="flat vector illustration with clean dark line art, two-tone cel shading and flat colours. " --prompt "<SCENE>" --width 768 --height 1152 --seed 11 --out out/s4` Cleanest flat-colour result; props are isolated on white. |

## Post-processing

```sh
# S2 / S3 character (flat background): detect the pixel grid, fit the 64x128 cell
artgen.py post out/s3/*.png --grid auto --colours 22 --outline inner --keep-largest --out out/s3_px
artgen.py post out/s3/*.png --grid fit --cell 64x128 --feet-row 105 --shadow --outline inner --colours 22 --keep-largest --out out/s3_cell
# S2: --colours 40
# S4 (not pixel art): fixed 4 px downscale
artgen.py post out/s4/*.png --grid 4 --colours 32 --outline none --keep-largest --out out/s4_px
# Props that fill the frame or keep a scene background: --bg none
```
Background removal needs a flat background. Gradients, vignettes and photographic backdrops (Pony, Z-Image S2) make it fail
and eat the figure; ask for `plain flat <colour> background` and check the `px` output.

## Assessment (one seed, so indicative only)

- **S2**: no SDXL option gives true "realistic hi-res pixel". WAI v17 and Illustrious are closest (detailed, shaded, pixel
  look); SDXL base + LoRA 0.5 is cleaner but cartoonish; Pony is photographic; Z-Image is a 3D render. FLUX was the most polished here.
- **S3**: SDXL base, Illustrious and WAI with pixel-art-xl are all good, better than FLUX on pixel crispness; Illustrious is the
  most "anime", WAI the most detailed. Z-Image is not pixel art.
- **S4**: Z-Image-Turbo is the cleanest flat vector; Illustrious/WAI/base are good line-art cel; Pony is a photo.
- Props: Illustrious and WAI zoom in so far that the sofa is cropped; SDXL base and Z-Image give whole, isolated sofas.

## Pose (OpenPose ControlNet, xinsir) and ref

```sh
artgen.py pose --preset walk_side_0 --size 768x1152 --out out/ctl_walk0.png   # walk_side_0..3, stand_front, stand_side, sit_front, sit_pair (two people, use 1024x768)
artgen.py generate --backend sdxl --opt model=wai_v17 --opt loras=pixel_art_xl:0.8 --opt pose=out/ctl_walk0.png \
    --opt background="simple background, white background" --width 768 --height 1152 --seed 11 --out out/walk \
    --prompt "1boy, solo, male focus, mature male, adult, white t-shirt, jeans, white sneakers, walking, from side, full body, profile, anime style pixel art, thick dark outlines, flat cel shading"
# add --ref out/front.png --opt ip_scale=0.3 to pull the look towards a reference. ip_scale 0.6 (default) breaks the image together with pose.
```
Measured (M5, wai_v17, 768x1152, 28 steps): pose only 55-60 s/image, peak 14.9 GB MPS; pose + ref 72-86 s, peak 17.4 GB.
Legs follow the skeleton well, arms are weaker. Identity across walk frames stays loose even with ref 0.25-0.4 (hair, trousers colour drift).
Two-person pose works (two figures seated side by side on a sofa; the skeletons' legs look standing because front-view sitting is foreshortened).
