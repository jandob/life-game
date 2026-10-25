## Why

Janosch wants the game to play like a side-view adventure in the style of The Captain
(Sysiac Games, 2021): side-on rooms, floors linked by stairs and lifts, and moving only
by clicking (user request 2026-10-25). The plan, agreed the same day, is in the project's
"Side-view RPG plan" doc. Decisions: keep 540 art px of height and the current sprites,
keep Tiled as an object editor over painted images, fade between floors, keep only the
forest art in the library.

## What Changes

Five stages, one PR each. Main stays playable on the top-down map until stage 5.

1. **Spike: one room** (this change so far). Flat 3A as a side-on room, `--view side`
   (web `?view=side`):
   - Map property `view = "side"`, Tiled image layers drawn behind (or with `above`, in
     front of) the characters, maps without tilesets.
   - `Floor` polyline: the feet line and the walkable x span. Characters stand on it.
   - `Hotspots` layer: rectangles with `node`, `label`, `stand_x`. Hover shows the label
     and a pointer cursor; a click walks to `stand_x`, faces the hotspot and starts the
     node (the same option list as E today).
   - Click-to-walk only (double click runs). Keyboard movement and E are off in the
     side view.
   - The camera follows on x, stops at the room's edges, keeps the room's middle.
   - Placeholder background cut from the top-down 3A art
     (`tools/mapgen/side_placeholder_3a.py`).
2. Rooms and floors: the building and the shop, stair/lift/door teleports with a fade,
   a `room` command, start points per room; viewing and move-in ported.
3. Art: painted backgrounds (artgen), door and prop sprites, side-only sheets.
4. Croissant, dinner and second Thursday ported, start points replayed.
5. Switch over: side view by default, top-down code and the forest map removed.
   Stages 4 and 5 ship together (user decision 2026-10-25, before the art of stage 3,
   which needs artgen on Janosch's Mac). Removed: keyboard movement and E-to-talk with
   the start hint and key hints, y-sorting, tile layers and tile collision (the loader
   reads image and object layers only; tile layers are skipped with a warning),
   `bevy_rapier2d` (characters move by transform), flora with `bevy_hanabi` (so the web
   build goes back to WebGL2), the wanderer, `--view`. The top-down `.tmj` files and the
   map tools (`scenekit`, `map-bootstrapper`) stay: `route1_flat.tmj` is the source of
   the placeholder room art, and the tools are a separate decision.

## Non-Goals (stage 1)

- Doors between rooms, scenes, NPC hotspots that follow the NPC, polygon hotspots.
- Clicking dialogue options (keys and the existing click-to-continue still work).
