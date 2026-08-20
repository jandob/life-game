## Context

See proposal.md — Why for motivation. Current state: the game runs on Bevy 0.14.2 with ecosystem crates pinned to that era (`bevy_asset_loader` 0.21, `bevy_rapier2d` 0.27, `bevy_kira_audio` 0.20, `noisy_bevy` 0.7, `bevy_tweening` 0.11, `bevy_particle_systems` 0.13, `bevy_ecs_tilemap` 0.14, `bevy_trickfilm` 0.8, `bevy_yarnspinner` 0.3). Two crates cannot reach Bevy 0.19: `bevy_particle_systems` (last release 0.13.0, Bevy 0.14 only) and `bevy_trickfilm` (last release 0.11.0, Bevy 0.16 only). Everything else has a published version requiring `bevy ^0.19`. Behavior contract: `specs/visual-effects/spec.md` (player/NPC/UI animations + flora particles).

## Goals / Non-Goals

**Goals:**
- Single coherent upgrade to Bevy 0.19.1 so all crates compile against one Bevy version (no duplicate Bevy copies in the dependency graph).
- Preserve all observable behavior in `specs/visual-effects/spec.md`: same animation states and playback, same particle effect (sakura petals spawning, drifting, fading, despawning with their flora entity).
- Native build and wasm build (`[profile.wasm]`, used by `push_to_itch.sh`) both succeed.

**Non-Goals:**
- No gameplay, content, or feature changes; no asset redesign (same sprite sheets, same textures; only animation metadata format changes).
- No replacement of the dialogue, physics, or tilemap libraries — those get version bumps only.
- No visual "improvements" beyond matching current behavior.

## Decisions

### D1: Target Bevy 0.19.1 and bump all tracked ecosystem crates in one change
Bevy 0.14 → 0.19 spans five majors with pervasive breaking changes; intermediate "staging" (0.15 → 0.16 → ...) buys nothing since ecosystem crates are released against the latest major. Bump everything at once and fix iteratively against the official migration guides (0.15, 0.16, 0.17, 0.18, 0.19), using `cargo check` as the loop's feedback.

Version matrix (verified against crates.io — each latest version declares `bevy ^0.19`):
- `bevy` 0.14.2 → 0.19.1
- `bevy_asset_loader` 0.21 → 0.27
- `bevy_rapier2d` 0.27 → 0.36
- `bevy_kira_audio` 0.20 → 0.26
- `noisy_bevy` 0.7 → 0.14
- `bevy_tweening` 0.11 → 0.16
- `bevy_ecs_tilemap` 0.14 → 0.19
- `bevy_yarnspinner` 0.3 → 0.9
- Remove `bevy_particle_systems` 0.13, add `bevy_hanabi` 0.19
- Remove `bevy_trickfilm` 0.8 (replaced by built-in, see D3)

*Alternatives considered:* pin Bevy at 0.16 (trickfilm's max) — rejected because `bevy_particle_systems` still can't follow, and it just defers the same migration.

### D2: Replace `bevy_particle_systems` with `bevy_hanabi` 0.19
`bevy_hanabi` is actively maintained, tracks Bevy majors (0.19 out), and is GPU-accelerated. Migration: convert the petal `ParticleSystem` config in `src/world/map/flora.rs` (spawn rate 2/s, initial speed jittered ±3, ~1 s lifetime, circle-segment emitter opening π/2 downward, color gradient fade-in/fade-out, constant drift vector + noise wobble, scale 0.5, z ≈ 100, looping, despawn with entity) into a `bevy_hanabi` `EffectAsset` graph + `ParticleEffect` component on the tree entity. The effect is tuned to match the old visual behavior; exact numeric parity is not required, visual parity is (per spec).

*Alternatives considered:* (a) fork/keep `bevy_particle_systems` — unmaintained, would pin us to Bevy 0.14 forever; (b) hand-rolled ECS particle system — most control but the most new code to own; hanabi is the least-effort maintained path.

### D3: Replace `bevy_trickfilm` with Bevy's built-in 2D sprite animation
Bevy 0.16+ ships `SpriteAnimation`/`AnimationClip` in `bevy_sprite`, covering exactly what trickfilm provided (named keyframe ranges + durations on a spritesheet atlas). Migration: convert the 8 `.trickfilm` RON manifests (named `KeyframesRange` + duration entries) into Bevy `AnimationClip` assets (`.bevy_animation_clip` text asset format) or code-defined clips, preserving animation names and frame ranges. The `SpriteAnimations`-style named lookup (e.g. `play("walking-left")`) is replaced by swapping the clip on the `SpriteAnimation` component when the player/NPC/UI state changes. Six source files touch trickfilm (`src/assets.rs`, `src/player/spawn.rs`, `src/player/state.rs`, `src/npc/spawn.rs`, `src/ui/keyboard_hint.rs`, `src/ui/dialogue/start_hint.rs`); `src/main.rs` drops `Animation2DPlugin`.

*Alternatives considered:* (a) `bevy_aseprite`/`bevy_aseprite_ultra` — requires `.aseprite` source assets; the project has PNG + RON manifests, so not applicable without an art-pipeline change; (b) keeping trickfilm — caps Bevy at 0.16. Built-in is the only path to 0.19 that keeps the asset pipeline intact.

### D5: Replace `bevy_kira_audio` with Bevy's built-in `bevy_audio`
`bevy_kira_audio` 0.26 pulls in `kira` 0.12 → `cpal` 0.18, which conflicts with
`bevy_audio` (rodio → cpal 0.17) under the wasm profile's LTO (duplicate
`__wbg_*` symbols). Investigation showed that the game's audio needs are fully
covered by Bevy's default audio:

