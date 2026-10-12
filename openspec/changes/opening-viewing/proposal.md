## Why

Life Game has pivoted to an 18+ branching story in a modern city (ideas `Pivot: adult branching story`, `Opening: apartment hunting`, `Route 1: feminization`). The game still boots into the retired forest story (Jotem, Eleonore, Isabelle, Ionas & Antonius on `maps/forest.tmj`). The first playable slice of the new story is one scene: the viewing of route 1's flat, 3B. The player knocks on 3B. **Samantha** (25, a psychology master's student and the landlord's daughter, who lives across the landing) opens her own door instead, unlocks 3B, and walks him through the kitchen and bedroom to the window. Back on the landing she ends with "I'll let you know" and goes back through her door. The scene draft is `openspec/ideas/drafts/viewing-scene.md` (node `Route1Viewing`).

The user decided (2026-10-12) that the draft's stage directions are **real in-engine movement** driven from the dialogue, not narrator lines. So this slice needs a small scripted-scene layer: Yarn commands that walk Samantha (and the player) along paths authored in Tiled, turn them, show or hide her, and open or close doors. The slice also moves the boot path onto the new story and settles where story flags live, without building the route system.

## What Changes

- **Boot path**: the start map becomes `assets/maps/route1_flat.tmj`, a new map that the scene-designer derives from `apartment_v2.tmj`. It holds the flat 3B (living room/bedroom, kitchen, window), vacant for a viewing, and **the third-floor landing** with 3B's door and Samantha's door. *(Landing and flat on one map for now; design D7. User decision.)* `YarnSpinnerPlugin` loads only the new story's Yarn file. The forest bird and cricket ambience no longer plays.
- **Forest story leaves the boot path; no assets are deleted**: the forest `.yarn` files move to `assets/dialogue/forest/`, and `maps/forest.tmj` and all forest art stay. Forest-only code is removed from the build (git keeps it). Generic systems stay. *(Design D1. User decision.)*
- **Samantha**: a new NPC with the character id `Samantha`, spawned hidden from the `NPCs` object of the same name (behind her door). She uses a 64x128, 10x12 sheet in the player's layout (`CHARACTER_CLIPS`) with idle and walk clips in four directions. She has a kinematic body (scripted, never stuck, pushes the player aside), a feet collider while visible, and a 64x64 portrait. The code uses placeholder art until her real sprite and portrait arrive: the wanderer sheet and `pai.png`.
- **Player portrait**: "You" lines currently show `pai.png`, the former female protagonist. A male player portrait replaces it. His age stays unstated (blank slate).
- **Talk targets**: a conversation can start from an NPC *or* from a map **interactable**, an object in the Tiled `Interact` layer with a `node` property, such as the 3B door. Runners are keyed by start node, not by `NpcDialogue`.
- **Scripted scenes**: new Yarn commands `walk`, `await_walks`, `face`, `show`, `hide`, `open_door` and `close_door`. A blocking `walk` holds the dialogue until the actor arrives. Paths are polyline or point objects in a Tiled `Paths` layer, measured at the feet. Doors are rectangle objects in a `Doors` layer: a collider, plus an optional tile layer of the same name that is hidden while the door is open. Nodes tagged `cutscene` can't be left with Escape.
- **Map objects**: the Tiled loader reads object **properties** and **polyline** points (needed for interactables and paths; door transitions will need them later too).
- **Dialogue**: `assets/dialogue/route1_viewing.yarn` with the node `Route1Viewing`. It is the game designer's draft, with each `//` stage direction replaced by commands and the `$name` variable renamed to `$samantha_name`. It ends with `<<end_demo>>`, an end card ("To be continued") through the existing ending sequence. *(Design D5. User decision.)*
- **Story state**: one game-wide Yarn variable storage (`StoryVars`) shared by every runner, so `$r1_viewing_*` choices and `visited()` survive the conversation and later map switches. Creating a runner must not reset values. Typed route flags, save/load and consequences are not built.
- **Speakers**: portrait and typewriter speed come from one speaker table instead of `NpcDialogue::from_str` on display names.
- **Yarn checks**: `src/ui/dialogue/test.rs` drops the forest rules and enforces this project's conventions, including the new command names.
- **Wanderer**: she spawns only where a map has a `Wanderer` object (no fallback next to `SpawnPoint`), so she isn't in the flat.
- **`male-player-wandering-npc`**: its open manual tests 6.4–6.6 use forest content. They are run on the current build before this change lands, then that change is archived (design D8; the user decides).

