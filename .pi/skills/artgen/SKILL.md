---
name: artgen
description: Generate, edit, compose and animate game art with tools/artgen (sprites, characters, portraits, props, room scenes, walk sheets) and post-process it into pixel art. Use when asked to make or change game art, a transparent prop, a character turnaround, a scene with several characters, a local fix of a generated image, or a sprite sheet, and when raw model output must become pixel-art cells.
---

# artgen: game art generation and pixel-art post-processing

Project numbers (cell size, feet row, outline and shadow colours, style words) come from the **active profile**
(lookup: env `ARTGEN_PROFILE=<path>`, else the first `art/artgen-profile.json` above the current directory or the tool, else the bundled generic `tools/artgen/profiles/default.json`). The commands below show the
life-game values (cell 96x192, feet row 157); `sheet` uses the profile values when you omit `--post-cell`/`--feet-row`.
**Life Game conventions: see the life-game-art skill.**

Everything lives in `tools/artgen/`. Run commands from that directory with `.venv/bin/python artgen.py <cmd>` (written
`artgen.py` below). `edit`, `sheet`, `refine`, `inpaint`, `mask`, `pose`, `snap` and `cache` print one JSON object as the
last stdout line; `generate` prints paths unless `--json`; `post` prints the output paths. Errors exit non-zero; every
generated PNG gets a `.json` sidecar. Write outputs under `out/` (git-ignored). Details:
`tools/artgen/README.md` (setup, memory, flags) and `tools/artgen/STYLES.md` (recipes with more prompts).

## 1. Setup check (do this first)

```sh
cd tools/artgen
ls .venv/bin/python                 # venv exists? if not: README.md "Setup", ask before downloading anything
.venv/bin/python artgen.py backends # lists backends with their caps; qwen_image21 must be present
.venv/bin/python artgen.py cache --stats
```

Models are read from the Hugging Face cache; never download models or install packages without approval.

## 2. Which backend for which stage

| | `qwen_image21` | `flux2_klein_pixel_lora` | `z_image_turbo` |
|---|---|---|---|
| text to image | yes, best, 1024², 55-95 s | yes, fast, 512², 5-11 s | yes, ~100 s |
| `generate --ref` (composition) | yes | runs, but weak for scenes (clothes/poses ignored in the eval) | no |
| real alpha (`--opt rgba=1`) | **only this one** | no (painted background, removed in post) | no (same) |
| `edit`, `sheet` | **only this one** | no | no |
| `refine`, `inpaint` (strength img2img; scenekit map tiles) | no | **only this one** | no |

A command that a backend lacks fails with a message naming the backends that support it. Default for new art:
`qwen_image21`. Edits, sheets, turnarounds, compositions and transparent output are `qwen_image21` only.

## 3. Operating rules (24 GB Apple Silicon Mac)

- **One model process at a time.** A second heavy process swaps the machine. Wait for a run to finish; do not run
  generation in parallel and do not run other heavy jobs meanwhile.
- Expected times: generate 1024² 55-95 s (peak 10-13 GB); sheet 1920x768 + refs about 3 min (peak ~15 GB). The first run of
  a new prompt/reference set also runs the text encoder in a separate process: about 20 s text only, about 3 min with 3 refs
  at 512, about 5 min with 1 ref at 1024, about 8.5 min with 2 refs + strip at 768. Use background execution and poll.
- **Reuse references and prompts**: encodings are cached (`~/.cache/artgen/enc/qwen21/`), so extra seeds (`--n`, `--seed`) and
  reruns skip the encode. Changing a ref pixel or the prompt re-encodes. `artgen.py cache --stats`, `--prune --older-than 30`.
- Image `i` of a run uses seed + i; MPS reruns are not guaranteed bit-exact across machines.
- Read the JSON stdout and the sidecar (`stats.peak_mps_gb`, timings, `enc_cache_hit`, `drift_outside_reach`).
- Local fixes are pasted back with a mask (below); a bare `edit` drifts over the whole image.
- Outputs stay in `tools/artgen/out/` (git-ignored). Do not overwrite project assets or commit generated images unless asked.

## 4. Recipes

### 4.1 Character (front view) and post-processing

