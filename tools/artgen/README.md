# artgen: AI pixel-art pipelines for Life Game

`artgen` generates raw images with a pluggable **backend** (a local model or
a remote service). It then turns them into game-ready pixel art with a
**backend-agnostic post-processor**, and compares backends on a fixed
**benchmark**. Every output PNG has a JSON sidecar (backend, models, prompt,
seed, options, timings), so any image can be reproduced.

```
tools/artgen/
  artgen.py            CLI: backends | generate | inpaint | refine | cast | mask | pose | snap | post | palette-from
  compose.py           two-stage scenes: FLUX klein (refs) -> SDXL refine; scene | refine | sheet
  maskkit.py           box/ellipse/head-protect repaint masks (artgen.py mask)
  bench.py             runs a backend over prompts/bench.yaml -> contact sheets + table
  compare.py           item x run grid to compare variants or backends side by side
  postprocess.py       grid detect, downscale, bg removal, palette, cleanup, outline, cell fit
  backends/
    base.py            Backend interface + BackendInfo metadata
    __init__.py        registry (name -> module:Class)
    flux2_klein_pixel_lora.py
    sdxl.py            SDXL checkpoints: Illustrious, WAI, Pony, SDXL base (+ LoRA, ref, pose, inpaint)
    z_image_turbo.py   Z-Image-Turbo built from the ComfyUI single files
    _common.py         models.json reader, HF cache helpers, memory tracker
    example_stub.py    template for new backends
  models.json          registry for sdxl / z_image_turbo: model files (paths or HF files), LoRAs, VAE, IP-Adapter
  pose.py              draws OpenPose skeleton PNGs (artgen.py pose)
  STYLES.md            ready-to-run command templates per style (S2/S3/S4) x backend
  test_backends.py     tests for the two backends above
  prompts/bench.yaml   the fixed benchmark prompt set
  palettes/player_ref.hex  37 colours from assets/library/characters/player/player.png
```

## Setup (macOS, Apple Silicon)

```sh
cd tools/artgen
uv venv --python 3.14 .venv            # any Python >= 3.10 works
uv pip install --python .venv/bin/python torch transformers accelerate safetensors \
    huggingface_hub peft Pillow numpy pyyaml \
    "git+https://github.com/huggingface/diffusers.git"   # needs >= 0.37.0.dev0
```

`.venv/` and `out/` are git-ignored. On first use the models download to the
Hugging Face cache (`~/.cache/huggingface/hub`). For the FLUX backend, fetch
only the diffusers folders (about 15 GB plus 310 MB for the LoRA):

```sh
.venv/bin/python -c '
from huggingface_hub import snapshot_download as d
d("Limbicnation/pixel-art-lora", allow_patterns=["pytorch_lora_weights.safetensors","*.json","*.yaml","README.md","LICENSE"])
d("black-forest-labs/FLUX.2-klein-4B", allow_patterns=["model_index.json","LICENSE.md","README.md",
  "scheduler/*","text_encoder/*","tokenizer/*","transformer/*","vae/*"])'
```

Don't download `flux-2-klein-4b.safetensors` (the single-file checkpoint). The
diffusers pipeline doesn't need it.

## Commands

All commands run with `tools/artgen/.venv/bin/python`.

```sh
# list backends
artgen.py backends

# generate 4 seeds (11..14). --prompt is the subject; the backend wraps it in
# its trigger template ("pixel art sprite, <subject>, game asset, transparent background").
artgen.py generate --backend flux2_klein_pixel_lora \
    --prompt "an adult man, grey hoodie, jeans, standing, front view, full body" \
    --seed 11 --n 4 --out out/man --name man_front
# options: --opt lora_scale=1.0 --opt steps=4 --opt background="plain white background"
#          --opt offload=none (all on GPU)   --raw-prompt (no template)   --width/--height

# keep a character consistent: condition on an approved image (FLUX.2 reference)
artgen.py generate --backend flux2_klein_pixel_lora --ref out/man/man_front_s11.png \
    --prompt "the same man from the reference image, same clothes, back view, full body" \
    --seed 11 --out out/man --name man_back

# post-process a character into a 64x128 cell, feet on row 105, with the drop shadow
artgen.py post out/man/*.png --grid fit --cell 64x128 --feet-row 105 --shadow \
    --outline inner --colours 24 --keep-largest --out out/man_px

# realistic characters (96x192 cell, feet on row 157, shadow centre (47.5, 152.5), radii 33.75x17.25):
# fix N (the generator's pixel size in raw px) ONCE per character and backend from a standing front
# view (man 132 rows, Samantha 126) and reuse it for every pose, so all frames share one pixel size.
# --grid N samples at phase (0, 0); `--grid fit` is only for a first look, it re-scales every image.
artgen.py post out/man/*.png --grid N --cell 96x192 --feet-row 157 --shadow \
    --outline inner --colours 24 --keep-largest --out out/man_px96

# props / portraits: native grid detection, no cell
artgen.py post out/sofa/*.png --grid auto --colours 16 --outline inner --out out/sofa_px

# tiles: snap to the native grid, take a 16x16 centre crop (or --tile-mode resample)
artgen.py post out/floor/*.png --tile --cell 16x16 --colours 8 --out out/floor_px

# lock to a fixed palette instead of adaptive colours
artgen.py post IN.png --grid auto --palette palettes/player_ref.hex --out OUT
artgen.py palette-from SOME.png --out palettes/new.hex
```

