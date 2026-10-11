## ADDED Requirements

### Requirement: Male player sprite

The player SHALL be rendered from `assets/player/player.png`, which contains the male character in a 64x128-pixel cell grid of 10 columns by 12 rows, with idle, walking and running clips for the down, left, right and up directions at the same frame ranges as `CHARACTER_CLIPS`.

#### Scenario: Player appears male
- **WHEN** the game enters the `Gaming` state
- **THEN** the player SHALL spawn at the `SpawnPoint` using the male sprite sheet

#### Scenario: Player animation per direction and state
- **WHEN** the player walks, runs or idles in any of the four directions
- **THEN** the clip shown SHALL be the one returned by the shared `character_clip` helper for that direction and state

### Requirement: Dialogue addresses the player as male

Dialogue lines that address the player by gender SHALL use male forms.

#### Scenario: Jotem's greeting
- **WHEN** the player first talks to Jotem
- **THEN** Jotem SHALL say "Greetin's, young lad."
