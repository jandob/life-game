## 1. Fix Petal Velocity Model

- [ ] 1.1 Replace the constant velocity vector with a random-angle outward spread expression using `ExprWriter` — generate a random direction (0–2π) per particle for the horizontal component, combined with a gentle downward bias
- [ ] 1.2 Ensure velocity magnitude keeps particles on-screen near the tree (~20–40 px/s outward + downward, not 21 px/s purely rightward)
- [ ] 1.3 Add wobble via a wider random velocity perturbation or per-frame random flutter (e.g., `writer.rand()` re-evaluated on each frame via a continuous modifier if available, or a wide initial spread with drag)
- [ ] 1.4 Verify the effect is visible in-game — particles should appear as a drifting cloud around the tree crown

## 2. Adjust Spawn Rate

- [ ] 2.1 Change `SpawnerSettings::rate(2.0.into())` to `SpawnerSettings::rate(4.0.into())` for a visibly continuous shower
- [ ] 2.2 Verify the rate increase does not cause performance issues or excessive particle counts

## 3. Rename "pedal" → "petal" Typos

- [ ] 3.1 Rename `SakuraPedal` component struct to `SakuraPetal`
- [ ] 3.2 Rename effect name `"sakura_pedal"` to `"sakura_petal"` in `build_petal_effect()`
- [ ] 3.3 Rename texture slot name `"pedal"` to `"petal"` in `module.add_texture_slot()`
- [ ] 3.4 Rename variable `tree_pedals` to `tree_petals` in `spawn_tree()`
- [ ] 3.5 Check `GameAssets` struct for `tree_pedal` field and rename if present
- [ ] 3.6 Verify the project compiles and runs after all renames

## 4. Update Main Spec

- [ ] 4.1 After the delta spec is archived, sync the clarified flora particle requirements from the delta spec into `openspec/specs/visual-effects/spec.md`