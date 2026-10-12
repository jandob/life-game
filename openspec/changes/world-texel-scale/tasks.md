## 0. Decisions (user)

- [x] 0.1 Tile size (design D2): 48 px (default), or 32 px
- [x] 0.2 Camera (design D3): C1 integer scaling with about 540 px visible (default; 19 px faces in a DPR 1 1280x720 window, 38 in 1080p fullscreen), or C2 a fixed 480 px view (same framing everywhere, uneven pixels at 720p and 1080p). See `renders/framing_options_720p.png`
- [x] 0.3 Confirm that `route1_flat.tmj` is rebuilt in place at 48 px (the 16 px version stays in git history)

Decided by the user, 2026-10-12: 48 px tiles, C1 integer scaling, route1_flat rebuilt in place.

## 1. Tooling (scene-designer or tooling engineer; design D6)

- [ ] 1.1 `tools/scenekit/common.py`: tile size from the library manifest (`tile_size`) instead of `TILE = 16`; compose, render, slicing and collision checks use it; the existing 16 px library keeps working (its tests stay green)
- [ ] 1.2 New library `assets/library/tilesets/gen48/` (768x768 pages, `.tsj` with 48 px tiles); `validate` rejects maps that mix tile sizes
- [ ] 1.3 Generation recipes: tileable 48/96 px floor and wall textures and per-prop generation at the D6 sizes with a fixed `--grid`, the characters' style suffix and a shared palette; at most about 128x128 art px per generation
- [ ] 1.4 `tools/scenekit/README.md` and `.claude/agents/scene-designer.md`: 48 px tiles, 74 art px per metre, the size table, the new path and clearance numbers (D7)

## 2. Map (scene-designer; design D6 and D7)

- [ ] 2.1 Generate the `gen48` tiles and props for the landing, 3B (main room, kitchen, window) and both doors; door leaves on their own tile layers as before
- [ ] 2.2 Rebuild `assets/maps/route1_flat.tmj` at 48 px with realistic sizes and the same layer, object and path names
- [ ] 2.3 Re-author every `Paths` polyline at the feet: segments at least 24 px clear of colliders, end points of two actors in one room at least 72 px apart; `Doors` and `Interact` rectangles at the new doorways; `SpawnPoint` and `Samantha` at sprite centres
- [ ] 2.4 `validate`, `render --check-tmx` and `library check` pass; opens in Tiled 1.12; deliver a render with the collision overlay and object layers, plus a 1x frame at 540 px visible with both characters composited (`renders/mock_framing.py`)

## 3. Code (gameplay-engineer; lands with section 2)

- [x] 3.1 `TiledMap::tile_size` from the `.tmj`; loader error on a tileset with another tile size; remove `TILE_SIZE`; use the map value in `tiled_to_game`, `chunk_manager.rs`, `collision.rs` and `wander.rs` (design D4); a unit test with an inline 48 px map
- [x] 3.2 New `src/character.rs` (module in `src/main.rs`) with `FEET_RADIUS`, `FEET_BELOW_CENTRE`, `SheetFormat`, `LEGACY` (1.5), `feet_collider()` and `transform()`; the player, Samantha and the wanderer use `LEGACY` (design D5)
- [x] 3.3 Every constant in the design D5 table (speeds, distances, hint offsets and sizes, shake, `FEET_TO_TRANSFORM` → `FEET_BELOW_CENTRE`); update the `TiledMap::path` tests to the +48 offset
- [x] 3.4 `src/world/camera.rs`: per 0.2, C1 (`ScalingMode::WindowSize`, `ortho.scale = scale_factor / t × debug_zoom`, `t = max(1, round(physical_height / 540))`, recomputed on window or scale-factor changes) or C2 (`FixedVertical { viewport_height: 480 }`); `zoom_camera` changes the separate debug factor
- [x] 3.5 `cargo check`, `cargo check --target wasm32-unknown-unknown`, `cargo test`, `cargo clippy` clean for the touched files

## 4. Verification (lead)

- [ ] 4.1 Native, 1280x720 window: tile and character pixels the same size and even; the room framed with little scrolling; fullscreen (1080p) → 2x2 screen px per art px
- [ ] 4.2 Movement feels as before relative to the characters (walk, run, scripted walks); start hint above Samantha's head; camera shake magnitude
- [ ] 4.3 F3 overlay (looking only): feet colliders under the (legacy, scale 1.5) sprites, tile colliders on the new art; then F3 off: walls and the closed 3B door block the player
- [ ] 4.4 The full viewing scene (opening-viewing 9.3–9.7) on the rebuilt map
- [ ] 4.5 A 16 px fixture map (`enginetest.tmj`) still loads without errors
- [ ] 4.6 Wasm build via the `push_to_itch.sh` steps without publishing; in a WebGPU browser at DPR 1 and 2 the pixels are whole multiples; no console errors
