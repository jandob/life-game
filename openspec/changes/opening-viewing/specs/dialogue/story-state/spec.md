## ADDED Requirements

### Requirement: Shared persistent story variables

All dialogue runners SHALL share one game-wide Yarn variable storage that is created fresh when a playthrough starts. Values set in one conversation, including node visit counts, SHALL remain available in later conversations and after the runner that set them has been despawned. Creating a new runner SHALL NOT reset variables that the story has already set.

#### Scenario: Value survives the end of a conversation
- **WHEN** a conversation sets `$r1_viewing_opening` to "nervous" and completes
- **THEN** a later conversation, and Rust code reading the story variables, SHALL see "nervous"

#### Scenario: New runner does not reset values
- **WHEN** a new dialogue runner is created after a story variable was changed from its declared default
- **THEN** the variable SHALL keep the changed value

### Requirement: Speaker table

The dialogue UI SHALL look up the portrait and the typewriter speed of a line's speaker through a single speaker table keyed by the Yarn character name with a leading `_` removed. `You` SHALL map to the player and show the player portrait. Names not in the table SHALL keep the previous portrait and the average speed.

#### Scenario: Player line
- **WHEN** a line is spoken by `You`
- **THEN** the player portrait SHALL be shown (with `pai.png` as a placeholder until `portraits/player.png` exists)

### Requirement: Yarn conventions are checked

The test suite SHALL check every `.yarn` file directly under `assets/dialogue/` for: unique node titles across files, jumps only to nodes in the same file, no narrator lines, every node's first dialogue line being a non-player line, speaker name variables being declared in the file, custom command names (`stop_chat`, `end_demo`, `walk`, `await_walks`, `face`, `show`, `hide`, `open_door`, `close_door`) without typos, and scripted commands having the expected number of arguments. Files in subdirectories such as `assets/dialogue/forest/` SHALL NOT be checked.

#### Scenario: Misspelled command
- **WHEN** a Yarn file contains `<<walkk Samantha ToKitchen>>`
- **THEN** `cargo test` SHALL fail and name the closest valid command
