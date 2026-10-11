## ADDED Requirements

### Requirement: Multiple tile layers

The map loader SHALL keep every tile layer of a `.tmj` in file order, and the chunk manager SHALL render all of them, each lower layer below the next, and all below every YSorted entity unless the layer is an above layer.

#### Scenario: Floor and wall layers
- **WHEN** a map has tile layers `Floor` and `Walls`, in that order
- **THEN** wall tiles SHALL draw over floor tiles in the same cell, and the player SHALL draw over both

#### Scenario: Forest map unchanged
- **WHEN** the forest map (one tile layer, one tileset) loads
- **THEN** it SHALL render and collide as before this change

### Requirement: Multiple tilesets

The loader SHALL read every tileset a map references (external or embedded), load each tileset's image through the asset server as a dependency of the map, and resolve each gid to its tileset by `firstgid`. The chunk manager SHALL render each (layer, tileset) combination in a chunk with that tileset's image. Collision SHALL use each tileset's per-tile shapes. The game SHALL log a warning if a tileset has more tiles than the device's `max_texture_array_layers`.

#### Scenario: Map using a forest tile and generated pages
- **WHEN** a map's cells reference tiles from the forest tileset, `gen-000` and `gen-003`
- **THEN** every cell SHALL show its own tile's image, and collision SHALL come from the shapes in the tileset each tile belongs to

#### Scenario: Web build
- **WHEN** such a map loads in the wasm build on WebGPU
- **THEN** it SHALL render without errors in the browser console

### Requirement: Flip flags

The loader SHALL mask Tiled's flip and rotation bits before resolving gids and SHALL render horizontally, vertically and diagonally flipped tiles as Tiled does. Until flipped collision is supported, a flipped tile with a collision shape SHALL log a warning and use the unflipped shape.

#### Scenario: Flipped tile renders like Tiled
- **WHEN** a cell holds an asymmetric tile with the horizontal flip flag
- **THEN** the game SHALL show it mirrored, matching `tmxrasterizer`

### Requirement: Above-player layer

A tile layer with the bool property `above = true` SHALL render above the player and every YSorted entity, and SHALL NOT spawn colliders unless its `collides` property is true. Any tile layer with `collides = false` SHALL spawn no colliders.

#### Scenario: Walking behind the south wall
- **WHEN** the player walks along the inside of a room's south wall whose top rows are on an above layer
- **THEN** those rows SHALL cover the player's sprite

### Requirement: Configurable start map

The map the game starts in SHALL be selectable without editing Rust code, through an asset file loaded by the asset server, and the game SHALL run on a map without `Flora` or `NPCs` layers.

#### Scenario: Demo apartment
- **WHEN** the start map is set to `maps/apartment.tmj`
- **THEN** the player SHALL spawn at the apartment's `SpawnPoint`, walk inside the room, collide with its walls and furniture, and be unable to leave it, on native and on wasm
