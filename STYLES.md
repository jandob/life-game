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

## Two-stage: consistent characters in a scene (FLUX refs -> SDXL refine)

IP-Adapter `ref` on WAI/Illustrious drifts, so identity comes from FLUX klein's multi-reference and SDXL only restyles.
Use clothed, front-view character images (the style swatches) as refs; replace `<SCENE>`, `<TAGS>`, `<HEAD boxes>`.

```sh
# 1. compose (about 40 s per 1024x768 image); the prompt must say "from the reference images" and "same clothes"
artgen.py generate --backend flux2_klein_pixel_lora --opt lora_scale=1.0 --raw-prompt \
    --ref out/man_front.png out/woman_front.png --width 1024 --height 768 --seed 11 --n 3 --out out/c --name scene \
    --prompt "anime style pixel art, thick dark outlines, flat cel shading with two tones. The man and the woman from the reference images, both adults, both fully clothed in the same clothes as in the references, <SCENE>"
# 2. look at out/c/scene_s11.png, read the head boxes (incl. hair) off it, check them
artgen.py mask --image out/c/scene_s11.png --heads <HEAD1> --heads <HEAD2> --head-pad 0.06 --feather 3 --preview out/c/mask_check.png --out out/c/mask.png
# 3. refine: full image, then with heads protected (about 30 s per strength at 1024x768)
artgen.py refine --image out/c/scene_s11.png --opt model=wai_v17 --opt loras=pixel_art_xl:0.8 --strength 0.3 0.45 0.6 --seed 11 \
    --prompt "<TAGS: 2people, 1boy, 1girl, adult, <scene>, hair colours, each outfit with colours>, anime style pixel art, thick dark outlines, flat cel shading with two tones" --out out/c --name full
artgen.py refine ... --mask out/c/mask.png --name heads
```
Same with `compose.py scene|refine|sheet` (see README). Repeat the outfit and hair colours of both characters in `<TAGS>`.

Results (WAI v17, S3, man + woman, sofa, one seed; sheet in the session scratchpad `refine/sheet.png`):
- FLUX stage: faces, hair, outfit colours of both characters carried over from the refs in 3 of 3 seeds.
- Full-image refine: 0.30 already changes the faces (man's face redrawn, woman gets green eyes), outfit colours hold; 0.45-0.60 hair
  turns blocky and the faces are new people; at 0.75 hair colour drifts (woman towards purple), props change. SDXL pixel style and
  proportions are clearly in by 0.45.
- Heads protected: faces and hair stay the FLUX originals at every strength, clothes and room take the SDXL pixel look,
  outfit colours hold up to 0.60 (at 0.75 the jacket gets darker). Cost: the heads stay smooth FLUX art while bodies and room are
  chunky pixels, plus a faint halo around the head ellipse at 0.75. Best compromise: 0.45 with heads protected,
  or 0.30 full image for a lighter touch; for a uniform pixel look run `post --grid auto` on the result.

## Character refine: put a character's LoRA back into a multi-person scene

Generating with a character LoRA directly fights multi-person scenes (it was trained on one person alone and drags poses toward
its dataset). Instead: generate the scene without it, then repaint each character's head and/or body with that character's LoRA
through a mask. Masks are made by the agent (`artgen.py mask`, boxes/ellipses read off the image); there is no detector.

```sh
# 1. scene (clothed, adults), about 40 s at 768x1152
artgen.py generate --backend sdxl --opt model=wai_v17 --opt loras=pixel_art_xl:0.7 --width 768 --height 1152 --seed 7 --out out/s \
    --prompt "2people, 1boy, 1girl, adult, sitting on sofa, talking, living room, <hair/outfit colours of both>"
# 2. look at it, place an ellipse on the head incl. hair, check the preview
artgen.py mask --image out/s/scene_s7.png --ellipse 278,328,462,505 --preview out/s/mask_check.png --out out/s/head_woman.png
# 3a. one region ...
artgen.py refine --image out/s/scene_s7.png --mask out/s/head_woman.png --opt model=wai_v17 \
    --opt loras=lgwoman1:0.8,pixel_art_xl:0.5 --strength 0.5 --seed 7 --prompt "1girl, auburn ponytail, blue eyes, face" --out out/s/r
# 3b. ... or all characters in one command (recipe: tools/artgen/examples/cast_recipe.json)
artgen.py cast recipe.json --out out/s/cast
```

Recommended settings (full image resolution, whole image as context):

| region | strength | character LoRA | `pixel_art_xl` |
|---|---|---|---|
| head (hair + face, ellipse slightly larger than the head) | 0.40-0.55 | 0.7-0.9 | 0.4-0.6 |
| full body (box/ellipse around the figure, keep the other person out) | 0.60-0.75 | 0.7-0.9 | 0.5-0.7 |

Put the character's hair colour and distinguishing features in the region prompt (the LoRA trigger is added automatically).
Repaint a second character with a second region (own LoRA, own mask), or paint the body before the head so the head is last.
Keep `feather` at 4-8 px; outside the feathered mask the pixels are unchanged (checked: 0 differing pixels).

Result (WAI v17, 768x1152, man + woman on a sofa, head ellipse 184x177 px, `lgwoman1:0.8,pixel_art_xl:0.5`, strength 0.5, seed 7):
head repainted in about 25 s; hair turns auburn, the face becomes the LoRA's, the man, sofa and room are untouched. `refine` and a one-region
`cast` give identical pixels. The LoRA head is smoother and finer than the chunky scene pixels (the LoRA's own style), so run `post --grid auto`
on the final image if a uniform pixel grid matters.


# Examples
```
.venv/bin/python artgen.py generate --backend sdxl --opt model=wai_v17 --opt loras=lgwoman1:0.6,pixel_art_xl:0.7 --opt rating=explicit --prompt "1boy, 1girl, sex, couch, penis, realistic, detailed, hi-res, shading, crisp specular highlights, limited palette" --width 768 --height 1152 --seed 11 --n 4 --out out/s2
```