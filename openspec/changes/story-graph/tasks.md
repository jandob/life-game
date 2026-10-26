## 1. Format and checks

- [ ] 1.1 `<<choice>>` and `<<option>>` commands, `|` and `=` in requirements, cross-chapter requirements; rename `chart` to `graph` (tag, files, module)
- [ ] 1.2 Graph checks: well-formed, reachable, walkable, meaningful, complete
- [ ] 1.3 Yarn link checks: gate conditions, option assignments, menus set choices or are `flavour`
- [ ] 1.4 Remove the walker; start points set gates and choices from the graph, `--set choice_<id>=<key>`

## 2. Rendering

- [ ] 2.1 `dialogue_graph` draws choices, options, alternatives and cross-chapter edges

## 3. Route 1

- [ ] 3.1 Second Thursday: her riddle as a choice (wine errand or socks), meeting at her door
- [ ] 3.2 Janosch decides, menu by menu, which become choices and which go: viewing (what he looks at first), move-in (where the socks go), Sunday (socks worn or on the rack), first Thursday (notebook, turning around at the sink), second Thursday (gifts, reaching for her), and her text replies
- [ ] 3.3 Chapter start nodes set the world from choices (where the socks are, items)

## 4. Checks

- [ ] 4.1 `cargo test --workspace`, clippy, fmt, `cargo check --target wasm32-unknown-unknown`
- [ ] 4.2 Play the second Thursday on both branches natively
