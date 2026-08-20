## 1. Dependency Bump & Baseline

- [x] 1.1 Update `Cargo.toml` to the design's version matrix: `bevy` 0.19.1, `bevy_asset_loader` 0.27, `bevy_rapier2d` 0.36, `bevy_kira_audio` 0.26, `noisy_bevy` 0.14, `bevy_tweening` 0.16, `bevy_ecs_tilemap` 0.19, `bevy_yarnspinner` 0.9; remove `bevy_particle_systems` and `bevy_trickfilm`; add `bevy_hanabi` 0.19
- [x] 1.2 Run `cargo update` and an initial `cargo check` to enumerate the full breakage surface (native build; note wasm-only errors separately)
- [x] 1.3 Run the `bevy_migration_guide` tool against the codebase and record which migrations it automates vs. which need hand-fixing

## 2. Core Engine & Asset Migration

- [x] 2.1 Fix app/plugin setup in `src/main.rs` (plugin registrations incl. removed `ParticleSystemPlugin`/`Animation2DPlugin`, Bevy 0.15+ default plugins/feature config, ECS Required Components, `bevy_state`/stage renames)
- [x] 2.2 Migrate `src/assets.rs` to `bevy_asset_loader` 0.27 (new asset collection API, typed/paths syntax) and Bevy 0.19 asset system (handles, `AssetServer`, image/format changes)
- [x] 2.3 Migrate sprite/UI rendering and color APIs across `src/ui/`, `src/player/`, `src/npc/` (new `Color`/`Srgba`, UI node/bundle changes, sprite atlas changes)

## 3. Ecosystem Crate Migration

- [x] 3.1 Migrate `bevy_rapier2d` 0.36 usage in `src/player/movement.rs`, `src/npc/spawn.rs`, `src/world/map/collision.rs`, `src/world/camera.rs`, `src/utils/mod.rs`, `src/utils/debug.rs`, `src/ui/keyboard_hint.rs` (RapierContext/query API changes)
- [x] 3.2 Migrate `bevy_kira_audio` 0.26 usage in `src/audio/sound.rs`, `src/audio/mod.rs`, `src/audio/spacial.rs`, `src/world/camera.rs`, `src/player/audio.rs`
  *Note: bevy_kira_audio was replaced by Bevy's built-in bevy_audio (rodio) per design decision D5, because kira→cpal 0.18 conflicted with bevy_audio→cpal 0.17 under wasm LTO. The spatial audio and reverse playback features were dead code.*
- [x] 3.3 Migrate `bevy_ecs_tilemap` 0.19 usage in `src/world/map/chunk_manager.rs` (chunk/tile API changes)
- [x] 3.4 Migrate `bevy_yarnspinner` 0.9 in `src/ui/dialogue/*` (runner, typewriter, command, option_selection, updating, spawn), `src/ui/main_menu.rs`, `src/player/state.rs`, `src/player/chat.rs` and update workspace members `dialogue_graph`/`dialogue_lines` if their APIs changed
- [x] 3.5 Migrate `bevy_tweening` 0.16 and `noisy_bevy` 0.14 usage (splash screen, menu, screen fade, ending text, camera shake, map generation in `src/world/map/generation/*`)

## 4. Flora Particle Effects (visual-effects spec)

- [x] 4.1 Register `HanabiPlugin`; build the petal `EffectAsset` in `src/world/map/flora.rs` matching the original behavior: ~2 spawns/s, jittered initial speed, circle-segment emitter facing downward, color gradient fade-in/fade-out, constant drift + noise wobble, scale 0.5, loop, rendered above world sprites (z ≈ 100)
- [x] 4.2 Attach the `ParticleEffect` to the flora tree entity so petals despawn with it (`despawn_recursive` on flora removal in `despawn_flora_chunks`/`despawn_flora_around_*`)

## 5. Sprite Animation Replacement (visual-effects spec)

- [x] 5.1 Convert the 8 `.trickfilm` manifests (player, 4 named NPC idles + shadow, dialogue start hint, keys) into Bevy `AnimationClip` assets/definitions, preserving animation names, keyframe ranges, and durations
- [x] 5.2 Rework `src/assets.rs` to load the new animation clips and atlas layouts; update collection entries
- [x] 5.3 Rework player animation in `src/player/spawn.rs` and `src/player/state.rs` to swap clips via `SpriteAnimation` per state (idle/walking/running) and facing direction
- [x] 5.4 Rework NPC idle animations in `src/npc/spawn.rs` to use the new clip asset directly
- [x] 5.5 Rework UI animations in `src/ui/keyboard_hint.rs` and `src/ui/dialogue/start_hint.rs` (dialogue hint + key icons)
- [x] 5.6 Remove all `bevy_trickfilm` imports/usages and `Animation2DPlugin` registration; after visual verification, delete the `.trickfilm` manifest files

## 6. Verification & wasm

- [x] 6.1 `cargo build` (native) succeeds and the game runs; verify every scenario in `specs/visual-effects/spec.md`: player idle/walking/running × 4 facing directions, NPC idles, dialogue start hint + key icon animations, petal particles spawning/drifting/fading and despawning with their flora entity
- [x] 6.2 `cargo build --target wasm32-unknown-unknown --profile wasm` succeeds; confirm `push_to_itch.sh` flow is unaffected
- [x] 6.3 Commit the verified migration in logical chunks (deps, core migration, particles, animation, wasm verification)