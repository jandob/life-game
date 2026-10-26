## Why

The game is now a side view, and the art is redrawn in a new style (anime outline, modern indie pixel art, realistic adults, about half the screen height). The current sprite format (one 960x2304 sheet, 96x192 cells, 12 fixed clip rows, four directions for walk and run) cannot hold that: the cell is too small for the new density, every clip is fixed in the layout, and a new outfit, hairstyle or clip means rebuilding a whole sheet.

## What Changes

- A character has several named **looks** (hairstyle plus outfit, e.g. `sam_casual`, `sam_ponytail`, `player_main`). A look is a folder with a `look.ron` manifest and one PNG **strip per clip**.
- Cells are **128x256**, feet on a fixed row, figure centred, drawn at scale 1.0.
- Initial clips: `idle` (four rows: front, left, right, back) and `walk` (one row, drawn facing right, mirrored for left). No run and no vertical walks: moving up or down plays the walk clip facing the last horizontal direction.
- A look lists only the clips it has. A missing clip falls back to the character's default look, then to idle.
- Adding a clip later is one new strip plus one manifest entry; nothing else is regenerated.
- The 960x2304 sheet format of `realistic-character-sprites` is superseded for new looks; legacy sheets keep working until removed.
- Strips are plain PNGs with fixed cells, so they open and export in Pixelorama (import as spritesheet with the frame counts; export by animation tag).

## Impact

- Specs: new `characters/character-looks`; supersedes the sheet-size requirement of `realistic-character-sprites/specs/characters/sprite-format`.
- Code: `src/animation.rs` (`CHARACTER_CLIPS`, `character_clip`), `src/assets.rs` (per-character layout handles), `src/player/state.rs`, `src/npc/mod.rs`, the collider offset (48 px below the sprite centre assumed a 192 px cell).
- Art pipeline: `tools/sprite_gen` gets a strip builder reading `art/characters/<name>/looks/`; `art/artgen-profile.json` gets the new cell and feet row.
