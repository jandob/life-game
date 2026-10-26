## Context

`story-chart` declares chapters and gates in chart nodes (`chart_route1.yarn`), tests the declaration statically, and proves the scenes against it with a walker that plays every chapter. Start points replay the walker's shortest path. Route flags (`$r1_socks_at`, `$r1_dishes_turn`, ...) live outside the chart and mostly change lines.

## Decisions

**D1. One graph node per chapter, in Yarn.** Example, the second Thursday with her riddle as a real branch:

```
title: GraphR1Thu2
tags: graph
---
<<chapter R1Thu2 "Thursday. A week later.">>
<<gate r1_thu2_text "Read her riddle">>
<<choice r1_thu2_riddle "Answer her riddle" r1_thu2_text>>
<<option r1_thu2_riddle wine "Wine again?">>
<<option r1_thu2_riddle ask "What would you want?">>
<<gate r1_thu2_wine "Buy the Red Fox 2021" r1_thu2_riddle=wine r1_thu1_text>>
<<gate r1_thu2_socks "Put on the blush socks" r1_thu2_riddle=ask>>
<<gate r1_thu2_door "Knock on 3A" r1_thu2_wine|r1_thu2_socks>>
...
<<bottleneck r1_thu2_bed "Go to bed" r1_thu2_night>>
===
```

Requirements, separated by spaces, are all needed. `a|b` needs any one of them. `choice=key` needs that option to have been picked. A requirement may name anything in its own or an earlier chapter, so the first Thursday's wine clue (`r1_thu1_text`) can matter a week later.

**D2. State stays plain Yarn.** Gates are `$gate_<id>` bools, choices are `$choice_<id>` strings holding the picked key (empty until picked), and `$chapter` is a string. A choice is picked once and stays picked.

**D3. Every choice is meaningful, and every branching flag is a choice.** A route flag that a later chapter or another scene reads is a choice in the graph. Example: where he put the socks on moving day (`drawers`, `box`) becomes `<<choice r1_move_socks>>`, and Sunday's gates depend on it. A menu whose options all lead to the same gates is either turned into a choice or removed. Lines may still vary by choice, but varying lines alone never justify a menu.

**D4. Graph checks instead of the walker.** The graph is dozens of nodes, so checks are exact and fast:
- *Well-formed*: unique ids, known references, no requirement on a later chapter, no cycles, every option belongs to a declared choice, one start node per chapter.
- *Reachable*: every gate and option can be reached by some set of picks.
- *Walkable*: for every combination of picks reachable so far, every chapter's bottleneck can still be reached. Picks are enumerated chapter by chapter, and only picks that something later still reads are kept apart, so routes that converge collapse into one case.
- *Meaningful*: for every choice, each option makes reachable (or required) at least one gate or option the others don't.
- *Completeness*: every gate lies on some path to its chapter's bottleneck.

Failures name the node and, for walkability, the picks that strand the player.

**D5. Yarn link checks keep scenes honest, statically.** On the compiled story:
- Every `$gate_X` that is set to true is set under conditions (the enclosing `<<if>>`s, option conditions and the hotspot's popup condition) that read every requirement of X. For `a|b` the conditions must read `a` or `b`.
- Every option `key` of every choice is assigned somewhere (`<<set $choice_id to "key">>`), and no other value is.
- Every menu (`->`) in route files sets a choice in each branch, or is in a node tagged `flavour` (phone small talk) that sets no route variables.
- `$chapter` is only set in start nodes; story conditions don't use `visited()` (kept from `story-chart`).

This does not prove the scenes play as drawn (a condition can read a variable and still be wrong), but it catches forgotten requirements and stray flags, and costs nothing as the story grows.

**D6. Start points come from the graph.** A start point names a chapter or a gate. It sets every gate and choice that the target needs and everything earlier, picking the first option of each choice unless `--set choice_<id>=<key>` picks another, then runs the chapter's start node. Items and world state that a chapter needs are set by its start node from the graph state (for example Thu2's start puts the socks where `$choice_r1_move_socks` says). So start nodes, not replay, own the world at a chapter's start.

**D7. Rendering.** `dialogue_graph` writes `graphs/graph_<route>.dot`: one cluster per chapter labelled with its card, boxes for gates, bold for bottlenecks, diamonds for choices with one edge per option labelled with its text, solid edges for "all of", dashed edges for "any of", and dotted edges across chapters.

## Risks

- **Link checks are approximate.** A scene can satisfy them and still be wrong. Mitigation: start points make any point quick to play, and the old walker stays in git history if we need it back.
- **Combinations of picks.** Walkability enumerates picks. Convergence keeps it small; if a route grows past a cap, the check fails and names the choices to converge.
