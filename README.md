# artgen: AI pixel-art pipelines for Life Game

`artgen` generates raw images with a pluggable **backend** (a local model or
a remote service). It then turns them into game-ready pixel art with a
**backend-agnostic post-processor**, and compares backends on a fixed
**benchmark**. Every output PNG has a JSON sidecar (backend, models, prompt,
seed, options, timings), so any image can be reproduced.

```
tools/artgen/
  artgen.py            CLI: backends | generate | post | palette-from
  bench.py             runs a backend over prompts/bench.yaml -> contact sheets + table
  compare.py           item x run grid to compare variants or backends side by side
  postprocess.py       grid detect, downscale, bg removal, palette, cleanup, outline, cell fit
  backends/
    base.py            Backend interface + BackendInfo metadata
    __init__.py        registry (name -> module:Class)
    flux2_klein_pixel_lora.py
    example_stub.py    template for new backends
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

# props / portraits: native grid detection, no cell
artgen.py post out/sofa/*.png --grid auto --colours 16 --outline inner --out out/sofa_px

# tiles: snap to the native grid, take a 16x16 centre crop (or --tile-mode resample)
artgen.py post out/floor/*.png --tile --cell 16x16 --colours 8 --out out/floor_px

# lock to a fixed palette instead of adaptive colours
artgen.py post IN.png --grid auto --palette palettes/player_ref.hex --out OUT
artgen.py palette-from SOME.png --out palettes/new.hex
```

### Post-processing stages (`postprocess.py`)

| Stage | What it does |
|---|---|
| `remove_background` | Uses real alpha if present. Otherwise it flood-fills from the image border through pixels within `tol` of up to 4 dominant border colours. This handles the fake grey checkerboard models paint for "transparent background". |
| `detect_grid` | Autocorrelates the colour-edge profile per axis at 1/4 px resolution and takes the smallest strong peak as the pseudo-pixel size. A comb search then refines the scale and finds the phase. Generated art does not keep one exact grid, so expect about ±0.3 px error. |
| `downscale` | One output pixel per cell, using the mode colour of the cell centre and a majority-vote alpha. `keep_dark` keeps thin dark lines (outlines, eyes) that fall between cell centres. |
| `grid="fit"` | Instead of the native grid, picks the cell size that maps the subject's height to the character height of the 64×128 cell (rows 17–105, like `player.png`). |
| `quantize` | Adaptive N colours (median cut, no dither) or snapping to a `.hex`/`.gpl`/`.png` palette. |
| `cleanup` | Removes opaque islands smaller than N pixels, fills 1–2 px holes, and recolours orphan pixels whose 8 neighbours mostly agree. |
| `add_outline` | `outer` grows a 1 px outline in the project navy `#222034`. `inner` recolours the silhouette boundary instead (keeps the size, and works best on model output that already has a broken outline). |
| `fit_cell` | Crops to content, centres it horizontally and puts the lowest opaque row on `feet_row`. It can add the project drop shadow (ellipse at (31.5, 102), radii 22.5×11.5, `#3f3f74` and a `#5c5ca9` rim, alpha 125). Content is never resampled here, only clipped (and the clip is reported). |

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
