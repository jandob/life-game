## Context

Talk targets are side-view hotspots (map layer `Hotspots`, property `node`). Their nodes are dispatchers that open with an action popup (adventure-mechanics). Story state is one shared `MemoryVariableStorage` (`StoryVars`). Items are `$item_<id>` bools. Start points fast-forward named scenes on a bare `Dialogue` (`start_point::fast_forward`) and replay world commands. Today the "where are we" check is `visited("...")` in each dispatcher, and chapters are chained by `<<next_scene>>` at the end of each scene.

## Decisions

**D1. The chart is data in Yarn nodes that never run.** Janosch chose Yarn over a separate chart file. Each chapter gets a node tagged `chart`, for example:

```
title: ChartR1Thu2
tags: chart
---
// Chart data: never run. Read by the chart checks, start points and dialogue_graph.
<<chapter R1Thu2 "Thursday. A week later.">>
<<gate r1_thu2_text "Read her text">>
<<gate r1_thu2_wine "Buy the wine she drinks" r1_thu2_text>>
<<gate r1_thu2_door "Knock on 3A" r1_thu2_wine>>
<<gate r1_thu2_shoes "Shoes off at her door" r1_thu2_door>>
...
<<bottleneck r1_thu2_bed "Go to bed" r1_thu2_night>>
===
```

`<<gate ID "LABEL" REQUIRES...>>` lists the gates it needs. `<<bottleneck>>` has the same shape and is the gate that ends the chapter. Using commands keeps it in the files the test and `dialogue_graph` already parse. Since the node never runs, the commands need no runtime handlers. They get arity entries in `CUSTOM_COMMANDS`, and `chart` nodes are exempt from the first-line rule.

Requirements are only gates. Items and flags that a gate needs are checked by the Yarn condition of the action that sets it ("Knock" needs `$item_wine_fox`), and the walk check (D4) proves the two agree with the chart.

**D2. State is plain Yarn variables.** `$chapter` is a Yarn enum `Chapter` with one case per chapter, in story order. Each gate is a `$gate_<id>` bool. Both are declared in `chart_route1.yarn`. As with items (adventure-mechanics D2), this makes start points, `--set` and fast-forward work with no extra code. Conditions read `$chapter == Chapter.R1Thu2 and $gate_r1_thu2_wine and not $gate_r1_thu2_door`. They do not read `visited()`. That keeps the chart the only source of story order and keeps the walker's state small (D4).

If the Yarn runtime's enum support turns out to be incomplete, `$chapter` falls back to a string, and the static check validates its values against the chart's `<<chapter>>` ids.

**D3. Chapters start in a start node.** For each chapter exactly one node sets `$chapter` to it (its start node). It also shows the card and sends her goal text, which adds the chapter's open note. The bottleneck's action sets its gate and starts the next chapter's start node with `<<next_scene>>`. No other `<<next_scene>>` crosses chapters. Scene endings no longer start the next scene.

**D4. A walker proves the chart.** `src/story/chart.rs` has a walker on a bare `Dialogue`, as `fast_forward` uses:
- An **action** is one available option of one hotspot node's popup (the node list comes from the map's `Hotspots` layer), or reading a pending phone text. A hotspot node that opens with a line is one action.
- Running an action plays the node to completion. A `<<next_scene>>` it queues plays after it. Other option sets inside the run branch the search as well, and world commands are ignored.
- A **state** is the variable storage plus pending phone texts and open notes. Visit counts are left out, because conditions don't read `visited()` (D2).
- From the chapter's start state it searches breadth-first, with deduplication and a cap on the number of states, and keeps the action path to each state.

The checks then assert, per chapter: every gate is set on some path. A gate is never set while one of its requirements is false. From every reached state some path reaches the bottleneck (no dead ends). Some note is open in every state before the bottleneck. The bottleneck leads to the next chapter's start state.

The same walker gives start points their path (D5) and could later give a "what's left" debug view.

**D5. Chapter start points replay a walk.** `Begin::Chapter(Chapter)` takes the walker's shortest action path from the game start to that chapter's start node, plays it like `fast_forward`, and replays the world commands. The hand-written `played` lists for route 1 go away. Points in the middle of a chapter are a chapter plus `--set`. Scene start points (`Begin::Scene`) stay for scenes that are tested on their own.

**D6. No skip.** The bottleneck's object (usually the bed) has its action only when its requirements are met. Before that, the same object gives a line that it is too early, and her note on the phone says what's left. Notes get updated by the gates, as on the second Thursday today.

**D7. Scenes she leads take object actions.** Inside such a scene, the player's input is an action on a hotspot or on her (give, wear, stand, wait), shown in the same popup. The scene's remaining lines play when the last required action is done. A popup with a wrong action (turning around at the sink) is allowed: it sets a flag and gets a line, but it never blocks the scene. Dialogue menus are only kept in phone replies, where they are flavour.

## Risks

- The walker's state space. Flavour flags multiply states. The cap is generous, and a chapter that hits it fails the check with the number of states, so it gets noticed. Chapters are small (under ~15 gates).
- Hotspots that follow an actor (`actor` property) are disabled while she is hidden. The walker can't know this, so it may try an action the player can't reach. Gate conditions must not depend on that, and the walker treats such actions as reachable, which is the safe side for the dead-end check.
- Many files are rewritten at once. The refit goes chapter by chapter (tasks 5.x), with the checks green after each one.
- `validate_first_line_is_npc_line` and the "two lines before any option" rule (`was_mentioned_by_*`) were relaxed for popups already. Chart nodes are a second exemption.
