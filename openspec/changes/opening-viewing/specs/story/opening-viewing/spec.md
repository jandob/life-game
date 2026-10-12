## ADDED Requirements

### Requirement: Boot into the route 1 flat

On entering the `Gaming` state, the game SHALL load `maps/route1_flat.tmj` as the start map, spawn the player at its `SpawnPoint` on the third-floor landing, and load only the new story's Yarn files. The forest map, the forest Yarn files and the forest NPCs SHALL NOT be loaded, and the forest bird and cricket ambience SHALL NOT play.

#### Scenario: Start the game
- **WHEN** the player presses Play in the main menu
- **THEN** the player SHALL appear on the landing outside flat 3B, on native and on wasm (WebGPU)
- **THEN** no forest NPC, forest dialogue or forest ambience SHALL be present

#### Scenario: Forest assets kept
- **WHEN** the change is applied
- **THEN** `assets/maps/forest.tmj`, the forest art under `assets/library/` and the forest Yarn files under `assets/dialogue/forest/` SHALL still exist

### Requirement: The viewing scene

Interacting with the door of flat 3B SHALL start the Yarn node `Route1Viewing`. During this node Samantha SHALL come out of her own door, unlock 3B, and walk the player through the kitchen and the bedroom to the window and back to the landing. She SHALL then go back through her own door. The movement SHALL be driven by the dialogue, and the player SHALL walk along with her. The node SHALL end with Samantha saying she will let him know, and no flat decision SHALL be made.

#### Scenario: Knock on 3B
- **WHEN** the player stands at 3B's door and presses the talk key
- **THEN** Samantha's door SHALL open, she SHALL appear and walk out onto the landing, and her first line SHALL show her name as "???"

#### Scenario: The tour
- **WHEN** the dialogue reaches the kitchen, bedroom, window and landing beats
- **THEN** Samantha and the player SHALL walk to those places before her next line is shown, and she SHALL face the player when she speaks

#### Scenario: Choices are flavour only
- **WHEN** the player picks any option at one of the three choice points
- **THEN** the choice SHALL be stored in a `$r1_viewing_*` story variable and the scene SHALL continue on the same main line

#### Scenario: Scene cannot be abandoned mid-tour
- **WHEN** the player presses Escape during the viewing node
- **THEN** the dialogue SHALL stay open and the scene SHALL continue

### Requirement: End of the slice

After Samantha has gone back through her door at the end of the viewing, the game SHALL play the ending sequence with an end card saying the story continues ("To be continued") and a thanks line, and SHALL NOT show "- FIN -".

#### Scenario: Viewing ends
- **WHEN** the last line of the viewing has been continued
- **THEN** the screen SHALL fade to black around the player, the volume SHALL fade out, and the end card SHALL be written out
