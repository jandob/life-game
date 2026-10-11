## Why

The current world is randomly procedurally generated every run — unrepeatable terrain, arbitrary NPC placement, no authored spaces. This makes level design, narrative integration, and iteration impossible. Switching to Tiled-authored maps gives us a hand-crafted, intentional world that supports the game's dialogue-driven story while keeping the same rendering pipeline (chunk streaming, YSort).

## What Changes

- **Replace procedural map generation** (noise-based terrain, MST paths, Poisson flora) with Tiled map files as the world data source
- **Bootstrap an initial map** by running the existing procedural generation once and exporting it as `.tmj`/`.tsj`
- **Delete ~1200 lines of procedural generation code** (entire `src/world/map/generation/` module + `poisson_sampling.rs`)
- **Add Tiled map loading** via the `tiled` crate — map is loaded at game start into a `TiledMap` resource; chunk manager reads tile data from it instead of `BitMap`
- **Authored map content**: terrain tiles, flora objects (trees, bushes, rocks), NPC spawn positions, player spawn point — all placed in Tiled
- **Collision shapes defined in the tileset** (`.tsj`) per tile, not computed from bitmask
- **The chunk manager, YSort, and bevy_ecs_tilemap rendering remain unchanged** — Tiled is a data source, not a renderer
- **BREAKING**: Removes `BitMap` resource and all procedural generation systems

## Capabilities

### New Capabilities
- `world/map`: Tiled-based world map loading, chunked rendering, and authored object placement (flora, NPCs, player spawn, collision)

### Modified Capabilities
- *(none — no existing spec's requirements change; `visual-effects` is unrelated)*

## Impact

- **Code deleted**: `src/world/map/generation/` (bitmap.rs, bitmask.rs, path.rs, graph.rs, mod.rs), `src/world/map/poisson_sampling.rs`
- **Code rewritten**: `src/world/map/chunk_manager.rs` (read from TiledMap), `src/world/map/collision.rs` (read collision from tileset), `src/world/map/flora.rs` (read from object layer), `src/npc/spawn.rs` (read from object layer), `src/player/spawn.rs` (read from object layer)
- **Code added**: Tiled map loader (new module), bootstrap export tool
- **Dependencies added**: `tiled = { version = "0.16", features = ["serde_json"] }`
- **Dependencies removed**: `noisy_bevy` (only used by procedural generation)
- **Assets changed**: `tileset.png` stays but gets a `.tsj` companion with collision shapes; `water_sparkles.png` referenced from tileset
- **Assets added**: `.tmj` map file, `.tsj` tileset file (bootstrapped then hand-edited)