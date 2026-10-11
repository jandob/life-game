## ADDED Requirements

### Requirement: Wanderer spawn

The system SHALL spawn one wandering NPC using `assets/npc/wanderer.png` on entering the `Gaming` state. Her position SHALL come from an object named `Wanderer` in the Tiled `NPCs` layer if one exists, otherwise from a fixed offset to the `SpawnPoint`. Her spawn position SHALL be her home.

#### Scenario: No Wanderer object in the map
- **WHEN** the `NPCs` layer has no object named `Wanderer`
- **THEN** she SHALL spawn next to the player's `SpawnPoint`
- **THEN** no warning about an unknown NPC name SHALL be logged

#### Scenario: Wanderer object placed in Tiled
- **WHEN** the `NPCs` layer contains an object named `Wanderer`
- **THEN** she SHALL spawn at that object's position

### Requirement: Random wandering near home

The wanderer SHALL repeatedly pick a random reachable point within a fixed radius of her home, walk to it at a walking speed slower than the player's, and then pause for a random few seconds. While moving she SHALL play the walking clip for her direction of travel; while paused she SHALL play the idle clip for her last direction.

#### Scenario: Walk and pause cycle
- **WHEN** her pause ends
- **THEN** she SHALL walk in a straight line to a new point within the radius whose tile has no collision shape
- **THEN** on arrival she SHALL stop and idle for a few seconds before picking another point

#### Scenario: Blocked on the way
- **WHEN** she makes no progress toward her target for about 1.5 seconds
- **THEN** she SHALL give up that target, pause, and pick a new one

### Requirement: Wanderer physics

The wanderer SHALL be a physics body that is blocked by water tiles, flora, the map border, NPCs and the player.

#### Scenario: Water in the way
- **WHEN** she walks toward water within the loaded area
- **THEN** she SHALL NOT enter the water

#### Scenario: Far from the camera
- **WHEN** she is farther from the camera than the area whose tile colliders are guaranteed to be loaded
- **THEN** she SHALL stand still

### Requirement: Wanderer is not talkable

The wanderer SHALL NOT be an `Npc`: she SHALL NOT start dialogue, show a start hint, turn toward the player, or take part in the ending sequence.

#### Scenario: Player presses the talk key next to her
- **WHEN** the player is within talking distance of the wanderer and no story NPC
- **THEN** no dialogue SHALL start and no start hint SHALL be shown
