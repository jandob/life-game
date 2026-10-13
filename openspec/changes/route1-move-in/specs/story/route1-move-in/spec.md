## ADDED Requirements

### Requirement: Moving day follows the viewing

After the viewing, the screen SHALL fade to black, a "Saturday. Moving day." card SHALL be shown, and the node `Route1MoveIn` SHALL start on the landing with Samantha waiting by her door. The scene SHALL end with the end card.

#### Scenario: Viewing hands over
- **WHEN** the viewing's last command has run
- **THEN** the screen SHALL fade out, the card SHALL show, the screen SHALL fade in on the landing and `Route1MoveIn` SHALL continue without player input to start it

#### Scenario: Callback to the viewing
- **WHEN** the player answered "The light" to "Why this one?" during the viewing
- **THEN** Samantha SHALL mention telling her father about the light

### Requirement: Move-in choices are recorded

The three choices of the scene SHALL be stored in `$r1_movein_keys`, `$r1_movein_socks` and `$r1_movein_rules` in the shared story variables.
