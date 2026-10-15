# artgen: AI pixel-art pipelines for Life Game

`artgen` generates raw images with a pluggable **backend** (a local model or a remote service), edits and
composes them (references, instruction edits, sprite sheets), and turns them into game-ready pixel art with a
**backend-agnostic post-processor**. Every output PNG has a JSON sidecar (backend, models, prompt, seed,
options, timings, shas), so any image can be reproduced. Every command prints one JSON object on stdout
(`generate` prints paths unless `--json`) and exits non-zero on error. The stage-by-stage workflow with
copy-paste commands is in [STYLES.md](STYLES.md); the agent skill is `.claude/skills/artgen/SKILL.md`.

```
tools/artgen/
  artgen.py            CLI: backends | generate | edit | sheet | refine | inpaint | mask | pose | snap | post | palette-from | cache
  runner.py            JobSpec + LocalRunner / RemoteRunner (remote hosts via ARTGEN_REMOTE_<NAME>_CMD)
  maskkit.py           repaint masks, draw_mark, paste_back (artgen.py mask / edit)
  pose.py              OpenPose-style skeletons; the strip that `sheet` feeds the model
  bench.py / compare.py  run a backend over prompts/bench.yaml; side-by-side comparison
  postprocess.py       grid detect, downscale, bg removal, palette, cleanup, outline, cell fit
  backends/
    base.py, __init__.py, _common.py    interface, registry, models.json reader, memory tracker
    qwen_image21.py    Qwen-Image 2.1 Turbo, GGUF transformer (generate, refs, edit, sheet)
    qwen_encode.py     text-encoder worker (separate process), _enc_cache.py (encoding cache), _gguf.py (diffusers GGUF fix)
    flux2_klein_pixel_lora.py, z_image_turbo.py, example_stub.py
  models.json          model files / HF repos for z_image_turbo and qwen_image21
  STYLES.md            the pipeline stage by stage, with commands
  test_backends.py, test_infra.py, test_qwen.py, test_postprocess.py
  prompts/bench.yaml   the fixed benchmark prompt set;  palettes/player_ref.hex
```

## Setup (macOS, Apple Silicon, 24 GB)

```sh
cd tools/artgen
uv venv --python 3.14 .venv            # any Python >= 3.10 works
uv pip install --python .venv/bin/python torch transformers accelerate safetensors \
    huggingface_hub peft gguf Pillow numpy pyyaml \
    "git+https://github.com/huggingface/diffusers.git@85c9fa4caee33d1c5b473395784471d2d7957c1b"
```

diffusers is **pinned to commit `85c9fa4caee33d1c5b473395784471d2d7957c1b`** (0.41.0.dev0): `QwenImage21Pipeline`
only exists in the dev branch and `qwen_image21` checks the `encode_prompt` / `__call__` / `sample_sigmas` API at load
time and fails with this commit in the message if it changed. `gguf` is needed for the GGUF transformer. `.venv/` and
`out/` are git-ignored. Models download to the Hugging Face cache (`~/.cache/huggingface/hub`); nothing is
downloaded without you running these:

```sh
.venv/bin/python -c '
from huggingface_hub import snapshot_download as d, hf_hub_download as f
# Qwen-Image 2.1 Turbo: configs, text encoder, VAE, processor. NOT the 40 GB transformer shards (the GGUF replaces them).
d("Qwen/Qwen-Image-2.1-Turbo", allow_patterns=["*.json","*.jinja","*.txt","README.md","scheduler/*","vae/*","processor/*","text_encoder/*","transformer/config.json"])
f("abenzerps/Qwen-Image-2.1-Turbo-Quantized", "qwen-image-2.1-turbo-Q8_0.gguf")          # 7.6 GB
# FLUX.2 klein + pixel LoRA (about 15 GB + 310 MB); not the single-file flux-2-klein-4b.safetensors
d("Limbicnation/pixel-art-lora", allow_patterns=["pytorch_lora_weights.safetensors","*.json","*.yaml","README.md","LICENSE"])
d("black-forest-labs/FLUX.2-klein-4B", allow_patterns=["model_index.json","LICENSE.md","README.md","scheduler/*","text_encoder/*","tokenizer/*","transformer/*","vae/*"])'
```

Z-Image-Turbo reads the ComfyUI single files listed in `models.json` (`~/ComfyUI-Shared/models/...`) plus a few kB of
config JSON from `Tongyi-MAI/Z-Image-Turbo`. Licences: Qwen-Image 2.1 and the GGUF conversion use the Qwen Research
licence (see the model card); FLUX klein and Z-Image are Apache-2.0.

Tests (fast, no models): `.venv/bin/python test_backends.py`, `test_infra.py`, `test_qwen.py`, `test_postprocess.py`;
`ARTGEN_TEST_MODELS=1 .venv/bin/python test_backends.py` loads Z-Image.

## Project profile

