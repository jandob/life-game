## Context

**Today**: tiles are 16 px (`TILE_SIZE`, `src/world/map/mod.rs:10`), drawn at 1 art px per world px. Characters are 64x128 cells at scale 0.5 (2 art px per world px). The camera shows a fixed 250 world px vertically (`src/world/camera.rs:22,88-95`) in a 1280x720 logical, non-resizable window (`src/main.rs:39-60`), so a tile pixel is 2.88 screen px and a character pixel 1.44: both uneven, and different from each other. In `route1_flat.tmj` the 3B door leaf is 3 tiles (48 px) tall, which gives about 23 art px per metre for the tiles. The chibi player is 44.5 world px tall.

**Characters** (`realistic-character-sprites`): 96x192 cells, a man 132 art px tall, so about **74 art px per metre**. The generator draws on a native grid of about 8 raw px, so one 1024 px image covers at most about 128 art px.

**User decisions (2026-10-12)**: realistic, more detailed characters; bigger sprites so faces are readable; "the rooms and furniture shall be adjusted to the new more detailed characters, not the other way around"; consistent pixel size across the image.

**Bevy camera** (verified, `bevy_render-0.19.1/src/camera.rs:425-429`): `camera_system` calls `projection.update()` with the **logical** viewport size. With `ScalingMode::WindowSize`, one world unit is one logical px at `ortho.scale = 1`. An integer number of physical px per world unit `t` therefore needs `ortho.scale = scale_factor / t`.

**Renders**: `renders/framing_options_720p.png` shows 720, 540, 480 and 360 art px visible at 1280x720 with the realistic test figures at 1x. The tiles there are today's art upscaled 3x as a placeholder for framing only. Their pixels are 3x the characters' pixels, which is also exactly what the rejected "upscale the existing tiles" option (D2) looks like. `renders/mock_framing.py` regenerates it.

## Decisions

### D1: One world unit is one art pixel

Tiles, props and characters are all drawn at 1 art px per world px (characters at scale 1.0; legacy 64x128 sheets at 1.5 until replaced). The pixel size is then the same everywhere by construction, and every on-screen size comes from the camera (D3). Every world-space constant is multiplied by 3 (D5), because the characters' world footprint grows from 32x64 to 96x192.

*Alternative considered:* keep today's world units and draw everything at scale 1/3 (48 px tile art in 16 world px tiles). It needs the same new art, but adds a scale factor everywhere and a Tiled-px to world-px conversion for every map. Rejected.

### D2: Tile size 48 px at the characters' density (user decision; default 48)

All tile art is redrawn at about 74 art px per metre; only the grid size differs.

| | **48 px (default)** | 32 px | 16 px |
|---|---|---|---|
| Metres per tile | 0.65 (today: 0.7) | 0.43 | 0.22 |
| Door leaf (2.0 m) | 3 tiles | 4.5 tiles | 9 tiles |
| Main room 4.5x5 m | 7x8 tiles | 10.5x12 | 21x23 |
| Tiles per room, unique tiles per prop | as today | about 2.3x | about 9x; one prop becomes dozens of fragments |
| Engine change | tile size per map | same | none |

- **48 (default):** today's layout grain and tile counts, so chunk streaming, collision building and Tiled authoring behave as now. A 48 px tile is a meaningful texture unit for generation (one tileable floor or wall piece). Collision shapes are drawn per tile in the tileset, so collision isn't limited to the 0.65 m grid.
- **32:** finer placement (a 2.0x1.4 m bed is 4.6x3.2 tiles instead of 3x2), at about twice the tiles. Choose it if the scene-designer finds 0.65 m too coarse.
- **16:** no engine change, but at this density a 16 px tile is a fragment of an object; tileset pages and placement work multiply. Rejected.
- **Rejected: keep today's 16 px tile art and render the tile layers at 3x.** Tile pixels would be 3x the size of character pixels (see the placeholder tiles in the render), which is what the user ruled out.

### D3: Camera with integer pixel scaling (user decision; default C1)

| Physical window height | **C1: integer, about 540 visible (default)** | C2: fixed 480 visible |
|---|---|---|
| 720 (1280x720 window, DPR 1) | t = 1, 720 visible, head 19 px | t = 1.5 (uneven), head 28 px |
| 900 (DPR 1.25) | t = 2, 450 visible, head 38 px | t = 1.88 (uneven), head 36 px |
| 1080 (1080p fullscreen, DPR 1.5) | t = 2, 540 visible, head 38 px | t = 2.25 (uneven), head 43 px |
| 1440 (DPR 2 window, 1440p) | t = 3, 480 visible, head 57 px | t = 3, head 57 px |
| 2160 (4K fullscreen) | t = 4, 540 visible, head 76 px | t = 4.5 (uneven), head 86 px |

