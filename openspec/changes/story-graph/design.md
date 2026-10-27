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

## Puzzle boxes (2026-10-27)

Janosch redesigned route 1 as an adventure with puzzles (thread "Shape the story graph together"). The box model stays; what is inside a box changes, and the graph now drives the game. These decisions replace D1 to D3 and D6 where they differ.

**D8. Steps.** A box holds steps: `gate` (a puzzle or action), `item`, `clue`, `choice` with `option`s, and `exit`. Syntax is in the header of `assets/dialogue/graph_route1.yarn`. A requirement `BOX.clue` names a clue from an earlier box: the player remembers it, the game stores nothing, and the checks treat it as a hint. A wrong move may end a box early through an exit into a short retry box, which can loop on itself.

**D9. Scenes ask the graph.** The graph is the only source of what can happen when:
- `<<done BOX ID>>` records a step. It is the only way a step becomes done.
- `can("BOX", "ID")` is true when `BOX` is the current box, the step is not done, and its requirements in the box hold. Scene conditions use it instead of hand-written `$chapter` and `$gate_*` tests. Extra scene conditions (an item in hand, an option already taken) are ANDed to it.
- `is_done("BOX", "ID")` reads a step, for lines that explain why something can't happen yet.
- Doing an exit enters its target box: the target's entry node (`entry=NODE` on `<<box>>`) runs next, and that node runs `<<enter_box BOX>>`, which sets `$box` and clears every step of that box. A box therefore always starts the same way, even on a second visit.
- State stays in Yarn variables (`$box`, and `$step_<box>_<id>` in lower case, true once done), so the shared story variables, the walker and start points see it. The functions read the same storage.

**D10. What goes.** `chart_route1.yarn`, `$chapter`, `$gate_*`, the route flags that live across chapters (`$r1_viewing_why`, `$r1_movein_socks`, `$r1_croissant_socks`, `$r1_dishes_turn`, `$r1_socks_at` across chapters) and the lines that read them across boxes. Within one box, flavour variables may stay, owned by that box and reset by its entry node.

**D11. Start points and the walker.** A start point is a box: it runs the box's entry node, so no path replay is needed. Inside-box start points do the listed steps first. The walker stays as a check: from each box's entry it plays every way through the box and asserts an exit is always reachable and every step can be done.
