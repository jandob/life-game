## ADDED Requirements

### Requirement: Looks and clip strips

A character SHALL have one or more named looks. A look SHALL be a folder containing a manifest and one PNG strip per clip. Every strip SHALL use 128x256-pixel cells with the figure centred horizontally and the lowest opaque row of the feet on one fixed row, drawn at scale 1.0. A strip SHALL be at most 2048 px on each side.

#### Scenario: Adding a clip
- **WHEN** a new clip strip and its manifest entry are added to a look
- **THEN** no other strip of any look SHALL need to change

### Requirement: Clip set and direction rules

Every look SHALL provide `idle` with four directions (front, left, right, back) and `walk` facing right. A clip MAY be mirrored for left through its manifest flag. A look MAY omit any other clip. The game SHALL NOT require vertical walk clips: moving up or down SHALL play `walk` facing the last horizontal direction.

#### Scenario: Walking left
- **WHEN** a character with a mirrored walk clip moves left
- **THEN** the right-facing walk SHALL play flipped horizontally and the figure SHALL NOT shift sideways

### Requirement: Clip fallback

When a look lacks a requested clip, the game SHALL use the same clip of the character's default look, then `idle` of the same facing.

#### Scenario: Missing clip
- **WHEN** a look without a `sit` clip is asked to sit
- **THEN** the default look's `sit` SHALL play, and if that is missing too, idle SHALL play

### Requirement: Look change resets animation state

Changing a character's look SHALL swap its image, atlas layout and clip together and reset the frame index and horizontal flip.

#### Scenario: Look swap mid-walk
- **WHEN** a character switches look while walking
- **THEN** the new look's walk SHALL start on frame 0 with the correct flip