The project's art constants (outline and shadow colours, the 64x128 reference geometry, the realistic sheet cell 96x192 with
feet row 157, the sheet style words, the bench reference sheet) live in `profiles/life-game.json`, read by `artprofile.py` and
used by `postprocess.py`, `sheet` and `bench.py`. Select another profile with env `ARTGEN_PROFILE=<name or path.json>`. Life Game
is the only profile; the project conventions are in the `life-game-art` skill.

## Memory and timing (24 GB Mac)

**Run one model process at a time**: a second heavy process pushes the machine into swap.

| Step | Cost |
|---|---|
| Qwen generate 1024², 8 steps | 55-95 s, peak 10-13 GB MPS |
| Qwen sprite sheet 1920x768 + 3 refs @768 | ~160-185 s, peak ~15 GB MPS |
| Qwen text encode (Qwen3-VL 8B bf16, CPU, 17.5 GB) | ~20 s text only; ~3 min with 3 refs @512; ~5 min with 1 ref @1024; ~8.5 min with 2 refs + strip @768 |
| Qwen transformer load | 8-13 s |

Why it fits, and the Mac workarounds the backend applies:

- **Encoder in a separate process** (`backends/qwen_encode.py`, stdout routed to stderr). The 17.5 GB encoder and the
  transformer are never resident together; `generate` encodes first, and drops the transformer before encoding on a miss.
- **Encoding cache** (`~/.cache/artgen/enc/qwen21/`, key = prompt + resized reference pixels + `ref_res` + encoder repo and
  revision). Extra seeds and repeated runs skip the encode entirely. `artgen.py cache --stats` / `--prune`.
- **GGUF fix** (`_gguf.py`): diffusers leaves 65 non-Linear GGUF params (`txt_in.text_norm`, attention `norm_q/norm_k`) as raw
  bytes, which fails at the first forward; they are dequantised after loading (count in the sidecar as `gguf_fixed`).
- **Tiled VAE always** (an untiled 1024 px decode peaks at 28 GB); **bf16 VAE when references are passed**, fp32 otherwise.
- MPS is not bit-exact across runs of different machines/versions; on this Mac, same-input reruns were identical.
- FLUX klein and Z-Image notes are at the end of this file.

## Commands

All commands run with `tools/artgen/.venv/bin/python artgen.py ...` from `tools/artgen`.

Each backend declares capabilities (`BackendInfo.caps`, printed by `artgen.py backends`); a command a backend lacks fails
with a message naming the backends that support it (a backend never silently ignores references).

| Command | `qwen_image21` | `flux2_klein_pixel_lora` | `z_image_turbo` |
|---|---|---|---|
| `generate` (text to image) | yes | yes | yes |
| `generate --ref` (refs) | yes (Picture 1, 2, ...) | yes (FLUX multi-reference, untested for composition) | no |
| `generate --opt rgba=1` (real alpha) | yes, the only one | no (painted background, removed in `post`) | no (same) |
| `edit`, `sheet` | yes | no | no |
| `refine`, `inpaint` (scenekit map tiles) | no | yes | no |
| `--opt runner=remote:NAME` | yes | no | no |

```sh
artgen.py backends                                  # registered backends

# generate: --prompt is the subject; the backend wraps it in its template (--raw-prompt sends it verbatim).
# qwen_image21 defaults to 1024x1024 (others 512x512); image i uses seed+i. --json prints {ok, files, seeds, stats}.
artgen.py generate --backend qwen_image21 --prompt "a modern grey three-seat sofa, top-down 3/4 view" \
    --seed 11 --n 2 --out out/sofa --name sofa --json
#   --opt rgba=1                 trained RGBA wording: transparent background (alpha 1-9, post makes it 0)
#   --opt background="..."      template background (default "plain flat white background")
#   --opt sigmas=[...]           override the Turbo 8-step schedule      --opt variant=turbo|base
#   --opt runner=local|remote:NAME   run locally (default) or on a remote host (below)
# references: --ref A B C = Picture 1, 2, 3. With refs the prompt is sent VERBATIM (no sprite template).
artgen.py generate --backend qwen_image21 --ref room.png man.png woman.png --opt ref_res=512 --seed 11 \
    --width 1024 --height 1024 --prompt "Picture 1 is an empty room. ... Keep the room unchanged." --out out/scene --name scene

# edit: source = Picture 1, extra --ref = Picture 2.. ; output size = source size; --ref-res (default 1024) is one value for all.
artgen.py edit --image front.png --prompt "Picture 1 shows a man from the front. Draw the same man from behind ..." --seed 11 --out out/e
# local fix: --mark draws a red circle on the source (the model sees it); --mask pastes ONLY the masked area back (feathered)
artgen.py edit --image in.png --mark 508,338,42 --mask mask.png --feather 8 --prompt "..." --seed 11 --out out/fix --name fix
#   -> fix_s11.png (pasted), fix_s11_raw.png (unpasted edit), sidecar with drift_outside_mask / drift_outside_reach (must be 0) and mask sha

# sheet: one generation for a whole animation from character refs + a pose-skeleton strip (added last as the final Picture).
artgen.py sheet --ref front.png side.png --poses walk_side --frames 5 --cell 384x768 --ref-res 768 --seed 11 \
    --subject "a young adult man, olive hoodie, dark jeans" --slice --out out/walk --name walk
#   --prompt/--prompt-file gives the full prompt verbatim. --slice writes walk_f{i}.png, walk_f{i}_px.png, walk_px_row.png, walk.gif;
#   all frames share ONE pixel size (--grid N, else fitted on frame 0). --post-cell 96x192 --feet-row 157 are the defaults.

artgen.py pose --preset walk_side_0 --size 384x768 --out pose.png     # preview a skeleton (presets: stand_front, stand_side, sit_front, ...)
artgen.py cache --stats                              # encoding cache size;  --prune --older-than 30 [--max-gb 20]
```

