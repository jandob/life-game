## Context

The player (`src/player/`) is a `RigidBody::Dynamic` with `LockedAxes::ROTATION_LOCKED`, `Velocity`, `Ccd`, `YSort(0.0)`, scale 0.5 and a child `Collider::ball(16.0)` at y = -32 (`src/player/spawn.rs`). Its sprite sheet is 64x128, 10x12 (`src/assets.rs:7-10`) and its clips are `PLAYER_CLIPS` (`src/animation.rs:108`). `update_animation` (`src/player/state.rs:64`) maps `current_direction` + `PlayerState` to a clip.

The four story NPCs carry an `Npc` component. Every NPC-facing system filters on it: `face_player` (`src/npc/mod.rs:60`), `start_chat` (`src/player/chat.rs:23`), `spawn_hints` (`src/ui/dialogue/start_hint.rs:59`), `increase_ysorts` (`src/world/ending.rs:30`), dialogue runner and commands (`src/ui/dialogue/runner.rs:52,162`, `command.rs:53`). Every player system queries `Player` (via `With<Player>` or `&Player`), so a second animated character does not break any `.single()` call.

Water collision is **streamed**: `spawn_water_collisions` (`src/world/map/collision.rs:15`) adds tile colliders only to chunks that exist around the camera (`RENDERED_CHUNKS_RADIUS = 3`, `CHUNK_SIZE = 16`, so at least 3 * 256 = 768 px past the camera's chunk). Flora colliders (`flora.rs`) and map borders are spawned once and always exist.

## Goals / Non-Goals

**Goals:** male player art with no layout change; a decoupled wandering NPC using the female art; one shared clip-selection helper.

**Non-Goals:** dialogue for the wanderer, pathfinding, editing `world.tmj`, the `pai.png` portrait.

## Decisions

### D1: Asset moves
`git mv assets/player/player.png assets/npc/wanderer.png`. `GameAssets` gets `wanderer_texture` (`npc/wanderer.png`) and `wanderer_layout` (same `texture_atlas(64, 128, 10, 12)`). Until the male sheet lands, `player_texture` may point at `npc/wanderer.png` (the asset server returns the same handle for both; harmless). When the art lands: `git mv assets/player/player_male.png assets/player/player.png` and restore `player_texture` to `player/player.png`.

### D2: Shared clip selection
In `src/animation.rs`: rename `PLAYER_CLIPS` to `CHARACTER_CLIPS`; add `pub enum CharacterAnim { Idle, Walk, Run }`, `pub fn character_clip(dir: Vec2, anim: CharacterAnim) -> SpriteAnimationClip` (the angle logic and `MOVEMENT_ANIMATION_ANGLE_BUFFER` from `state.rs`, with the `Vec2::ZERO -> NEG_X` fallback), and `pub fn play_character_clip(animator: &mut SpriteAnimator, sprite: &mut Sprite, clip)` that sets the atlas index immediately on a clip change (the block at `state.rs:106-112`). `PlayerState::Talking` maps to `Idle`.

### D3: Wanderer entity and behaviour
New `src/npc/wander.rs` with `WanderPlugin`, added by `NpcPlugin`. Component:

```rust
#[derive(Component)]
pub struct Wanderer {
    home: Vec2, radius: f32,             // ~96 px
    target: Option<Vec2>,
    pause: Timer,                         // 2..5 s, randomised
    facing: Vec2,
    best_dist: f32, stuck: Timer,         // ~1.5 s without >2 px progress -> retarget
}
```

Entity mirrors the player body exactly: `RigidBody::Dynamic`, `LockedAxes::ROTATION_LOCKED`, `Velocity::zero()`, `YSort(0.0)`, scale `Vec3::splat(0.5)`, `SpriteAnimator` + `Sprite` with the wanderer atlas, child `Collider::ball(16.0)` at `(0, -32, 0)` with default `CollisionGroups`. No `Ccd` (60 px/s does not tunnel), no `ActiveEvents` (nothing reads `CollisionEvent`), **no `Npc`**.

`wander` system (Update, `run_if(in_state(GameState::Gaming))`), writes `Velocity` every frame:
- paused: velocity zero; when the pause timer finishes pick a target.
- target picking: up to ~8 tries of a random point in the disc `home + r * radius`; accept the first whose tile (`(pos / 16).round()`) and ~4 samples along the straight segment have no `TiledMap::tile_collision_shape`, and which lies inside `world_bounds()`; otherwise stay paused and retry next pause.
- walking: `velocity = dir * 60.0`, `facing = dir`; within 4 px of the target -> clear target, zero velocity, restart pause with a random 2-5 s.
- stuck: if the distance to target has not improved by 2 px for 1.5 s (flora or another body in the way), drop the target and pause.
- out of range: if her distance to `MainCamera` is above ~640 px (inside the guaranteed collider radius), zero velocity and do nothing, because water colliders may not exist under her.

`animate_wanderer` (PostUpdate, `.before(PhysicsSet::Writeback)`, like the player): `anim = if velocity.linear.length() > 1.0 { Walk } else { Idle }`; clip from `character_clip(facing, anim)`.

`OnExit(GameState::Gaming)`: zero her velocity, otherwise the dynamic body keeps drifting during `Ending` (zero gravity, no damping) after `wander` stops running.

Randomness: `rand::thread_rng()` (as in `flora.rs`). Timers are Bevy `Timer`s ticked by `Time`, so no `std::time::Instant` (wasm-safe).

### D4: Spawn
`spawn_wanderer` in `wander.rs` on `OnEnter(GameState::Gaming)`: use the object named `Wanderer` in the `NPCs` layer if present, else `SpawnPoint + (48, 0)`, else origin. The `home` is the spawn position. `spawn_npcs` gets a `"Wanderer" => {}` arm so it doesn't warn when the user later places her. The area around `SpawnPoint` (about game (159, 31)) is open grass for more than 12 tiles in every direction, so the fallback and a 96 px radius are valid on the current map. `world.tmj` is not edited.

### D5: Dynamic body, not kinematic
Kept dynamic. A `KinematicVelocityBased` body ignores fixed colliders, so she would walk through water and trees; getting blocking would need `KinematicCharacterController` and a translation-based movement model that differs from the player's. With two dynamic bodies the player can nudge her and she can nudge the player; because both systems rewrite velocity every frame the push only lasts while in contact, and she walks back towards her home afterwards. If the user wants her immovable by the player, raise her mass (`ColliderMassProperties::Density`) rather than switching body type.

## Risks / Trade-offs

- [Streamed water colliders] -> target validation against tile collision data plus freezing her out of camera range.
- [Straight-line walking gets blocked by trees] -> stuck timer retargets; flora colliders always exist.
- [Player can push her into odd spots] -> acceptable; she returns via later targets; she can't leave the map (border colliders).
- [F3 noclip only changes the player's collision groups] (`src/player/collision.rs:10`), not hers; testing her collisions must happen with F3 off.
