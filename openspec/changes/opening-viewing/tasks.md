## 0. Decisions (user)

- [x] 0.1 Confirm or change the defaults in design.md "Open Questions": forest code removal (A), landing and flat on one map (L1), `StoryVars` now, end card, scripted tour, Samantha's door across the landing, `assets/dialogue/forest/`, and a new player portrait
- [x] 0.2 `male-player-wandering-npc` 6.4–6.6: run them on the current build before section 4 lands (default), or mark them superseded (design D8)

Decided by the user, 2026-10-12: all defaults (forest code removed, L1 one map, StoryVars now, end card, scripted tour, 3A across if it reads, forest/ folder, new player portrait); wanderer tests 6.4–6.6 superseded.

## 1. Close out older changes (lead + user)

- [x] 1.1 Per 0.2: the user runs `male-player-wandering-npc` 6.4–6.6 on current `main` (forest, F3 off), or the lead marks them superseded with a note pointing at this change
- [x] 1.2 Mark `tiled-map-integration` 9.4 (water sparkles) superseded (forest retired)
- [x] 1.3 Delete the stray `openspec/changes/male-player-wandering-npc/tasks.md-E`
- [ ] 1.4 Archive `tiled-map-integration`, `scene-authoring-toolkit` and `male-player-wandering-npc`, in that order, before archiving this change

## 2. Map (scene-designer, scenekit only)

- [x] 2.1 Copy `assets/maps/apartment_v2.tmj` to `assets/maps/route1_flat.tmj` (both demo maps stay unchanged)
- [x] 2.2 Make 3B a vacant rental: remove the moving boxes, bedding, laptop and personal items; no bed or a bare frame ("the bed's not included"); keep the kitchen; a reachable window with free floor in front
- [x] 2.3 Add the third-floor landing south of the flat (map about 30–36 x 20): 3B's door at the existing south doorway, a stairs end, and Samantha's door 3A with a niche at least 2 tiles deep behind it. Prefer 3A across the landing (south wall) if it reads in a 3/4 render; otherwise put it on the north wall beside 3B and tell the game designer
- [x] 2.4 Door leaves on their own tile layers `Door3B` and `Door3A` (property `collides = false`), with the open doorway on the layers below
- [x] 2.5 `Doors` object layer: rectangles `Door3B` and `Door3A` covering the doorways, bool property `open = false`
- [x] 2.6 `Interact` object layer: object `Door3B` in front of 3B's door with string property `node = "Route1Viewing"`
- [x] 2.7 `NPCs`: point `Samantha` in her niche with bool property `hidden = true`; delete the `Wanderer` object
- [x] 2.8 `Spawn`: `SpawnPoint` on the landing near the stairs, 3–5 tiles from 3B (a sprite-centre position)
- [x] 2.9 `Paths` object layer: polylines at **feet** positions for every move in design D6 (`SamanthaOut`, `SamanthaTo3B`, `SamanthaToKitchen`, `PlayerToKitchen`, `SamanthaToBedroom`, `PlayerToBedroom`, `SamanthaToWindow`, `PlayerToWindow`, `SamanthaToLanding`, `PlayerToLanding`, `SamanthaHome`; agree the final list with the game designer). Straight segments at least 8 px clear of colliders, and the two actors' end points in a room at least 24 px apart
- [x] 2.10 `validate`, `render --check-tmx` and `library check` pass; the map opens in Tiled 1.12; deliver a render with the collision overlay and the object layers marked

## 3. Art (artgen or pixel-artist, in parallel with sections 4–6)

- [x] 3.1 `assets/library/characters/samantha/samantha.png`: 640x1536, 64x128 cells, 10x12, rows as in design D10 (idle 0–3 using columns 0–7, walk 4–7 using columns 0–9; run rows 8–11 may repeat walk frames). Anchor and scale like `player.png` (feet at y ≈ 114, centred on x = 32). Clearly adult (25), everyday clothes
- [x] 3.2 `assets/library/portraits/samantha.png`: 64x64, transparent, a bust in the style of the existing portraits
- [x] 3.3 `assets/library/portraits/player.png`: 64x64, transparent, matches the male player sheet, no apparent age
- [x] 3.4 Contact sheet (3–4x) of every row of 3.1 next to `player.png`; the feet anchor matches
- [x] 3.5 `LIBRARY.md` rows for 3.1–3.3 (source, tool and recipe, licence)

## 4. Code: forest out of the boot path (gameplay-engineer; assumes D1-A)

