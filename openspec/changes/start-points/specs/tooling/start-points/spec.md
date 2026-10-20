## ADDED Requirements

### Requirement: Start at a story point

The game SHALL accept a start point name at launch (`--start NAME` natively, the `start`
URL query parameter on the web). With a known name it SHALL skip the main menu, set the
story variables and visit counts as if the scenes before the point had been played with
the first available option at every choice, restore the world state those scenes leave,
and then start the point's scene or hand the player control. With an unknown name it
SHALL log the available start points and start normally.

#### Scenario: Croissant scene
- **WHEN** the game is launched with `--start croissant`
- **THEN** the croissant scene SHALL start on the landing without the menu, and its
  moving-day callbacks SHALL read the first-option flags

### Requirement: Listing start points

`--start list` SHALL print every start point with a one-line description and exit; on
the web it SHALL log them to the console.

### Requirement: Overriding variables

`--set NAME=VALUE` SHALL set the Yarn variable after the fast-forward, typed like its
declaration. An unknown variable or a value of the wrong type SHALL be logged and skipped.
