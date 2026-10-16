## ADDED Requirements

### Requirement: Sunday morning is played on the landing

After moving day, the screen SHALL fade to black, a "Sunday morning." card SHALL be shown, and the player SHALL get control on the landing by the stairs, with Samantha hidden behind her door. The croissant scene SHALL start only when the player knocks on 3A. The scene SHALL end with the end card.

#### Scenario: Control after the time skip
- **WHEN** moving day's last line has been read
- **THEN** the player SHALL be able to walk on the landing, and no conversation SHALL be active

#### Scenario: Knocking on her door
- **WHEN** the player interacts with 3A on Sunday morning
- **THEN** `Route1Croissant` SHALL start

#### Scenario: His own door first
- **WHEN** the player interacts with 3B on Sunday morning
- **THEN** he SHALL say a line that points him to her door, and no scene SHALL start

#### Scenario: Callback to her rules
- **WHEN** the player answered "And if I knock?" to her rules on moving day
- **THEN** Samantha SHALL first say from behind her door that she is deciding whether she's home

### Requirement: Croissant choices are recorded

The three choices of the scene SHALL be stored in `$r1_croissant_bag`, `$r1_croissant_socks` and `$r1_croissant_dinner` in the shared story variables.

### Requirement: Talk targets are chosen by story state and distance

Each door interactable SHALL start a dispatcher node that picks its scene or line from `visited()`. When several talk targets are in range, the nearest one SHALL be used and the start hint SHALL be shown over it.

#### Scenario: Viewing still starts from 3B
- **WHEN** the game has just started and the player interacts with 3B
- **THEN** `Route1Viewing` SHALL start
