## Context

Prototype: `tools/artgen/out/eval_2026-10/qwen_eval.py` (+ `gguf_te.py`), git-ignored. It loads `QwenImage21Pipeline` (diffusers dev, venv at commit `85c9fa4`) with the transformer from `abenzerps/Qwen-Image-2.1-Turbo-Quantized` Q8_0 GGUF and configs, VAE, processor and text encoder from `Qwen/Qwen-Image-2.1-Turbo`.

Measured on the 24 GB Mac:

| Step | Cost |
|---|---|
| Text encode (Qwen3-VL 8B bf16, CPU) | ~20 s text only; ~3 min with 3 refs at 512 px; ~5-6 min with one 1024 px ref |
| Generate 1024 px, 8 steps | 55-90 s, 11-13 GB MPS |
| Generate 1920x768 sprite sheet | ~165 s |

Encode time is dominated by the language model reading image tokens (a 512 px ref is ~256 tokens).

**Consumers that must keep working:**
- `tools/scenekit/gencmds.py` runs `artgen.py inpaint` (default backend `flux2_klein_pixel_lora`, `--name raw` -> `raw-{i}.png`, last stdout line JSON with `prompt`, `stats`, `gen_opts`) and `artgen.py snap` (`results[].out`, `report`).
- `tools/sprite_gen/realistic/flux_batch.py` imports `artgen.generate_images`, `get_backend` and `postprocess.run_pipeline` / `shadow_layer` / `save_palette_hex`.

## Goals / Non-Goals

**Goals:**
- One Qwen backend inside the existing `Backend` framework.
- Composition, edit and sprite-sheet workflows as CLI commands with reproducible JSON sidecars.
- Memory-safe sequencing on 24 GB.
- A runner seam for future remote base-model runs.
- Removal of the SDXL stack.

**Non-Goals:**
- Prefix/KV encode caching or an int8 MPS encoder.
- A Qwen ControlNet port.
- Choosing a cloud host.
- Fixing tile generation (still weak for every model).
- Art polish.

## Decisions

### D1: Module layout

- `backends/qwen_image21.py`: `QwenImage21(Backend)`. Variant profiles: `turbo` (8 steps, saved sigmas, cfg 1) and `base` (40 steps, true_cfg > 1 with a negative prompt; remote only for now).
- `backends/qwen_encode.py`: encoder worker, `python -m backends.qwen_encode JOBFILE`. It reads `[{prompt, ref_paths, ref_res}]`, fills the cache and exits. Its stdout goes to stderr so callers that parse stdout stay clean.
- `backends/_enc_cache.py`: cache in `~/.cache/artgen/enc/qwen21/`. Key = sha256 of the prompt, the **resized** condition pixels, `ref_res`, the encoder repo + revision, and a preprocessing version string. Stored with `torch.save`, loaded with `weights_only=True`.
- `backends/_gguf.py`: idempotent dequantisation of GGUF params that live in non-Linear modules (diffusers bug). Returns the fixed count for the sidecar.
- `maskkit.paste_back(orig, edited, mask, feather)`: resize the edit to the original size, then composite through a feathered mask.
- `pose.strip(poses, cell, frames)`: a row of skeletons.
- `runner.py`: `JobSpec` (kind, variant, prompt, refs as bytes + sha, seed, n, size, steps/sigmas, cfg) and a `Runner` protocol (`submit`, `fetch`). `LocalRunner` now; a `RemoteRunner` stub that a fake subprocess can satisfy in tests.

### D2: Fitting the Backend interface

- `load()` is light: scheduler, processor, VAE.
- `precompute(prompts, refs)` encodes every uncached key in one subprocess.
- `generate()` calls `_ensure_encoded()` before it loads the transformer. On a cache miss with the transformer resident it drops the transformer first (as `z_image_turbo` does): encoder and transformer together would swap.
- Generation is one call per seed, so image i is reproducible from seed + i.
- VAE: tiled always; bf16 when references are passed, fp32 otherwise.
- The embeddings reach the pipeline by replacing `encode_prompt`. A load-time check asserts its signature and 3-tuple return, so a diffusers change fails loudly instead of silently.
- Qwen gets no `inpaint()`: it has no masked denoising, and scenekit's inpaint path expects mask-aware output.

