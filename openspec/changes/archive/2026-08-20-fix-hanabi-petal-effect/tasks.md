## 1. Fix Petal Velocity Model

- [x] 1.1 Replace the constant velocity vector with a random-angle outward spread expression using `ExprWriter` — generate a random direction (0–2π) per particle for the horizontal component, combined with a gentle downward bias
- [x] 1.2 Ensure velocity magnitude keeps particles on-screen near the tree (~20–40 px/s outward + downward, not 21 px/s purely rightward)
- [x] 1.3 Add wobble via a wider random velocity perturbation or per-frame random flutter (e.g., `writer.rand()` re-evaluated on each frame via a continuous modifier if available, or a wide initial spread with drag)
- [x] 1.4 Verify the effect is visible in-game — particles should appear as a drifting cloud around the tree crown

## 2. Adjust Spawn Rate

- [x] 2.1 Change `SpawnerSettings::rate(2.0.into())` to `SpawnerSettings::rate(4.0.into())` for a visibly continuous shower
- [x] 2.2 Verify the rate increase does not cause performance issues or excessive particle counts

## 3. Rename "pedal" → "petal" Typos

- [x] 3.1 Rename `SakuraPedal` component struct to `SakuraPetal`
- [x] 3.2 Rename effect name `"sakura_pedal"` to `"sakura_petal"` in `build_petal_effect()`
- [x] 3.3 Rename texture slot name `"pedal"` to `"petal"` in `module.add_texture_slot()`
- [x] 3.4 Rename variable `tree_pedals` to `tree_petals` in `spawn_tree()`
- [x] 3.5 Check `GameAssets` struct for `tree_pedal` field and rename if present
- [x] 3.6 Verify the project compiles and runs after all renames

## 4. Fix Particle Rendering (z-ordering & shader issues)

- [x] 4.1 Fix `LinearDragModifier` drag parameter — was `Vec3` expression causing shader error, now scalar `f32`
- [x] 4.2 Fix `PETAL_Z` from `100.0` to `-100.0` — particles were rendering behind the tree (negative z = closer to camera)
- [x] 4.3 Increase particle size from 0.5 world units (~1.5 px) to 16 screen-space pixels and set `screen_space_size: true`
- [x] 4.4 Increase spawn position box from 16×16 to 32×32 for better spread
- [x] 4.5 Increase velocity range from ±20 px/s to ±60 px/s for visible motion
- [x] 4.6 Reduce drag from 2.0 to 0.5 so particles drift for ~2s instead of stopping in 0.5s

## 5. Randomize Per-Tree Petal Patterns & Fix Stem Clipping

- [x] 5.1 Add random `prng_seed: Some(rng.gen())` per `ParticleEffect` instance so each tree produces different random particle patterns
- [x] 5.2 Make petal entity a standalone entity (not a child of the tree) at world position `(tree_x, tree_y, -100)` to avoid y-sort interaction and clipping behind stems
- [x] 5.3 Add `PetalSpawner(Entity)` component to Flora to track the petal entity for cleanup
- [x] 5.4 Update `despawn_flora_chunks`, `despawn_flora_around_start_hint`, and `despawn_flora_around_npcs` to also despawn the linked petal entity

## 6. Update Main Spec

- [x] 6.1 After the delta spec is archived, sync the clarified flora particle requirements from the delta spec into `openspec/specs/visual-effects/spec.md`