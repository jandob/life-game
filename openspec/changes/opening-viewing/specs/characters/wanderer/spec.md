## MODIFIED Requirements

### Requirement: Wanderer spawn

The system SHALL spawn one wandering NPC using `assets/library/characters/wanderer/wanderer.png` on entering the `Gaming` state only if the current map has an object named `Wanderer` in its Tiled `NPCs` layer, at that object's position. Her spawn position SHALL be her home. A map without that object SHALL have no wanderer.

#### Scenario: No Wanderer object in the map
- **WHEN** the `NPCs` layer has no object named `Wanderer`
- **THEN** no wanderer SHALL spawn
- **THEN** no warning about an unknown NPC name SHALL be logged

#### Scenario: Wanderer object placed in Tiled
- **WHEN** the `NPCs` layer contains an object named `Wanderer`
- **THEN** she SHALL spawn at that object's position