### refine, mask and the two-stage recipe

`refine` runs an existing image through another model (img2img). `--strength` is the share of the image that gets
repainted: 0.3 keeps layout, faces and colours, 0.75 repaints most of it. Several values run in one model load.

```sh
artgen.py refine --backend sdxl --image scene.png --prompt "<tags>" --strength 0.3 0.45 0.6 \
    --opt model=wai_v17 --opt loras=pixel_art_xl:0.8 [--mask mask.png] [--pose pose.png] --seed 11 --n 1 \
    --out out/refine --name scene
# -> out/refine/scene_st30_s11.png (+ .json: source sha256, mask sha256, strength, seed, prompt, opts)
```

sdxl uses `StableDiffusionXLImg2ImgPipeline` (no mask) or the inpaint pipeline (mask; white = repaint). With a mask the
original pixels are pasted back outside it (edge blur `--opt feather=6`), so protected areas stay unchanged. `--pose`
switches to the ControlNet img2img/inpaint variants. Sides snap to a multiple of 8. Other backends: only the flux backend
(through `inpaint` with a full mask). The prompt gets the backend's quality/rating tags like `inpaint`; `--raw-prompt` skips them.

```sh
# mask helper: white = repaint. Boxes are x0,y0,x1,y1 (px; --units frac for 0..1)
artgen.py mask --image scene.png --heads 245,38,420,205 --heads 612,68,795,265 --feather 3 \
    --preview mask_check.png --out mask.png       # everything except the heads; look at mask_check.png
artgen.py mask --size 1024x768 --rect 0,300,1024,768 --keep-ellipse 100,300,200,400 --out m2.png
```
`--rect/--ellipse` paint white on black, `--keep-rect/--keep-ellipse` paint black, `--heads` (ellipse grown by `--head-pad`,
default 15 %, includes hair) paints black on white. No segmentation model: read the boxes off the stage-1 image.

`compose.py` wraps both stages (styles s2/s3/s4 carry the wording and LoRA of STYLES.md):

```sh
compose.py scene  --ref man.png woman.png --scene "The man and the woman from the reference images, ..." --out out/c
compose.py refine --image out/c/scene_s11.png --heads 245,38,420,205 --heads 612,68,795,265 \
    --prompt "<tags>" --strength 0.3 0.45 0.6 --model wai_v17 --out out/c      # also writes the mask and its preview
compose.py sheet --row "full=0.30@a.png,0.45@b.png" --row "heads=0.30@c.png" --out sheet.png
```

### cast: several masked regions in one command

`cast RECIPE.json` applies a list of regions to one image, in order (each step's output is the next step's input).
Every region is a full-resolution masked refine (whole image as context, same as `refine --mask`); one model load for all.
The recipe is validated before any model loads: errors print `{"ok": false, "error": ...}` and exit 2.

```sh
artgen.py cast examples/cast_recipe.json --out out/cast      # default out: <recipe dir>/<recipe stem>_cast
# -> out/cast/01_woman_head.png, 01_woman_head_mask.png (mask tinted red), 02_..., final.png, cast.json
```

Recipe (`examples/cast_recipe.json`; relative paths are relative to the recipe file):