```sh
artgen.py generate --backend qwen_image21 --seed 11 --out out/man --name man_front --json \
  --prompt "an adult man in his late twenties, short brown hair, grey hoodie, dark blue jeans, white sneakers, standing, front view facing the viewer, full body, top-down RPG character"
artgen.py post out/man/man_front_s11.png --grid fit --cell 96x192 --feet-row 157 --shadow --outline inner --colours 24 --keep-largest --out out/man_px
```

`--prompt` is the SUBJECT: it is wrapped in "Pixel art sprite of <subject>, 16-bit video game asset, crisp hard-edged pixels,
flat colours, plain flat white background." (`--raw-prompt` sends it verbatim). The `fit` run is a first look; read the grid
scale N from `out/man_px/*_px.json` (`report.grid.scale`). Fix N once per character and reuse it for every pose of that
character: `--grid N --cell 96x192 --feet-row 157 --shadow --outline inner --colours 24 --keep-largest`. Never re-fit per frame.

### 4.2 Transparent prop

```sh
artgen.py generate --backend qwen_image21 --opt rgba=1 --seed 11 --out out/sofa --name sofa \
  --prompt "a modern grey fabric three-seat sofa, top-down 3/4 view from above, furniture prop for an apartment"
artgen.py post out/sofa/sofa_s11.png --grid auto --colours 16 --outline inner --out out/sofa_px
```

`rgba=1` swaps the template for the trained RGBA wording. The raw alpha is 1-9 (not 0) in the background; `post` makes it
fully transparent. Check the px PNG's alpha (about two thirds of a sofa image should be 0). Props, portraits: `--grid auto
--colours 16 --outline inner`, no `--cell`.

### 4.3 Turnaround / outfit change / portrait from a character (`edit`)

```sh
artgen.py edit --image out/man/man_front_s11.png --seed 11 --out out/man --name man_back \
  --prompt "Picture 1 shows a young adult man from the front. Draw the same man from behind: back view seen from directly behind, the face is not visible, full body, same pixel art style, same clothes, plain flat white background."
```

Source = Picture 1; extra `--ref B C` are Picture 2, 3. Output has the source's size. `--ref-res` (default 1024) is ONE
value for the source and all refs. The prompt is verbatim. Describe what stays the same and what changes. Side view: same
prompt with "in strict side view facing right". Portrait: "Draw a head and shoulders dialogue portrait of the same man ...".

### 4.4 Scene composition (room + characters)

```sh
artgen.py generate --backend qwen_image21 --seed 11 --width 1024 --height 1024 --opt ref_res=512 --out out/scene --name scene \
  --ref out/room/room_s11.png out/man/man_front_s11.png out/woman/woman_front_s11.png \
  --prompt "Picture 1 is an empty apartment room, Picture 2 is a man, Picture 3 is a woman. Place the man and the woman from Pictures 2 and 3 sitting on the sofa cushions of the room in Picture 1, not on the rug or the coffee table. Keep the room unchanged: same layout, furniture and colours. Keep both characters' faces, hair and clothes. Scale them to the sofa so they look life-size. Same pixel art style."
```

With `--ref` the prompt is sent verbatim (no template). Order on the command line = Picture 1, 2, 3. Set `--width/--height`
to the room image's size (multiples of 32; default 1024x1024 for qwen). `generate` redraws the whole room, so "keep the room
unchanged" is a request, not a guarantee: the room drifts slightly. To keep the room's pixels exactly, use
`edit --image ROOM --ref MAN WOMAN --mask AREA --feather 8` with a mask over the area where the people go (paste-back, sidecar
`drift_outside_reach` 0.0). That variant is not yet tried on the model; check it.

### 4.5 Local fix with mark + mask (hands, faces)

```sh
artgen.py mask --size 1024x1024 --ellipse 448,300,568,440 --out out/fix/mask.png
artgen.py edit --image out/scene/scene_s11.png --mark 508,338,42 --mask out/fix/mask.png --feather 8 --seed 11 \
  --out out/fix --name hand --prompt "Picture 1 has a red circle marking a hand. Redraw that hand correctly with five fingers, same style and lighting. Remove the circle and change nothing else."
