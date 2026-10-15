> **Note (2026-10-16):** `artgen cast`, `cast.py`, `compose.py` and the SDXL backend were removed by change `artgen-qwen-image`. Identity now comes from reference images (`generate --ref`, `edit`, `sheet` with `qwen_image21`). This proposal is kept as a record.

## Why

The user's experiments (2026-10-12) settled the character pipeline: generate scenes (clothed or explicit) with SDXL/WAI + `pixel_art_xl`, then bring each character's identity back by repainting their head and/or body with that character's LoRA (e.g. `lgwoman1`) through agent-made masks. Generating with the character LoRA directly fights multi-person scenes (it was trained on one woman alone) and drifts poses toward the dataset.

`artgen refine` can already do masked inpainting with LoRAs, but every character needs a hand-chained command.

**Decision (user):** no crop-and-upscale ("only masked") refine. Repainting a crop at a different scale loses scene context and breaks the consistent pixel grid across the image, so every region is repainted at full image resolution with the whole image as context.

## What Changes

- `artgen.py cast RECIPE.json`: one image, a list of regions applied in order; each region has a mask (file or `mask` boxes), prompt, LoRAs, strength and seed. Writes the final image plus each intermediate step and a JSON log, so a result is reproducible.
- Docs: the pipeline in `tools/artgen/STYLES.md` (generate -> masks -> cast), with recommended strengths (head ~0.4-0.55, full body ~0.6-0.75) and LoRA scales.
- Masks remain agent-made (`artgen.py mask` boxes/ellipses chosen by looking at the image). No detector model is added now.

## Capabilities

### New Capabilities
- `tooling/character-refine`: multi-region cast recipes (full-resolution masked refine per character).

## Impact

`tools/artgen/` only (artgen.py, backends/sdxl.py, a new cast module, README/STYLES). No game code, no new downloads.
