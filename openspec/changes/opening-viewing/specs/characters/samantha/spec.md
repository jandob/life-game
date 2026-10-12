## ADDED Requirements

### Requirement: Samantha spawn

The system SHALL spawn Samantha, the landlord's daughter, from an object named `Samantha` in the Tiled `NPCs` layer, at the object's position (sprite centre). If the object has the bool property `hidden = true`, she SHALL start invisible and without an active collider.

#### Scenario: Hidden behind her door
- **WHEN** `route1_flat.tmj` loads with the `Samantha` object marked `hidden`
- **THEN** she SHALL exist but not be drawn, and the player SHALL be able to stand where she is without colliding

#### Scenario: Shown by the scene
- **WHEN** the dialogue runs `<<show Samantha>>`
- **THEN** she SHALL be drawn and her feet collider SHALL block the player

### Requirement: Samantha sprite sheet

Samantha SHALL be rendered from `assets/library/characters/samantha/samantha.png`, a 64x128-pixel cell grid of 10 columns by 12 rows in the same layout and frame ranges as `CHARACTER_CLIPS` (idle rows 0–3, walk rows 4–7, run rows 8–11, in the order down, left, right, up), drawn at scale 0.5 with her feet aligned to a ball collider at the same offset as the player's. Until that file exists, the game SHALL use the wanderer sheet as a placeholder.

#### Scenario: Walking and idling
- **WHEN** she walks along a scripted path
- **THEN** she SHALL play the walk clip for her direction of travel
- **WHEN** she stands still
- **THEN** she SHALL play the idle clip for her last facing direction

### Requirement: Samantha is moved only by the script

Samantha SHALL be a kinematic body that moves only through scripted commands. She SHALL never be pushed by the player, she SHALL push the player aside when her path crosses him, and she SHALL change facing only through `walk` and `face` commands.

#### Scenario: Player in her way
- **WHEN** the player stands on her scripted path
- **THEN** she SHALL keep walking and the player SHALL be pushed aside, and the scene SHALL NOT stall

### Requirement: Samantha portrait

Lines spoken by Samantha SHALL show her portrait `assets/library/portraits/samantha.png` (64x64), with the `pai.png` portrait as a placeholder until that file exists, regardless of whether her name is displayed as "???" or "Samantha".

#### Scenario: Before she introduces herself
- **WHEN** a line is spoken by `_Samantha`
- **THEN** the name box SHALL show "???" and her portrait
