## ADDED Requirements

### Requirement: The croissant scene follows moving day

After moving day, the screen SHALL fade to black, a "Sunday morning." card SHALL be shown, and the node `Route1Croissant` SHALL start on the landing with the player by the stairs and Samantha hidden behind her door. The scene SHALL end with the end card.

#### Scenario: Moving day hands over
- **WHEN** moving day's last command has run
- **THEN** the screen SHALL fade out, the card SHALL show, the screen SHALL fade in on the landing and `Route1Croissant` SHALL continue without player input to start it

#### Scenario: Callback to her rules
- **WHEN** the player answered "And if I knock?" to her rules on moving day
- **THEN** Samantha SHALL first say from behind her door that she is deciding whether she's home

### Requirement: Croissant choices are recorded

The three choices of the scene SHALL be stored in `$r1_croissant_bag`, `$r1_croissant_socks` and `$r1_croissant_dinner` in the shared story variables.
