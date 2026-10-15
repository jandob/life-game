## 1. Scene

- [x] 1.1 Write `assets/dialogue/route1_croissant.yarn` (node `Route1Croissant`, cutscene): knock on 3A, croissant, sock check, dinner invitation, back to 3B, end card
- [x] 1.2 Hand moving day over to it: `<<fade_out>>` and `<<next_scene Route1Croissant>>` replace `<<end_demo>>`
- [x] 1.3 Register the file in `YarnSpinnerPlugin`
- [x] 1.4 Map paths `PlayerTo3A` and `SamanthaIn` in `route1_flat.tmj`

## 2. Checks

- [x] 2.1 `cargo test --workspace`, `cargo clippy`, `cargo fmt --check`; `cargo check --target wasm32-unknown-unknown`
- [x] 2.2 Play moving day into the croissant scene end to end; screenshots in `screenshots/` (wasm build in Chromium on SwiftShader under Xvfb, first option at every choice; the player's scripted walks hit the stuck fail-safe on old and new paths alike in that software-rendered run, so walking smoothness is still to be checked on real hardware)

## 3. Review (user)

- [ ] 3.1 Read the scene and decide on wording, the dinner hook and the sock check
