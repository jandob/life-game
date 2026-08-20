## Why

The sakura petal particle effect (powered by bevy_hanabi) is not visible at all. The velocity expression `7.0 * Vec3::new(3.0, -1.5, 0.0) + rand * Vec3::new(4.0, 2.5, 0.0)` produces a constant rightward/downward velocity of ~21 px/s, which launches all petals off-screen instantly. This breaks the visual-effects spec's "drift outward and downward with a gentle wobble" contract. Even at the intended speed, the current hard-coded direction would prevent multi-directional outward spread.

## What Changes

- Fix the petal particle velocity model so that petals are visible and drift outward in random directions from the tree position, drift downward gently, and wobble naturally over their lifetime (currently they fly off-screen instantly)
- Tweak the spawn rate to produce a visually pleasing continuous shower of petals (currently ~2 particles/second is sparse)
- Fix naming typos: "pedal" → "petal" throughout the codebase (struct `SakuraPedal`, effect name `sakura_pedal`, texture slot `pedal`)
- Clarify the flora particle effects requirement in the visual-effects spec to be more precise about the expected particle motion (outward spread, gentle drift, wobble)

## Capabilities

### New Capabilities

- None

### Modified Capabilities

- `visual-effects`: Clarify the "Flora particle effects" requirement, specifically the sakura petal particle behavior — drift direction, wobble, spawn rate, and lifetime characteristics

## Impact

- `src/world/map/flora.rs`: The `build_petal_effect()` function and `spawn_tree()` function
- `openspec/specs/visual-effects/spec.md`: Clarified requirement for petal motion behavior
- All identifiers using "pedal" renamed to "petal" (struct, effect name, texture slot, variables)