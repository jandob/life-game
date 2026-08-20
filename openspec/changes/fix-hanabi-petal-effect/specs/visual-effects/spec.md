## MODIFIED Requirements

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