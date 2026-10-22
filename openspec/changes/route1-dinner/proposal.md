## Why

The croissant scene ends with Samantha setting a time and a place: Thursday, eight o'clock, dinner at hers. This is the first scene inside her flat. It is built player-first (user feedback 2026-10-16: "we are building a game, not a movie"): the player walks to her door, looks around her flat, sits down at the table and goes to the sink himself. Cutscenes are kept to the short beats in between. The scene moves the route from the landing into her space and adds a new thread: she has been taking notes about him.

## What Changes

- **Time skip**: `route1_croissant.yarn` no longer ends with `<<end_demo>>`. After he goes home it fades out, places him on the landing, shows a "Thursday. Eight o'clock." card and fades in. One line from him reads `$r1_croissant_dinner` (the wine if she said to bring some). Then the player walks freely.
- **Her flat on the same map**: `route1_flat.tmj` grows south with flat 3A behind her door (kitchen with a sink, a table with two chairs, a bookshelf, a window). This extends design D7 (one map, no map switching); the camera follows him through her door.
- **Dialogue**: new `assets/dialogue/route1_dinner.yarn` with three cutscene nodes, each started by the player:
  - `Route1DinnerDoor` (knock on 3A): she lets him in, with callbacks to the wine and the socks, and a shoes rule. She sends him to look around and sit down when he's ready.
  - `Route1Dinner` (the table): pasta, and the reveal that she studies people and has notes about him. Two choices set `$r1_dinner_notes` and `$r1_dinner_reply`. She tells him he washes up.
  - `Route1Dishes` (the sink): she stands behind him. One choice sets `$r1_dishes_turn`. A kiss on the cheek, the next Thursday is set, she walks him out, end card.
- **Dispatchers**: new single-node files `table_3a.yarn`, `sink_3a.yarn`, `shelf_3a.yarn` (one look at her books, `$r1_dinner_shelf`), `samantha_3a.yarn` (talking to her before and after dinner) and `door_3a_inside.yarn` (she doesn't let him leave before the dishes). `door_3a.yarn` starts `Route1DinnerDoor` after the croissant; `door_3b.yarn` has a line for Thursday.
- **Graph check**: `dialogue_graph` treats every `<<next_scene X>>` target as an entry node, so a file may hold several scenes started from dispatchers.
- **Registration**: the new files are added to `YarnSpinnerPlugin` in `src/main.rs`.

## Non-Goals

- Consequences of the `$r1_dinner_*` flags beyond flavour; save/load.
- New character art (Samantha in evening clothes), food or wine props, sound.
- The next Thursday.