- one-shot playback (footsteps, UI) with volume + speed control
- looping (bird, cricket)
- runtime volume modulation via `AudioSink` (bird sound)
- global volume via `GlobalVolume`

Spatial audio (`SpatialAudioEmitter`/`SpacialSound`) and reverse playback were
dead code (no caller set `parent: Some(..)` or `reverse: true`). Replacing
`bevy_kira_audio` with `bevy_audio` removes one `cpal` version, fixes the wasm
build, and simplifies the dependency tree.

*Alternatives considered:* (a) keep bevy_kira_audio but disable bevy_audio
default feature (removes cpal 0.17, leaves cpal 0.18 — weaker wasm support);
(b) keep both, skip wasm — rejected because wasm build is a verification
requirement (see Goals).

### D4: Migrate incrementally with the official Bevy migration guides
Apply the official migration guides in order (0.15 → 0.16 → 0.17 → 0.18 → 0.19) as a checklist while fixing compile errors. The `bevy_migration_guide` cargo tool can automate a portion (it targets 0.16+); run it, then hand-fix the rest. Frequent `cargo check` (and `cargo build` after the wasm-only crates settle) keeps each step small.

## Risks / Trade-offs

- **`bevy_hanabi` rendering looks different from the old ECS particles** (GPU billboards vs CPU sprites, different fade/noise) → Tune the effect against the spec's observable criteria (spawn continuity, drift + wobble, fade in/out, despawn with entity); verify visually in-game.
- **Large migration surface across 5 Bevy majors** — many API breaks (ECS required components, asset system, sprite/UI rendering, color types, audio, physics) → Work through migration guides in order; keep the change compiling after each subsystem; commit in logical chunks.
- **Ecosystem crate API drift in big jumps** (notably `bevy_yarnspinner` 0.3→0.9 and `bevy_asset_loader` 0.21→0.27 may have changed setup/collection APIs) → Verify each crate's current setup API against its docs/examples during migration; the workspace members `dialogue_graph`/`dialogue_lines` may need small updates.
- **Animation clip conversion errors** (frame ranges/durations) → Compare converted clips against the original `.trickfilm` values; keep manifests until conversion is verified, then remove.
- **wasm target breakage** (feature-flag or wasm-only dependency issues, e.g. `web-sys`) → Run the wasm profile build as an explicit verification step before considering the change done.

## Migration Plan

1. Update `Cargo.toml` (version matrix above); `cargo update`; expect a large compile-error surface.
2. Run `bevy_migration_guide`, then fix errors iteratively per the 0.15→0.19 migration guides until `cargo check` passes; commit progressively.
3. Replace `bevy_particle_systems` with `bevy_hanabi`; port the petal effect in `src/world/map/flora.rs`; register `HanabiPlugin`.
4. Replace `bevy_trickfilm` with built-in sprite animation: convert the 8 manifests to Bevy animation clips, rework the 6 animation-consuming files + plugin registration in `src/main.rs`.
5. Verify visually in-game against `specs/visual-effects/spec.md` (all animation states, particle behavior).
6. Verify `cargo build` (native) and the wasm profile build succeed; confirm `push_to_itch.sh` flow is unaffected.
7. Remove the `.trickfilm` manifests after conversion is verified.

Rollback: revert the dependency bump commits; the old `Cargo.lock` pins the previous working set.

## Open Questions

- Exact visual parity of hanabi petals vs. the old particle system (numeric tuning) — can be settled during implementation without changing the spec or task breakdown.
- Whether the `.trickfilm` manifests are deleted or kept as reference after conversion — cosmetic; decided during implementation.