### Post-processing commands

```sh
# character into a 96x192 cell, feet on row 157, drop shadow. Fix N (raw px per art pixel) ONCE per character from a
# standing front view and reuse it for every pose; `--grid fit` is only for a first look (it re-scales every image).
artgen.py post out/man/*.png --grid N --cell 96x192 --feet-row 157 --shadow --outline inner --colours 24 --keep-largest --out out/man_px
# older 64x128 characters: --grid fit --cell 64x128 --feet-row 105
# props / portraits: native grid detection, no cell
artgen.py post out/sofa/*.png --grid auto --colours 16 --outline inner --out out/sofa_px
# tiles (still weak for every model): native grid, 16x16 centre crop
artgen.py post out/floor/*.png --tile --cell 16x16 --colours 8 --out out/floor_px
# fixed palette
artgen.py post IN.png --grid auto --palette palettes/player_ref.hex --out OUT;  artgen.py palette-from SOME.png --out palettes/new.hex
```

### refine, mask, inpaint, snap

`refine` runs an existing image through FLUX klein's inpaint (img2img). `--strength` is the share that gets repainted
(0.3 keeps layout and faces, 0.75 repaints most). With `--mask` white = repaint.

```sh
artgen.py refine --image scene.png --mask mask.png --prompt "..." --strength 0.3 0.45 --seed 11 --out out/refine --name scene
# mask helper: white = repaint. Boxes are x0,y0,x1,y1 (px; --units frac for 0..1); no segmentation model.
artgen.py mask --image scene.png --ellipse 448,300,568,440 --feather 3 --preview mask_check.png --out mask.png
artgen.py mask --size 1024x768 --rect 0,300,1024,768 --keep-ellipse 100,300,200,400 --out m2.png
```

For local fixes with Qwen prefer `edit --mark ... --mask ...` (instruction-driven, exact paste-back).

### Remote runner

`--opt runner=remote:<name>` (generate, edit, sheet) pipes a JobSpec JSON to the command in `ARTGEN_REMOTE_<NAME>_CMD`
(shell words, e.g. `ssh gpu 'artgen-worker'`) and reads a JSON list of `{png_base64, meta}` from its stdout. No host is
bundled: without the variable the command fails with "no remote host configured". The `base` variant (40 steps, true_cfg
4.0, negative prompt) runs remote only: `--opt variant=base` with the local runner fails.

## What was removed

The SDXL stack (the `sdxl` backend with LoRAs, IP-Adapter and OpenPose ControlNet, `cast`, `compose.py`, `train/` and the
SDXL part of `refine`) was deleted by the OpenSpec change `artgen-qwen-image` (user decision, 2026-10-16). Qwen-Image 2.1
covers what it was used for: reference images keep a character's identity instead of a trained LoRA, instruction `edit`
replaces masked LoRA repaints, and the skeleton strip of `sheet` replaces ControlNet pose. LoRA weights in
`~/.cache/artgen/loras/` were left on disk. The evaluation that led here is in `out/eval_2026-10/results.md` (git-ignored,
local only).

## Post-processing stages (`postprocess.py`)

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

`prompts/bench.yaml` fixes the items, seeds (11, 42) and size (512²; `sizes:` in the yaml overrides it per backend, `qwen_image21` runs at 1024²). Items with `ref:` pass the referenced raw image as `--ref` (qwen_image21 then sends the subject verbatim):

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

The stub's docstring sketches Replicate and PixelLab. Remote backends read API keys from the environment and must never
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

## Z-Image backend

Built from `z_image_turbo_bf16.safetensors`, `qwen_3_4b.safetensors` and `ae.safetensors` plus a few kB of
config JSON from `Tongyi-MAI/Z-Image-Turbo`. 8 steps, guidance 0 (negative prompts ignored). Natural-language prompts only, no tags, no
LoRA support yet. The text encoder (8 GB) and the transformer (12 GB) are never in memory together: a prompt is encoded first, the
encoder is dropped, then the transformer loads to MPS (12 s). Peak about 18 GB on MPS, so close other heavy apps.
`--opt style="anime style pixel art. "` is prepended to the prompt; `--opt background=...` is appended.

```sh
.venv/bin/python artgen.py generate --backend z_image_turbo --width 768 --height 1152 --seed 11 \
    --opt style="detailed hi-res pixel art, limited palette. " --prompt "a young man in a grey hoodie, front view, full body" --out out/z
```


