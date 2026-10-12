## MODIFIED Requirements

### Requirement: Male player sprite

The player SHALL be rendered from `assets/library/characters/player/player.png`, which contains the male character with realistic proportions in the realistic character sheet format (96x192-pixel cells, 10 columns by 12 rows, drawn at scale 1.0, feet on row 157), with idle, walking and running clips for the down, left, right and up directions at the same frame ranges as `CHARACTER_CLIPS`.

#### Scenario: Player appears male
- **WHEN** the game enters the `Gaming` state
- **THEN** the player SHALL spawn at the `SpawnPoint` using the male sprite sheet

#### Scenario: Player animation per direction and state
- **WHEN** the player walks, runs or idles in any of the four directions
- **THEN** the clip shown SHALL be the one returned by the shared `character_clip` helper for that direction and state
