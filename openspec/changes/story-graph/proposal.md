## Why

The story chart (`story-chart`) made route 1 a set of chapters with gates, and a walker test that plays every chapter by brute force. Two things came out of reviewing it (Janosch, 2026-10-26):

- **Every choice must be meaningful.** Today most choices only change her next line. A choice should change the world: which gates open, where something can be found. Branches may converge later into a mostly linear story, but a choice that leads nowhere different is not a choice.
- **The walker does not scale.** The second Thursday alone is about 60,000 game states. Every new chapter, item and flag multiplies that.

Decided by Janosch (2026-10-26):
- The story graph is what we design and discuss. It covers the whole story, including choices, and is written in Yarn.
- Tooling renders it as a graph and checks it for walkability and other graph properties. The checks work on the graph, not by playing the game.
- Chapters stay. They keep the world state controllable (a day, a reset of where everyone is).

## What Changes

- **Graph format.** The chart nodes become graph nodes (tag `graph`, files `graph_<route>.yarn`). Besides `<<chapter>>`, `<<gate>>` and `<<bottleneck>>` they hold `<<choice>>` and `<<option>>`. Requirements can name gates of earlier chapters, picked options (`choice=key`), and alternatives (`a|b`, any one of them).
- **Graph rendering.** `dialogue_graph` draws the whole route: chapters as clusters, gates as boxes, choices as diamonds with one labelled edge per option, alternatives as dashed edges.
- **Graph checks** (`cargo test`): well-formed, every gate and option reachable, no combination of choices that strands the player before a bottleneck, and every choice meaningful (each option opens something the others don't).
- **Yarn link checks** (`cargo test`, static): the scenes match the graph. A gate is only set under conditions that include its requirements, every option is set somewhere, and every menu and action that branches the story sets a choice.
- **The walker goes.** Start points set the graph state directly: every gate before the target, and the first option of every choice unless `--set choice_<id>=<key>` says otherwise.
- **Route 1.** The second Thursday gets the first real branch: her riddle. Every other menu in route 1 either becomes a choice in the graph or is removed. Which is which is listed in the tasks for Janosch to decide.

## Non-Goals

- Proving that the scenes play exactly as the graph says. The link checks catch most drift; playing the game still finds the rest.
- A graph editor. The graph is edited as Yarn.
- New route 1 content after the second Thursday.

## Impact

- **Code**: `src/story/chart.rs` becomes `src/story/graph.rs` (parser and graph checks, no walker). `src/story/start_point.rs` sets state from the graph. Link checks in `src/ui/dialogue/test.rs`. `dialogue_graph` draws choices and alternatives.
- **Assets**: `chart_route1.yarn` becomes `graph_route1.yarn`. Route 1 scenes set `$choice_*` variables; route flags that later chapters read become choices.
- **Other changes**: supersedes the walker, the walk checks and walker start points of `story-chart`.