## Capabilities

### New Capabilities
- `story/opening-viewing`: the game boots onto the landing of the route 1 flat, knocking on 3B runs the viewing, the slice ends with an end card, and the forest is out of the boot path.
- `characters/samantha`: Samantha as a scripted, four-direction NPC with a portrait.
- `dialogue/story-state`: a shared, persistent Yarn variable storage, the speaker table, and the Yarn conventions enforced by tests.
- `dialogue/scripted-scenes`: talk targets (NPCs and interactables), movement and visibility commands, doors, and cutscene nodes.

### Modified Capabilities
- `world/map` (from the unarchived `tiled-map-integration`): the new cast in `NPCs`; object properties, `Paths`, `Doors` and `Interact` layers.
- `characters/wanderer` (from the unarchived `male-player-wandering-npc`): spawn only from a `Wanderer` map object.
- `visual-effects`: NPC animations no longer name the forest NPCs.

Archive order: `tiled-map-integration`, then `scene-authoring-toolkit`, then `male-player-wandering-npc`, then this change.

## Non-Goals

- Map switching and door *transitions* between maps (decided for later; design D9 keeps the path open). The doors here are scripted props on one map.
- Pathfinding. Paths are authored polylines that are walked in straight segments.
- The other viewings, choosing a flat, route lock-in, typed route flags, save/load and choice consequences. The `$r1_viewing_*` flags are recorded but nothing reads them.
- Sound effects for knocking, the window or the tram (a follow-up audio pass), and indoor ambience.
- The wanderer in this scene, camera clamping, an age gate and the itch.io adult flag. The last two are required before the new story is published, but not for this non-explicit slice.
- Deleting forest assets or the forest map.

## Impact

- **Assets**: new `assets/maps/route1_flat.tmj`; `assets/start.assets.ron`; new `assets/dialogue/route1_viewing.yarn`; the forest `.yarn` files move to `assets/dialogue/forest/`; new art at `assets/library/characters/samantha/samantha.png`, `assets/library/portraits/samantha.png` and `assets/library/portraits/player.png` (placeholders until delivered), plus rows in `LIBRARY.md`.
- **Code**: `src/main.rs`, `src/assets.rs`, `src/animation.rs`, `src/world/map/{tiled_map,chunk_manager}.rs`, `src/npc/{mod,spawn,wander}.rs`, `src/player/{chat,movement,state,audio}.rs`, `src/ui/dialogue/{runner,command,updating,typewriter,start_hint,test}.rs`, `src/world/ending.rs`, `src/ui/ending_text.rs`; new `src/story/mod.rs`, `src/story/scripted.rs`, `src/world/map/doors.rs` and `src/ui/dialogue/speaker.rs`.
- **Agents and docs (lead)**: `.claude/agents/game-designer.md`, `gameplay-engineer.md`, `scene-designer.md` and `architect.md` still describe the forest story or old paths. The scene-designer needs the `Paths`, `Doors` and `Interact` conventions (design D7).
- **Dependencies**: none (`MemoryVariableStorage`, `TaskFinishedIndicator` and `ColliderDisabled` come from crates already in use).
- **Web build**: nothing wasm-sensitive is added. Assets load through the asset server, timing uses Bevy `Time`, command completion uses `Arc<AtomicBool>` (fine on wasm32), and `std::fs` stays inside `#[cfg(test)]`. A missing art file stalls `AssetLoading` on both targets, so placeholders are used until the art is delivered.
