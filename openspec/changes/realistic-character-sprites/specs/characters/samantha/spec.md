## MODIFIED Requirements

### Requirement: Samantha sprite sheet

Samantha SHALL be rendered from `assets/library/characters/samantha/samantha.png` in the realistic character sheet format (96x192-pixel cells, 10 columns by 12 rows, in the same layout and frame ranges as `CHARACTER_CLIPS`: idle rows 0–3, walk rows 4–7, run rows 8–11, in the order down, left, right, up), drawn at scale 1.0 with her feet on row 157 and her feet collider at the same world offset as the player's. She SHALL be a few rows shorter than the player.

#### Scenario: Walking and idling
- **WHEN** she walks along a scripted path
- **THEN** she SHALL play the walk clip for her direction of travel
- **WHEN** she stands still
- **THEN** she SHALL play the idle clip for her last facing direction
