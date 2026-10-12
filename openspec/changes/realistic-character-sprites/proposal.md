## Why

The user decided (2026-10-12) that Life Game's characters move from the chibi style to **realistic proportions** (about 7 heads tall), generated with `tools/artgen` (a reference front view, the other views with FLUX klein, then `artgen.py post` into cells). The user also decided that the sprites get **bigger so faces stay readable**, and that **"the rooms and furniture shall be adjusted to the new more detailed characters, not the other way around"**. In the current 64x128 cell a realistic figure is about 89 rows tall, so the head gets about 12 rows and the eyes 1–2 px (`tools/artgen/out/sam_art/stills_contact.png`).

The generator decides how much detail is possible. On the reference fronts, SDXL with `pixel_art_xl` at 768x1152 draws on a native pseudo-pixel grid of about 8.0 raw px, and a full-body figure is about 1040 raw px tall. One output pixel per model pixel gives a figure of about 130 rows.

## What Changes

- **New sheet format for realistic characters**: 96x192 cells, 10 columns x 12 rows (960x2304), the same row layout and frame ranges as `CHARACTER_CLIPS`, feet on row 157. A man is 132 rows tall and a woman about 126, and the head gets about 19 rows.
- **Drawn at scale 1.0 in the texel-unit world** of change `world-texel-scale`: one world px is one art pixel, for tiles and characters alike. The world is rebuilt around the characters (48 px tiles, a door 3 tiles = 144 px tall). This change depends on that one.
- **Feet collider in world units** through one helper (radius 24, centre 48 px below the sprite centre in the new world units), because Rapier scales a child collider by its parent's scale.
- **Player and Samantha** switch to the new sheets when the art arrives. Until then the old 64x128 sheets are drawn at scale 1.5 (same footprint, chunkier pixels) so the world change can land first.
- **The wanderer** keeps her 64x128 sheet at scale 1.5 until she gets realistic art. She isn't on any current map.
- **Art tooling**: `artgen.py post --shadow` scales the drop shadow with the cell, and character frames are posted with a fixed `--grid` pixel size per character instead of `--grid fit`.
- **Portraits** stay 64x64 (shown at 128x128).

## Capabilities

### New Capabilities
- `characters/sprite-format`: the realistic character sheet format, its anchor and the world-unit feet collider.

### Modified Capabilities
- `characters/player` (from the unarchived `male-player-wandering-npc`): the male player sprite uses the realistic format.
- `characters/samantha` (from the unarchived `opening-viewing`): her sheet uses the realistic format.

Archive order: after `male-player-wandering-npc`, `opening-viewing` and `world-texel-scale`.

## Non-Goals

- New animation clips, frame counts or a second clip table. The 10x12 layout and `CHARACTER_CLIPS` stay.
- Realistic art for the wanderer or the retired forest NPCs.
- The world scale, tiles, camera and maps: all in `world-texel-scale`.

## Impact

- **Assets**: `assets/library/characters/player/player.png` and `assets/library/characters/samantha/samantha.png` are replaced by 960x2304 sheets; `LIBRARY.md` rows. Portraits unchanged.
- **Code**: `src/character.rs` (created by `world-texel-scale`), `src/assets.rs`, `src/player/spawn.rs`, `src/npc/spawn.rs`.
- **Tools**: `tools/artgen/postprocess.py` (shadow and the fit reference rows per cell), `tools/artgen/README.md`.
- **Web build**: nothing wasm-sensitive. A 960x2304 RGBA texture is far below WebGPU's 8192 px limit (about 8.8 MB of GPU memory per sheet).
