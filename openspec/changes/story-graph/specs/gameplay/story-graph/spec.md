## ADDED Requirements

### Requirement: The story graph is declared in Yarn

Each chapter SHALL have one node tagged `graph` that is never run. It SHALL hold one `<<chapter ID "CARD">>`, any number of `<<gate ID "LABEL" REQ...>>`, `<<choice ID "LABEL" REQ...>>` and `<<option CHOICE KEY "LABEL">>`, and exactly one `<<bottleneck ID "LABEL" REQ...>>`. A requirement SHALL be a gate id, `CHOICE=KEY`, or alternatives joined by `|`, and it MAY name its own or an earlier chapter.

#### Scenario: Two ways to her door
- **WHEN** the graph holds `<<gate r1_thu2_door "Knock on 3A" r1_thu2_wine|r1_thu2_socks>>`
- **THEN** knocking SHALL need either gate, and the graph SHALL draw two dashed edges into it

### Requirement: The graph is well-formed

A test SHALL fail when an id is duplicated, a requirement names an unknown or later node, requirements form a cycle, an option names an unknown choice, or a chapter does not have exactly one start node.

#### Scenario: An option of a missing choice
- **WHEN** a graph holds `<<option r1_thu2_riddl wine "Wine again?">>`
- **THEN** the test SHALL fail and name the option

### Requirement: The graph is walkable

For every combination of picks the player can reach, every chapter's bottleneck SHALL still be reachable, and every gate and option SHALL be reachable by some combination. A failure SHALL name the picks that strand the player.

#### Scenario: A branch with no way out
- **WHEN** picking `ask` leads to a gate that nothing after it requires and the bottleneck needs `r1_thu2_wine`
- **THEN** the test SHALL fail and name `r1_thu2_riddle=ask`

### Requirement: Every choice is meaningful

For every choice, each option SHALL make reachable or required at least one gate or option that no other option of that choice does.

#### Scenario: A choice that changes nothing
- **WHEN** both options of a choice lead to the same gates
- **THEN** the test SHALL fail and name the choice

### Requirement: The scenes match the graph

A test SHALL fail when a gate is set to true outside conditions that read its requirements, when an option is never assigned or a choice variable gets an undeclared value, or when a menu in a route file has a branch that sets no choice and is not in a node tagged `flavour`.

#### Scenario: A gate set too early
- **WHEN** a scene sets `$gate_r1_thu2_door` without its conditions reading `$gate_r1_thu2_wine` or `$gate_r1_thu2_socks`
- **THEN** the test SHALL fail and name the node

### Requirement: Start points come from the graph

A start point SHALL name a chapter or a gate. It SHALL set every gate and choice the target needs and everything in earlier chapters, picking each choice's first option unless `--set choice_<id>=<key>` picks another, and then run the chapter's start node.

#### Scenario: Starting the second Thursday on the socks branch
- **WHEN** the game starts with `--start r1thu2 --set choice_r1_thu2_riddle=ask`
- **THEN** the second Thursday SHALL start with the riddle answered `ask`, and the shop SHALL not sell the wine

### Requirement: The graph can be drawn

`dialogue_graph` SHALL write `graphs/graph_<route>.dot` with one cluster per chapter, boxes for gates, bold bottlenecks, diamonds for choices with one labelled edge per option, solid edges for required nodes, dashed edges for alternatives and dotted edges across chapters.

#### Scenario: Reading route 1
- **WHEN** `dialogue_graph` runs
- **THEN** `graphs/graph_route1.dot` SHALL show the riddle as a diamond with two labelled edges that meet again at her door

## REMOVED Requirements

### Requirement: Every chapter can be finished in any order
**Reason**: The walker does not scale. Replaced by the graph checks and the scene link checks.

### Requirement: Chapter start points
**Reason**: Start points now set state from the graph instead of replaying the walker's path.