### D3: Commands

| Need | Command |
|---|---|
| New character / prop / room | `generate --backend qwen_image21` (or `z_image_turbo`, `flux2_klein_pixel_lora`) |
| Transparent output | `generate ... --opt rgba=1` (adds the trained RGBA wording) |
| Scene composition | `generate --backend qwen_image21 --ref ROOM CHAR1 CHAR2 --prompt "...Picture 1/2/3..."` |
| Turnaround, outfit change, NSFW transform, portrait from a character | `edit --image SRC --prompt ... [--ref EXTRA...]` |
| Local fix | `edit --image SRC --prompt ... --mark x,y,r` and/or `--mask M --feather F` (paste-back) |
| Walk / animation sheet | `sheet --ref FRONT SIDE --poses walk_side --frames 5 --cell 384x768 [--slice --post-cell 96x192 --grid N]` |
| Cache housekeeping | `cache --stats` / `cache --prune [--older-than D]` |

- `edit` defaults: output size = source size; one `--ref-res` for the source and all extra refs, default 1024 (the pipeline resizes every condition image with a single `output_resolution`; 512 loses detail of the source). The generated size is the source size rounded to a multiple of 32, resized back to the exact source size.
- With `--mask`, the sidecar records the mean drift outside the mask (must be 0) and the mask sha.
- `edit` and `sheet` print one JSON object (`ok`, `files`, `seeds`, `stats`).
- `generate` stays path-printing; `--json` is opt-in because the sprite_gen shell jobs parse paths.

### D4: Removals

Delete:
- `backends/sdxl.py`, `cast.py`, `compose.py`, `train/`, `examples/cast_recipe.json`;
- the SDXL/LoRA/IP-Adapter/ControlNet sections of `models.json` (keep `z_image_turbo`, add `qwen_image21`);
- the `cast` CLI and the SDXL path of `refine`.

`refine` keeps the FLUX klein path, and its default backend becomes `flux2_klein_pixel_lora`. `mask` and `pose` stay: they now feed `edit` and `sheet`.

The LoRA weights in `~/.cache/artgen/loras/` are left on disk (not in git) for the user to delete. `tools/sprite_gen/realistic/jobs/01_fronts_sdxl.sh` stays as a historical record of how Samantha's first front was made, with a header note that it no longer runs.

### D5: Reproducibility

The sidecar records:
- GGUF repo, file and sha256;
- diffusers commit;
- variant, sigmas, steps and cfg;
- VAE tiling and dtype;
- reference shas and `ref_res`;
- the encode cache key;
- the mark, mask sha and feather;
- the gguf-fixed parameter count;
- timings and peak memory.

MPS is not bit-exact, so tests compare with a tolerance ("near-identical"), not equality.

### D6: Agent skill

An `artgen` skill teaches agents to use the tool without reading its source.

- **Locations:** the canonical copy is `.claude/skills/artgen/SKILL.md` (Claude Code). Byte-identical copies go to `.pi/skills/artgen/SKILL.md` and `.github/skills/artgen/SKILL.md`, the same layout as the OpenSpec skills. A test fails if the copies drift.
- **Frontmatter:**
  - `name: artgen`
  - a `description` that triggers on generating, editing, composing or animating game art, sprites, portraits, props or scenes, and on post-processing them into pixel art.
