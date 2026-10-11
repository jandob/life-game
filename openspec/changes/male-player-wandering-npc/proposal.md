## Why

The player character should be male. The current female character art is good and should stay in the world, so she becomes an ambient NPC who wanders around near the start of the game. This makes the world feel more alive without touching the dialogue structure.

## What Changes

- **Male player sprite**: a new sheet `assets/player/player_male.png` (produced by the pixel-artist) with exactly the same layout as the current `assets/player/player.png` (64x128 cells, 10 columns x 12 rows, same clip ranges). Once it lands it replaces `assets/player/player.png`.
- **Female sheet becomes an NPC asset**: `assets/player/player.png` moves to `assets/npc/wanderer.png`.
- **Shared character animation**: the direction + movement-state to clip mapping in `src/player/state.rs::update_animation` moves into `src/animation.rs` (`CharacterAnim`, `character_clip`, `CHARACTER_CLIPS`) and is used by the player and the wanderer.
- **Wandering NPC**: a new `Wanderer` entity with physics (dynamic body, blocked by water, trees, the map border and other characters) that picks a random point near her home, walks there, pauses a few seconds and repeats. She has no dialogue and is not an `Npc` (no chat, no start hint, no `face_player`, no ending role).
- **Spawn**: from an optional object named `Wanderer` in the Tiled `NPCs` layer, falling back to an offset from `SpawnPoint`. `world.tmj` is not edited.
- **Dialogue**: `assets/dialogue/jotem.yarn:8` "young lady" becomes "young lad".

## Capabilities

### New Capabilities
- `characters/wanderer`: a non-talkable NPC that wanders randomly near her home with physics and directional animation.

### Modified Capabilities
- `characters/player`: the player uses the male sprite sheet; the clip selection is shared with other characters. (No accepted spec exists yet for the player; the delta is written as ADDED.)

## Non-Goals

- Dialogue, a `NpcDialogue` variant or Yarn content for the wanderer.
- Replacing the `pai.png` dialogue portrait (later change).
- Pathfinding. She walks in straight lines and retargets when stuck.
- Editing `assets/map/world.tmj` (the user can place a `Wanderer` object later).

## Impact

- **Assets**: `assets/player/player.png` (replaced by male art), `assets/npc/wanderer.png` (moved), `assets/dialogue/jotem.yarn`.
- **Code**: `src/assets.rs`, `src/animation.rs`, `src/player/state.rs`, `src/player/spawn.rs`, `src/npc/mod.rs`, `src/npc/spawn.rs`, new `src/npc/wander.rs`.
- **Dependencies**: none. Randomness uses the existing `rand` 0.8 (`thread_rng`, already used on wasm by `flora.rs` and `audio/sound.rs` via `getrandom` with the `js` feature).
