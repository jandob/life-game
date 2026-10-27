## ADDED Requirements

### Requirement: Boxes are declared in Yarn

Each box SHALL have one node tagged `graph` that is never run. It SHALL hold one `<<box ID "LABEL" ENTRY_NODE [PARENT]>>`, any number of `<<gate>>`, `<<choice>>` and `<<option>>`, and at least one `<<exit ID "LABEL" REQ... TARGET>>`. A requirement SHALL be a node id of the same box, `CHOICE=OPTION`, or ids joined by `|` (any one).

#### Scenario: Two ways to her door
- **WHEN** a box holds `<<gate door "Knock on her door" wine|socks>>`
- **THEN** knocking SHALL need either gate, and the box's diagram SHALL draw two dashed edges into it

### Requirement: A box always starts the same way

Entering a box SHALL reset every `$<box>_*` variable to its default. A node SHALL only read or write another box's variables inside `<<if $box == "<ID>">>`.

#### Scenario: Looping back
- **WHEN** an exit leads back to a box the player has played before
- **THEN** the box SHALL start exactly as on the first visit

### Requirement: The graph checks hold

A test SHALL fail when ids are duplicated or unknown, a box has a cycle, a box has no exit or two exits to the same box, some reachable local state of a box can no longer reach an exit, some node is unreachable, some box can no longer reach an ending, or a box has more than `X_MAX` exits or `N_MAX` nodes. It SHALL report, without failing, the choices whose options lead to the same nodes and the number of choices per box.

#### Scenario: A branch with no way out
- **WHEN** picking an option leads to gates from which no exit can be reached
- **THEN** the test SHALL fail and name the box and the option

### Requirement: The scenes match the graph

A test SHALL fail when a gate or choice is set in a node whose conditions do not read its requirements, when a choice gets a value that is not one of its options, or when a node starts another box's node other than through an exit.

#### Scenario: A gate set too early
- **WHEN** a scene sets `$r1thu2_gate_door` with no condition reading `$r1thu2_gate_wine` or `$r1thu2_gate_socks`
- **THEN** the test SHALL fail and name the node

### Requirement: Start points start boxes

`--start <box>` SHALL set `$box` and run the box's entry node, with no replay.

#### Scenario: Starting the second Thursday
- **WHEN** the game starts with `--start R1Thu2`
- **THEN** the second Thursday SHALL start exactly as when reached by playing

### Requirement: Diagrams are generated from the Yarn

`dialogue_graph` SHALL write a story-level diagram (boxes and exits) per route and one diagram per box (gates, choices with labelled options, "all of" and "any of" edges, entry and exits), from the graph nodes only.

#### Scenario: Reading route 1
- **WHEN** `dialogue_graph` runs
- **THEN** `graphs/story_route1.dot` and one `graphs/box_<ID>.dot` per route 1 box SHALL be written

## REMOVED Requirements

### Requirement: Every chapter can be finished in any order
**Reason**: The walker does not scale. Replaced by the graph checks and the link checks.

### Requirement: Chapter start points
**Reason**: A box always starts the same way, so start points run its entry node directly.