- **Body, task-oriented:**
  1. Setup check: venv, models in the HF cache, `artgen.py backends`.
  2. Which backend for which stage: initial generation with `z_image_turbo`, `flux2_klein_pixel_lora` or `qwen_image21`; composition, edit, sheet and transforms with `qwen_image21`.
  3. One recipe per task (character, transparent prop, scene composition, turnaround, local fix with mark + mask, walk sheet), each with a copy-paste command and the post-processing settings (`--grid N --cell 96x192 --feet-row 157 ...`).
  4. Prompt patterns that worked in the eval:
     - "Picture 1/2/3" naming;
     - explicit placement ("on the sofa cushions, not on the rug or coffee table"), scale and "keep the room unchanged";
     - the trained RGBA wording;
     - per-frame pose words plus a skeleton strip.
  5. Operating rules:
     - one model process at a time on the 24 GB Mac;
     - expected run times;
     - reuse references so the encoding cache hits;
     - paste back local fixes;
     - read the sidecar and stats;
     - outputs go to git-ignored `tools/artgen/out/`.
  6. What it can't do: exact pose control, seamless 16 px tiles, bit-exact reruns on MPS.
- **Size:** under ~300 lines. Long references link to README/STYLES rather than copying them.

### D7: Generic tool, project profile and project skill

User decision (2026-10-16): split, but keep it light. Life Game is the only user, and a bigger refactor can come later.

- **Profile.** `tools/artgen/profiles/life-game.json` holds the project's art constants. Today they are hard-coded:
  - outline and shadow colours, the 64x128 reference geometry (feet row 105, top row 17, shadow centre and radii);
  - the realistic sheet cell 96x192 with feet row 157;
  - the default palette;
  - the style suffix used by `sheet`'s generated prompt;
  - the bench reference sheet path.

  `postprocess.py`, `sheet` and `bench.py` read it. It is the default profile, overridable with env `ARTGEN_PROFILE=<name or path>`. Not a plugin system: one JSON file, one loader function, the same defaults as today, so outputs stay identical.
- **`artgen` skill (generic).** Tool usage, backends and capability table, recipes, prompt patterns, operating rules. Project sizes come from "the active profile", and the skill points to `life-game-art` for this project's numbers and conventions.
- **`life-game-art` skill (project).** `.claude/skills/life-game-art/SKILL.md`, with copies in `.pi/` and `.github/`. It covers:
  - the sprite format, with a link to the authoritative OpenSpec spec `realistic-character-sprites/specs/characters/sprite-format`: 96x192 cells, feet row 157, a man 132 rows tall and a woman about 126, sheet layout;
  - the character registry: the canonical reference images for the player and Samantha in `tools/artgen/out/sam_art/keys/` and `assets/library/`, plus their subject descriptions;
  - the style suffix;
  - every character is an adult;
  - art is "good enough", not polished;
  - the output flow: `tools/artgen/out/` → `tools/sprite_gen/realistic/build_sheets.py` → `assets/library/...`;
  - which agent does what: pixel-artist for characters and sprites, scene-designer through scenekit for maps.
- **`.claude/agents/pixel-artist.md`** is updated to use artgen with both skills instead of only hand-written Pillow generators.
- **Test:** the profile's realistic cell and feet row match the sprite-format spec text, and the skill copies are identical.

## Risks / Trade-offs

- **Memory:** any path that encodes while the transformer is resident swaps. Mitigated by D2's sequencing and a peak-memory assertion in the smoke test.
- **diffusers dev API** (`sample_sigmas`, `output_resolution`, `encode_prompt` tuple): pin the commit in README/setup, plus the load-time check from D2.
- **GGUF conversion changes:** the shape error surfaces at the first forward. The sidecar keeps the GGUF sha for diagnosis.
- **Tiling seams** on flat opaque backgrounds. Accepted: art polish is not a goal, and RGBA cut-outs lose them in post.
- **Edits drift the whole image** (~13/255). Paste-back is the documented way to make local fixes.
- **Cache growth:** encodings with refs are large. Mitigated by `cache --prune`.
- **Loss of SDXL features** (character LoRAs, IP-Adapter, ControlNet pose): accepted by the user. Qwen references replace LoRAs for identity; the skeleton strip replaces ControlNet pose.
