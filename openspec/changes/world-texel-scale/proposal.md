## Why

The user decided (2026-10-12) that the characters become realistic and more detailed (change `realistic-character-sprites`: 96x192 cells, a man 132 art px tall), and that **"the rooms and furniture shall be adjusted to the new more detailed characters, not the other way around"**. The user also wants the pixel size to be consistent across the image. Today the tiles have 1 art pixel per world px and the characters 2, at about 23 art px per metre for the tiles, while the realistic characters are drawn at about 74 art px per metre. Upscaling today's tiles would give tile pixels three times the size of character pixels, so the world has to be redrawn at the characters' density.

## What Changes

- **World unit = one art pixel** for tiles, props and characters. Every world-space constant (collider, offsets, speeds, distances) is multiplied by 3, so gameplay feels the same relative to the characters.
- **48 px tiles** *(user decision; default)* drawn at the characters' density (one tile is about 0.65 m, close to today's 0.7 m grain). The engine reads the tile size from the map instead of the `TILE_SIZE = 16` constant, so the old 16 px maps still load as engine fixtures.
- **Camera with integer pixel scaling** *(user decision; default)*: each art pixel covers a whole number of physical screen pixels (1, 2, 3 or 4), chosen from the window height so that about 540 art px are visible. Faces get 38 screen px at 1080p and 57 physical px on a HiDPI 1280x720 window.
- **`route1_flat.tmj` is rebuilt** at 48 px with realistic proportions: the door leaf 3 tiles (144 px) tall, walls about 4 tiles high, furniture at real sizes. The object and path names stay the same, so `route1_viewing.yarn` doesn't change.
- **scenekit gets a 48 px tile library**, and generation works per object or texture (at most about 128x128 art px per generation), because the generator's pixel grid (about 8 raw px) caps how much area one image can cover at this density.
- **In-world markers** (start hints, keyboard hints) are drawn at scale 3 until they are redrawn at 48 px density (the one accepted density mismatch).

## Capabilities

### New Capabilities
- `world/scale`: the world unit, per-map tile size, and integer camera scaling.

### Modified Capabilities
- None as requirements. The `world/map` conventions (sprite centres for `SpawnPoint` and `NPCs`, feet for `Paths`) keep their meaning; only their pixel values scale (design D7).

Archive order: after `opening-viewing`; before `realistic-character-sprites`.

## Non-Goals

- Realistic character art (`realistic-character-sprites`).
- Rebuilding the forest, apartment demo or enginetest maps; they keep 16 px tiles and stay loadable as fixtures.
- Per-map camera zoom, camera clamping, pixel-snapping sprites to the screen grid.
- Free-placed furniture objects (props stay tile layers).

## Impact

- **Assets**: a new 48 px tile library under `assets/library/tilesets/`; `assets/maps/route1_flat.tmj` rebuilt; start-hint and keyboard-hint art unchanged for now.
- **Code**: `src/world/map/{mod,tiled_map,chunk_manager,collision}.rs`, `src/world/camera.rs`, `src/world/camera_shake.rs`, new `src/character.rs`, `src/player/{mod,spawn}.rs`, `src/npc/{spawn,wander}.rs`, `src/story/scripted.rs`, `src/ui/dialogue/start_hint.rs`, `src/ui/keyboard_hint.rs`.
- **Tools**: `tools/scenekit` (tile size per library), its generation prompts and recipes; `.claude/agents/scene-designer.md`.
- **Web build**: nothing wasm-sensitive. The camera reads the physical window height, which on wasm includes `devicePixelRatio`; the itch embed must stay 1280x720 or larger.
