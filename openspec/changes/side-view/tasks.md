## 1. Stage 1: one side-on room

- [x] 1.1 Tiled loader: map property `view`, image layers, maps without tilesets
- [x] 1.2 `maps/side/flat3a.tmj` and its placeholder background (`tools/mapgen/side_placeholder_3a.py`)
- [x] 1.3 `src/world/side_view.rs`: floor line, hotspots, click-to-walk, hover label and cursor, camera clamp
- [x] 1.4 Keyboard movement, E-to-talk and the movement key hints off in the side view
- [x] 1.5 `--view side` / `?view=side` launch option
- [x] 1.6 `cargo test`, `cargo clippy`, `cargo fmt --check`, `cargo check --target wasm32-unknown-unknown`
- [x] 1.7 Play it natively (Xvfb, lavapipe): walk, run, hover, use each hotspot; screenshots
- [ ] 1.8 Janosch plays it and judges the feel and pixel scale

## 2. Rooms and floors

- [ ] 2.1 Building floors and the shop as Tiled maps; stair, lift and door teleports with a fade
- [ ] 2.2 `room` command; start points name a room and a spawn
- [ ] 2.3 Port and replay the viewing and move-in

## 3. Art

- [ ] 3.1 Painted backgrounds per room (artgen), door and prop sprites
- [ ] 3.2 Side-only sheets for the player and Samantha

## 4. Remaining scenes

- [ ] 4.1 Port croissant, dinner and second Thursday; replay every start point

## 5. Switch over

- [ ] 5.1 Side view by default; remove y-sort, keyboard movement, tile chunks, rapier for characters, the forest map, wanderer and flora code
