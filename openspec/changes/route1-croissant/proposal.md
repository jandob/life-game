## Why

Moving day ends with Samantha telling him to bring her a croissant the next morning ("Call it rent"), and with two threads left open: she said she'd ask whether he wears the socks, and her third rule ("if I knock, you answer") got a reply from him. The next beat of route 1 pays those off in a short, cheap scene on the landing, and sets up the first scene in her flat. It keeps the route's slow, power-dynamics-first pace: he turns up at her door at six because she told him to, she keeps him on the doorstep, checks up on him, and then sets the next date herself.

## What Changes

- **Dialogue**: new `assets/dialogue/route1_croissant.yarn`, node `Route1Croissant` (`tags: cutscene`). Sunday morning: he comes back up the stairs from the bakery and knocks on 3A. She answers through the door, then comes out. Three choice points set `$r1_croissant_bag`, `$r1_croissant_socks` and `$r1_croissant_dinner` (flavour; they rejoin). Two lines read moving-day flags as callbacks: `$r1_movein_rules == "fair"` (she decides whether she's home) and `$r1_movein_socks == "refuse"`. She invites him to dinner at hers on Thursday at eight; that is the next scene's hook. It ends with him back in 3B and `<<end_demo>>`.
- **Moving day**: `route1_movein.yarn` ends with `<<fade_out>>` and `<<next_scene Route1Croissant>>` instead of `<<end_demo>>`.
- **Registration**: the file is added to `YarnSpinnerPlugin` in `src/main.rs`.
- **Map**: `route1_flat.tmj` gets the `Paths` objects `PlayerTo3A` (point, on the landing left of her doormat) and `SamanthaIn` (polyline from her doorstep back into her niche).

No new commands, code or art. The existing scene commands (`place`, `card`, `fade_in`, `walk`, `face`, `show`, `hide`, `open_door`, `close_door`, `wait`) cover it.

## Non-Goals

- The Thursday dinner itself (needs the inside of 3A, so a new map and map switching).
- Consequences of the `$r1_croissant_*` flags; save/load.
- New art (bakery bag, Samantha in morning clothes) and sound effects (knocking).
