## Context

**Boot path today.** `assets/start.assets.ron` points `world_map` at `maps/forest.tmj`. `src/main.rs:73-78` registers the four forest Yarn files. `GameAssets` (`src/assets.rs`) loads the forest NPC sheets and portraits, flora art, and bird and cricket ambience, and `src/player/audio.rs:128-130` starts the ambience on `OnEnter(Gaming)`. The engine already handles interiors. `scene-authoring-toolkit` added multiple layers and tilesets, flip bits, an `above` layer and start-map selection, and its demo `apartment.tmj` was verified on native and wasm (its tasks 3.9 and 3.10).

**Candidate maps** (rendered with `scenekit render`):
- `apartment.tmj`: 20x14, one room with a bed, sofa, desk, rug, moving boxes and a south doorway at columns 9–10.
- `apartment_v2.tmj`: 30x14, the same room plus a kitchen (counter, stove, fridge, table) through an opening at rows 8–9, using pages `gen-000` and `gen-001`.

Both maps have `SpawnPoint` at Tiled (160, 184) and a `Wanderer` object. Neither has a landing.

**Scene draft.** `openspec/ideas/drafts/viewing-scene.md`: one node, `Route1Viewing`, about 60 lines. It has three option points that set `$r1_viewing_opening`, `$r1_viewing_why` and `$r1_viewing_question` (flavour only; they all rejoin). It uses `{$name}` with `_Samantha`, then `Samantha`, and its `//` stage directions are knock, door opens, unlock, shoes, kitchen, bedroom, window, landing, and her going back inside. User decisions: she is Samantha, 25; his age stays unstated; the stage directions become in-engine movement.

**NPCs and dialogue are forest-shaped.** `NpcDialogue` (`src/npc/mod.rs:10`) has three jobs at once: character id, Yarn start node (`runner.rs:77`) and the key for portraits and typewriter speed (`updating.rs:27`, `typewriter.rs:212`), found by parsing the Yarn *display* name. Only `Npc` entities can be talked to (`player/chat.rs:23`), and runners are cached per `NpcDialogue` (`runner.rs:89-110`). Each runner gets a fresh `MemoryVariableStorage` and is despawned on `DialogueCompleted` (`runner.rs:206`), so variables and `visited()` are lost after a conversation. `player_movement` zeroes the player's velocity while `Talking` (`player/movement.rs:21-24`). The tests in `src/ui/dialogue/test.rs` read `assets/dialogue/*.yarn` (not recursively) and enforce forest rules. `TiledObject` (`tiled_map.rs:96`) has no properties and no polyline points.

**Verified in dependency sources:**
- *Variable reset:* `DialogueRunnerBuilder::try_build` calls `add_program` (`bevy_yarnspinner-0.9.0/src/dialogue_runner/builder.rs:80`), and `add_program` → `extend_variable_storage_from` (`yarnspinner_runtime-0.9.0/src/dialogue.rs:294-326`) overwrites every known variable (declared or inferred) with its initial value. A storage shared between runners would be reset each time a conversation starts.
- *Blocking commands:* a Yarn command system may return any `TaskFinishedIndicator`, for example `Arc<AtomicBool>` (`bevy_yarnspinner-0.9.0/src/commands/command_wrapping.rs:95-120`). After a command the runner calls `continue_in_next_update`, but it only advances once `poll_tasks_and_check_if_done()` is true (`dialogue_runner/runtime_interaction.rs:65-71,164-169`). So a command can hold the dialogue until a walk finishes, with no custom polling. Commands may take `Option<T>` parameters. The built-in `wait` command exists.
- `bevy_rapier2d` 0.36 has `RigidBody::KinematicPositionBased` and `ColliderDisabled`.

**Wanderer.** `spawn_wanderer` (`src/npc/wander.rs:61-71`) falls back to `SpawnPoint + (48, 0)`, so deleting her map object doesn't remove her.

## Goals / Non-Goals

**Goals:** boot onto the landing of route 1's flat; knocking on 3B plays the viewing with Samantha walking him through the flat; a minimal, reusable command set for scripted movement, visibility and doors; story variables that persist; forest out of the boot path with every asset kept; native and wasm keep working.

