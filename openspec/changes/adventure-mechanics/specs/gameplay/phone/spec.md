## ADDED Requirements

### Requirement: Texts

`<<phone NODE>>` SHALL deliver the text conversation NODE (a node tagged `phone`). The key hint SHALL show unread texts. `P` with an unread text SHALL play the oldest one in the dialogue box; it stays unread until it has completed. Her lines and his replies in `phone` nodes SHALL be kept in the phone's message history.

#### Scenario: Reading her text
- **WHEN** the player presses `P` on Sunday morning
- **THEN** her text SHALL play with his reply options, and afterwards the phone SHALL list it under Messages

### Requirement: Notes

`<<note ID "TEXT">>` SHALL add an open note or update its text, and `<<note_done ID>>` SHALL mark it done. The phone SHALL list open notes before done ones.

#### Scenario: Croissant note
- **WHEN** her Sunday text has been read
- **THEN** the phone SHALL list the open note to bring her the croissant, and the croissant scene SHALL tick it off

### Requirement: Phone panel

`P` without unread texts SHALL open the phone with notes and recent messages. While it is open the player SHALL not walk or start a conversation. `P`, E or Escape SHALL close it.

#### Scenario: Closing
- **WHEN** the phone is open and the player presses Escape
- **THEN** it SHALL close and the player SHALL walk again

### Requirement: Start points

Start points SHALL replay `note`, `note_done` and `phone` from the scenes they fast-forward. A replayed `phone` whose node is in the start point's played scenes SHALL not be pending.

#### Scenario: Sunday text
- **WHEN** the game starts at `sunday`
- **THEN** the phone SHALL show an unread text from Samantha