- [x] 4.1 `git mv assets/dialogue/{eleonore,jotem,isabelle,ionas-and-antonius}.yarn assets/dialogue/forest/`
- [x] 4.2 `assets/start.assets.ron`: `world_map` → `maps/route1_flat.tmj` (use `apartment_v2.tmj` temporarily until 2.x lands) *(done with `apartment_v2.tmj` for now; switch to `route1_flat.tmj` when 2.x lands)*
- [x] 4.3 `src/main.rs`: the only Yarn source is `dialogue/route1_viewing.yarn` (a stub file with a `Route1Viewing` node until section 7 lands)
- [x] 4.4 Remove the forest NPC code: forest `NpcDialogue` variants, `spawn_eleonore/jotem/isabelle/antonius/ionas`, `Npc::was_talked_to/was_mentioned_by`, `face_player`, `target_npc_mentioned_command`, `trigger_ending_command`, `update_target_npc(s)`/`update_mentioned_by`, the forest idle clips in `animation.rs`, and the forest arms in `typewriter.rs`, `updating.rs` and `ending_text.rs`
- [x] 4.5 `src/assets.rs`: drop the forest NPC sheets and portraits and `bird_sounds`/`cricket_sounds`; `src/player/audio.rs`: drop the bird and cricket spawn and `update_bird_sound` (files stay)
- [x] 4.6 `src/npc/wander.rs`: spawn only from a `Wanderer` object (remove the `SpawnPoint` fallback)
- [x] 4.7 `cargo check` (native and wasm32) and `cargo test` green with the stub Yarn file

## 5. Code: map objects, talk targets, story state (gameplay-engineer)

- [x] 5.1 `tiled_map.rs`: `TiledObject` gains `properties` (string, bool, int and float) and `points` (absolute polyline points); helpers `prop_str`/`prop_bool`; `TiledMap::path(name) -> Option<Vec<Vec2>>` (game space, feet +16 px y)
- [x] 5.2 `Talkable { node }`: `start_chat` and `spawn_hints` query it; `PlayerStartedChat { node, direction }`; `RunnerFlags` and the runner cache keyed by start node
- [x] 5.3 Spawn interactables from the `Interact` layer (`Talkable` + `Transform` at the object centre); missing `node` → `warn!` and skip
- [x] 5.4 `src/story/mod.rs`: `StoryVars(MemoryVariableStorage)`, fresh on `OnExit(MainMenu)`; `spawn_dialogue_runner` uses `build_dialogue_runner().with_variable_storage(clone_shallow())` with snapshot and restore around `build()` (design D4)
- [x] 5.5 `src/ui/dialogue/speaker.rs`: the speaker table (`You` → player and `player_icon`; `Samantha` → `samantha_icon`); used by `updating.rs` and `typewriter.rs`
- [x] 5.6 `GameAssets`: `samantha_texture` (placeholder `library/characters/wanderer/wanderer.png`), `samantha_layout` (64x128, 10x12), `samantha_icon` and `player_icon` (placeholder `library/portraits/pai.png`)
- [x] 5.7 `EndingTriggered { ending: Ending, npc: Option<NpcDialogue> }`; `<<end_demo>>` command; `ending_text.rs` "To be continued" plus "Thanks for Playing", no "- FIN -"

## 6. Code: Samantha, scripted scenes, doors (gameplay-engineer)

- [x] 6.1 `NpcDialogue::Samantha`; `spawn_samantha` from the `NPCs` object (`hidden` property → `Visibility::Hidden` + `ColliderDisabled`); kinematic position-based body, `Actor("Samantha")`, `FourWayFacing`, scale 0.5, child `ball(16)` at y -32 (design D3)
- [x] 6.2 `Actor("Player")` on the player
- [x] 6.3 `src/story/scripted.rs`: `ScriptedWalk` + `scripted_walk` system (kinematic: transform step; player: velocity), 70 px/s, arrival at 2 px, 1.5 s fail-safe snap with `warn!`
- [x] 6.4 The player under `ScriptedWalk`: `player_movement`/`switch_player_move_state` skip; `update_animation` plays Walk in the travel direction while staying `Talking`
- [x] 6.5 `animate_actors` for `FourWayFacing` NPCs (PostUpdate, before `PhysicsSet::Writeback`): Walk while walking, else Idle in `facing`
- [x] 6.6 Commands `walk` (blocking through `Arc<AtomicBool>`, optional `no_wait`), `await_walks`, `face`, `show`, `hide`; unknown names → `error!` and finished; registered in `spawn_dialogue_runner`
- [x] 6.7 `src/world/map/doors.rs`: door colliders from `Doors`, `DoorStates` from `open`; `open_door`/`close_door` commands; `TileLayerName` on tilemaps in `chunk_manager::spawn_chunk`; `sync_door_layers` on state change and chunk spawn
- [x] 6.8 Cutscene nodes: Escape ignored while the active runner's current node has the tag `cutscene`; continue indicator hidden while a blocking command runs
- [x] 6.9 `cargo check` (native and wasm32), `cargo clippy` clean for the new code