**Non-Goals:** map switching and door transitions, pathfinding, typed route flags, save/load, other viewings, sound effects, camera clamping, the age gate.

## Decisions

### D1: Retiring the forest story (user decision; default A)

- **A (default): remove forest-only code; keep every asset.** Remove the forest `NpcDialogue` variants and `spawn_eleonore/jotem/isabelle/antonius/ionas`, `Npc::was_talked_to/was_mentioned_by`, `target_npc_mentioned_command`, `trigger_ending_command`, `update_target_npc(s)`/`update_mentioned_by`, `face_player` (`flip_x`), the forest arms in `ending_text.rs`, `typewriter.rs` and `updating.rs`, the forest idle clips in `animation.rs`, and the forest NPC sheets and portraits in `GameAssets`. Keep the map engine, flora (generic, covered by the accepted petal spec), the wanderer, the dialogue UI, start hints and the ending sequence. `forest.tmj` stays usable as an engine regression map: it loads with flora, and its NPC objects only log "Unknown NPC name".
  *Pros:* one cast; no `$target_npc` error spam; smaller wasm boot download; the tests stop enforcing forest rules. *Cons:* a moderate diff; bringing the forest back means restoring code from git.
- **B: keep the forest code compiled beside the new cast.** Smallest diff, but every refactor below (talk targets, runner keys, endings) must also keep the forest paths working, and the forest art keeps loading at boot.
- **C: put the forest code behind a cargo feature.** Still buildable, but it doubles the cfg surface and the feature is never tested.

The user said the forest "should leave the boot path but not be deleted". This change reads that as applying to **assets**, which are all kept. Removing forest **code** (A) needs the user's confirmation.

**Yarn files:** `git mv` the four forest files to `assets/dialogue/forest/`. `test.rs`, `dialogue_graph` and `dialogue_lines` read `assets/dialogue` non-recursively, so they then see only the active story. This supersedes the earlier "forest `.yarn` files stay where they are for now" (idea `Asset library`). **Ambience:** stop spawning the bird and cricket sounds and drop them from `GameAssets`; the files stay.

### D2: Talk targets, runners and speakers

