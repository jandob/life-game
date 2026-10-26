## ADDED Requirements

### Requirement: The chart is declared in Yarn

Each chapter SHALL have one node tagged `chart` that is never run. It SHALL hold one `<<chapter ID "CARD">>`, any number of `<<gate ID "LABEL" REQUIRES...>>` and exactly one `<<bottleneck ID "LABEL" REQUIRES...>>`. Chapters SHALL be cases of the Yarn enum `Chapter`, in story order. Every gate and bottleneck SHALL have a declared `$gate_<ID>` bool.

#### Scenario: A gate with requirements
- **WHEN** the chart of the second Thursday holds `<<gate r1_thu2_door "Knock on 3A" r1_thu2_wine>>`
- **THEN** `$gate_r1_thu2_door` SHALL be declared, and it SHALL only become true while `$gate_r1_thu2_wine` is true

### Requirement: The chart is well-formed

A test SHALL fail when a gate is not declared, is never set to true outside chart nodes, or is not required (directly or through other gates) by its chapter's bottleneck. It SHALL also fail when a requirement names an unknown gate or a gate of a later chapter, when requirements form a cycle, or when a chapter does not have exactly one start node.

#### Scenario: A forgotten gate
- **WHEN** a chart declares a gate that no node sets
- **THEN** the test SHALL fail and name the gate

### Requirement: Chapters start in their start node

The start node of a chapter SHALL be the only node that sets `$chapter` to it. It SHALL show the chapter's card and add an open note with the chapter's goal. The bottleneck's action SHALL start the next chapter's start node. In the last written chapter it SHALL end the demo. No other `<<next_scene>>` SHALL start a node of another chapter.

#### Scenario: Going to bed
- **WHEN** every gate of a chapter is done and the player uses the bed
- **THEN** the next chapter's card SHALL show and her text with its goal SHALL arrive

### Requirement: Story conditions read the chart state

Conditions in route files SHALL read `$chapter`, `$gate_*`, `$item_*` and route flags. They SHALL not use `visited()`.

#### Scenario: Her door on two Thursdays
- **WHEN** the player uses her door
- **THEN** which Knock is offered SHALL depend only on `$chapter` and the chapter's gates

### Requirement: Every chapter can be finished in any order

For every chapter a walk of all player actions (every available popup option of every hotspot node, and reading every pending text) SHALL show the following. Every gate can be reached. No gate is set while a requirement is false. From every reachable state the bottleneck can still be reached. An open note exists in every state before the bottleneck. The bottleneck leads to the next chapter's start. A chapter whose walk exceeds the state cap SHALL fail with its state count.

#### Scenario: A dead end
- **WHEN** an action can use up an item that a later gate needs, with no way to get it again
- **THEN** the walk check SHALL fail and print the action path that leads to the dead end

### Requirement: There is no skip

The bottleneck's action SHALL only be available when its requirements are met. Before that, the same object SHALL give a line that it is too early. Wrong actions SHALL get a line and SHALL not change the chapter or set a gate.

#### Scenario: Bed too early
- **WHEN** the player uses the bed before her text has been read
- **THEN** he SHALL say it is too early, and the chapter and its gates SHALL stay as they were

### Requirement: Chapter start points

Every chapter SHALL have a start point that replays the walker's shortest path to its start node. `--set gate_<ID>=true` SHALL work on top of it for points inside a chapter.

#### Scenario: Starting at the second Thursday
- **WHEN** the game starts with `--start r1thu2`
- **THEN** the second Thursday's card SHALL show and her riddle SHALL be unread, with all earlier gates set

### Requirement: The chart can be drawn

`dialogue_graph` SHALL write one Graphviz file per chart file. It SHALL draw one cluster per chapter, labelled with the card, one box per gate with its label, an edge for every requirement, and the bottleneck in bold.

#### Scenario: Reading route 1
- **WHEN** `dialogue_graph` runs
- **THEN** `graphs/chart_route1.dot` SHALL show route 1's chapters in story order