```

`--mark x,y,r` (source pixels) draws a red circle the model sees. `--mask` (white = take the edit) pastes only that area back
onto the unmarked source, feathered. Outputs `hand_s11.png` (pasted) and `hand_s11_raw.png` (unpasted). The sidecar must
show `drift_outside_reach` 0.0. Make the mask a bit larger than the mark circle. `artgen.py mask` also takes `--rect`,
`--keep-ellipse`, `--heads`, `--feather`, `--preview check.png` (look at the preview before running `edit`).

### 4.6 Walk sheet

```sh
artgen.py sheet --ref out/man/man_front_s11.png out/man/man_side_s11.png --poses walk_side --frames 5 --cell 384x768 \
  --ref-res 768 --seed 11 --subject "a young adult man with short messy brown hair, an olive green hoodie, dark blue jeans and brown sneakers" \
  --slice --out out/walk --name walk
```

One generation draws all frames (the skeleton strip is added as the last picture). `--slice` cuts frames into
`walk_f{i}.png` and post-processes each like a character (`--shadow --outline inner --colours 24 --keep-largest` built in) into
the profile's cell (`--post-cell`, `--feet-row`; Life Game: 96x192, row 157) with ONE shared pixel grid: `--grid N`, else fitted
on frame 0 and reused. N depends on the generation size: a 384x768 cell gives N ≈ 5.1 for an adult man, so a fixed N measured
on other raw images (e.g. 576x1024 key frames) does not apply here; let it fit on frame 0 unless you have N for this cell size.
It writes `walk_f{i}_px.png`, `walk_px_row.png` and `walk.gif` (140 ms/frame). Frames x cell width and cell height must be
multiples of 32. `--prompt`/`--prompt-file` replaces the generated prompt. Look at the row and the GIF: legs should alternate and
size and outfit stay consistent; reroll with another `--seed` otherwise (the encode is cached, a new seed costs about 3 min).
Only `--poses walk_side` exists.

### 4.7 Other post settings

| Kind | Flags for `artgen.py post` |
|---|---|
| characters 96x192 | `--grid N --cell 96x192 --feet-row 157 --shadow --outline inner --colours 24 --keep-largest` |
| props, portraits | `--grid auto --colours 16 --outline inner` |
| tiles 16x16 | `--tile --cell 16x16 --colours 8` (weak: not seamless, needs hand touch-up) |
| fixed palette | `--palette art/palettes/player_ref.hex` |

Locked-grid downscale without cell fitting (scenekit): `artgen.py snap`. Other commands: `artgen.py pose` previews skeletons,
`artgen.py palette-from IMG --out art/palettes/x.hex`.

## 5. Prompt patterns that worked

- Name every reference ("Picture 1 is ..., Picture 2 is ...") and refer to them by number.
- Explicit placement and scale ("on the sofa cushions, not on the rug or coffee table", "life-size next to the sofa").
- Say what must not change ("keep the room unchanged", "same face, hair, clothes", "change nothing else").
- For turnarounds say "the face is not visible" for back views and "plain flat white background".
- Transparent output: `--opt rgba=1`, not a "transparent background" phrase in the subject.
- Sheets: per-frame pose words are part of the generated prompt; add `--subject` with outfit details.
- Style words: the `generate` template (no `--ref`) already says "pixel art sprite ...". Verbatim prompts (`--ref`, `edit`,
  `sheet --prompt`) get the project's style words written into the prompt; for `sheet` without `--prompt`, put them at the
  end of `--subject`.
- Output files are `<out>/<name>_s<seed>.png` (+ `.json`); `--n` adds seed+1, seed+2 ... To check alpha:
  `.venv/bin/python -c "from PIL import Image; import numpy as n; a=n.array(Image.open('X.png').getchannel('A')); print((a==0).mean())"`.

## 6. What it cannot do

- Exact pose control: the skeleton strip is a hint, legs and arms land approximately.
- Seamless 16 px tiles (weak for every model).
- Bit-identical reruns across machines or versions (MPS); compare with tolerance.
- References on `z_image_turbo`, `edit`/`sheet` on flux (the command refuses with a message).
- Remote runs: `--opt runner=remote:runpod --opt variant=base` (40-step base model) needs
  `ARTGEN_REMOTE_RUNPOD_CMD="python remote/runpod_cmd.py"`, `RUNPOD_API_KEY` and `ARTGEN_RUNPOD_ENDPOINT`; it costs money
  per job (RunPod Serverless, README "RunPod Serverless"), so ask before using it. The base variant runs remote only.

## 7. Verify what you made

Open the PNGs (view them), check sizes (`edit` = source size, cells = the profile's cell), read the sidecar JSON, and report the command,
the seed and the output paths. Do not claim art quality you did not look at.
