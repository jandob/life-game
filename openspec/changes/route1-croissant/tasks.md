## 1. Scene

- [x] 1.1 Write `assets/dialogue/route1_croissant.yarn` (node `Route1Croissant`, cutscene): knock on 3A, croissant, sock check, dinner invitation, back to 3B, end card
- [x] 1.2 Moving day ends with the Sunday time skip and hands control to the player instead of `<<end_demo>>`
- [x] 1.3 Register the new files in `YarnSpinnerPlugin`
- [x] 1.4 Map paths `PlayerTo3A` and `SamanthaIn` in `route1_flat.tmj`

## 2. Player control

- [x] 2.1 Dispatcher nodes `Door3B` (`door_3b.yarn`) and `Door3A` (`door_3a.yarn`), chosen by `visited()`; the map's interactables point at them, plus a new `Door3A` interactable
- [x] 2.2 `nearest_talkable`: `start_chat` and the start hint pick the nearest talk target in range
- [x] 2.3 `test.rs`: the first-line rule only for nodes with NPC lines

## 3. Checks

- [x] 3.1 `cargo test --workspace`, `cargo clippy`, `cargo fmt --check`
- [x] 3.2 Play the viewing, moving day, free roam on Sunday and the croissant scene end to end in the wasm build; screenshots in `screenshots/` (Chromium on SwiftShader under Xvfb; first option at every choice)

## 4. Review (user)

- [ ] 4.1 Play it and decide on wording, the dinner hook and the sock check
