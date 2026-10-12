## MODIFIED Requirements

### Requirement: Place NPCs via Tiled object layer

The system SHALL read an "NPCs" object layer from the Tiled map and spawn the correct NPC entities at the authored positions. The known NPC names are `Samantha` (spawned as described in `characters/samantha`) and `Wanderer` (spawned as described in `characters/wanderer`). Objects with any other name, including the retired forest NPCs, SHALL be skipped with a warning.

#### Scenario: NPC object spawns correct NPC type
- **WHEN** the Tiled map contains an object named "Samantha" in the "NPCs" layer
- **THEN** the system SHALL spawn Samantha at that position with her sprite, collider and character id

#### Scenario: Retired forest NPC names
- **WHEN** the forest map is loaded as the start map and contains "Eleonore", "Jotem", "Isabelle" or "IonasAntonius"
- **THEN** those objects SHALL be skipped with a warning and the map SHALL otherwise load and play

## ADDED Requirements

### Requirement: Object properties and polylines

The Tiled map loader SHALL read each object's custom properties (string, bool, int and float values) and, for polyline objects, the list of points in absolute Tiled coordinates, so that game systems can use them.

#### Scenario: Interactable with a start node
- **WHEN** an object in the `Interact` layer has the string property `node = "Route1Viewing"`
- **THEN** the loaded object SHALL expose that property to the game

#### Scenario: Polyline path
- **WHEN** an object in the `Paths` layer is a polyline with three points
- **THEN** the loaded path SHALL contain those three points in order, converted to game space

### Requirement: Scene object layers

The game SHALL recognise these object layers in any map: `Paths` (polyline, point or rectangle objects naming walkable routes, measured at the feet), `Doors` (rectangle objects with an optional bool property `open`, and an optional tile layer of the same name for the door leaf), and `Interact` (objects with a string property `node` naming a Yarn start node). A map without these layers SHALL load and play normally.

#### Scenario: Map without scene layers
- **WHEN** the start map has no `Paths`, `Doors` or `Interact` layer
- **THEN** the game SHALL run without errors
