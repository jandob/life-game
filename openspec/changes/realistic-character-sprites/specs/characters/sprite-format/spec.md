## ADDED Requirements

### Requirement: Realistic character sheet format

A character with realistic art SHALL be rendered from a 960x2304 RGBA sheet of 96x192-pixel cells, 10 columns by 12 rows, in the row order and frame ranges of `CHARACTER_CLIPS` (idle rows 0–3, walk rows 4–7, run rows 8–11, each in the order down, left, right, up). The sprite SHALL be drawn at scale 1.0, so one sheet pixel is one world pixel, the same as a tile pixel. In every cell the figure SHALL be centred horizontally with the lowest opaque row of the feet on row 157. A standing adult man SHALL be 132 rows tall (±2) and a standing adult woman about 126 rows.

#### Scenario: Same pixel size as the room
- **WHEN** a realistic character stands next to a door on a 48 px tile map
- **THEN** one character pixel and one tile pixel SHALL cover the same number of screen pixels

#### Scenario: Same height in every frame
- **WHEN** a realistic character's idle and walk clips play in any direction
- **THEN** the standing height and head size SHALL NOT change by more than 2 rows between frames

### Requirement: Feet collider in world units

Every character's feet collider SHALL be a ball of radius 24 world px whose centre is 48 world px below the sprite centre, whatever scale its sheet is drawn at.

#### Scenario: Realistic and legacy characters collide alike
- **WHEN** a character drawn at scale 1.0 and one drawn at scale 1.5 stand on the same spot
- **THEN** their colliders SHALL have the same world radius and centre