| field | meaning |
|---|---|
| `image` | source PNG (required). Optional top level: `backend` (default `sdxl`), `opts` (like `--opt`, e.g. `model`), `negative` |
| `regions[].name` | required, unique, `[A-Za-z0-9_-]`; used in file names |
| `regions[].mask` **or** boxes | `mask`: PNG, white = repaint, same size as the image. Boxes: `rect`, `ellipse` (white), `keep_rect`, `keep_ellipse` (black), `heads` (everything except heads, like `artgen.py mask`); each a `"x0,y0,x1,y1"` string or list of them; `units` `px`/`frac`, `head_pad`, `head_shape`, `base` as in `mask` |
| `regions[].feather` | edge blur in px (default 6), applied by the backend when it pastes the original back outside the mask |
| `regions[].prompt` | required subject; backend tags and LoRA triggers are added (`raw_prompt: true` sends it verbatim); optional `negative` |
| `regions[].opts` | per-region `--opt` values (`loras`, `model`, `rating`, `steps`, ...), merged over the top-level `opts` |
| `regions[].strength` | (0, 1], default 0.5 |
| `regions[].seed` | integer, default 0; same recipe + same seeds reproduce the result |

`cast.json` logs the resolved prompt, generation options, seed, strength, mask coverage and seconds of every region.
There is no crop mode: the model always sees the whole image, so the pixel grid stays consistent across it.

### Post-processing stages (`postprocess.py`)

| Stage | What it does |
|---|---|
| `remove_background` | Uses real alpha if present. Otherwise it flood-fills from the image border through pixels within `tol` of up to 4 dominant border colours. This handles the fake grey checkerboard models paint for "transparent background". |
| `detect_grid` | Autocorrelates the colour-edge profile per axis at 1/4 px resolution and takes the smallest strong peak as the pseudo-pixel size. A comb search then refines the scale and finds the phase. Generated art does not keep one exact grid, so expect about ±0.3 px error. |
| `downscale` | One output pixel per cell, using the mode colour of the cell centre and a majority-vote alpha. `keep_dark` keeps thin dark lines (outlines, eyes) that fall between cell centres. |
| `grid="fit"` | Instead of the native grid, picks the cell size that maps the subject's height to the character height of the cell (64×128: rows 17–105 like `player.png`; the top row scales with the cell width, 96×192: rows 26–157). |
| `quantize` | Adaptive N colours (median cut, no dither) or snapping to a `.hex`/`.gpl`/`.png` palette. |
| `cleanup` | Removes opaque islands smaller than N pixels, fills 1–2 px holes, and recolours orphan pixels whose 8 neighbours mostly agree. |
| `add_outline` | `outer` grows a 1 px outline in the project navy `#222034`. `inner` recolours the silhouette boundary instead (keeps the size, and works best on model output that already has a broken outline). |
| `fit_cell` | Crops to content, centres it horizontally and puts the lowest opaque row on `feet_row`. It can add the project drop shadow (64×128: ellipse at (31.5, 102), radii 22.5×11.5; other cells scale by width/64 and put the centre 3×k rows above the feet row, 96×192 with feet 157: (47.5, 152.5), radii 33.75×17.25; `#3f3f74` and a `#5c5ca9` rim, alpha 125). Content is never resampled here, only clipped (and the clip is reported). |

Outputs use alpha 0 or 255 only, except the drop shadow (alpha 125, like the
reference).

## Benchmark

```sh
bench.py --backend flux2_klein_pixel_lora --out OUT --precompute \
    --variant lora1.0:lora_scale=1.0 --variant base:lora_scale=0
```

`prompts/bench.yaml` fixes the items, seeds (11, 42) and size (512²):

- an adult man (front, side, back);
- side and back again, conditioned on the front image (`ref:`);
- the blue-haired woman (the wanderer);
- a sofa prop;
- wood floor and wall tiles;
- an apartment interior;
- a portrait bust.

Subjects are backend-neutral. Each backend adds its own trigger template.

For each variant it writes, under `OUT/<backend>/<variant>/`:
`raw/` and `px/` (PNG + sidecar), `rows/<item>.png` (raw | processed at 4×,
the `player.png` reference cell next to characters, tiles shown 3×3 for seam
checks), `contact.png`, `results.md` (timings, peak memory, grid and notes per
image) and `results.json`. `--precompute` lets a backend prepare all prompts
up front. FLUX uses it to encode every prompt and then move the 8 GB text
encoder off the GPU.

`--post-only` reuses the existing `raw/` images and only re-runs post-processing
and the sheets. Use it to tune `postprocess.py` without regenerating.

