## Why

Route 1 is a chain of scenes. Each scene starts the next with `<<next_scene>>`, and inside a scene the player mostly picks one of three replies that all lead to the same place. Those menus are where the combinatorial explosion comes from, and they are the only thing he does in the viewing, the move-in, the croissant and the first dinner. The target nodes find out "where are we in the story" from long `visited()` chains (`door_3a.yarn`, `table_3a.yarn`, `sink_3a.yarn`), and every new scene makes those chains longer.

Classic adventures (Monkey Island, Thimbleweed Park, Gabriel Knight) are built on a puzzle dependency chart instead. The story is cut into chapters. Inside a chapter the world is open and anything whose prerequisites are met can be done, in any order. Each chapter narrows to one bottleneck that opens the next. The second Thursday already plays like this (wine, socks and gifts in any order before her door). This change makes it the rule for the whole story. See `openspec/ideas/idea-1793024436300.md`.

Decided by Janosch (2026-10-26):
- The story is a puzzle dependency chart. Scenes inside a chapter may play in different orders, and that is a goal.
- The unit is a chapter, not a day. A chapter has a time label shown on a card. Usually it is a whole day, sometimes half of one. He does not choose to advance time.
- A gate is a condition, not a choice. Wrong actions get a line and leave the chapter as it was. They never fail the run and never fork the timeline. A flag may remember how he did something.
- One open goal per chapter, set by her text and kept on the phone as a note. At most one new location per chapter.
- Going to bed is the usual bottleneck. There is no skip: a stuck chapter is his to solve.
- Inside a scene she leads, talk does not advance it. His inputs are object actions.
- The chart lives in Yarn.
- All of route 1 is refit to chapters before the next scene is written.

## What Changes

- **Chart in Yarn.** Each chapter has a chart node (tag `chart`) that is never run. It names the chapter with its card text, lists its gates with what each one requires, and names its bottleneck: `<<chapter>>`, `<<gate>>`, `<<bottleneck>>`. Story state is plain Yarn: `$chapter` (an enum of the chapters) and one `$gate_<id>` bool per gate, declared next to the chart. Target nodes check `$chapter` and gate variables instead of `visited()` chains.
- **Chapter start nodes.** The bottleneck's action starts the next chapter's start node. That node sets `$chapter`, shows the card and sends her text with the chapter's goal note. This replaces the scene-to-scene `<<next_scene>>` chains between chapters. `<<next_scene>>` stays for starting a scene from a target.
- **Chart walker.** A pure Yarn walker (no Bevy, wasm-safe) plays a chapter the way a player could. It tries every available action on every hotspot node and every pending phone text, and searches the resulting states.
- **Chart checks** (`cargo test`):
  - static: the chart is well-formed. Every gate is declared, set somewhere in the story and required (directly or not) by its chapter's bottleneck, and requires only gates of its own or earlier chapters. There are no cycles, and every chapter has exactly one start node.
  - walk: in every chapter, every gate can be reached, no gate is set before what it requires, there is no dead end (from every reachable state the bottleneck can still be reached), an open note always exists until the bottleneck, and the bottleneck starts the next chapter.
- **Start points per chapter.** A chapter start point replays the walker's shortest path to that chapter, so `--start` works however the earlier chapters are played. Mid-chapter points are a chapter plus `--set gate_...=true`. Scene start points stay where they help.
- **Chart drawing.** `dialogue_graph` also writes one Graphviz chart per route from the chart nodes, so the chart can be read and reviewed.
- **Route 1 refit.** All route 1 scenes from the viewing to the second Thursday become chapters with gates (see `specs/story/route1-chapters`). Reply menus inside scenes she leads are removed. Each choice variable that a later scene reads is set by an object action instead, and the others are dropped. Phone replies stay as flavour. The gate lists are a first draft for Janosch to react to, and new and changed lines are placeholders for him to rewrite.

## Non-Goals

- New route 1 beats after the second Thursday. They will be written as chapters once this lands.
- A real branch. The crisis beat (outline beat 8) can be a chapter with two outcomes later. Nothing in route 1 so far needs one.
- Checking rooms and walking. The walker treats every hotspot as reachable and does not model portals or where the player stands.
- Save and load, and hints beyond the phone note.
- A chart editor. The chart is edited as Yarn.

## Impact

- **Code**: new `src/story/chart.rs` (chart parsing and the walker, shared by tests and start points), chapter start points in `src/story/start_point.rs`, chart checks in `src/ui/dialogue/test.rs` (new commands, `chart` nodes exempt from the first-line rule), and chart output in `dialogue_graph`. No new runtime systems: `<<chapter>>`, `<<gate>>` and `<<bottleneck>>` are only read, never run.
- **Assets**: new `assets/dialogue/chart_route1.yarn` (registered in `main.rs`). Rewrites of every route 1 scene and target file: `route1_*.yarn`, `door_*.yarn`, `bed_3b.yarn`, `sink_3a.yarn`, `table_3a.yarn`, `samantha_3a.yarn`, `phone_route1.yarn` and the 3B and shop objects. Possibly new hotspots in the side-view map for gates that don't have an object yet (the 3B window and counter for the viewing, his doormat).
- **Other changes**: this supersedes the scene-chaining parts of `route1-move-in`, `route1-croissant`, `route1-dinner` and `route1-second-thursday` (their `next_scene` endings and in-scene menus). Their story content stays.
- **Web build**: nothing wasm-sensitive. The walker only uses the Yarn runtime, which start points already run on wasm.
