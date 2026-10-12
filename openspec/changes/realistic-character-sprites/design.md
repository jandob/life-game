## Context

**Current format** (`src/animation.rs:106`, `src/assets.rs:9-21`): 64x128 cells, 10x12 sheets (640x1536), drawn at scale 0.5. Measured on the sheets: the lowest opaque row of the feet is **105** in every sheet (player, Samantha, wanderer); the head top is at row 17 (player) and 20 (Samantha); the shadow reaches row 114. The player is 89 rows tall.

**Collider**: a child `Collider::ball(16.0)` at local `(0, −32)` under a parent scaled 0.5 (`src/player/spawn.rs:24-30`, `src/npc/spawn.rs:15-20`, `src/npc/wander.rs:72-77`). Rapier applies the parent's `GlobalTransform` scale to the shape (`bevy_rapier2d-0.36.0/src/plugin/systems/collider.rs:48-84`, `apply_scale`).

**Generator resolution**: `artgen.py post --grid auto` detects a native pseudo-pixel of 8.01 raw px on `out/sam_art/front/sam_front_s13.png` and `player_front_s12.png` (SDXL + `pixel_art_xl`, 768x1152), and 5.2–7.7 on the FLUX klein views (576x1024). A fixed grid of 7.9 gives the player 132 rows and 8.2 gives Samantha 127, so both figures are about 1040 raw px tall: at the native grid that is **about 130 rows**.

**User decisions (2026-10-12)**: realistic proportions; bigger sprites so faces are readable; the rooms and furniture adapt to the characters, not the other way around. The pixel size must be consistent across the image. The world side is designed in `world-texel-scale`. An earlier draft of this design kept the old rooms and drew the characters at scale 1/3; that is superseded (`renders/superseded_size_options_720p.png`).

## Decisions

### D1: Cell 96x192, drawn at scale 1.0 in the texel-unit world

| | now (chibi) | new (realistic) |
|---|---|---|
| Cell, sheet | 64x128, 640x1536 | **96x192, 960x2304** |
| Draw scale | 0.5 (old world) | **1.0** (`world-texel-scale`: 1 world px = 1 art px) |
| World size of a cell | 32x64 (old units) | 96x192 (new units, the same 3x footprint) |
| Feet row (lowest opaque row) | 105 | **157** (62 px below the sprite centre) |
| Head top, man / woman | 17 / 20 | **26 / 32** (±2) |
| Figure height, man / woman | 89 / 86 rows | **132 / 126 rows** |
| Head (7 heads) | ~12 rows | **~19 / 18 rows** |
| Against the door leaf | 93 % of 48 px | 92 % / 88 % of 144 px (3 tiles of 48) |
| Drop shadow | centre (31.5, 102), radii 22.5x11.5 | centre (47.5, 152.5), radii 33.75x17.25 |

*Why 96x192:* 132 rows matches the generator's native grid (about 130 rows), so every output pixel is one model pixel. A 128x256 cell would need a grid of about 5.9 raw px, finer than the model draws, which only duplicates pixels (or off-distribution generation sizes). 64x128 can't hold a 7-head figure with a readable face.

*Scale 1.0:* tiles are drawn at 1 world px per art pixel too, so tile and character pixels are always the same size on screen, as the user asked. On-screen size and readability come from the camera (`world-texel-scale` D3): 2–3 screen px per art pixel puts the head at 38–57 screen px.

### D2: Layout and frames stay 10x12 with `CHARACTER_CLIPS`

The row order (idle 0–3, walk 4–7, run 8–11; down, left, right, up) and frame ranges stay, so the code keeps one clip table and `character_clip` unchanged. The generator gives about two distinct poses per direction (contact `A`, passing `P`), plus mirroring. Frame reuse fills the cells:

| Rows | Columns | Fill | Loop |
|---|---|---|---|
| 0–3 idle | 0–7 | the standing still `S` in 0–3; a breathing still `B` (shoulders 1 row lower) in 4–7, or `S` again | 0.8 s |
| 4–7 walk | 0–9 | `A A A P P A' A' A' P' P'` | 1.0 s |
| 8–11 run | 0–7 | `A A P P A' A' P' P'` (walk poses until run art exists) | 0.8 s |

`A'`/`P'` are the other leg leading: for down and up the horizontal mirror of `A`/`P`; for left and right a second generated contact pose if there is one, else `A`/`P` again. The right row is the horizontal mirror of the left row (asymmetric details flip; accepted). Columns 8–9 of idle and run rows stay transparent. Samantha never runs, but her run rows get the same fill.

Walk-cycle duration against the walk speeds (foot sliding) can be tuned in `CHARACTER_CLIPS` later; not part of this change.

