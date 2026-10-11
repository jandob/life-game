## 1. Art

- [x] 1.1 Create `assets/player/player_male.png`: male character, 64x128 cells, 10 columns x 12 rows, same frame ranges as `CHARACTER_CLIPS` (pixel-artist)
- [x] 1.2 Check the sheet in game: every idle/walk/run clip in all four directions, feet aligned with the collider at y = -32 (scaled 0.5)
- [x] 1.3 `git mv assets/player/player_male.png assets/player/player.png` and point `GameAssets::player_texture` back at `player/player.png`

## 2. Code: assets

- [x] 2.1 `git mv assets/player/player.png assets/npc/wanderer.png`
- [x] 2.2 Add `wanderer_texture` (`npc/wanderer.png`) and `wanderer_layout` (`texture_atlas(64, 128, 10, 12)`) to `GameAssets` in `src/assets.rs`; point `player_texture` at `npc/wanderer.png` until 1.3

## 3. Code: shared animation

- [x] 3.1 In `src/animation.rs` rename `PLAYER_CLIPS` to `CHARACTER_CLIPS`; add `CharacterAnim { Idle, Walk, Run }`, `character_clip(dir, anim)` and `play_character_clip(animator, sprite, clip)`
- [x] 3.2 Make `src/player/state.rs::update_animation` use them (Talking -> Idle); update `src/player/spawn.rs` imports

## 4. Code: wanderer

- [x] 4.1 Create `src/npc/wander.rs` with the `Wanderer` component and `WanderPlugin`; register it from `NpcPlugin` in `src/npc/mod.rs`
- [x] 4.2 `spawn_wanderer` on `OnEnter(Gaming)`: `Wanderer` object in `NPCs` layer, else `SpawnPoint + (48, 0)`; body identical to the player's (dynamic, rotation locked, Velocity, YSort(0), scale 0.5, child ball(16) at y -32); no `Npc`
- [x] 4.3 Add a `"Wanderer" => {}` arm to `spawn_npcs` in `src/npc/spawn.rs`
- [x] 4.4 `wander` system: pause timer (2-5 s), target picking within ~96 px validated against `tile_collision_shape` and `world_bounds`, walk at 60 px/s, arrival at 4 px, stuck retarget after 1.5 s, freeze beyond ~640 px from `MainCamera`
- [x] 4.5 `animate_wanderer` in PostUpdate before `PhysicsSet::Writeback`, Walk/Idle from velocity, facing kept while paused
- [x] 4.6 Zero her velocity on `OnExit(GameState::Gaming)`

## 5. Dialogue

- [x] 5.1 `assets/dialogue/jotem.yarn:8`: "young lady" -> "young lad"

## 6. Verification

- [x] 6.1 `cargo check` (native)
- [x] 6.2 `cargo check --target wasm32-unknown-unknown`
- [x] 6.3 Run the game: male player animates in all directions and states; wanderer spawns near the player, walks, pauses, faces her travel direction
- [ ] 6.4 With F3 off: she is blocked by water, trees and the player; talk key next to her starts nothing and shows no hint
- [ ] 6.5 Walk far away and back: she stands still out of range and never ends up inside water
- [ ] 6.6 Jotem greets with "young lad"; the ending sequence still works