`t` = physical screen px per art px; head = 19 art rows × `t`. A room with a 4-tile (192 px) wall face and 7–8 floor tiles is about 530–580 px tall, so 450–540 visible shows a room with little scrolling.

- **C1 (default):** `t = max(1, round(physical_height / 540))`, `ScalingMode::WindowSize`, `ortho.scale = scale_factor / t × debug_zoom`, recomputed when the window size or scale factor changes. Every pixel, tile or character, is exactly `t` screen px: the most consistent pixelation possible. The framing varies between 450 and 720 px with the screen.
  *Con:* in a 1280x720 window on a DPR 1 screen, `t` is 1: crisp, but faces are only 19 px and the view is wider. Players there get readable faces in fullscreen (1080p: 38 px). Rounding the other way (`t = 2`, only 360 px visible) would cut a room to its wall and half its floor (bottom-right panel of the render).
- **C2:** a fixed 480 visible (`ScalingMode::FixedVertical`), the same framing everywhere and close to the "66 px variant" the lead described (today's equivalent: about 1.44 screen px per art px). But pixels are uneven at 720p (1.5) and 1080p (2.25): rows of 1 and 2 (or 2 and 3) screen px alternate, the same for tiles and characters, and shimmer while the camera moves.
- Both keep the 1280x720 default window. A larger default window, or per-map zoom, would be a follow-up.

### D4: Tile size per map

`TiledMap` stores `tile_size` from the `.tmj` (`tilewidth`, which must equal `tileheight`). Every tileset in the map must have that tile size; otherwise the loader returns an error (`AssetLoader` error, no panic). `TILE_SIZE` is removed. `tiled_to_game`, `chunk_manager` (`TilemapTileSize`, chunk origin), `collision.rs` (tile positions, `BORDER_THICKNESS`), `has_collision` callers and the wanderer's `TILE` use the map's value. `CHUNK_SIZE` stays 16 tiles (768 px chunks) and `RENDERED_CHUNKS_RADIUS` stays 3 (7x7 chunks, 5376 px), which covers the widest view (1280x720 at `t = 1`) with room for the F3 zoom. The 16 px maps (`forest`, `apartment*`, `enginetest`) keep loading as engine fixtures; with 132 px characters they aren't playable, which is accepted.

### D5: World-space constants x3

New `src/character.rs`:

```rust
pub const FEET_RADIUS: f32 = 24.0;          // world px (was 8)
pub const FEET_BELOW_CENTRE: f32 = 48.0;    // collider centre below the sprite centre (was 16)
#[derive(Clone, Copy)]
pub struct SheetFormat { pub scale: f32 }
pub const LEGACY: SheetFormat = SheetFormat { scale: 1.5 }; // 64x128 cells → 96x192 world px
impl SheetFormat {
    pub fn feet_collider(self) -> (Collider, Transform) {
        (Collider::ball(FEET_RADIUS / self.scale),
         Transform::from_xyz(0.0, -FEET_BELOW_CENTRE / self.scale, 0.0))
    }
    pub fn transform(self, pos: Vec2) -> Transform {
        Transform::from_translation(pos.extend(0.0)).with_scale(Vec3::splat(self.scale))
    }
}
```

At `LEGACY` the local collider is `ball(16)` at −32, the same numbers as today. `realistic-character-sprites` adds `REALISTIC = 1.0`.

| Constant | File | Now | New |
|---|---|---|---|
| player, Samantha, wanderer scale | `player/mod.rs`, `npc/spawn.rs`, `npc/wander.rs` | 0.5 | `LEGACY` (1.5) |
| `FEET_TO_TRANSFORM` | `world/map/tiled_map.rs:74` | 16 | `character::FEET_BELOW_CENTRE` (48) |
| `WALK_SPEED`, `RUN_SPEED` | `player/mod.rs:17-18` | 100, 150 | 300, 450 |
| `NPC_PROXIMITY_DISTANCE` | `player/mod.rs:15` | 50 | 150 |
| `SCRIPT_WALK_SPEED`, `ARRIVE_DISTANCE`, `STUCK_PROGRESS` | `story/scripted.rs:17-23` | 70, 2, 2 | 210, 6, 6 |
| wanderer `FEET_OFFSET`, `WANDER_RADIUS`, `WALK_SPEED`, `ARRIVE_DISTANCE`, `STUCK_PROGRESS`, `MAX_CAMERA_DISTANCE`, `CLEARANCE`, `TILE` | `npc/wander.rs:17-32` | −16, 96, 60, 4, 2, 640, 8, 16 | −48, 288, 180, 12, 6, 1920, 24, map tile size |
| start hint `SIZE` (tween end scale), child offset, `YSort` | `ui/dialogue/start_hint.rs:28,44,51` | `SIZE`, y 40, 100 | `SIZE` x3, y 120, 300 |
| keyboard hint `ICON_SIZE`, `Collider::cuboid(16, 16)`, `YSort` | `ui/keyboard_hint.rs:15,95,124,141` | 0.5, 16x16, −200 | 1.5, 48x48, −600 |
| `TRANSLATION_SHAKE_STRENGTH` | `world/camera_shake.rs:9` | 15 | 45 |
| `PROJECTION_SCALE` and `zoom_camera` | `world/camera.rs` | 250, sets `ortho.scale` | D3 system; F3 zoom as a separate factor |

Flora (`flora.rs`) is forest-only and stays at 16 px values. YSort (`z = −y × 0.0001`) stays inside range: a 100x100 map of 48 px tiles spans 4800 px, z ±0.24. Rapier keeps its default length unit; distances become 3x larger, which it handles.

The start-hint and keyboard-hint icons are 16 px art drawn at 3x, so their pixels are 3x bigger than everything else. They count as UI and are accepted until redrawn (follow-up idea).

### D6: Tile library and generation

- **scenekit**: `TILE = 16` (`tools/scenekit/common.py:23`) becomes the library's tile size, read from a `tile_size` field in the library manifest. A new library `assets/library/tilesets/gen48/` has 768x768 pages (16x16 tiles of 48 px) and `.tsj` files with `tilewidth = tileheight = 48`. The 16 px library `gen/` stays for the fixtures. `validate` rejects maps that mix tile sizes. `render` and `--check-tmx` work for both sizes.
- **Density and size table** for the scene-designer (74 art px per metre; floor depth drawn unforeshortened as today):

| Item | Real size | Art px | Tiles of 48 |
|---|---|---|---|
| Door leaf (in a 2-tile-wide frame) | 0.85 x 2.0 m | 63 x 148 | leaf about 1.3 x 3 |
| Wall face height (3/4 view) | 2.6 m | about 192 | 4 |
| Double bed (footprint) | 1.4 x 2.0 m | 104 x 148 | 2 x 3 |
| Kitchen counter (front plus top) | 0.9 m high, 0.6 m deep | 67 + 44 | 1 wide per 0.65 m, about 2.3 tall |
| Fridge | 0.6 x 1.8 m | 44 x 133 | 1 x 3 |
| Window (in the wall) | 1.2 x 1.4 m | 89 x 104 | 2 x 2 |
| Main room floor | 4.5 x 5 m | 333 x 370 | 7 x 8 |
| Kitchen floor | 2.5 x 3 m | 185 x 222 | 4 x 5 |
| Landing depth | 2 m | 148 | 3 |

- **Generation** (artgen through scenekit): one generation covers at most about 128x128 art px at a fixed `--grid` near the native 8 raw px (a 1024 px raw image). Floors and walls are generated as tileable 48 or 96 px textures; each prop is generated alone on a plain background at its art-px size from the table, posted with a fixed `--grid`, then sliced into 48 px tiles and stamped. The prompts use the characters' style suffix ("anime style pixel art, thick dark outlines, flat cel shading with two tones") and a shared palette, so props and characters read as one image. No whole-room generation at this density.

### D7: `route1_flat.tmj` rebuilt at 48 px

The scene-designer rebuilds the map at the same path with the `gen48` library (the 16 px version stays in git history), with realistic sizes (D6): the landing with stairs, 3B (main room and kitchen, a reachable window, no bed or a bare frame), Samantha's door 3A across the landing with a niche behind it. Layers and object **names** stay the same (`Floor`, `Walls`, `Decor`, `Door3B`, `Door3A`, `Above`, `Spawn`, `NPCs`, `Doors`, `Interact`, `Paths` and every path name), so `route1_viewing.yarn` and the scripted-scene code don't change.

Position conventions keep their meaning with new values: `SpawnPoint` and `NPCs` points are sprite centres; `Paths` points are feet (collider centres), and `TiledMap::path` adds 48 px. Path segments stay at least 24 px clear of wall and furniture colliders, and two actors' end points in one room at least 72 px apart. `Doors` rectangles cover the doorway (2 tiles wide), and the `Interact` rectangle sits in front of 3B's door.

## Risks / Trade-offs

- [All tile art must be regenerated] → accepted by the user's decision; only `route1_flat` is needed now.
- [Generation can't produce whole rooms at this density] → per-prop and per-texture generation (D6); the scene-designer composes.
- [Faces only 19 px in a DPR 1, 1280x720 window under C1] → C2 is the alternative; fullscreen gives 38 px.
- [Constants missed in the x3 pass] → the table in D5 lists every one found with `grep`; the manual run checks speeds, hint positions and the shake.
- [16 px fixture maps unplayable with large characters] → accepted; they only test the loader.
- [Legacy sheets at scale 1.5 in the interim] → bigger pixels on the characters until `realistic-character-sprites` lands.
