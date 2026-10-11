## Context

The current world uses procedural generation (simplex noise → water/grass classification → bitmasked tile selection, Kruskal MST + Bezier paths, Poisson disk flora, hotspot-based NPC placement). This produces an unrepeatable random world every run. See proposal.md for motivation.

The rendering side uses `bevy_ecs_tilemap` with a chunk manager that spawns/despawns tiles in a radius around the camera, plus custom YSort systems for sprite depth ordering. These remain unchanged — only the data source changes.

The existing `BitMap` resource (`src/world/map/generation/bitmap.rs`) is both the generator and the per-tile lookup (via `get_tile_index(v)`). It is replaced by a `TiledMap` resource that wraps the `tiled` crate's parsed map.

## Goals / Non-Goals

**Goals:**
- Replace `BitMap` with `TiledMap` as the sole tile data source
- Keep chunk streaming, YSort, bevy_ecs_tilemap rendering exactly as-is
- Spawn flora, NPCs, player, and collision from Tiled object layers and tileset tile data
- Create a bootstrap binary that exports the current gen as a `.tmj`/`.tsj` pair
- Delete all procedural generation code

**Non-Goals:**
- Changing YSort, camera, or rendering systems
- Adding scene transitions or multiple maps
- Hot-reloading maps during gameplay
- Procedural generation as an optional game mode
- Editor features (this is about loading pre-authored maps only)

## Decisions

### Decision: Use the `tiled` crate directly, not `bevy_ecs_tiled`

We use `tiled = { version = "0.16", features = ["serde_json"] }` as the sole new dependency for loading Tiled map data. `bevy_ecs_tiled` was considered but rejected because:
- It manages its own tilemap entity spawning, conflicting with our existing chunk manager
- Its Rapier integration targets bevy_rapier2d 0.35 (we use 0.36)
- It doesn't integrate with our YSort system
- It removes control over chunking, which is core to our camera-based streaming

Instead, the `tiled` crate gives us raw parsed data: tile indices, object positions, tileset collision shapes. We feed these into our existing systems.

### Decision: `TiledMap` resource wraps the parsed map

A new resource `TiledMap` holds the parsed `tiled::Map`. Systems access it for:
- Tile lookup by chunk coordinates → `chunk_manager.rs`
- Tile collision shapes → `collision.rs`
- Object layer "Flora" → `flora.rs`
- Object layer "NPCs" → `npc/spawn.rs`
- Object layer "Spawn" → `player/spawn.rs`

The map is loaded once during `OnEnter(GameState::AssetLoading)` and stays in memory as a resource.

### Decision: Collision from tileset tile properties

Each tile in the `.tsj` that forms a water-edge, water-corner, or water-bank tile gets an authored collision shape in Tiled's tileset editor. When `spawn_water_collisions()` iterates placed tiles, it checks the Tiled tile definition for a collision object — if present, it spawns a Rapier collider. This replaces the `get_tile_collision()` bitmask logic.

The current collision shapes (bot-rect, left-rect, top-rect, right-rect, and the four triangle corner shapes) map directly to Tiled's polygon/rectangle collision tools. Setting them up in the `.tsj` is a one-time task.

### Decision: Bootstrap tool as a separate Rust binary in the workspace

A new member `map-bootstrapper` in the workspace `members` array. It depends on the same procedural generation modules (plus `tiled` and `serde_json`) and runs the gen for a bounded region, then writes a `.tmj` and `.tsj`.

This keeps the gen code alive long enough to produce the map, after which both the gen modules and the bootstrapper are deleted from the workspace.

### Decision: No chunk-based flora spawning

Currently, flora spawns per-chunk via a `SpawnedChunk` event. With an authored map, flora positions are fixed and known at load time. Flora entities are spawned once from the "Flora" object layer during `OnEnter(GameState::Gaming)`, not via the chunk event. The `despawn_flora_chunks` and despawn-around-start-hint/NPC systems remain to handle cleanup.

Chunk-sized Flora objects are no longer needed — flora entities can be spawned globally from the object layer.

### Decision: Finite map boundaries, no procedural fallback

The map has finite boundaries defined by the Tiled map dimensions. The chunk manager still streams tiles within the camera radius, but tiles outside the map bounds are treated as empty (no tile). The `BitMap`'s dynamic growth is gone. If the camera moves beyond the map edge, the player boundary system (implicit via map edge tiles being empty) stops them.

## Risks / Trade-offs

- **[Risk] Bootstrap map may look different from current gen** → The bootstrap runs the exact same noise MST Poisson pipeline currently used, producing a faithful export. The player can then edit the map in Tiled.
- **[Risk] Tile collision shapes in .tsj must match the current bitmask system** → A systematic mapping from current tile (x, y) to collision type is known from the bitmask module. This is a one-time authoring task in Tiled. Worst case: missing collision on some tiles → player walks through water edges. Mitigation: thorough mapping + test by loading the bootstrap map.
- **[Trade-off] Map boundary is finite** → Currently the world is effectively infinite (though never fully explored). A bounded map constrains player movement. Acceptable because the game has authored NPCs and dialogue — the playable space is intentionally designed.
- **[Risk] Removing `noisy_bevy` dependency** → `noisy_bevy` is only used by the procedural generation. After deleting gen code, the dependency can be removed. Verify no other module imports it.

## Open Questions

- What are the exact map dimensions for the initial bootstrap map? (suggestion: 100×100 tiles = 1600×1600 px = ~6 camera-widths across)
- Should water sparkle animation indices be defined as Tiled tile animations (in the `.tsj`) or kept as code (current `water_sparkle_mask` approach)? The `.tsj` format supports per-tile animation frames, which would be cleaner.
- Where does the `.tmj` file live in the assets directory? (suggestion: `assets/map/world.tmj`)