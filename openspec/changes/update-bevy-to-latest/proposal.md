## Why

The project pins Bevy to `0.14.2` (released July 2024). The latest Bevy release is `0.19.1` — five major versions ahead, with significant bug fixes, performance improvements, and API changes. Staying on 0.14 blocks the project from adopting current Bevy ecosystem crates and makes the eventual migration costlier. Two currently-used crates are unmaintained for newer Bevy (`bevy_particle_systems` tops out at Bevy 0.14, `bevy_trickfilm` at 0.16), so reaching 0.19 requires replacing them.

## What Changes

- **BREAKING**: Upgrade `bevy` from `0.14.2` to `0.19.1` and fix all breaking changes across the 0.14 → 0.19 migration (ECS, Required Components, asset system, sprite/UI rendering, audio, physics, tilemap, dialogue integrations).
- **BREAKING**: Update all Bevy ecosystem crates to their latest Bevy-0.19-compatible versions:
  - `bevy_asset_loader` 0.21 → 0.27
  - `bevy_rapier2d` 0.27 → 0.36
  - `bevy_kira_audio` 0.20 → 0.26
  - `noisy_bevy` 0.7 → 0.14
  - `bevy_tweening` 0.11 → 0.16
  - `bevy_ecs_tilemap` 0.14 → 0.19
  - `bevy_yarnspinner` 0.3 → 0.9
- **BREAKING**: Replace `bevy_particle_systems` (unmaintained, only supports Bevy 0.14) with a maintained Bevy-0.19-compatible particle solution (candidate: `bevy_hanabi` 0.19); migrate the flora particle effects (sakura petals) to the new API.
- **BREAKING**: Replace `bevy_trickfilm` (unmaintained, only supports Bevy 0.16) with Bevy's built-in 2D sprite animation (available since Bevy 0.16); migrate the 8 `.trickfilm` RON animation manifests (player, NPCs, UI key hints, dialogue hint) to native Bevy animation assets.
- **BREAKING**: Remove the `ParticleSystemPlugin` and `Animation2DPlugin` registrations in `src/main.rs`; re-register the replacement systems/plugins.
- Verify the game builds and runs on native, and that the wasm build (used by `push_to_itch.sh`) still succeeds.

## Capabilities

### New Capabilities

- `visual-effects`: The game's sprite animations and particle effects — which animation states exist (player idle/walk/run per direction, NPC idles, UI key hints, dialogue hint), that they play correctly, and that flora particle effects render — as observable behavior that must be preserved across the engine upgrade.

### Modified Capabilities

- None (no existing specs; this is the project's first capability spec).

## Impact

- `Cargo.toml` / `Cargo.lock`: Bevy + ecosystem crate version bumps, two crate removals (`bevy_particle_systems`, `bevy_trickfilm`) and additions of their replacements.
- `src/main.rs`, `src/assets.rs`: plugin registration, asset collection changes.
- `src/player/` (spawn.rs, state.rs), `src/npc/spawn.rs`, `src/ui/` (keyboard_hint.rs, dialogue/start_hint.rs): sprite animation code migration.
- `src/world/map/flora.rs`: particle system migration.
- `assets/`: 8 `.trickfilm` manifest files converted to native Bevy animation assets (or equivalent).
- Build pipeline: native (`cargo build`) and wasm (`[profile.wasm]`, `push_to_itch.sh`).