- **`Talkable { node: String }`** (new, in `player/chat.rs`) marks anything the player can start a conversation with. `start_chat` and `spawn_hints` (`start_hint.rs:55`) query `Talkable` + `Transform` instead of `Npc`. Proximity stays `NPC_PROXIMITY_DISTANCE` (50 px between transform centres).
- **Interactables** (D7 map) spawn as an entity with `Talkable`, a `Transform` at the object's centre, and no sprite or collider.
- `PlayerStartedChat { node: String, direction }`. `RunnerFlags` and the runner cache are keyed by **start node** instead of `NpcDialogue`, and the runner starts that node.
- **`Npc { id: NpcDialogue }`** stays as the character id (the enum isn't renamed, to keep the diff small). After D1-A it has one variant, `Samantha`. The id is used for the Tiled `NPCs` object name, script actor names (D11), the speaker table and file names.
- **Speaker table** `src/ui/dialogue/speaker.rs`: `speaker(raw) -> Option<Speaker>`, where `raw` is the Yarn character name with `_` trimmed, `"You"` maps to `Player` and `"Samantha"` to `Npc(Samantha)`. `portrait(assets, speaker)` and `writer_speed(speaker)` replace `NpcDialogue::from_str` in `updating.rs::character_icon` and `typewriter.rs::set_writer_speed`.
- **Endings:** `EndingTriggered { ending: Ending, npc: Option<NpcDialogue> }` with `enum Ending { Demo }`. `ending.rs` raises the player and (if `Some`) that NPC above the fade, and `ending_text.rs` matches on `Ending`.

### D3: Samantha's entity

`spawn_samantha(commands, assets, pos, hidden)` in `src/npc/spawn.rs`, from the `"Samantha"` arm of `spawn_npcs`. `hidden` comes from the object's bool property `hidden` (D7).
- Parent: `Npc { id: Samantha }`, `Actor("Samantha")` (D11), `FourWayFacing { facing: Vec2::NEG_Y }`, `RigidBody::KinematicPositionBased`, `YSort(0.0)`, `SpriteAnimator::looping(CHARACTER_CLIPS[0])`, a `Sprite` with `samantha_texture`/`samantha_layout`, and `Transform` at `pos` with scale `0.5`. It gets `Visibility::Hidden` if `hidden`.
- Child: `Collider::ball(16.0)` at `(0, -32, 0)` (the same feet collider as the player), `CollisionGroups::default()`, and `ColliderDisabled` if `hidden`.
- **Kinematic, not dynamic, not fixed:** script code moves her by setting `Transform`. She never gets stuck on furniture or the player, and she pushes the dynamic player aside instead of deadlocking in a doorway. Kinematic bodies pass through fixed colliders, so her paths must be authored clear of walls and furniture (D7). That is the price of never stalling a scene.
- **No `Talkable`** in this slice: the scene starts from the 3B door, and the end card follows it. A later scene adds `Talkable { node: "Samantha" }` with a dispatcher node.
- Animation (`animate_actors`, PostUpdate): Walk while a `ScriptedWalk` is active, in its direction of travel; otherwise Idle in `FourWayFacing.facing`, applied through `character_clip` and `play_character_clip`. She turns only through `walk` or `face`, never automatically.

### D4: Story state lives in one shared Yarn variable storage (user decision; default: build now)

```rust
// src/story/mod.rs
#[derive(Resource, Clone, Default)]
pub struct StoryVars(pub MemoryVariableStorage);   // bevy_yarnspinner::default_impl
```

`StoryVars` is inserted fresh on `OnExit(GameState::MainMenu)`. In `spawn_dialogue_runner` (`runner.rs:67`):

```rust
let saved = story_vars.0.variables();                       // snapshot
let mut runner = project.build_dialogue_runner(&mut commands)
    .with_variable_storage(story_vars.0.clone_shallow())
    .build();                                               // add_program resets every known variable ...
runner.variable_storage_mut().extend(saved)?;               // ... restore what the story already set
```

`clone_shallow` shares one `Arc<RwLock<HashMap>>`, so all runners and Rust code see the same values, including visit counts (`$Yarn.Internal.Visiting.*`). For save/load later, `variables()` can be serialised (on wasm via `localStorage`, never `std::fs`).

Why this location: map entities will be despawned on map switches and runners are despawned on completion, so state kept on either is lost. The writers set flags where the choices are, in Yarn (`$r1_viewing_*`), and Rust reads them through `StoryVars` when it needs to, without a command per flag. A Rust-side typed `StoryState` can later be added as a view on top. Per-runner storage (the status quo) would lose the viewing flags as soon as the scene ends. It costs about 15 lines plus one test (task 9.7). Route flags, consequences and save/load are not built.

### D5: End of the slice (user decision; default: end card)

The scene ends with her going back through her door, then `<<end_demo>>`. The command writes `EndingTriggered { ending: Demo, npc: None }`, and the existing sequence runs: black fade over the world with the player raised above it, volume fade-out, and the state changes to `Ending`. `ending_text.rs` shows "To be continued" and "Thanks for Playing" and leaves out "- FIN -". The game designer may reword them. The alternative, free roaming after the scene, needs the 3B door to stop retriggering the scene (a `once` property on interactables) and something for the player to do.

### D6: Yarn layout and conventions

- **File:** `assets/dialogue/route1_viewing.yarn`, the only `YarnFileSource` in `src/main.rs`. One file per scene: later scenes add `route1_<scene>.yarn`. Character dispatcher nodes (`Samantha`) arrive when she becomes talkable.
- **Node:** `Route1Viewing` (the start node of the `Door3B` interactable). It may be split into `Route1Viewing_<Part>` nodes joined by `<<jump>>` inside the file. It gets the header `tags: cutscene` (D11).
- **Speakers:** NPC lines are `{$samantha_name}: ...` with `<<declare $samantha_name = "_Samantha">>`. Until she introduces herself it shows "???", then `<<set $samantha_name to "Samantha">>`. This replaces the draft's generic `$name`: in shared storage a generic `$name` would be overwritten by the next character's scene. Player lines are `You: ...`. There are no narrator lines. A stage direction is either a command or is dropped. `//` comments may stay as writer notes.
- **Flags:** declare the draft's choice variables in the file: `<<declare $r1_viewing_opening = "">>`, `$r1_viewing_why` and `$r1_viewing_question`. Prefix every flag with route and scene.
- **Rules kept from the project and enforced by tests:** a node's first *line* is an NPC line (commands may come before it). Every conversation has at least two NPC lines before the first option. `<<stop_chat>>` is always followed by a `...` line. Jumps stay inside the file. Titles are unique across the project.
- **Custom commands:** `stop_chat`, `end_demo`, `walk`, `await_walks`, `face`, `show`, `hide`, `open_door`, `close_door` (D11, D12). Argument names (actors, paths, doors) are checked at runtime: an unknown name logs `error!` and the command finishes immediately, so the dialogue never hangs.
- **Tests (`test.rs`):** keep `validate_custom_commands` (with the new list), `validate_node_title_uniqueness`, `validate_node_exists` and `assert_no_narrator_lines`. Drop `validate_target_npc_mentioned_command`, `validate_trigger_ending`, `validate_npc_names_existence`, `match_names_with_files` and `check_all_required_variables`. Add three tests: every `{$x}` speaker variable is declared in its file; the first line of every node is an NPC line; and the arity of every scripted command matches D11.

**Command sketch for the draft** (illustrative; the game designer owns the final file):

```
title: Route1Viewing
tags: cutscene
---
<<declare $samantha_name = "_Samantha">>
<<open_door Door3A>>
<<show Samantha>>
<<walk Samantha SamanthaOut>>
<<face Samantha Player>>
{$samantha_name}: Nobody's in there. That's sort of the point.
...                                   // keys, introduction
<<walk Samantha SamanthaTo3B>>
<<face Samantha up>>
<<open_door Door3B>>
<<face Samantha Player>>
{$samantha_name}: Shoes off, please.
...                                   // socks
<<walk Samantha SamanthaToKitchen no_wait>>
<<walk Player PlayerToKitchen>>
<<await_walks>>
<<face Samantha Player>>
{$samantha_name}: Kitchen. The stove works. ...
...                                   // bedroom, window the same way
<<walk Samantha SamanthaToLanding no_wait>>
<<walk Player PlayerToLanding>>
<<await_walks>>
<<close_door Door3B>>
...                                   // last question, "I'll let you know."
<<walk Samantha SamanthaHome>>
<<hide Samantha>>
<<close_door Door3A>>
<<end_demo>>
===
```

### D7: The map: landing and flat on one map for now (user decision; default L1)

Separate maps joined by door triggers is the decided long-term structure, but this scene has her walk *continuously* from the landing into the flat while the conversation runs. Doing that across two maps would need actors and an active runner to survive a map switch, which is far more than a door transition.

- **L1 (default): one map, `assets/maps/route1_flat.tmj`, holds the landing and flat 3B.** Doors are scripted props (D12), not transitions. When map switching arrives, the landing stays part of this map, and the stairwell end of the landing becomes the first transition (to the street or stairs). The landing could also be split out later if another scene needs it alone. Cheap; it doesn't block the follow-up.
- **L2: separate landing and flat maps plus map switching now.** It matches the long-term rule, but it pulls the whole map-switch follow-up (D9) and cross-map scene continuity into the first slice.

Mark L1 as a deliberate exception to "one location per map".

**Building it (scene-designer, scenekit only):**
1. Copy `apartment_v2.tmj` to `route1_flat.tmj`. Both demo maps stay unchanged as toolkit fixtures.
2. Make 3B a vacant rental: remove the moving boxes, bedding, laptop and other personal items. The draft says "the bed's not included", so remove the bed or leave a bare frame. Keep the kitchen and a window that can be reached (the window scene: she stands at it, the player nearby).
3. Add the **landing** south of the flat (the map grows to about 30–36 x 20). 3B's door is the existing south doorway (columns 9–10). Add **Samantha's door 3A** on the landing with a niche at least 2 tiles deep behind it, where she spawns hidden, plus a stairs end (decoration; the future exit). The draft says her door is "across the hall", so the preferred place is the landing's south wall, if it reads clearly in the 3/4 view (check a render). Otherwise put it on the north wall beside 3B and tell the game designer to change "across the hall" to "next door".
4. Doors: draw each door leaf on its **own tile layer** named exactly like the door (`Door3B`, `Door3A`) with the property `collides = false`. The open doorway (floor or threshold) is on the normal layers below. Add a **`Doors`** object layer with a rectangle object per door (same name) covering the doorway, and a bool property `open` (default false).
5. **`Interact`** object layer: a rectangle or point object `Door3B` in front of 3B's door, with the string property `node = "Route1Viewing"`.
6. **`NPCs`**: a point object `Samantha` in her niche with the bool property `hidden = true`. Delete the `Wanderer` object.
7. **`Spawn`**: `SpawnPoint` on the landing near the stairs, 3–5 tiles from 3B.
8. **`Paths`** object layer: polyline (or point) objects for the moves in D6, for example `SamanthaOut`, `SamanthaTo3B`, `SamanthaToKitchen`, `PlayerToKitchen`, `SamanthaToBedroom`, `PlayerToBedroom`, `SamanthaToWindow`, `PlayerToWindow`, `SamanthaToLanding`, `PlayerToLanding` and `SamanthaHome`. The final names are agreed with the game designer.

**Position conventions:** `SpawnPoint` and `NPCs` points are **sprite centres** (existing behaviour; the feet land about 25 px below). `Paths` points are **feet positions** (the collider centre): the code adds +16 px game-y to get the transform target, so authors draw paths along the floor. Each segment must be straight and clear of wall and furniture colliders by at least 8 px (her feet radius), because she ignores fixed colliders. Player paths must also be clear, or he gets stuck (D11 fail-safe). End points for the two actors in one room must be at least 24 px apart. `validate` and `render --check-tmx` must pass, and the map must open in Tiled 1.12.

### D8: Wanderer and `male-player-wandering-npc` 6.4–6.6

`spawn_wanderer` spawns her **only** if the map has a `Wanderer` object. The fallback is removed; her code and art stay for the city. Her open manual tests 6.4–6.6 (blocked by water, trees and the player; frozen out of range; Jotem's "young lad"; the ending) all need the forest. **Default:** the user runs them on the current `main` **before** this change's code lands (one short session, F3 off), then archives that change. **Alternative:** mark them superseded. 6.4 and 6.5 would be re-specified for the first city map, and 6.6 would lapse with the forest (the `jotem.yarn` edit can be checked with `grep`). The user decides. `tiled-map-integration` 9.4 (water sparkles) is forest-only too: mark it superseded. The lead should delete the stray `openspec/changes/male-player-wandering-npc/tasks.md-E`.

### D9: Keeping map switching open (follow-up, not built)

- No story state on map entities: it lives in `StoryVars`. Door open/closed state lives in a map-scoped `DoorStates` resource that is rebuilt from `Doors` properties on map load.
- All map-driven spawns (`spawn_npcs`, doors, interactables, player, wanderer, flora, borders) stay plain functions of `Res<TiledMap>` on `OnEnter(Gaming)`, so the follow-up can rerun them from a "map entered" event.
- This change adds object properties, which the follow-up needs for door targets (`target_map`, `target_door`).
- Still missing for the follow-up: a `MapEntity` marker on everything spawned from a map, a switchable `TiledMap` (it is copied once on `OnExit(AssetLoading)` today), a fade, and a rule for runners and scripted walks that are active during a switch.

### D10: Art deliverables and placeholders

> **Amended 2026-10-12:** the user moved the characters to realistic proportions with bigger sprites, and decided that the rooms adapt to the characters. Two follow-up changes cover it: `world-texel-scale` (one world px = one art px, 48 px tiles, integer camera scaling, world constants x3, `route1_flat.tmj` rebuilt at 48 px with the same layer, object and path names) and `realistic-character-sprites` (96x192 cells at scale 1.0, feet on row 157). The 64x128 format below and the D7 pixel values (+16 path offset, 8 px clearance, 24 px apart) stay valid for this change, which is verified (section 9) on the current 16 px map and sheets.

| File | Format | Code handle |
|---|---|---|
| `assets/library/characters/samantha/samantha.png` | 640x1536 RGBA PNG, 64x128 cells, 10 columns x 12 rows | `samantha_texture`, `samantha_layout = texture_atlas(64, 128, 10, 12)` |
| `assets/library/portraits/samantha.png` | 64x64 RGBA, transparent background | `samantha_icon` (shown at 128x128, nearest) |
| `assets/library/portraits/player.png` | 64x64 RGBA, transparent background | `player_icon` ("You" lines) |

**Sheet layout the code expects** (`CHARACTER_CLIPS`, `src/animation.rs:108`). Atlas index = row x 10 + column. Unused cells stay transparent.

| Row | Clip | Columns used | Loop |
|---|---|---|---|
| 0 | idle down (facing the camera) | 0–7 | 0.8 s |
| 1 | idle left | 0–7 | 0.8 s |
| 2 | idle right | 0–7 | 0.8 s |
| 3 | idle up (back view) | 0–7 | 0.8 s |
| 4 | walk down | 0–9 | 1.0 s |
| 5 | walk left | 0–9 | 1.0 s |
| 6 | walk right | 0–9 | 1.0 s |
| 7 | walk up | 0–9 | 1.0 s |
| 8–11 | run down/left/right/up | 0–7 | 0.8 s |

She never runs, so rows 8–11 may repeat walk frames 0–7. **This slice needs rows 0–7.** Anchor and scale must match `library/characters/player/player.png`: the character is centred on x = 32 with feet on y ≈ 114, and the head top is near y ≈ 15 (the union of the player's bounding boxes is x 7–57, y 15–114). Use the same drop-shadow ellipse. She may be a few pixels shorter than him. Hard pixels only (alpha 0 or 255 except the shadow). Left and right are mirror-consistent, and up and down show back and front. In game she is drawn at scale 0.5 (about 48 world px tall).

Portraits match the style of the existing `library/portraits/*.png`: a bust with the head about 30–40 px tall and centred, the shoulders cut by the bottom edge, and a transparent background.

Content: Samantha is a clearly adult woman (25), cool and teasing, in everyday clothes with nothing explicit. The player portrait matches the male player sheet, with no apparent age. Each file gets a `LIBRARY.md` row (generated in-house; tool and recipe; model and LoRA licence).

**Placeholders first:** `bevy_asset_loader` stalls `AssetLoading` on a missing file (on wasm the loader page just stays up). Until the art lands, `samantha_texture` → `library/characters/wanderer/wanderer.png` (a female sheet with the same layout), and `samantha_icon` and `player_icon` → `library/portraits/pai.png`. On delivery only the paths in `src/assets.rs` change.

### D11: Scripted movement and cutscene commands

New module `src/story/scripted.rs` (`ScriptedPlugin`). Commands are registered on every runner next to `stop_chat` (`runner.rs:68-75`).

**Actors.** `Actor(String)` on the player (`"Player"`) and on Samantha (`"Samantha"`). Commands look actors up by that name.

**Paths.** `TiledMap::path(name) -> Option<Vec<Vec2>>` reads the `Paths` object layer: a polyline gives `obj + points[i]`, and a point or rectangle gives its single (centre) point. Every point is converted with `tiled_to_game`, then +16 px y (feet to transform, D7).

| Command | Effect | Blocks the dialogue? |
|---|---|---|
| `<<walk ACTOR PATH>>` | Inserts `ScriptedWalk { points, next, done: Arc<AtomicBool> }`, which walks the points in order in straight segments at `SCRIPT_WALK_SPEED` (70 px/s, both actors) | yes, until the actor reaches the last point |
| `<<walk ACTOR PATH no_wait>>` | Same, but returns finished immediately (`Option<String>` third argument) | no |
| `<<await_walks>>` | Returns an indicator that is finished when no `ScriptedWalk` is left | yes |
| `<<face ACTOR DIR>>` | `DIR` is `up`, `down`, `left`, `right` or another actor's name. Sets `FourWayFacing` (player: `current_direction`) | no |
| `<<show ACTOR>>` / `<<hide ACTOR>>` | Toggles `Visibility` and `ColliderDisabled` on the actor's collider children | no |

Movement:
- **Samantha** (kinematic): `transform.translation` steps toward the target by `speed * dt`.
- **Player** (dynamic): `velocity = dir * speed`. `player_movement` and `switch_player_move_state` skip while `ScriptedWalk` is present, and `update_animation` plays Walk in the travel direction (`current_direction = dir`) and stays in `PlayerState::Talking`.
- Arrival at 2 px: snap to the point, go to the next one, and on the last point remove `ScriptedWalk`, set `done`, and zero velocity.
- **Fail-safe:** if an actor makes less than 2 px progress in 1.5 s (the player blocked by her or by furniture), snap it to the current target point and `warn!`. A scene never hangs.
- An unknown actor or path logs `error!` and finishes immediately.

**Cutscene nodes.** A node with the header `tags: cutscene` can't be left with Escape: `stop_chat` (`player/chat.rs:63`) checks `DialogueRunner::get_tags_for_node(current_node)` for the active runner and ignores Escape there. The player stays in `Talking` for the whole node, so he can't walk away while she moves. While a blocking command runs, the last line stays on screen and the continue arrow is hidden (`DialogueContinueNode`), so the player can tell he is waiting and not stuck.

All timing comes from Bevy `Time` and `Timer`. `Arc<AtomicBool>` works on wasm32. There is no new crate and no `std::time` or `std::fs`.

### D12: Doors

New `src/world/map/doors.rs`. On `OnEnter(Gaming)`, every `Doors` rectangle spawns a fixed `Collider::cuboid(w/2, h/2)` at the rectangle's centre (Tiled top-left plus half the size, then `tiled_to_game`) with `Door(name)`. `DoorStates: HashMap<String, bool>` is initialised from each door's `open` property. When a door is open, its collider gets `ColliderDisabled` and its door tile layer (a layer with the same name) is hidden.

To hide a layer, `chunk_manager::spawn_chunk` tags every tilemap with `TileLayerName(layer.name)`, and `sync_door_layers` (Update) sets `Visibility` on tagged tilemaps whenever `DoorStates` changes or chunks spawn. This works with chunk streaming. `<<open_door NAME>>` and `<<close_door NAME>>` set `DoorStates`. Samantha is kinematic and ignores door colliders, so scripts open a door before she walks through it, for the visuals. A door without a tile layer is just an invisible barrier, which is acceptable while door art is missing.

## Risks / Trade-offs

- [`add_program` resets shared variables on each new runner] → snapshot and restore (D4); test 9.7.
- [A blocking command in the custom front end: `continue_dialogue` and `typewriter.last_before_options` call `continue_in_next_update` repeatedly] → the runner ignores this until its tasks are done (verified in source); manual test 9.9 covers a full walk-through.
- [A kinematic Samantha walks through walls if a path is badly authored] → D7 clearance rule; checked in 9.9 with F3 off for the player (she isn't affected by F3).
- [Player path blocked by her or by furniture] → fail-safe snap after 1.5 s; the authoring rule keeps end points apart.
- [Escape inside a cutscene would leave her mid-walk] → `cutscene` tag blocks Escape (D11).
- [Hidden door layers reappear when a chunk respawns] → `sync_door_layers` also runs on chunk spawn.
- [Missing art stalls loading] → placeholders (D10).
- [Interior 3/4 view: a door on the south wall can be hard to read] → D7 lets the scene-designer use the north wall, with a one-line text change.
- [Camera not clamped: black void at the map edges] → accepted for this slice.
- [F3 is noclip] → test player collision with F3 off.

## Open Questions (proposed defaults in brackets)

1. Forest code: remove (A), keep compiled (B), or feature-gate it (C)? [A; all assets kept]
2. Landing and flat on one map now (L1), or separate maps plus map switching now (L2)? [L1, flagged as an exception to "one location per map"]
3. Story state: build the shared `StoryVars` now? [yes, about 15 lines]
4. End of the slice: end card, or free roam? [end card]
5. Player during the tour: scripted to walk with her (cutscene), or the dialogue pauses at each room and he walks there himself and talks to her again? [scripted cutscene; it matches the draft's single node]
6. Samantha's door: across the landing (south wall) or next to 3B (north wall, with "next door" in the text)? [across, if it reads in the 3/4 render]
7. `male-player-wandering-npc` 6.4–6.6: run now on the forest build, or supersede? [run now, then archive]
8. Player portrait: a new male portrait, or hide the portrait for "You"? [new portrait; `pai.png` placeholder meanwhile]
9. Forest Yarn location: `assets/dialogue/forest/`? [yes]
