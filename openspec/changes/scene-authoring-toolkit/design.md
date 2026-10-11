## Context

**Tools today.** `tools/mapgen/` (`tmj.py`, `tmjlib.py`, `preview.py`, `validate.py`) edits `.tmj` maps cell by cell, by tile id (`tileset:localid`, flip flags `|h|v|d`), writes atomically (temp file + rename), renders through `tmxrasterizer` plus Pillow overlays, and validates against the game loader and `tiled --export-map`. `tools/artgen/` runs FLUX.2 klein 4B + a pixel LoRA on MPS (`backends/flux2_klein_pixel_lora.py`, reference images through the pipeline's `image` argument) and post-processes with grid detection, downscaling, palette lock, cleanup and background removal (`postprocess.py`). The installed diffusers also has `Flux2KleinInpaintPipeline` (`pipeline_flux2_klein_inpaint.py:830`: `image`, `image_reference`, `mask_image`, `strength`, `height`, `width`), with the same weights.

**Benchmark findings.** Whole rooms come out painted (a 3/4 "dollhouse" view, weak pixel grid). Seamless 16 px tiles from text alone fail. Generation therefore has to be pinned to the grid and to the surrounding scene through the *input image* (block-out or existing pixels plus a mask), not through the prompt.

**Engine today** (`src/world/map/`): only the last tile layer is kept (`tiled_map.rs:303-313`); only the first tileset is read (`tiled_map.rs:275-279`) and its image is ignored, since the render texture is the hard-coded `GameAssets::tileset` (`chunk_manager.rs:75`, `assets.rs:48`); flip bits are not masked (`tile_at`, `tiled_map.rs:182-200`); every chunk sits at `z = -BACKGROUND_ZINDEX_ABS` (`chunk_manager.rs:68`, `mod.rs:11`), so nothing draws above the player; `TiledObject` has no properties; one global map (`GameAssets::world_map`, `assets.rs:50`).

**Texture limits** (read from the sources, not measured on devices):
- `bevy_ecs_tilemap` 0.19 is used without its `atlas` feature. In that mode a `TilemapTexture::Single` atlas is copied into a **2D texture array with one layer per tile**, where the tile count is derived from the *image size* (`render/texture_array_cache.rs:74-82`, `155-171`, `246-300`).
- WebGPU guarantees `maxTextureArrayLayers = 256` and `maxTextureDimension2D = 8192` (`wgpu-types-29.0.4/src/limits.rs:376-378`).
- Bevy 0.19 defaults to `WgpuSettingsPriority::Functionality`, which requests the adapter's own limits (`bevy_render-0.19.1/src/settings.rs:95`, `renderer/mod.rs:300-310`); `main.rs` doesn't override `WgpuSettings`. Real adapters often report 2048 layers, but **256 is the only guaranteed value**.
- The forest tileset already has exactly 256 tiles (`tileset.tsj`: 16 columns, 256x256 px).

## Goals / Non-Goals

**Goals:** agents can treat a scene as an image (see it, query it, edit it, regenerate parts of it) while Tiled `.tmj`/`.tsj` stays the master copy; a large shared library of generated tiles with identity, provenance and dedup; edits that never silently change other scenes; an agent-built apartment room that is walkable in game on native and wasm.

**Non-Goals:** a new scene format; Wang auto-tiling for generated tiles; animated tiles; map transitions and doors (later change); re-paging the hand-made forest tileset; a GUI.

## Decisions

### D1: One shared generated-tile library

All generated art goes into one library, `gen`, at `assets/library/tilesets/gen/`. Hand-made tilesets (forest) stay as they are and can be mixed with it in one map.

| Option | For | Against |
|---|---|---|
| **One shared library (recommended)** | Dedup across scenes; the usage index means something; one palette and style anchor; a scene can borrow tiles from another | Git merges of a growing binary file (D11); one place for all provenance |
| One tileset per scene | Isolated; a deleted scene takes its tiles with it | No reuse or dedup across scenes; "where else is this used" is always "nowhere"; maps still need several tilesets (hand-made + own) |
| Themed libraries (`gen-interior`, `gen-street`) | Smaller sheets to browse | Arbitrary boundaries; the same floor gets generated twice |

The model allows more than one library (a library is a directory with a manifest), so themed libraries stay possible; the default is one.

### D2: Fixed pages of 256 tiles, one Tiled tileset per page

A library is a sequence of **pages**: `page-000.png` (256x256 px RGBA, 16 columns x 16 rows of 16x16 tiles, unused slots fully transparent) and `page-000.tsj` (an ordinary external Tiled tileset: `name: "gen-000"`, `tilecount: 256`, `columns: 16`, `image: "page-000.png"`, per-tile `objectgroup` collision, `type`, `properties`). A page image is always the full 256x256 px, because bevy_ecs_tilemap derives the layer count from the image size.

Why 256: it is the WebGPU-guaranteed array-layer count, so every page renders on every WebGPU adapter regardless of what it reports. Pages are append-only: new tiles go into the last page; when it is full, a new page starts. Only the newest page changes in git when tiles are added.

| Option | For | Against |
|---|---|---|
| **256-tile pages, one tilemap per (chunk, layer, page used) (recommended)** | Works at the guaranteed limit; append-only, small git diffs; maps onto Tiled's multi-tileset model, which the engine needs anyway | More tilemap entities (a chunk spawns one per layer per page it uses; a 20x15 room with 3 layers and 4 pages has at most 12) |
| One growing tileset image | One texture per layer | Breaks above 256 tiles on adapters at the WebGPU minimum; the whole PNG is rewritten on every append; image width/height changes renumber nothing but churn git |
| Enable bevy_ecs_tilemap's `atlas` feature (sample the 2D atlas directly, up to 8192x8192 px = 262k tiles) | No array-layer limit | Crate-wide switch of the render path; disables `Vector`/`TextureContainer`; atlas sampling bleeds at the camera's non-integer zoom unless tiles are padded; not verified on WebGPU |

A later optimisation (not in this change): build one runtime texture array per map with only the tiles it uses (`TilemapTexture::TextureContainer`), sized against `RenderDevice::limits()`.

### D3: Tile identity, provenance and the manifest

- **Library id:** `gen:N` with `page = N / 256`, `local = N % 256`. The mapgen form `gen-007:42` (tileset name + local id) is accepted everywhere too. Ids are never reused or renumbered.
- **Gid in a map:** `firstgid(page tileset in that map) + local`. A page tileset is appended to a map's `tilesets` list the first time the map uses it, so existing gids never shift. The tools never remove a tileset from a map automatically.
- **Content hash:** `sha256` over the 16x16 RGBA bytes in row order, with every pixel of alpha 0 normalised to `(0,0,0,0)`. A fully transparent tile is "empty" (gid 0) and is never stored.
- **Manifest** `assets/library/tilesets/gen/tiles.json`:

```json
{
  "version": 1, "library": "gen", "tile_size": 16, "page_tiles": 256,
  "next_id": 1835,
  "tiles": {
    "1834": {
      "hash": "sha256:9f2c...",
      "created": "2026-10-11T14:03:22Z",
      "origin": "generate | fill | edit | import | fork",
      "parent": "gen:1200 | forest:16 | null",
      "job": "20261011-140310-ab12",
      "source": {"map": "maps/apartment.tmj", "layer": "Floor", "x": 3, "y": 4},
      "gen": {"backend": "flux2_klein_pixel_lora", "models": {"base": "black-forest-labs/FLUX.2-klein-4B", "lora": "Limbicnation/pixel-art-lora"},
              "lora_scale": 1.0, "prompt": "<full prompt after template>", "seed": 42, "strength": 0.75, "steps": 4,
              "scale": 3, "refs": ["sha256:..."], "layout": "sha256:...", "palette": "scene:apartment"},
      "material": "floor",
      "revisions": [{"hash": "sha256:...", "at": "...", "op": "edit --global", "job": "..."}]
    }
  }
}
```

`gen` is present only for model-made tiles. Collision, `type` and `material` live in the page `.tsj` (that is what Tiled and the engine read); the manifest copies `material` only for search. The `hash -> ids` lookup is built when the manifest loads; it isn't stored.

### D4: Dedup on insert

Every path that creates a tile (generate, fill, edit, import) goes through one insert function:

1. **Exact:** same pixel hash **and** same metadata signature (collision shapes + `type` + `material`) as the tile it would inherit -> reuse that id. Same pixels with different metadata -> a new tile, reported as `meta_variant`. (This is what lets `collide region` fork a tile that has identical pixels; see D8.)
2. **Near (opt-in, `--near N[:T]`):** a stored tile whose pixels differ from the new one in at most `N` pixels by more than `T` (max channel difference, default 8) -> reuse it. Candidates are pre-filtered by a 4x4 mean-colour signature. Every near match is listed in the result with its pixel difference count. Default off: in this project a cell may be unique on purpose.
3. **Flip-aware (opt-in, `--dedup-flips`, only after engine flip support lands, E3):** a match against a flipped or rotated stored tile is painted as that tile plus flip bits.
4. Otherwise append.

Inserts also dedup within the batch (two identical new cells -> one new tile).

### D5: Usage index, on demand

`index` scans `assets/maps/**/*.tmj` (or `--maps GLOB`), resolves every non-zero gid (flip bits masked) to `(tileset path, local id)`, and returns `tile -> [(map, layer, x, y, flip)]`. It covers every tileset (forest too), not only `gen`.

Computed on demand, not cached: two maps today, at most a few hundred thousand cells later; Python parses a 100x100x4 map in tens of milliseconds. A cache would go stale whenever a human saves in Tiled, and a cache file in git would conflict on every branch. If a full scan ever passes about 1 s, add a gitignored cache at `tools/scenekit/.cache/index.json` keyed by (path, size, mtime, sha256). The index is never written to `assets/` or git.

### D6: One CLI, `tools/scenekit/scene.py`

Run with `mise exec -- python3 tools/scenekit/scene.py <command>` (mise python + Pillow). It imports `tools/mapgen/tmjlib.py` for map and tileset I/O. Commands that need a model run `tools/artgen/.venv/bin/python tools/artgen/artgen.py inpaint ...` as a subprocess, so scenekit itself never imports torch.

Conventions (shared with mapgen):
- One JSON object on stdout per command (`{"ok": true, ...}` or `{"ok": false, "error": "...", "code": "..."}`, exit code non-zero on error). Images are written to the paths given; their paths are returned in the JSON.
- Cell coordinates are Tiled tile coordinates (origin top-left, y down). Regions are `x,y,w,h` in tiles. Pixel coordinates are **map pixels** (`tile * 16`, origin top-left, y down), never game coordinates.
- Tile refs: `gen:N`, `tileset:local` (mapgen form), or a raw gid; flips as `|h|v|d`.
- Every mutating command takes `--dry-run`, `--if-hash SHA` (D10), and returns `map_hash`, `changed_files`, `journal` (D10).

**Compositor.** scenekit renders maps itself with Pillow (tile layers bottom to top, `visible` honoured, layer `opacity` applied, flips applied with Tiled semantics: diagonal = transpose first, then horizontal, then vertical). It has to be pixel-exact because edits are diffed against it. `render --check-tmx` compares it against `tmxrasterizer` at scale 1 and reports differing pixels; layer offsets and parallax are refused by `validate`.

#### Inspect

| Command | Inputs | Output |
|---|---|---|
| `render MAP --out PNG` | `[--region x,y,w,h] [--layers A,B\|all] [--scale N=1] [--grid [N]] [--ids] [--uses] [--collision] [--material] [--highlight TILE...] [--context K]` | PNG. `--grid` lines + coordinate labels in a margin; `--ids` prints the tile ref per cell (needs scale >= 4; falls back to a legend of short codes A, B, ...); `--uses` tints cells by use count (unique / shared in this map / shared with other maps); `--highlight` outlines every cell using the given tiles. JSON: `{"image", "region", "scale", "px_origin": [x, y], "legend": {...}}` |
| `cells MAP` | `[--region] [--layers]` | JSON: `{"map", "map_hash", "region", "layers": [{"name", "above", "cells": [[{"tile": "gen:1834", "gid": 523, "flip": "", "hash": "sha256:...", "uses": {"map": 3, "total": 7, "maps": 2}, "collision": true, "material": "floor"} \| null, ...], ...]}], "tiles": {"gen:1834": {"origin", "prompt_short", "parent"}}}` |
| `where TILE` | `[--maps GLOB] [--sheet PNG --context K]` | JSON: `{"tile", "hash", "uses": [{"map", "layer", "x", "y", "flip"}], "count", "maps"}`; `--sheet` writes a contact sheet of every use with K cells of context |
| `diff A B` | A/B are map paths or `git:REV:path` (read via `git show`, read-only); `[--region] [--out PNG]` | JSON: per layer `changed: [{"x", "y", "old", "new"}]`, `pixels_changed`, `tiles_added`; PNG: A, B and a highlight of changed cells |
| `tile TILE` | `[--out PNG --scale 8]` | Provenance from the manifest, `.tsj` metadata, use count; optional enlarged image |
| `library` | `stats \| sheet --page N --out PNG \| check \| orphans` | `check` verifies page sizes, manifest vs pages (hash of every slot), `.tsj` tilecount; `orphans` lists tiles no map uses (never deletes) |

#### Generate (region) and fill (inpaint)

`generate MAP --layer L --region x,y,w,h --prompt TEXT [--ref PNG...] [--layout FILE] [--context K=2] [--strength S=0.75] [--seed N] [--n K=4] [--palette HEX|scene|none] [--alpha] [--scale S|auto] [--near N]` creates a **candidate job**; `apply JOB --pick K` commits it. `fill MAP --layer L (--cells "x,y;x,y" | --mask PNG | --empty --region R) [--like TILE] [--context K=3] [--strength 1.0] ...` is the same pipeline with an arbitrary cell mask.

Pipeline (D7). Job output in `tools/scenekit/out/jobs/<job-id>/`: `cand-K.png` (the region at 1x), `preview-K.png` (before | after with context and grid, 4x), `job.json` (all parameters, seeds, timings, and per candidate the number of new, deduped and near-matched tiles). `generate` and `fill` never write to the library or the map; `apply` does, through the import core (D8).

#### Pixel edit

`edit MAP --layer L --ops OPS.json [--global --expect-uses N] [--near N]`. Ops are a JSON list in map pixel coordinates, applied in order to the layer's image:

| op | meaning |
|---|---|
| `{"px": [x, y, "#rrggbb[aa]"]}` | one pixel |
| `{"rect": [x, y, w, h, colour]}` | filled rectangle (`"#00000000"` erases) |
| `{"line": [x1, y1, x2, y2, colour]}` | 1 px Bresenham line |
| `{"paste": {"at": [x, y], "image": "path.png", "mode": "over\|replace"}}` | paste an image (alpha-composited or replacing) |
| `{"copy": {"from": [x, y, w, h], "to": [x, y]}}` | copy pixels within the layer |
| `{"replace": {"from": colour, "to": colour, "region": [x, y, w, h]}}` | exact colour swap |
| `{"remap": {"map": {"#a": "#b", ...}, "region": [...]}}` | palette map |
| `{"quantize": {"palette": "file.hex", "region": [...]}}` | snap to a palette |

`tile edit TILE --ops OPS.json --expect-uses N` edits one tile's pixels in tile-local coordinates. This is a global edit by definition (D8).

#### Export and import (round trip)

- `export MAP --region R (--layer L | --composite) --out PNG [--scale 1]` writes the PNG and `PNG.json`: `{"map", "map_hash", "layer" | "composite": true, "region", "px_origin", "cells": [[gid...]], "cell_hashes": [[...]]}`.
- `import PNG [--sidecar PNG.json] [--layer L] [--global --expect-uses N] [--near N] [--force]` diffs the PNG against the layer *as it was at export time* (sidecar hashes) and applies the changed cells through the import core. If a changed cell was also changed in the map since the export, it is a `conflict` error unless `--force`. An image whose size doesn't match the region is an error, as is any scale other than 1 at import.
- Composite exports are context only. `import --flatten-into L` is the one way to write a composite back: each changed cell gets one flattened tile on layer L, the same cell is cleared on the other non-`above` tile layers, and the new tile inherits the union of the cleared tiles' collision. The result lists the cleared cells.

#### Collision and material

`collide tile TILE --shape SHAPE --expect-uses N`, `collide region MAP --layer L --region R --shape SHAPE`, `material tile TILE NAME`, `material region MAP --layer L --region R NAME` (D9).

#### Safety

`undo [--steps N]`, `journal` (list). See D10.

### D7: Generation pipeline (mask-anchored img2img/inpaint)

1. **Canvas.** Take region R plus a ring of K context cells (clipped to the map). Composite the current pixels of all layers at and below L. Inside R, either keep the current pixels (re-generation) or draw the **block-out** from `--layout`: a text grid (one character per cell, legend in `materials.json`) or a PNG with one pixel per cell. Each material has a flat colour and an optional texture hint.
2. **Scale.** Upscale the canvas by an integer S with nearest neighbour. `--scale auto` picks the largest S in 2..8 for which the long side is at most 1024 px and both sides are multiples of 16 (FLUX latent alignment). Regions that don't fit at S = 2 (more than 512 game px on a side) are refused; the agent splits them.
3. **Mask.** White over R (times S), black over the context.
4. **Model.** `artgen.py inpaint` with `Flux2KleinInpaintPipeline` (`image` = canvas, `mask_image` = mask, `image_reference` = `--ref` images, `strength`, the backend's prompt template and LoRA scale), `n` seeds. A block-out with `strength` around 0.6-0.8 is img2img that keeps layout and perspective. `fill` defaults to 1.0 (pure inpaint) because the context carries the style.
5. **Snap to grid.** The canvas fixes the grid (S model px per game px, phase 0), so downscaling is a fixed factor: the mode colour of each SxS block (`postprocess.downscale` with a given grid, no detection). `--grid detect` falls back to `detect_grid` if the model drifts off the grid at low strength.
6. **Palette and cleanup.** `--palette scene` quantises to the colours already used in the map (a fallback for empty maps: adaptive, 32 colours); a `.hex` file locks to a fixed palette; `cleanup` removes islands and orphan pixels.
7. **Alpha layers.** `--alpha` generates on a flat key colour and runs `remove_background`, for decor layers that sit on top of a floor.
8. **Keep R only.** Context pixels are discarded, so neighbours never change. `fill --ring 1` is an opt-in that also regenerates the first context ring (those cells go through copy-on-write) to hide seams.
9. **Cut** into 16x16 cells -> candidate. `apply` runs the import core with `origin` generate/fill, full provenance, and the per-cell material from the layout (which sets collision presets, D9).

The text-to-tile route is not offered: the benchmark showed it doesn't produce seamless tiles. `fill --like TILE` adds the tile (upscaled) as a reference image for variants.

### D8: Import core and copy-on-write

Every write of pixels (apply, edit, import) goes through one function. It takes a target layer L, a region, and new RGBA pixels:

For each cell: `old` = layer L alone rendered at that cell (flips applied); `new` = the new pixels.
- `new == old` -> unchanged; the gid **and its flip bits** are kept. This makes a no-op round trip byte-identical.
- `new` fully transparent -> gid 0.
- Otherwise (**copy-on-write, the default**): insert `new` through D4, with `parent` = the old tile and inheriting the old tile's collision, `type` and `material` (`--no-inherit` to drop them). The cell gets the new id without flip bits. Other cells and maps keep the old tile.

`--global` (only for `gen` tiles; tiles of hand-made tilesets are refused unless `--allow-foreign`): group changed cells by old tile id. If every cell of a tile carries the same new pixels (after undoing that cell's flip), the tile's slot in its page is overwritten in place, a `revisions` entry is added, and the result lists every use from the index. If uses of the tile exist outside the edited cells, `--expect-uses N` is required and must equal the total use count; otherwise the command fails with `impact` and the use list, and writes nothing. Different new pixels for the same tile in one global edit -> error. Global edits are the only in-place page change.

Result JSON: `{"cells_changed", "tiles_new": [...], "tiles_reused": [...], "near_matches": [...], "meta_variants": [...], "global": {"tile": "gen:12", "uses": [...]} | null, "map_hash", "changed_files", "journal"}`.

### D9: Collision and material on generated tiles

- Collision stays **per tile, in the page `.tsj`** (`objectgroup` with rectangles or polygons in tile-local pixels). That is what the engine already reads (`parse_tile_colliders`, `tiled_map.rs:132`) and what a human edits in Tiled's collision editor.
- `--shape` presets: `none`, `full`, `top`, `bottom`, `left`, `right` (halves), `top-quarter`, `bottom-quarter`, `rect:x,y,w,h`, `poly:x1,y1,x2,y2,...`.
- **Materials** are a tile property `material` (string). `assets/library/tilesets/gen/materials.json` maps material -> default shape, block-out colour, prompt hint and layer hint, e.g. `floor` -> `none`, `wall` -> `full`, `wall_top` -> `none` + `above`, `water` -> `full`, `furniture` -> `full`, `counter` -> `bottom`. When `apply` writes cells from a layout, every new tile gets its cell's material and the material's shape.
- `collide region` / `material region` resolve the region to the tiles in it. A tile used only inside the region is changed in place. A tile also used outside the region and whose metadata would change is **forked** by default (same pixels, new id, `origin: fork`, new metadata) for the region's cells; `--global --expect-uses N` changes it everywhere instead. `collide tile` is always global and needs `--expect-uses`.
- In the engine (E2), each cell spawns the colliders of every tile layer that isn't marked `collides=false`; `above` layers default to `collides=false`.
- Map-level collision objects (an object layer `Collision` with rectangles) are a later engine change and aren't needed for the demo.

### D10: Versioning and safety

- **Atomic files.** Every file is written to a temp file in the same directory and renamed (as mapgen does).
- **Write order** for one operation: page PNG -> page `.tsj` -> `tiles.json` -> map(s). If the process dies part-way, the library may hold unreferenced tiles (harmless; `library orphans` lists them), but a map never references a missing tile.
- **Optimistic concurrency against Tiled.** Each command records the sha256 of every file it reads and re-checks it immediately before the rename; a mismatch aborts with `conflict`. Every command returns `map_hash`; mutating commands accept `--if-hash` and fail with `stale` if the map changed (for instance, a human saved in Tiled since the agent last looked). The scene-designer agent always passes it. Unknown JSON fields written by Tiled are preserved (tmjlib keeps the dicts); only the layout is re-serialised.
- Tiled itself can still overwrite a tool write if a human has the map open with unsaved changes and saves. Tiled 1.12 offers to reload files changed on disk; the README tells humans to reload before saving. The tool can't prevent this.
- **Library lock.** Library writes take `assets/library/tilesets/gen/.lock` (create-exclusive, pid + time, stale after 10 min; gitignored), because several commands may run at once.
- **Journal and undo.** Before writing, the old version of every touched file is copied to `tools/scenekit/out/journal/<seq>-<command>/` with `{path, old_sha, new_sha}`. `undo` restores the latest entry only if every file's current hash equals its recorded `new_sha`; otherwise it refuses and lists the files edited since, so it never clobbers a later hand edit. Git stays the long-term undo; the tools never commit (AGENTS.md: commits only on user request). `tools/scenekit/out/` and `.cache/` are gitignored.

### D11: Git and parallel agents

Page PNGs are binary. Two branches that both append to the newest page produce a conflict git can't merge. For now, library writes are serialised: one scene-designer (one worktree) writes to the library at a time. A later `library rebase --from BRANCH` can re-append another branch's new tiles by hash and remap that branch's maps. (Open question 8.)

### D12: Engine changes, in phase order

Needed for the demo (phase 3):

- **E1 Multiple tile layers.** `TiledMap` keeps `Vec<TileLayer { name, data, above: bool, collides: bool }>` in file order. The chunk manager spawns tilemaps per layer at `-BACKGROUND_ZINDEX_ABS + index` (still below every YSort z, which is `(ysort - y) * 0.0001`, `camera.rs:21,39`). The forest map (one layer) must render unchanged.
- **E2 Multiple tilesets (pages).** The loader parses every tileset (external or embedded) into `{ first_gid, tilecount, image: Handle<Image>, colliders }`. The image is loaded as an asset dependency of the map (`load_context.load(path relative to the .tsj)`), which is wasm-safe; `GameAssets::tileset` is no longer used for rendering. `tile_at(layer, x, y) -> Option<(tileset, local, flip)>`. The chunk manager spawns one tilemap per (chunk, layer, tileset used in that chunk) with `TilemapTexture::Single(tileset.image)`. Collision reads each tileset's colliders. At map load, warn if a tileset's tile count exceeds `RenderDevice::limits().max_texture_array_layers`.
- **E3 Flip bits.** Mask `0xF0000000` (h `0x80000000`, v `0x40000000`, d `0x20000000`, hex rotation `0x10000000`) before resolving, and set `TileFlip { x: h, y: v, d }`. The implementer must check that bevy_ecs_tilemap's `d` means the same as Tiled's diagonal flip with a known asymmetric tile in game vs Tiled. Flipped *collision* can wait: log a warning and use the unflipped shape. scenekit doesn't emit flips by default.
- **E4 Above-player layer.** A tile layer with the bool property `above = true` renders at a fixed z above every YSort value (and below anything that must stay on top, such as world-space hints; the implementer checks `start_hint.rs` and the camera's far plane) and doesn't collide by default. Needed so a room's south wall and door lintels can cover the player.
- **E5 Start-map selection.** The demo has to start in `apartment.tmj` without replacing the forest. Recommended: `bevy_asset_loader`'s `standard_dynamic_assets` feature with `assets/start.assets.ron` providing the `world_map` key (editable without recompiling, wasm-safe). Alternatives: temporarily repoint `#[asset(path)]` (needs a code change each time), or a native-only env var (doesn't help wasm). The implementer must check that forest-specific systems (flora, NPCs, ending, wanderer fallback) tolerate a map without `Flora`/`NPCs` layers.

Can wait:
- **E6 Object properties** (`TiledObject.properties`), needed for doors and interactables.
- **E7 Multiple maps with transitions** (current-map resource, despawn/respawn chunks, colliders, borders, NPCs, flora, reset `ChunkManager`, spawn at the target door). This gets its own change.
- **E8** Flipped collision, animated tiles, a `Collision` object layer, and camera clamping or centring for rooms smaller than the viewport (the demo accepts black void around the room).

`tools/mapgen/validate.py` follows the engine: multiple layers and tilesets become valid after E1/E2; it errors on tilesets above 256 tiles or page images that aren't 256x256, on a non-bool `above`, and on `gen` gids missing from the manifest.

## Risks / Trade-offs

- [Generated rooms keep the "dollhouse" perspective or ignore the grid] -> block-out img2img pins layout and perspective; fixed-factor downscale snaps the grid; candidates are reviewed before `apply`. Quality is unverified until phase 2; if it fails, fall back to generating per material (floor region, wall band) instead of whole rooms.
- [Seams at the mask boundary] -> the context ring is visible to the model; `fill --ring 1` is opt-in; previews show seams at 4x.
- [Tile count explodes (every cell unique)] -> 256-tile pages scale linearly; one 20x15 room with 3 layers is at most about 900 tiles (4 pages, about 1 MB of PNG). Dedup and `--near` keep repeated floors shared. `library orphans` finds waste.
- [Many tilemap entities per chunk] -> bounded by layers x pages per chunk; fallback options in D2.
- [MPS non-determinism] -> provenance records everything needed to re-run, but a re-run is only best-effort identical.
- [Binary merge conflicts in pages] -> serialised library writes (D11).
- [Humans saving stale state in Tiled] -> hash checks catch tool-side races; Tiled-side overwrites can't be prevented, only documented.
- [Flip-diagonal semantics differ between Tiled and bevy_ecs_tilemap] -> explicit check in E3; the tools don't emit flips by default.

## Open Questions (proposed defaults in brackets)

1. Page size: 256 tiles (guaranteed on WebGPU) or 1024/2048, relying on adapter limits? [256]
2. One shared `gen` library, or themed libraries? [one]
3. Near-duplicate dedup: off by default? Tolerance when on? [off; 2 pixels with more than 8/255 difference]
4. Flip-aware dedup once the engine supports flips? [opt-in only]
5. Provenance manifest next to the pages (it ships to itch.io in `assets/`), or under `tools/`? [next to the pages; exclude from the web bundle later if size matters]
6. Start-map selection: a dynamic asset `.ron`, or temporarily repoint the asset path? [dynamic asset `.ron`]
7. Furniture as tiles on decor/above layers (this design) or as YSorted object sprites? [tiles for the demo; props as objects in a later change]
8. Serialise library writes across agents, or build `library rebase` now? [serialise]
9. Mark above layers with a layer property `above=true` or a name prefix? [property; the tool sets it]
10. Allow global edits on hand-made tilesets (forest)? [no, unless `--allow-foreign`]
11. Interior perspective: top-down 3/4 with visible south-facing wall faces, matching the forest? [yes]
