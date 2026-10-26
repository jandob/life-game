## 1. Format and runtime

- [ ] 1.1 `<<box>>`, `<<gate>>`, `<<choice>>`, `<<option>>`, `<<exit>>` in `CUSTOM_COMMANDS`; `graph` nodes exempt from the first-line rule; parser in `src/story/graph.rs`
- [ ] 1.2 `<<enter_box>>`: set `$box`, reset the box's variables
- [ ] 1.3 Start points: `--start <box>` runs the entry node; remove the walker and replay

## 2. Checks

- [ ] 2.1 Graph checks: well-formed, no cycles in a box, no dead ends, reachable, exits, bounds; report choices
- [ ] 2.2 Link checks: gate and choice conditions, variable ownership, option values, box starts only through exits

## 3. Route 1

- [ ] 3.1 Redraw route 1 as boxes in `graph_route1.yarn`; rename variables by box; shared dispatchers branch on `$box`
- [ ] 3.2 Janosch decides each cross-chapter callback: cut, or an exit (socks at the croissant and both Thursdays, the viewing's first look at the move-in, turning around at the sink at the second dinner, her notebook)
- [ ] 3.3 Janosch decides which in-box choices stay (fewer choices)

## 4. Diagrams

- [ ] 4.1 `dialogue_graph`: `story_<route>.dot` and `box_<ID>.dot`

## 5. Checks

- [ ] 5.1 `cargo test --workspace`, clippy, fmt, `cargo check --target wasm32-unknown-unknown`
- [ ] 5.2 Play every route 1 box from its start point natively
