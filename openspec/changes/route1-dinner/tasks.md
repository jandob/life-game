## 1. Scene

- [x] 1.1 Croissant ends with the Thursday time skip and hands control to the player
- [x] 1.2 Write `assets/dialogue/route1_dinner.yarn`: `Route1DinnerDoor`, `Route1Dinner`, `Route1Dishes`
- [x] 1.3 Dispatchers `Table3A`, `Sink3A`, `Shelf3A`, `Samantha3A`, `Door3AInside`; Thursday branches in `Door3A` and `Door3B`
- [x] 1.4 Register the new files in `YarnSpinnerPlugin`
- [x] 1.5 `dialogue_graph`: `next_scene` targets count as entry nodes

## 2. Map

- [x] 2.1 Flat 3A behind her door in `route1_flat.tmj` (kitchen, sink, table, chairs, bookshelf, window), with collision
- [x] 2.2 Paths and interactables for the scene

## 3. Checks

- [x] 3.1 `cargo test --workspace`, `cargo clippy`, `cargo fmt --check`
- [x] 3.2 Play the croissant scene, Thursday free roam, dinner and dishes end to end in the wasm build; screenshots in `screenshots/` (Chromium on SwiftShader under Xvfb; first option at every choice)

## 4. Review (user)

- [ ] 4.1 Play it and decide on wording, her notes and the kiss at the sink
