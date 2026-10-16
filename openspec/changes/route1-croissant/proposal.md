## Why

Moving day ends with Samantha telling him to bring her a croissant the next morning ("Call it rent"), and with two threads left open: she said she'd ask whether he wears the socks, and her third rule ("if I knock, you answer") got a reply from him. The next beat of route 1 pays those off in a short, cheap scene on the landing, and sets up the first scene in her flat. It keeps the route's slow, power-dynamics-first pace: he turns up at her door at six because she told him to, she keeps him on the doorstep, checks up on him, and then sets the next date herself.

## What Changes

- **Player control (user feedback 2026-10-16: "we are building a game, not a movie")**: the morning is played, not watched. Moving day ends on the landing with a "Sunday morning." card and one line from him ("Six o'clock. One croissant. Her door."), then the node ends and the player walks freely. He knocks on 3A himself to start the scene. This is the first time the slice hands control back between scenes.
- **Doors as story-driven talk targets**: the `Interact` objects point to dispatcher nodes, one file per door: `door_3b.yarn` (node `Door3B`) and `door_3a.yarn` (node `Door3A`). They pick what happens from `visited()`: 3B starts the viewing before it has happened and otherwise has a line nudging him to her door; 3A has a "wrong door" line before the viewing and starts `Route1Croissant` on Sunday. Scenes are started with `<<next_scene>>`, because jumps stay inside one file. The map's `Door3B` interactable changes from `Route1Viewing` to `Door3B`, and a new `Door3A` interactable sits on her doormat.
- **Nearest talk target**: with two doors on one landing the talk ranges overlap. `start_chat` and the start hint now pick the nearest target in range (`nearest_talkable` in `src/player/chat.rs`) instead of the first one found, and the hint moves when another target becomes nearer.
- **Dialogue**: new `assets/dialogue/route1_croissant.yarn`, node `Route1Croissant` (`tags: cutscene`). He steps up to her door and knocks; she answers through the door, then comes out. Three choice points set `$r1_croissant_bag`, `$r1_croissant_socks` and `$r1_croissant_dinner` (flavour; they rejoin). Two lines read moving-day flags as callbacks: `$r1_movein_rules == "fair"` (she decides whether she's home) and `$r1_movein_socks == "refuse"`. She invites him to dinner at hers on Thursday at eight; that is the next scene's hook. It ends with him back in 3B and `<<end_demo>>`.
- **Moving day**: `route1_movein.yarn` ends with the time skip (fade out, place him by the stairs, card, fade in, his line) instead of `<<end_demo>>`.
- **Yarn checks** (`test.rs`): the first-line rule applies only to nodes with NPC lines. Command-only staging nodes and the player's own remarks at an object are allowed.
- **Registration**: the three new files are added to `YarnSpinnerPlugin` in `src/main.rs`.
- **Map**: `route1_flat.tmj` gets the `Paths` objects `PlayerTo3A` (point, left of her doormat) and `SamanthaIn` (polyline from her doorstep back into her niche), and the `Door3A` interactable.

## Non-Goals

- The Thursday dinner itself (needs the inside of 3A, so a new map and map switching).
- Consequences of the `$r1_croissant_*` flags; save/load.
- New art (bakery bag, Samantha in morning clothes) and sound effects (knocking).
