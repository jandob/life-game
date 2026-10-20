## 1. Start points

- [x] 1.1 `src/story/start_point.rs`: start point table, launch options (args and URL query), fast-forward on a bare `Dialogue`, `--set`
- [x] 1.2 Replay the end state of world commands (walk, place, face, show, hide, doors, fades); `ScreenFade::black()`
- [x] 1.3 Skip the main menu, apply once the player is spawned; `--start list` in `main.rs`
- [x] 1.4 `web-sys` `Location` feature, direct `yarnspinner` dependency

## 2. Docs

- [x] 2.1 `docs/start-points.md`: usage, what it does, adding a start point, limits

## 3. Checks

- [x] 3.1 Tests: every start point fast-forwards against the real dialogue; sunday state; `--set` typing; launch option parsing
- [x] 3.2 `cargo test --workspace`, `cargo clippy`, `cargo fmt --check`, `cargo check --target wasm32-unknown-unknown`
- [x] 3.3 Launch `movein`, `sunday` and `croissant` natively (Xvfb, lavapipe) and check the log and screenshots

## 4. Review (user)

- [ ] 4.1 Try it and decide whether the start point names and the first-option default fit
