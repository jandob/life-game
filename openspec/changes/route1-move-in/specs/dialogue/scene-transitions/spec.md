## ADDED Requirements

### Requirement: Scene hand-over

`<<next_scene NODE>>` SHALL start `NODE` after the current dialogue completes. While a scene is queued, the player SHALL stay in the talking state and SHALL NOT start another conversation. If the node cannot start, an error SHALL be logged and the screen SHALL be cleared.

#### Scenario: Interact during the hand-over
- **WHEN** the player presses the talk key next to the 3B door between the viewing and moving day
- **THEN** the viewing SHALL NOT start again

### Requirement: Fades and title cards

`<<fade_out>>` and `<<fade_in>>` SHALL fade a black overlay over the world and dialogue box to opaque or clear, holding the dialogue until done. `<<card "TEXT">>` SHALL show the text on the overlay for a moment, holding the dialogue. Both SHALL run on real time. The end card text SHALL stay above the overlay.

### Requirement: Placing actors

`<<place ACTOR PATH>>` SHALL put the actor on the first point of the path at once and end any walk of that actor, releasing anything waiting on it. Unknown actors or paths SHALL log an error and do nothing.