### D3: Code: the sheet format and the feet collider

`src/character.rs` comes from `world-texel-scale` (its D5): `FEET_RADIUS = 24.0`, `FEET_BELOW_CENTRE = 48.0` in world px, and `SheetFormat { scale }` with `feet_collider()` (`Collider::ball(FEET_RADIUS / scale)` at local `y = −FEET_BELOW_CENTRE / scale`) and `transform(pos)`. That change defines `LEGACY = 1.5` (64x128 cells, the same 96x192 world footprint). This change adds `REALISTIC = 1.0` (96x192 cells) and switches the player and Samantha to it.

The cell size isn't in the struct because `bevy_asset_loader`'s `texture_atlas(...)` attribute needs literals in `src/assets.rs`; a comment there names the format.

**Switching is atomic per character:** the PNG, its `texture_atlas(...)` layout and the `SheetFormat` change in one commit. A 64x128 image with a 96x192 layout shows the wrong cells.

### D4: Art spec

For each realistic character (`player.png` now, `samantha.png` now, the rest of the cast later):

- **Sheet**: 960x2304 RGBA PNG, 96x192 cells, 10x12, layout and fill as in D2. Hard pixels (alpha 0 or 255) except the shadow.
- **Anchor**: figure centred on x = 47.5 (`fit_cell` centres the content), lowest opaque row of the standing feet on **row 157**. In walk frames the lowest foot is on row 157.
- **Height**: standing man 132 rows (head top row 26), Samantha 126 rows (row 32), ±2 rows on every standing frame. Width up to 96; `post` reports clipping.
- **Density**: 132 rows for a 1.78 m man is about **74 art px per metre**. Tiles and props (`world-texel-scale` D6) use the same density.
- **Shadow**: the project ellipse scaled 1.5x: centre (47.5, 152.5), radii 33.75x17.25, fill `#3f3f74` and top rim `#5c5ca9`, alpha 125.
- **Post-processing**, per frame:

  ```
  artgen.py post RAW.png --grid N --cell 96x192 --feet-row 157 --shadow \
      --outline inner --colours 24 --keep-largest --out OUT
  ```

  `N` is the fixed raw pixel size, chosen **once per character and per backend + generation size**: `N = raw height of the standing reference front / 132` (126 for Samantha). For the SDXL fronts at 768x1152 that is about 7.9 (player) and 8.3 (Samantha), close to the native grid of 8.0. The FLUX views at 576x1024 frame the figure differently, so measure `N` on a standing FLUX frame of each character. Record `N` in the recipe. A frame whose standing height is off by more than 2 rows is regenerated with the same framing, not re-posted with another `N`: a different `N` changes the head size between frames, which is what `--grid fit` does and why it isn't used.
- **Faces**: check every front frame at 1x: eyes at least 2 rows, a visible mouth or shadow line. In a test post of `player_front_s12.png` at `N = 7.9` with `--colours 24 --keep-dark 0.3` the face came out blank, so check faces separately and use more colours or a different `--keep-dark` if needed.
- **Portraits**: unchanged, 64x64 RGBA, transparent, head 30–40 px, shown at 128x128 (an integer 2x). They are UI, not world art.
- **Tooling prerequisite** (`tools/artgen/postprocess.py`): `shadow_layer` and `fit_cell` use the 64x128 constants (`SHADOW_CENTRE`, `SHADOW_RADII`, `CHAR_TOP_ROW`) whatever `--cell` is. Scale them by `cell width / 64` and place the shadow centre `3 × k` rows above `feet_row` (k = 1.5 gives the values above). Optional: `--grid N` downsamples from phase (0, 0); using the detected phase with a fixed `N` would keep thin lines on the model's grid.

### D5: The wanderer stays on the old sheet

She keeps `wanderer.png` (64x128) and `texture_atlas(64, 128, 10, 12)`, drawn with `LEGACY` (scale 1.5). Her footprint and collider equal the realistic format's, so physics and YSort don't change. Her pixels are 1.5x bigger than everything else, which is acceptable only while she isn't on a played map (she isn't on `route1_flat.tmj`). She gets realistic art before she appears on a city map (follow-up idea).

## Risks / Trade-offs

- [Head size jumps between frames] → fixed `N` per character and backend, ±2 rows rule (D4).
- [Layout and image out of step during the switch] → atomic switch per character (D3).
- [Collider at the wrong size because Rapier scales by the parent] → the helper divides by the scale; check with the F3 overlay (looking only, then F3 off for movement tests).
- [Interim chibi sheets at scale 1.5 next to 48 px tiles show bigger pixels] → only until the realistic sheets land; both sheets are in progress.
