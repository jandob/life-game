## Why

The October 2026 model evaluation (`tools/artgen/out/eval_2026-10/results.md`, git-ignored) settled the art pipeline. **Qwen-Image 2.1 Turbo** (stock weights, Q8_0 GGUF, diffusers) runs on the 24 GB Mac at ~1-1.5 min per 1024 px image and is the only tested model that does everything the game needs from one set of weights:

- real transparent (RGBA) output;
- reference edits that keep identity (front view -> back view, outfit changes, local fixes);
- multi-reference scene composition (room + player + Samantha placed on the sofa, room unchanged), including adult content;
- animation as one sprite-sheet image with a skeleton strip as reference (loose but usable pose control).

FLUX.2 klein (4B/9B, any text encoder), Qwen 2.1 "Uncensored", abliterated text encoders, Krea 2 and Qwen-Image-Edit 2511 were ruled out for composition/editing. The SDXL stack (WAI/Illustrious + character LoRAs, IP-Adapter, OpenPose ControlNet, `cast` recipes, `compose.py` two-stage scenes, LoRA training) is superseded.

**Decisions (user, 2026-10-15):**
- Initial character/furniture generation backends: `z_image_turbo`, `flux2_klein_pixel_lora`, and the new `qwen_image21`.
- Composition, editing, animation sheets, NSFW transforms and character variants: `qwen_image21` with the Turbo model locally. Qwen-Image 2.1 non-turbo (40 steps) is a future **remote** run option; no host is chosen yet, so only the interface is built.
- Encoding cache: keep only the exact cache (prompt + reference pixels) so extra seeds are cheap. No prefix/KV cache, no int8 encoder on MPS.
- Pose control: skeleton strip as a single reference in one sprite-sheet image. No ControlNet port.
- **Delete** the SDXL stack (`backends/sdxl.py`, IP-Adapter/ControlNet registry entries, `cast.py`, `train/`), `compose.py`, and the unused `--opt text_encoder` experiment.

## What Changes

- New backend `qwen_image21` (Turbo profile local; base profile behind a runner interface) with the Mac workarounds from the eval: GGUF norm dequantisation, VAE tiling, bf16 VAE with references, text encoder in a CPU subprocess with an on-disk encoding cache.
- `generate --ref A B C` drives multi-reference composition (no new command); new opt-in `--json` output.
- New `edit` command: instruction edit of one image, optional extra references, optional `--mark` circle and `--mask` paste-back so only the fixed region changes.
- New `sheet` command: builds a skeleton strip from `pose.py` presets, generates one sprite-sheet image, optionally slices it into cells and runs the post-processor.
- `JobSpec` + `Runner` protocol (local runner now, remote stub) for the future base-model cloud runs.
- `cache` command (`--stats`, `--prune`).
- Removed: `sdxl` backend, `refine`'s SDXL path, `cast`, `compose.py`, `train/`, SDXL entries in `models.json`; `refine` keeps working with `flux2_klein_pixel_lora` (its default changes from `sdxl`).
- Agent skill `artgen` (`.claude/skills/artgen/SKILL.md`, mirrored to `.pi/skills/` and `.github/skills/`): which backend per stage, copy-paste recipes, prompt patterns and operating rules, so agents can use the tool without reading its source.
- Docs: README/STYLES rewritten around the three backends and the stage-by-stage pipeline; diffusers pinned to a commit.

## Capabilities

### New Capabilities
- `tooling/artgen-qwen`: Qwen-Image 2.1 backend, reference composition, `edit` with paste-back, `sheet`, encoding cache, runner interface.

### Modified Capabilities
- `tooling/character-refine`: cast recipes removed with the SDXL stack.

## Impact

`tools/artgen/` (new backend and commands, deletions), `tools/sprite_gen/realistic/jobs/` (the SDXL job script becomes historical, kept as a record), `openspec/changes/character-refine/`. No game code. `tools/scenekit` keeps working unchanged (it uses only `inpaint` and `snap`, which stay byte-compatible). New downloads: none beyond the eval (Qwen GGUF, text encoder, VAE already in the HF cache).