To compare pipelines, run every backend with the same `bench.yaml`, then:

```sh
compare.py OUT/flux2_klein_pixel_lora/lora1.0 OUT/<other_backend>/default \
    --seed 11 --items man_front,man_back_ref,sofa,portrait_man --out compare.png
```

## Adding a backend

1. Copy `backends/example_stub.py` to `backends/<name>.py`. Subclass
   `Backend` and fill in `info = BackendInfo(...)`: the name, the model or
   service ids, the licence of the weights and outputs, `local`, `defaults`, and
   `prompt_template` (use `{prompt}` and optionally `{background}`).
2. Implement `load(**opts)` and
   `generate(prompt, negative, width, height, seed, n, **opts) -> list[PIL.Image]`.
   Image `i` must be reproducible from `seed + i`. Optionally implement
   `stats()` (timings, peak memory), `precompute(prompts)` and `unload()`.
3. Register it in `backends/__init__.py`: `"<name>": "<name>:<Class>"`.
4. Run `bench.py --backend <name> ...` and compare the contact sheets.

The stub's docstring sketches SDXL + pixel LoRA (diffusers), Replicate and
PixelLab. Remote backends read API keys from the environment and must never
write them into sidecars. Weights and services need approval before you
download or sign up.

## FLUX.2 klein + pixel LoRA notes

- `lora_scale` here multiplies the raw LoRA delta. The LoRA was saved with
  `use_rslora` (alpha 128, rank 64), so peft would scale it by 16, which
  produces black or noise images. The backend divides that out: `lora_scale=1.0`
  is the sweet spot, 2 gets muddy, and 4 breaks. The model card's "0.85–1.4" is
  ComfyUI strength, which roughly matches this scale.
- It runs 4 steps at CFG 1.0, so negative prompts are ignored.
- FLUX.2's multi-reference input (`--ref`) works well for keeping a
  character's outfit consistent across directions.
- Memory (M5, 24 GB): `offload=none` keeps everything resident and needs about
  18 GB on MPS. On this machine that pushes it into swap, at 14–34 s per image.
  The default `offload=free_te` moves the 8 GB text encoder to MPS only while
  encoding a new prompt (about 11 s), then back. Generation then peaks at
  about 10 GB and runs at about 5–11 s per 512² image (19 s with a `--ref`
  image). The bench's `--precompute` encodes every prompt once up front.

## inpaint and snap (used by scenekit)

`artgen.py inpaint --image canvas.png --mask mask.png --prompt "..." --strength 0.75 --n 4 --out DIR` runs
`Flux2KleinInpaintPipeline` (same weights and LoRA, `--ref` images become `image_reference`; white mask = repaint; sides must be
multiples of 16; scene prompt template). Prints one JSON object. `artgen.py snap IMG... --factor S [--palette P.hex|--colours N]
[--key #rrggbb] [--grid fixed|detect --target WxH] --out DIR` downscales by an exact integer block mode
(`postprocess.downscale_fixed`), locks the palette and cleans up. See `tools/scenekit/README.md`.

## SDXL and Z-Image backends

Two in-process diffusers backends next to FLUX. For ready-made commands per style see
`STYLES.md`. Model files are never copied: `models.json` points at the HF cache, at
`~/Downloads` (WAI v17) and at the shared ComfyUI folder `~/ComfyUI-Shared/models/`
(read-only; ComfyUI itself is not used). Edit `models.json`, or set `ARTGEN_MODELS=/path/other.json`,
to add a checkpoint.

### `sdxl`

```sh
.venv/bin/python artgen.py generate --backend sdxl \
    --opt model=illustrious_v1 --opt loras=pixel_art_xl:0.8 \
    --prompt "1boy, solo, adult, brown hair, grey hoodie, jeans, standing, front view, full body, anime style pixel art" \
    --opt background="plain flat white background" --width 768 --height 1152 --seed 11 --out out/man
```

