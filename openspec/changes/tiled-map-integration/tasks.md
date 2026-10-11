## 1. Dependency Setup

- [x] 1.1 Add `tiled = { version = "0.16", features = ["serde_json"] }` to `Cargo.toml` (not added — TMJ/TSJ are parsed directly with `serde_json`)
- [x] 1.2 Add `map-bootstrapper` to workspace members in `Cargo.toml`
- [x] 1.3 Create `map-bootstrapper/Cargo.toml` with dependencies on gen modules, `tiled`, and `serde_json`

## 2. Tiled Map Loader

- [x] 2.1 Create `src/world/map/tiled_map.rs` with `TiledMap` resource wrapping `tiled::Map`
- [x] 2.2 Implement `load_tiled_map()` system that runs on `OnEnter(GameState::AssetLoading)`, loading the `.tmj` file from `assets/map/world.tmj` (replaced by `TiledMapLoader`, see 2.4)
- [x] 2.3 Expose tile lookup functions: `tile_at(x, y) -> Option<u32>`, `tile_collision_shape(x, y) -> Option<Collider>`, `object_layer(name) -> &[tiled::Object]`
- [x] 2.4 Load the map via a Bevy `AssetLoader` (`.tmj` + referenced `.tsj`) through `GameAssets` instead of `std::fs`, so it works on wasm; copy into the `TiledMap` resource on `OnExit(AssetLoading)`

## 3. Rewrite Chunk Manager

- [x] 3.1 Replace `BitMap` dependency in `chunk_manager.rs` with `TiledMap` resource
- [x] 3.2 Rewrite `spawn_chunk()` to call `TiledMap::tile_at()` instead of `BitMap::get_tile_index()`
- [x] 3.3 Handle out-of-bounds tiles (outside map dimensions) as empty — no tile spawned
- [x] 3.4 Remove `spawn_water_collisions` from chunk manager (moved to collision system picking up from TiledMap)

## 4. Rewrite Collision System

- [x] 4.1 Rewrite `collision.rs` to iterate spawned chunk tiles and query `TiledMap::tile_collision_shape()` for each tile
- [x] 4.2 Remove all bitmask-based collision computation (bot_left_tri, top_left_tri, etc. — moved to tileset)
- [x] 4.3 Ensure the collision system runs on `Added<ChunkIndex>` entities (same pattern as before)

## 5. Rewrite Flora Spawning

- [x] 5.1 Rewrite `flora.rs` to read the "Flora" object layer from `TiledMap` during `OnEnter(GameState::Gaming)`
- [x] 5.2 Map Tiled object types to existing spawn functions: `"tree"` → `spawn_tree()`, `"bush1"` → `spawn_bush(0)`, `"bush2"` → `spawn_bush(1)`, `"rock"` → `spawn_rock()`
- [x] 5.3 Remove Poisson sampling and per-chunk flora spawning (keep despawn/cleanup systems)
- [x] 5.4 Remove `SpawnedChunk` / `DespawnedChunk` event handling from flora (flora is now static, loaded once)

## 6. Rewrite NPC Spawning

- [x] 6.1 Rewrite `npc/spawn.rs` to read the "NPCs" object layer from `TiledMap` during `OnEnter(GameState::Gaming)`
- [x] 6.2 Map Tiled object names to NPC types: `"Eleonore"`, `"Jotem"`, `"Isabelle"`, `"IonasAntonius"`
- [x] 6.3 Remove dependency on `BitMap::get_furthest_hotspots()`
- [x] 6.4 Remove `BitMap` import from NPC spawn module

## 7. Rewrite Player Spawning

- [x] 7.1 Rewrite `player/spawn.rs` to read the "SpawnPoint" object from the "Spawn" layer in `TiledMap`
- [x] 7.2 Implement fallback: if no spawn point found, use origin `(0, 0)`
- [x] 7.3 Remove hardcoded `PLAYER_SPAWN_POS` constant

## 8. Bootstrap Tool

- [x] 8.1 Create `map-bootstrapper/src/main.rs` that runs procedural generation for a bounded region (e.g., 100×100 tiles centered on origin)
- [x] 8.2 Export tile data as a Tiled `.tmj` file with a "Ground" tile layer
- [x] 8.3 Export flora positions as a "Flora" object layer with correct types
- [x] 8.4 Export NPC positions as a "NPCs" object layer with correct names
- [x] 8.5 Export player spawn point as a "Spawn" object layer
- [x] 8.6 Generate a `.tsj` tileset file referencing `tileset.png` with the 16×16 grid layout
- [x] 8.7 Run the bootstrap tool to produce `assets/map/world.tmj` and `assets/map/tileset.tsj`

## 9. Tileset Collision Setup

- [x] 9.1 Open the generated `tileset.tsj` in Tiled's tileset editor (manual)
- [x] 9.2 Review the bitmask tile mapping from `bitmask.rs` and identify which tiles need collision shapes (manual)
- [x] 9.3 Draw collision rectangles/triangles on water-edge, water-corner, and water-bank tiles (manual)
- [x] 9.6 Implement `tile_collision_shape()`: parse per-tile `objectgroup` from the `.tsj` (rectangles → cuboids, polygons → convex decomposition) into one compound collider per tile
- [ ] 9.4 Set up water sparkle animation as tile animation frames in the `.tsj` (or keep code-based if preferred) (manual)
- [x] 9.5 Save the updated `.tsj` (manual)

## 10. Asset & Dependency Cleanup

- [x] 10.1 Remove `noisy_bevy` from `Cargo.toml` dependencies (kept — still used by `camera_shake.rs` and `player/audio.rs`)
- [x] 10.2 Remove `BitMap` resource registration from `MapGenerationPlugin`
- [x] 10.3 Remove `MapGenerationPlugin` from `MapPlugin` (replaced with `TiledMapPlugin`)
- [x] 10.4 Remove unused asset handles from `assets.rs` (removed `water_sparkles`; `tileset` and `rocks_*` still used)
- [x] 10.5 Delete `src/world/map/generation/` directory entirely
- [x] 10.6 Delete `src/world/map/poisson_sampling.rs`
- [x] 10.7 Remove `map-bootstrapper` from workspace members and delete the directory (kept for potential re-bootstrapping)
- [x] 10.8 Remove unused `untitled.tiled-project` and `untitled.tiled-session` from project root

## 11. Integration & Testing

- [x] 11.1 Verify the game compiles without errors
- [x] 11.2 Verify the game loads the Tiled map and renders tiles correctly
- [x] 11.3 Verify flora (trees, bushes, rocks) appear at authored positions
- [x] 11.4 Verify NPCs appear at authored positions and dialogue works
- [x] 11.5 Verify player spawns at the correct position
- [x] 11.6 Verify water-edge collision stops the player (verified in the wasm build; note F3 debug mode disables player collision)
- [x] 11.7 Verify YSort rendering is correct (player walks under trees, behind NPCs, etc.)
- [x] 11.8 Verify the bootstrap map is playable and visually similar to current procedural output
- [x] 11.9 Verify the wasm build runs: map loads via asset server, WebGPU backend (Hanabi needs compute), `std::time::Instant` → `bevy::platform::time::Instant` in typewriter, `#game-canvas` is a `<canvas>`