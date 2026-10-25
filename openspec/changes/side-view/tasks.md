## 1. Stage 1: one side-on room

- [x] 1.1 Tiled loader: map property `view`, image layers, maps without tilesets
- [x] 1.2 `maps/side/flat3a.tmj` (replaced by `route1.tmj` in stage 2) and its placeholder background (`tools/mapgen/side_placeholder_3a.py`)
- [x] 1.3 `src/world/side_view.rs`: floor line, hotspots, click-to-walk, hover label and cursor, camera clamp
- [x] 1.4 Keyboard movement, E-to-talk and the movement key hints off in the side view
- [x] 1.5 `--view side` / `?view=side` launch option
- [x] 1.6 `cargo test`, `cargo clippy`, `cargo fmt --check`, `cargo check --target wasm32-unknown-unknown`
- [x] 1.7 Play it natively (Xvfb, lavapipe): walk, run, hover, use each hotspot; screenshots
- [x] 1.8 Janosch plays it and judges the feel and pixel scale

## 2. Rooms and floors

- [x] 2.1 Landing, 3B, 3A and the shop as rooms (`Rooms`, one `Floor` each) of `maps/side/route1.tmj`; doors and stairs as `Portals`; the screen dips to black as the player steps through one
- [x] 2.2 No `room` command needed: start points keep their spawn names, the room is the one the spawn lies in; scripted walks route through portals (`SideRooms::route`)
- [x] 2.3 Replay the viewing, move-in, dinner, shop and second Thursday start points (screenshots 7-10)

## 3. Art

- [ ] 3.1 Painted backgrounds per room (artgen), door and prop sprites
- [ ] 3.2 Side-only sheets for the player and Samantha

## 4. Remaining scenes

- [ ] 4.1 Port croissant, dinner and second Thursday; replay every start point

## 5. Switch over

- [ ] 5.1 Side view by default; remove y-sort, keyboard movement, tile chunks, rapier for characters, the forest map, wanderer and flora code