| `--opt` | Meaning |
|---|---|
| `model` | `illustrious_v1` (default), `wai_v17`, `cyberrealistic_pony_v18`, `sdxl_base`. Switching model reloads (about 5-10 s). |
| `loras` | `pixel_art_xl:0.8`, comma separated, or a path to a `.safetensors`. A registered LoRA's trigger (`pixel art`) is added to the prompt. `0` or omitted = none. |
| `rating` | `safe` (default), `questionable`, `explicit`. Becomes `rating_*` (Pony) or `general` / `sensitive` / `nsfw, explicit` (Illustrious, WAI). Not used for `sdxl_base`. |
| `background` | Text appended to the prompt (default `simple background`). `quality=` replaces the family's quality prefix (empty = none). |
| `steps`, `guidance`, `sampler` | Defaults per model in `models.json` (28 / 6.0 / `euler_a` for Illustrious and WAI, 30 / 5.0 / `dpmpp_sde_karras` for Pony, 30 / 7.0 for base). Samplers: `euler_a`, `dpmpp_2m_karras`, `dpmpp_sde_karras`. |
| `--negative` / `negative_extra` | `--negative` replaces the family default negative, `--opt negative_extra=...` appends to it. |
| `--ref FILE` + `ip_scale` | Reference image through IP-Adapter Plus (ViT-H), default scale 0.6 (use 0.25-0.4 together with `pose`, 0.6 corrupts the image). It carries colours and look more than exact identity. |
| `pose` + `pose_scale`, `pose_end` | Skeleton PNG (below) through the OpenPose ControlNet (scale 0.8, released at 80 % of the steps). |

- **Prompts follow each family's convention** (`--raw-prompt` turns that off). Pony: `score_9, score_8_up, score_7_up, rating_safe, ...`.
  Illustrious and WAI: `masterpiece, best quality, amazing quality, very aesthetic, absurdres, newest, general, ...`; Danbooru tags mixed with
  plain English work. Their default negative contains `child, loli, shota, young` because these checkpoints skew young: put `adult` and an
  age description in your prompt. `sdxl_base` takes plain English only.
- **Prompts longer than 77 CLIP tokens are not truncated**: the backend encodes them in 75-token chunks and joins the embeddings
  (an explicit `clip_skip` option falls back to diffusers' encoder and truncates). Pony's "clip skip 2" is diffusers' default for SDXL.
- fp16 on MPS uses `madebyollin/sdxl-vae-fp16-fix` (the stock VAE gives black images). Image `i` is reproducible from `seed + i`
  (CPU generator), but not identical to ComfyUI or Civitai seeds.
- **Sizes**: SDXL wants about 1 MP: 768x1152 or 832x1216 for characters, 1024x768 for props. Multiples of 8. At 832x1216 a 28-step image takes
  about 45 s on the M5, peaking at 13 GB on MPS.
- `inpaint` works: `artgen.py inpaint --backend sdxl --image canvas.png --mask mask.png --prompt "..." --strength 0.75 --opt model=wai_v17`
  (`StableDiffusionXLInpaintPipeline` on the loaded weights, white mask = repaint, sides multiples of 8; without `--raw-prompt` the
  family's quality prefix is added).
- **Pose (OpenPose ControlNet)**: `artgen.py pose --preset stand_front --size 768x1152 --out pose.png` draws the skeleton ourselves
  (presets `stand_front`, `stand_front_arms_out`, `stand_side`, `sit_front`, or `--keypoints my.json` with 18 `[x, y]` pairs in 0..1).
  No annotator model is used. The ControlNet is `xinsir/controlnet-openpose-sdxl-1.0` (Apache-2.0, single fp16-loaded safetensors, 2.5 GB, in the HF cache).
  Multi-person skeletons: pass a JSON list of 18-point lists to `--keypoints`, or use the `sit_pair` preset.

### `z_image_turbo`

Built from `z_image_turbo_bf16.safetensors`, `qwen_3_4b.safetensors` and `ae.safetensors` plus a few kB of
config JSON from `Tongyi-MAI/Z-Image-Turbo`. 8 steps, guidance 0 (negative prompts ignored). Natural-language prompts only, no tags, no
LoRA support yet. The text encoder (8 GB) and the transformer (12 GB) are never in memory together: a prompt is encoded first, the
encoder is dropped, then the transformer loads to MPS (12 s). Peak about 18 GB on MPS, so close other heavy apps.
`--opt style="anime style pixel art. "` is prepended to the prompt; `--opt background=...` is appended.

```sh
.venv/bin/python artgen.py generate --backend z_image_turbo --width 768 --height 1152 --seed 11 \
    --opt style="detailed hi-res pixel art, limited palette. " --prompt "a young man in a grey hoodie, front view, full body" --out out/z
```

Tests: `.venv/bin/python test_backends.py` (fast), `ARTGEN_TEST_MODELS=1 .venv/bin/python test_backends.py` (loads WAI v17 and Z-Image).
