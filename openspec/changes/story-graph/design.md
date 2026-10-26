## Context

The model is in `model.md`. This file is how it maps onto Yarn and the code. Today: chart nodes in `chart_route1.yarn`, `$chapter` and `$gate_*` variables, route flags that live across chapters, a walker (`src/story/chart.rs`), and start points that replay the walker's path.

## Decisions

**D1. One graph node per box.** Example, the inside-a-box picture of `model.md`:

```
title: GraphR1Thu2
tags: graph
---
<<box R1Thu2 "Thursday. A week later." Route1Thu2Start>>
<<gate text "Read her text">>
<<choice answer "Answer her text" text>>
<<option answer wine "Wine again?">>
<<option answer ask "What would you want?">>
<<gate wine "Buy the wine" answer=wine>>
<<gate socks "Find the socks" answer=ask>>
<<gate door "Knock on her door" wine|socks>>
<<gate dinner "Dinner" door>>
<<choice still "Stand still?" dinner>>
<<option still yes "Stand still">>
<<option still no "Reach for her">>
<<exit along "Went along" still=yes R1Thu3>>
<<exit refused "Refused" still=no R1Thu2Detour>>
===
```

`<<box ID "LABEL" ENTRY_NODE [PARENT]>>` names the box, its label, the Yarn node that enters it and, for nested boxes, the box it sits in. Ids of gates, choices and exits are local to the box. A requirement lists node ids (all needed), `a|b` (any one), and `choice=option`. `<<exit ID "LABEL" REQ... TARGET>>` ends with the box it leads to. A box with no gates is fine: a hub is a box whose exits are its side boxes and one exit onward.

**D2. Variables belong to boxes.** Story variables are named `$<box>_<name>`, lower case (`$r1thu2_gate_door`, `$r1thu2_choice_answer`, `$r1thu2_item_wine`). Gates are bools, choices hold the picked option. The current box is `$box`, the only story variable outside any box. Entering a box (its entry node runs `<<enter_box ID>>`) resets every variable of that box to its default. So a box always starts in its one state, even on a second visit, and nothing it set can outlive it. Items are box variables too: if wine bought in one box is needed in the next, that is an exit (`bought the wine`) into a box that starts with it.

**D3. Exits start the next box.** An exit's node runs the target box's entry node. Nothing else may start a node of another box.

**D4. Graph checks.** Per box, on the declared graph, and exact (boxes are small):
- *Well-formed*: unique ids, known references, every option belongs to a choice, every exit names a known box, one entry node per box (constraints 2, 4).
- *No cycles inside a box* (1). Exits between boxes may loop.
- *No dead ends*: enumerate the box's local states (sets of done nodes, at most one option per choice), and from every reachable one some exit can still be reached (5). At the story level, from every box some ending can still be reached, so every loop has a way out.
- *Everything reachable* (6).
- *Exits*: two exits of a box lead to different boxes (8).
- *Report, don't fail*: choices whose options lead to the same nodes, and the count of choices per box (7).
- *Bounds*: at most `X_MAX` exits and `N_MAX` nodes per box (9). Values to be decided, `3` and `20` to start.

**D5. Link checks** (static, on the compiled Yarn):
- A gate or choice variable is set only in nodes whose conditions read its requirements.
- A node that reads or writes `$<box>_*` variables either belongs to that box (tagged `box_<ID>`) or does so only inside `<<if $box == "<ID>">>`. Shared dispatchers (her door, the bed) branch on `$box` first.
- Every option of every choice is assigned somewhere, and no other value is.
- `<<enter_box>>` is only in entry nodes, and an entry node is only started from an exit of a box that leads to it (or a start point).

**D6. Start points.** Since every box starts the same way, `--start <box>` sets `$box` and runs its entry node. Mid-box points add `--set <var>=<value>`. The walker, path replay and world-command replay go.

**D7. Diagrams.** `dialogue_graph` writes, from the graph nodes:
- `graphs/story_<route>.dot`: boxes (hubs as hexagons), exits as labelled edges, nested boxes as clusters.
- `graphs/box_<ID>.dot`: the inside of a box. Boxes for gates, diamonds for choices with one labelled edge per option, solid edges for "all of", dashed for "any of", circles for the entry and exits.

Graphviz, as today. Mermaid output is a small addition if wanted.

## Risks

- **Lost callbacks.** Route 1 lines that refer back to earlier chapters lose their source. Each one is cut or becomes an exit. Task 3.2 lists them.
- **Link checks are approximate.** A condition can read the right variable and still be wrong. Start points make any box quick to play.
