## Purpose

Defines the observable behavior of the game's sprite animations and particle effects — which animations exist, how they play, and how flora particle effects render — as a contract that must be preserved across engine upgrades and rendering subsystem changes.

## Requirements

### Requirement: Player movement animations

The player character SHALL have idle, walking, and running animations, each with separate variants for the four facing directions (down, left, right, up). The player SHALL play the idle animation for its current facing direction when not moving, the walking animation while moving at walking speed, and the running animation while sprinting. The facing direction SHALL determine which direction variant plays.

#### Scenario: Player stands still
- **WHEN** the player is not moving
- **THEN** the idle animation for the player's facing direction plays and loops

#### Scenario: Player walks
- **WHEN** the player moves at walking speed
- **THEN** the walking animation for the player's facing direction plays and loops

#### Scenario: Player sprints
- **WHEN** the player moves at running speed
- **THEN** the running animation for the player's facing direction plays and loops

#### Scenario: Facing direction changes
- **WHEN** the player's facing direction changes while an animation is playing
- **THEN** the animation switches to the variant for the new direction

### Requirement: NPC idle animations

Each NPC (eleonore, jotem, isabelle, antonius, ionas) SHALL continuously play its idle animation while present in the world.

#### Scenario: NPC spawns
- **WHEN** an NPC spawns into the world
- **THEN** its idle animation plays and loops for as long as it is present

### Requirement: UI hint animations

The dialogue start hint overlay and the keyboard key icons (down, up, left, right, shift) SHALL play their animations continuously while visible.

#### Scenario: Dialogue start hint visible
- **WHEN** the dialogue start hint is displayed
- **THEN** its animation plays and loops until the hint is hidden

#### Scenario: Key icons visible
- **WHEN** a keyboard key icon is displayed
- **THEN** its animation plays and loops while the icon is visible

### Requirement: Flora particle effects

Sakura petal particles SHALL spawn continuously from flora trees, drift outward from the tree position in a random spread of directions, drift downward at a gentle speed, exhibit a visible wobble (sinusoidal or noise-based lateral oscillation) over their lifetime, fade in from transparent at spawn and fade out to transparent before despawning, and render above other world sprites. Particles SHALL despawn with their source flora entity when it is removed. The spawn rate SHALL produce a visually continuous shower of at least 3 particles per second.

#### Scenario: Tree with petals present
- **WHEN** a flora tree with particle effects is present in the world
- **THEN** sakura petal particles spawn continuously at its position, drift in random outward directions and downward with a gentle wobble, and fade in and out over their short lifetime

#### Scenario: Petal motion is multi-directional
- **WHEN** sakura petal particles are observed over their lifetime
- **THEN** individual particles travel in different outward directions from the tree (not all in the same horizontal direction), drift downward, and oscillate laterally with a visible wobble

#### Scenario: Flora entity removed
- **WHEN** a flora tree entity is despawned
- **THEN** its active petal particles are removed from the world