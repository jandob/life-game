## Context

The sakura petal particle effect is implemented using `bevy_hanabi` v0.19 in `src/world/map/flora.rs`. The current `build_petal_effect()` function creates an `EffectAsset` with a particle velocity model that has a strong directional bias: a constant drift of `(21.0, -10.5, 0)` pixels/second (from `7.0 * Vec3::new(3.0, -1.5, 0.0)`). In practice this launches all particles off-screen almost instantly — the effect is not visible. The spawn rate is 2 particles/second, which compounds the invisibility. See `proposal.md - Why` for motivation.

## Goals / Non-Goals

**Goals:**
- Fix the particle velocity to produce multi-directional outward spread from the tree position with gentle downward drift and visible wobble over the particle lifetime
- Increase spawn rate to produce a visually continuous shower of petals (≥3 particles/second)
- Rename all "pedal" typos to "petal" throughout the codebase
- All fixes must be compatible with bevy_hanabi v0.19 and the existing `EffectAsset`/`ExprWriter` API — no dependency upgrades

**Non-Goals:**
- Changing the particle texture, color gradient, or size modulation — these work correctly
- Adding new particle effect types or modifying other visual effects
- Refactoring the flora spawning or chunk management systems
- Upgrading bevy_hanabi or bevy engine versions

## Decisions

### Decision: Multi-directional outward velocity instead of constant vector

**Current**: `7.0 * Vec3::new(3.0, -1.5, 0.0) + random_wobble` — all particles go rightward + downward.

**Change**: Replace the constant drift with a direction that varies per particle using a random angle. The velocity formula will compute:
- Direction: random angle (0–2π) for the horizontal spread component, plus a constant downward component
- Speed: moderate magnitude (~20–40 px/s) split between outward and downward
- Wobble: add a sinusoidal time-varying lateral offset using `writer.rand()` re-evaluated each frame (or a noise-based wobble via `SetPositionSphereModifier` or explicit sine expression)

**Rationale**: This directly matches the spec's "drift outward and downward with a gentle wobble" — outward requires random directions, downward is a constant bias, and wobble needs oscillation.

**Alternatives considered:**
- Using `SetPositionSphereModifier` for spawn position (already handled separately) — not applicable for velocity
- Using `bevy_hanabi`'s noise module — not available in v0.19 ExprWriter API; random re-evaluation on each frame through `writer.rand()` provides a flutter effect that looks like wobble

### Decision: Increase spawn rate to 4 particles/second

**Current**: `SpawnerSettings::rate(2.0.into())`.

**Change**: `SpawnerSettings::rate(4.0.into())`.

**Rationale**: 2 particles/second produces a sparse, easily-missable effect. 4 particles/second (one every ~250ms) gives a visible continuous shower while remaining lightweight. The pool of 32768 particles remains more than adequate.

### Decision: Rename "pedal" → "petal" everywhere

**Current identifiers to rename:**
- Component `SakuraPedal` → `SakuraPetal`
- Effect name `"sakura_pedal"` → `"sakura_petal"`
- Texture slot name `"pedal"` → `"petal"`
- Variable `tree_pedals` → `tree_petals`
- Asset field `tree_pedal` → keep as-is if it references an asset file name; only rename the Rust identifier if a corresponding field rename is done in `GameAssets`

**Rationale**: Correct spelling is important for readability. The struct name, effect name, and texture slot are all internal to the effect system and renaming them has no external impact.

### Decision: Add wobble via per-frame random velocity perturbation

Since `bevy_hanabi` v0.19's `ExprWriter` does not expose a time-based sine function, the simplest approach to produce a visible wobble is to add a random perturbation to the velocity each frame. The `writer.rand()` expression in a `SetAttributeModifier` on `VELOCITY` (set as a continuous modifier rather than just init) would re-evaluate each frame, producing a flutter effect. However, `SetAttributeModifier` on velocity is typically an init-only modifier.

**Alternative wobble approach**: Use `LinearDragModifier` with a random initial velocity spread — particles will decelerate at different rates, creating apparent wandering. Or, use a wider initial velocity spread in random directions with a small initial speed — the lack of drag means particles continue on their initial trajectory, but the random spread creates the visual impression of drifting.

**Chosen approach**: Increase the random component of the velocity expression to be proportional to the main velocity direction, so each particle gets a unique direction and speed that varies within a range. The wobble effect will come from using the `init_age` randomization combined with the color fade — particles at different life stages with different velocities create a natural-looking dispersed cloud.

## Risks / Trade-offs

- [Visual quality] Removing the constant drift entirely may make petals feel directionless. **Mitigation**: Keep a gentle downward bias in all velocity vectors so petals always fall, and keep total magnitude low enough that particles remain on-screen near the tree.
- [Performance] Increasing spawn rate from 2 to 4 particles/second doubles particle throughput, but each particle lives <3s and the pool is 32768. **Mitigation**: The pool is more than sufficient (~12 active particles per tree); keep spawn rate modest to avoid unnecessary draw calls.
- [Renaming] Renaming `SakuraPedal` component may affect other systems querying for it. **Mitigation**: Only `spawn_tree` creates and uses this component; grep for all references before renaming.