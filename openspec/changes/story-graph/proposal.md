## Why

The story chart (`story-chart`) cut route 1 into chapters with gates and proved them with a walker that plays every chapter by brute force. Reviewing it (Janosch, 2026-10-26) led to a different model, written down in `model.md`:

- The story graph is what we design and discuss. It is written in Yarn, and its diagrams are generated from the Yarn.
- The story is boxes (subgraphs). Each box has one way in and always starts in the same world state. It has one or more ways out, and the way out is all the rest of the story learns. Nothing is remembered outside the graph.
- Boxes nest, and edges between boxes may form loops. Inside a box there are no cycles.
- Free time is a hub box whose side boxes loop back to it. Side stories start and end between two join points.
- Choices are few. A choice that only changes lines is allowed and reported, not an error.
- Checks run on the graph, not by playing the game, so they scale with the number of boxes. The walker does not scale (about 60,000 states for the second Thursday alone) and goes.

## What Changes

- **Graph format.** Graph nodes (tag `graph`, files `graph_<route>.yarn`) declare one box each: `<<box>>`, `<<gate>>`, `<<choice>>`, `<<option>>` and `<<exit>>`. Requirements can be "all of" and "any of".
- **Boxes own their variables.** Every story variable belongs to one box by its name. Entering a box resets them all, so a box always starts in its one world state, and a loop replays it exactly.
- **Diagrams from Yarn.** `dialogue_graph` writes a story-level diagram (boxes and their exits) and one diagram per box (gates, choices, exits), from the graph nodes.
- **Graph checks** (`cargo test`): the constraints of `model.md`, on the declared graph.
- **Link checks** (`cargo test`, static): the scenes match the graph and keep to their box's variables.
- **Start points** become trivial: a box starts the same way however it is reached, so `--start <box>` runs its entry node. No replay.
- **Route 1** is redrawn as boxes. The callbacks that today reach across chapters (her lines about earlier choices) are listed for Janosch to cut or to turn into exits.

## Non-Goals

- Proving that the scenes play exactly as drawn. The link checks catch most drift. Playing the game finds the rest.
- A graph editor. The graph is edited as Yarn.
- New route 1 content.

## Impact

- **Code**: `src/story/chart.rs` becomes `src/story/graph.rs` (parser and graph checks, no walker). Box entry resets box variables. `src/story/start_point.rs` starts boxes directly. Link checks in `src/ui/dialogue/test.rs`. `dialogue_graph` draws both levels.
- **Assets**: `chart_route1.yarn` becomes `graph_route1.yarn`. Route 1 variables are renamed by box. Cross-chapter callbacks are cut or become exits.
- **Other changes**: supersedes the walker, walk checks and walker start points of `story-chart`.
