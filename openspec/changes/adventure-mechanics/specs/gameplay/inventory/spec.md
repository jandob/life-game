## ADDED Requirements

### Requirement: Items as story variables

An item SHALL be a Yarn bool variable `$item_<id>` declared in `assets/dialogue/items.yarn`, with a name and description in the item table. The player SHALL carry the item while the variable is true.

#### Scenario: Item checks in Yarn
- **WHEN** a node has `-> Give her the bag <<if $item_bakery_bag>>`
- **THEN** the option SHALL be offered only while he carries the bag

### Requirement: Inventory panel

`I` SHALL open a panel listing the carried items with name and description, or "Nothing." when empty. While it is open the player SHALL not walk or start a conversation. `I`, E or Escape SHALL close it.

#### Scenario: Sunday morning
- **WHEN** the player presses `I` on Sunday morning
- **THEN** the panel SHALL list the blush socks and the bakery bag

### Requirement: New item notice

When an item variable becomes true during play, a short notice "Got: NAME" SHALL show.

#### Scenario: Socks on moving day
- **WHEN** Samantha gives him the socks on moving day
- **THEN** "Got: Blush socks" SHALL show
