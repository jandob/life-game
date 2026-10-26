## 1. Decisions (user)

- [x] 1.1 128x256 cells, per-clip strips per look, manifest files, no vertical walks, walk drawn once and mirrored (2026-10-26)
- [x] 1.2 Player 5, Samantha 1 and 2 are the first looks; backpack dropped

## 2. Art (pixel-artist)

- [x] 2.1 Key frames: front, side idle, back idle, walk contact and passing for player 5 (no bag), Sam 1, Sam 2 (`tools/artgen/out/side_views/`)
- [x] 2.2 Second walk half (contact B, passing B) for all three
- [x] 2.3 Measure N per character, post-process into 128x256 cells, build `idle.png` and `walk.png` per look plus `look.ron`
- [ ] 2.4 Look at the strips and the walk GIF; pick takes with the user

## 3. Tools

- [x] 3.1 Strip builder in `tools/sprite_gen` (cell 128x256, fixed feet row, mirrored left idle)
- [ ] 3.2 Update `art/artgen-profile.json` and the life-game-art skill with the new cell, feet row and looks layout

## 4. Game code (gameplay-engineer, after architect sign-off)

- [x] 4.1 `Look` manifest asset and loader; per-look clip table and fallback in `character_clip`
- [x] 4.2 Walk mirroring via `flip_x`, state reset on look or clip change, vertical movement plays walk
- [x] 4.3 Collider offset from the new cell; `cargo check` native and wasm
- [ ] 4.4 Switch the player and Samantha to their looks; run the game (code done, not yet run in a game session)
