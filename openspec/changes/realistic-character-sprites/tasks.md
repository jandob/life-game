## 0. Decisions (user)

- [x] 0.1 Confirm the format (design D1): 96x192 cells at scale 1.0 in the texel-unit world, the man 132 rows and Samantha about 126, about 74 art px per metre. The world side (tiles, camera) is decided in `world-texel-scale` section 0

## 1. Tooling (artgen owner; before section 2)

- [x] 1.1 `tools/artgen/postprocess.py`: scale `SHADOW_CENTRE`, `SHADOW_RADII` and `CHAR_TOP_ROW` by `cell width / 64` and put the shadow centre `3 × k` rows above `feet_row` (96x192, feet 157 → centre (47.5, 152.5), radii 33.75x17.25); 64x128 output stays byte-identical
- [ ] 1.2 Optional: `--grid N` with the detected phase instead of (0, 0)
- [x] 1.3 `tools/artgen/README.md`: the character example uses `--grid N --cell 96x192 --feet-row 157 --shadow` and explains choosing `N` once per character and backend (design D4)

## 2. Art (artgen; design D2 and D4)

- [ ] 2.1 Fix `N` per character and backend + size from a standing front (man 132 rows, Samantha 126); record it in the recipe
- [ ] 2.2 `assets/library/characters/player/player.png`: 960x2304, all 12 rows filled as in design D2 (run rows from walk poses until run art exists)
- [ ] 2.3 `assets/library/characters/samantha/samantha.png`: 960x2304, all 12 rows (rows 0–7 needed by the scene)
- [ ] 2.4 Check every frame: feet on row 157, standing height within ±2 rows, nothing clipped, eyes at least 2 rows on front frames, left and right mirror-consistent
- [ ] 2.5 Contact sheet: every row of both sheets at 3x, plus both characters at 1x in front of the rebuilt 3B door at 1280x720 (`world-texel-scale/renders/mock_framing.py` composites)
- [ ] 2.6 `LIBRARY.md` rows for 2.2 and 2.3 (tool, recipe with `N`, model and LoRA licence)

## 3. Code (gameplay-engineer; after `world-texel-scale` section 3, with the art from section 2)

- [ ] 3.1 `src/character.rs`: add `REALISTIC = SheetFormat { scale: 1.0 }` (96x192 cells)
- [ ] 3.2 Player (with 2.2): `src/assets.rs` `player_layout` → `texture_atlas(tile_size_x = 96, tile_size_y = 192, columns = 10, rows = 12)`; `src/player/spawn.rs` uses `REALISTIC.transform` and `REALISTIC.feet_collider()`
- [ ] 3.3 Samantha (with 2.3): `samantha_layout` → 96x192, 10x12; `src/npc/spawn.rs` uses `REALISTIC`
- [ ] 3.4 `src/assets.rs`: a comment on each character atlas naming its format (`REALISTIC` 96x192 or `LEGACY` 64x128)
- [ ] 3.5 `cargo check`, `cargo check --target wasm32-unknown-unknown`, `cargo test`, `cargo clippy` clean for the touched files

## 4. Verification (lead)

- [ ] 4.1 Native run at the default window: character pixels the same size as tile pixels; faces readable; no uneven pixels while walking
- [ ] 4.2 F3 overlay (looking only): the collider ball sits under the feet for both characters in all four directions; then F3 off: the player is blocked by the closed 3B door and walls
- [ ] 4.3 The full viewing scene: walks end on their path points, nobody walks visibly into walls, YSort against furniture correct
- [ ] 4.4 Wasm build via the `push_to_itch.sh` steps without publishing; the scene in a WebGPU browser; no console errors
