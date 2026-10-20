## ADDED Requirements

### Requirement: Action popup

When a conversation presents options before any line, the game SHALL show them as a popup without the dialogue box. If exactly one option is available, it SHALL be selected at once without showing anything. If none is available, the conversation SHALL end. The dialogue box SHALL appear with the first line.

#### Scenario: Two actions at a door
- **WHEN** the player presses E at Samantha's door on Sunday morning
- **THEN** a popup SHALL offer "Knock" and "Look", and picking "Knock" SHALL start the croissant scene

#### Scenario: One action
- **WHEN** a target's node has only one available option
- **THEN** that option SHALL run directly, as before this change

### Requirement: Escape forgets a popup

Escape on a popup SHALL close it, and the next E SHALL start the target's node again from the top.

#### Scenario: Re-checked actions
- **WHEN** the player escapes a popup and presses E at the same target again
- **THEN** the popup SHALL list the actions available now
