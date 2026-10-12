## MODIFIED Requirements

### Requirement: NPC idle animations

Each visible NPC SHALL continuously play an idle animation while it is not walking. NPCs that use the four-direction character sheet layout (`CHARACTER_CLIPS`) SHALL play the idle clip for their current facing direction.

#### Scenario: NPC spawns
- **WHEN** an NPC spawns into the world
- **THEN** its idle animation plays and loops for as long as it is present and not walking

#### Scenario: Four-direction NPC changes facing
- **WHEN** a four-direction NPC's facing changes while it stands still
- **THEN** the idle clip for the new direction plays
