## 1. Scene

- [x] 1.1 Write `assets/dialogue/route1_movein.yarn` (node `Route1MoveIn`, cutscene): keys, housewarming socks, neighbour rules, her going home, him entering 3B, end card
- [x] 1.2 Hand the viewing over to it: `<<fade_out>>` and `<<next_scene Route1MoveIn>>` replace `<<end_demo>>`
- [x] 1.3 Register the file in `YarnSpinnerPlugin`
- [x] 1.4 Map paths `PlayerArrive`, `SamanthaWait`, `PlayerInto3B` in `route1_flat.tmj`

## 2. Scene commands

- [x] 2.1 `next_scene`, queue started after the runner completes; `start_chat` and the idling observer wait while a scene is queued
- [x] 2.2 `fade_out`, `fade_in` on real time; overlay at ZIndex 500
- [x] 2.3 `card "TEXT"`
- [x] 2.4 `place ACTOR PATH`
- [x] 2.5 Fail-safes: clear the overlay when a queued node can't start; drop the queue on the end card and on leaving `Gaming`

## 3. Checks

- [x] 3.1 `test.rs`: new commands with arity, quote-aware parsing, speaker declares across files, `next_scene` targets exist
- [x] 3.2 `cargo check` native and `--target wasm32-unknown-unknown`; `cargo test`
- [x] 3.3 Wasm build via the `push_to_itch.sh` steps without publishing; play viewing and move-in end to end in a WebGPU browser; no console errors from the new code (Chromium on SwiftShader under Xvfb; screenshots in `screenshots/`)

## 4. Review (user)

- [ ] 4.1 Read the scene and decide on wording, the sock gift and the rules
