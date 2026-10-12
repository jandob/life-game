## ADDED Requirements

### Requirement: Talk targets

A conversation SHALL be startable from any talk target: an NPC with a start node, or an interactable from the Tiled `Interact` layer whose `node` property names the start node. When the player is within talking distance of a talk target and presses the talk key, the named node SHALL start, and a start hint SHALL be shown over the target while the player is in range and not talking.

#### Scenario: Interactable door
- **WHEN** the player is within talking distance of the `Door3B` interactable and presses the talk key
- **THEN** the node `Route1Viewing` SHALL start and the player SHALL enter the talking state

### Requirement: Scripted walking

The Yarn command `<<walk ACTOR PATH>>` SHALL move the named actor (`Player` or an NPC id) along the named path from the Tiled `Paths` layer, segment by segment in straight lines at a fixed walking speed, playing the walk animation in the direction of travel. The dialogue SHALL NOT advance until the actor reaches the last point, unless the optional third argument `no_wait` is given. `<<await_walks>>` SHALL hold the dialogue until no actor is walking. Path points SHALL be read as feet positions.

#### Scenario: Blocking walk
- **WHEN** the dialogue runs `<<walk Samantha SamanthaToKitchen>>` followed by a line
- **THEN** the line SHALL appear only after Samantha has arrived at the end of the path

#### Scenario: Walking together
- **WHEN** the dialogue runs `<<walk Samantha SamanthaToKitchen no_wait>>`, `<<walk Player PlayerToKitchen>>`, `<<await_walks>>`
- **THEN** both SHALL walk at the same time, and the next line SHALL appear after both have arrived

#### Scenario: Player blocked on his path
- **WHEN** the player makes no progress toward his current path point for about 1.5 seconds
- **THEN** he SHALL be placed at that point and the walk SHALL continue, so the scene never stalls

#### Scenario: Unknown actor or path
- **WHEN** a walk command names an actor or path that does not exist
- **THEN** an error SHALL be logged and the dialogue SHALL continue as if the walk had finished

### Requirement: Facing and visibility commands

`<<face ACTOR DIR>>` SHALL turn the actor's idle animation to `up`, `down`, `left`, `right`, or toward another named actor. `<<show ACTOR>>` and `<<hide ACTOR>>` SHALL make the actor visible with an active collider, or invisible with its collider disabled. None of these commands SHALL hold the dialogue.

#### Scenario: Face the player
- **WHEN** the dialogue runs `<<face Samantha Player>>`
- **THEN** Samantha SHALL play her idle clip for the direction toward the player

### Requirement: Doors

Every rectangle object in the Tiled `Doors` layer SHALL create a door that blocks the player while closed. Its initial state SHALL come from its bool property `open`. `<<open_door NAME>>` and `<<close_door NAME>>` SHALL change the state. While a door is open, its collider SHALL be disabled and a tile layer with the same name, if one exists, SHALL be hidden, including after map chunks are respawned.

#### Scenario: Unlocking 3B
- **WHEN** the dialogue runs `<<open_door Door3B>>`
- **THEN** the door leaf drawn on layer `Door3B` SHALL disappear and the player SHALL be able to walk through the doorway

#### Scenario: Closed door blocks the player
- **WHEN** the scene has not opened `Door3B` and the player walks into the doorway (F3 off)
- **THEN** the player SHALL be stopped

### Requirement: Cutscene nodes

While the active node has the Yarn tag `cutscene`, the player SHALL stay in the talking state and SHALL NOT be able to leave the conversation with Escape. While a blocking command runs, the current line SHALL stay visible and the continue indicator SHALL be hidden.

#### Scenario: Escape during the tour
- **WHEN** the player presses Escape while Samantha walks to the kitchen in `Route1Viewing`
- **THEN** the conversation SHALL stay open and the walk SHALL continue
