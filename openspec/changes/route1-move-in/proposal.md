## Why

The playable slice ends after the viewing with a "To be continued" card. The next beat of route 1 is the player getting the flat: on moving day Samantha hands him the keys on the landing, gives him a housewarming present and sets her neighbour rules. That is the first scene where her control over the arrangement shows, and the first one that reads the viewing's `$r1_viewing_*` choices. The slice should run from the viewing straight into moving day, then end on the end card.

## What Changes

- **Dialogue**: new `assets/dialogue/route1_movein.yarn`, node `Route1MoveIn` (`tags: cutscene`). Three choice points set `$r1_movein_keys`, `$r1_movein_socks` and `$r1_movein_rules` (flavour; they rejoin). One line reads `$r1_viewing_why` as a callback. Samantha's lines use `{$samantha_name}` (declared once, in the viewing file). It ends with `<<end_demo>>`.
- **Viewing**: `route1_viewing.yarn` ends with `<<fade_out>>` and `<<next_scene Route1MoveIn>>` instead of `<<end_demo>>`.
- **New scene commands** (`src/story/transition.rs`):
  - `<<next_scene NODE>>` queues a node that starts once the current dialogue has completed. While a scene is queued the player stays in the talking state and can't start another conversation. Yarn jumps stay inside one file, so this is how one scene file hands over to the next.
  - `<<fade_out>>` and `<<fade_in>>` fade a black overlay (above the dialogue box, below the end card) in or out over 1 s and hold the dialogue until done.
  - `<<card "TEXT">>` shows a title card on the overlay for 2.5 s and holds the dialogue.
  - `<<place ACTOR PATH>>` puts an actor on the first point of a path at once, cancelling a walk.
  Fades and cards run on real time, like the walk fail-safes. A queued scene that fails to start clears the overlay; the end card and leaving `Gaming` drop the queue and clear it.
- **Map**: `route1_flat.tmj` gets the `Paths` objects `PlayerArrive`, `SamanthaWait` (points) and `PlayerInto3B` (polyline).
- **Yarn checks** (`test.rs`): the new commands and their arity; quoted command arguments count as one; speaker variables may be declared in any file; every `<<next_scene>>` names an existing node.

## Non-Goals

- Map switching, the inside of 3B as a separate map, or free roaming after the scene.
- Consequences of the `$r1_movein_*` flags; save/load.
- New art (sock gift, keys, boxes) and sound effects.
