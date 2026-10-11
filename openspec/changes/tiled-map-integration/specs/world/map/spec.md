## Purpose

Defines the loading, rendering, and authored-content pipeline for the game's world map using Tiled as the data source instead of procedural generation.

## ADDED Requirements

### Requirement: Load map from Tiled file

The system SHALL load a Tiled `.tmj` map file at game start and expose tile data, object layers, and tileset definitions through a `TiledMap` resource.

#### Scenario: Map loads on entering Gaming state
- **WHEN** the game transitions to the `Gaming` state
- **THEN** the system SHALL load the configured Tiled map file
- **THEN** the `TiledMap` resource SHALL be available to all chunk and spawn systems

#### Scenario: Missing map file
- **WHEN** the configured Tiled map file does not exist or is corrupt
- **THEN** the game SHALL log an error and remain in the `MainMenu` state
- **THEN** the system SHALL NOT crash

### Requirement: Render tile layers through chunk manager

Tile layers from the Tiled map SHALL be rendered using the existing chunk-based streaming system (bevy_ecs_tilemap). The chunk manager SHALL read tile indices from the `TiledMap` resource instead of from `BitMap`.

#### Scenario: Chunk spawns around camera
- **WHEN** the camera moves within range of an unloaded chunk
- **THEN** the chunk manager SHALL query the `TiledMap` resource for tile indices within the chunk bounds
- **THEN** tiles SHALL be rendered with the same `TileBundle` structure as the current system

#### Scenario: Chunk despawns when camera moves away
- **WHEN** the camera moves beyond the configured radius from a loaded chunk
- **THEN** that chunk and its tile entities SHALL be despawned

### Requirement: Place flora via Tiled object layer

The system SHALL read a "Flora" object layer from the Tiled map and spawn the corresponding flora entities (trees, bushes, rocks) at the authored positions using the existing spawn functions.

#### Scenario: Tree placed in Tiled spawns in game
- **WHEN** the Tiled map contains an object of type "tree" in the "Flora" layer at position (x, y)
- **THEN** the system SHALL spawn a tree entity at world position (x, y) with the `YSortStatic(40)` component and sakura petal effect

#### Scenario: Bush placed in Tiled spawns in game
- **WHEN** the Tiled map contains an object of type "bush1" or "bush2" in the "Flora" layer
- **THEN** the system SHALL spawn the corresponding bush entity with the `YSort(0)` component

#### Scenario: Rock placed in Tiled spawns in game
- **WHEN** the Tiled map contains an object of type "rock" in the "Flora" layer
- **THEN** the system SHALL spawn a rock entity with the `YSort(-8)` component

### Requirement: Place NPCs via Tiled object layer

The system SHALL read an "NPCs" object layer from the Tiled map and spawn the correct NPC entities at the authored positions.

#### Scenario: NPC object spawns correct NPC type
- **WHEN** the Tiled map contains an object named "Eleonore" in the "NPCs" layer
- **THEN** the system SHALL spawn Eleonore with the `NpcDialogue::Eleonore` component, `YSort(16)`, and her idle animation

#### Scenario: All NPCs spawn from Tiled data
- **WHEN** the Tiled map contains objects named "Eleonore", "Jotem", "Isabelle", and "IonasAntonius" in the "NPCs" layer
- **THEN** each NPC SHALL spawn at its authored position with correct sprite, collider, and dialogue component

### Requirement: Player spawn point from Tiled object layer

The system SHALL read a "SpawnPoint" object from a "Spawn" object layer in the Tiled map to determine the player's starting position.

#### Scenario: Player spawns at Tiled-defined position
- **WHEN** the Tiled map contains a "SpawnPoint" object in the "Spawn" layer at position (x, y)
- **THEN** the player SHALL spawn at world position (x, y) instead of the hardcoded origin

#### Scenario: Missing spawn point
- **WHEN** the Tiled map does not contain a "SpawnPoint" object
- **THEN** the player SHALL spawn at the origin (0, 0) as a fallback

### Requirement: Collision from tileset definitions

The system SHALL read collision shapes defined on individual tiles in the Tiled tileset (`.tsj`) and spawn physics colliders when those tiles are rendered.

#### Scenario: Water-edge tile has collision
- **WHEN** a tile with an authored collision shape (e.g., a water-edge tile with a bottom-rect collider) is placed on the ground layer
- **THEN** a Rapier collider SHALL be spawned at that tile's position matching the authored shape

#### Scenario: Grass tile has no collision
- **WHEN** a grass tile without a collision shape is placed
- **THEN** no collider SHALL be spawned for that tile

### Requirement: Bootstrap tool exports procedural map

The system SHALL provide a bootstrap binary that runs the current procedural generation for a bounded region and exports the result as a Tiled `.tmj` file with tileset (`.tsj`), tile layers, and object layers for flora, NPCs, and spawn point.

#### Scenario: Bootstrap produces valid Tiled map
- **WHEN** the bootstrap tool is run with default parameters
- **THEN** it SHALL produce a `.tmj` file that can be opened in Tiled and contains a "Ground" tile layer, "Flora" object layer, "NPCs" object layer, and "Spawn" object layer

### Requirement: Remove procedural generation code

The entire `src/world/map/generation/` module and `src/world/map/poisson_sampling.rs` SHALL be removed from the codebase after the bootstrap tool has been used to generate the initial map.

#### Scenario: Generation module not compiled
- **WHEN** the game is compiled after the change
- **THEN** `src/world/map/generation/` and `poisson_sampling.rs` SHALL NOT exist in the source tree
- **THEN** the game SHALL compile without errors