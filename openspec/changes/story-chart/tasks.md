## 1. Chart format

- [x] 1.1 `<<chapter>>`, `<<gate>>`, `<<bottleneck>>` in `CUSTOM_COMMANDS`; `chart` nodes exempt from the first-line rule
- [x] 1.2 Check that the Yarn runtime supports enums for `$chapter` (fall back to a string if not): yarnspinner 0.9 has no enums, so `$chapter` is a string checked against the chart
- [x] 1.3 Chart parser in `src/story/chart.rs`
- [x] 1.4 Static checks: declared, set somewhere, required by the bottleneck, no unknown or later requirements, no cycles, one start node per chapter, no `visited()` in route conditions

## 2. Walker

- [x] 2.1 Walker on a bare `Dialogue`: actions from the map's hotspot nodes and pending texts, state from variables, texts and notes, breadth-first with a state cap and paths
- [x] 2.2 Walk checks: every gate reached, no gate before its requirements, no dead ends, a note always open, the bottleneck starts the next chapter

## 3. Start points

- [x] 3.1 `Begin::Chapter`: replay the walker's shortest path to the chapter's start node, then replay world commands
- [x] 3.2 One start point per chapter, `--set gate_...` on top; drop the hand-written route 1 `played` lists

## 4. Drawing

- [x] 4.1 `dialogue_graph` writes `graphs/chart_<file>.dot` from chart nodes

## 5. Route 1 refit (checks green after each)

- [x] 5.1 `chart_route1.yarn`: `Chapter` enum, gate declarations, the five chart nodes
- [x] 5.2 The viewing: hotspots for the window, kitchen and bath in empty 3B; tour gates; `$r1_viewing_why`
- [x] 5.3 The move-in: keys, box, socks and rules as gates
- [x] 5.4 Sunday morning: socks state at her door, no menus in the croissant scene
- [x] 5.5 The first Thursday: her text as the goal, 3A opens, sink and notebook actions, no leaving before the dishes
- [x] 5.6 The second Thursday: gates as listed, give actions, no menus in the dinner, standing still
- [x] 5.7 Dispatchers (`door_*`, `bed_3b`, `sink_3a`, `table_3a`, `samantha_3a`, `stairs_landing`, 3B objects) read `$chapter` and gates; too-early lines on the bed

## 6. Checks

- [x] 6.1 `cargo test --workspace`, clippy, fmt, `cargo check --target wasm32-unknown-unknown`
- [ ] 6.2 Play every chapter start point natively (Xvfb, lavapipe), once in chart order and once in another order where a chapter allows it; screenshots in `screenshots/` (partial: every start point loads natively; a full click-through is still to do)
- [x] 6.3 `dialogue_graph` output checked by eye against the specs

## 7. Review (user)

- [ ] 7.1 Janosch reacts to the route 1 gate lists
- [ ] 7.2 Rewrite the placeholder lines