## 7. Dialogue (game-designer)

- [ ] 7.1 Turn `openspec/ideas/drafts/viewing-scene.md` into `assets/dialogue/route1_viewing.yarn`, node `Route1Viewing`, header `tags: cutscene`
- [x] 7.2 Rename `$name` to `$samantha_name` (declared `"_Samantha"`); declare `$r1_viewing_opening`, `$r1_viewing_why` and `$r1_viewing_question`
- [x] 7.3 Replace every `//` stage direction with commands (design D6 sketch) using the path names from 2.9, or drop it; no narrator lines
- [x] 7.4 End with Samantha going home (`walk`, `hide`, `close_door Door3A`) and `<<end_demo>>` instead of `<<stop_chat>>`; adjust "across the hall" if 2.3 puts 3A on the north wall
- [x] 7.5 Check the project rules: first line of each node is hers, two of her lines before the first option, titles unique, jumps in-file; his age stays unstated

7.2–7.5 are done in the final text, section 4 of `openspec/ideas/drafts/viewing-scene.md`. 7.1 stays open until that text is copied into `assets/dialogue/route1_viewing.yarn`: the game-designer role may not write under `assets/`, so the lead does the copy.

## 8. Tests and tools (gameplay-engineer)

- [x] 8.1 `test.rs`: drop the forest-only tests; update the custom command list; add the speaker-variable, first-line and scripted-command arity checks (design D6)
- [x] 8.2 Unit test: `StoryVars` value set through runner 1 survives building runner 2 (design D4)
- [x] 8.3 Unit test: `TiledMap::path` and `prop_*` on a small inline `.tmj` JSON (polyline, point, properties)
- [x] 8.4 Run `dialogue_graph` and `dialogue_lines` once on the new file; fix them or note what breaks

## 9. Verification (lead; manual runs with F3 off)

- [ ] 9.1 `cargo check`, `cargo check --target wasm32-unknown-unknown`, `cargo test`
- [ ] 9.2 Native run: Play → landing; no forest NPCs, ambience or wanderer; the closed 3B door blocks the player; the start hint shows at 3B
- [ ] 9.3 Knock: 3A opens, Samantha appears and walks out, her first line shows "???" and her (placeholder) portrait
- [ ] 9.4 The full tour: every walk finishes before the next line; both walk together where scripted; she faces the player when talking; no walking through walls on screen
- [ ] 9.5 Escape mid-tour does nothing; stand in her path → pushed aside, the scene continues
- [ ] 9.6 Each of the three choice points × 3 options plays through (9 runs or spot checks plus logged `StoryVars` values)
- [ ] 9.7 End: she walks home and disappears, 3A closes, the end card shows "To be continued" and the thanks line, no "- FIN -"
- [ ] 9.8 Chunk respawn: zoom out in debug (F3 on only for this), move the camera away and back → open doors stay open and closed doors closed
- [ ] 9.9 Wasm: build via the `push_to_itch.sh` steps without publishing, run in a WebGPU browser, play the scene start to end, and check the console for errors
- [ ] 9.10 After the art lands (3.x): swap the placeholder paths in `src/assets.rs`, re-run 9.3–9.7 natively, and check the feet anchor against the collider

## 10. Docs and agents (lead)

- [ ] 10.1 Update `.claude/agents/game-designer.md` (new story, Yarn conventions, command list), `gameplay-engineer.md` (`assets/maps/`), `scene-designer.md` (the `Paths`/`Doors`/`Interact` conventions and feet vs. sprite-centre positions) and `architect.md` (map, Yarn and scripted-scene facts)
- [ ] 10.2 Record follow-ups as ideas: map switching and door transitions (design D9), sound effects for knock, window and tram, camera clamping, the age gate and the itch adult flag before publishing the new story
