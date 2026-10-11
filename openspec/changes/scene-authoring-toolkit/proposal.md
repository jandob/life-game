## Why

Tiles are now made by agents and image models, so tile art is cheap. A scene no longer has to be assembled from a small hand-made tileset: every cell *may* hold a unique tile, though it doesn't have to. The bottleneck has moved to tooling. A designer agent can paint cells by id (`tools/mapgen/`) and generate single images (`tools/artgen/`), but it can't treat a scene as a picture: it can't see which tile sits where, it can't regenerate one region so that it fits its neighbours, and it can't fix three pixels without hand-managing tile ids and side effects on other maps.

The artgen benchmark also showed that whole floors and rooms come out painted (a "dollhouse" 3/4 view with a weak pixel grid), and that seamless 16 px tiles from text alone fail. Generation has to be anchored to the grid and to the scene around it, not asked for tiles directly.

**Decision (user):** the master copy stays in Tiled format (`.tmj` maps and `.tsj` tilesets). The new toolset gives agents an *image view* of scenes on top of that format: render a scene or region as an image with metadata (which tile is where, where else each tile is used), edit or generate in image space, and have the tool translate the result back into tiles.

## What Changes

- **Generated tile library**: one shared, append-only library of generated tiles at `assets/library/tilesets/gen/`, stored as fixed-size **pages** (`page-NNN.png` 256x256 px = 256 tiles of 16x16, plus `page-NNN.tsj`). A manifest `tiles.json` records each tile's content hash and provenance (backend, model, prompt, seed, parent tile, job). New tiles are deduplicated by exact content hash, with optional near-duplicate matching.
- **Usage index**: tile -> list of (map, layer, x, y, flip), computed on demand by scanning `assets/maps/**/*.tmj`. It is never stored in git.
- **New CLI `tools/scenekit/scene.py`** (Python, mise python + Pillow; it calls the artgen venv as a subprocess for model work), reusing `tools/mapgen/tmjlib.py`:
  - **Inspect**: `render` (pixel-exact compositor with grid, coordinates, tile-id, usage and collision overlays), `cells` (per-cell JSON with tile ids and usage counts), `where` (all uses of a tile), `diff` (two map versions, including `git:REV`), `tile` and `library` info.
  - **Generate**: `generate` (prompt + optional reference + optional material block-out -> image -> snapped to the 16 px grid -> cut -> dedup -> appended -> cells painted), as candidate jobs that are applied with `apply`.
  - **Fill/inpaint**: `fill` (masked cells with neighbourhood context -> new tiles) with `Flux2KleinInpaintPipeline`.
  - **Pixel edit**: `edit` (pixel ops in map image space). Shared tiles are **copy-on-write by default**; `--global` edits a tile everywhere and reports the impact from the usage index.
  - **Round trip**: `export` a region as PNG plus sidecar, edit it externally, `import` it back as tiles with dedup and conflict detection.
  - **Collision and material marking**: `collide` (per-tile shapes in the `.tsj`, per-region marking that resolves to tiles) and `material` properties.
  - **Safety**: atomic writes, optimistic concurrency against hand edits in Tiled (`--if-hash`), a journal with `undo`, `--dry-run` on every mutating command.
- **Engine changes** (`src/world/map/`), phased: multiple tile layers, multiple tilesets/pages, flip bits, an above-player layer and a configurable start map are needed for the demo; object properties and multi-map transitions come later.
- **Demo**: an apartment room built entirely by an agent with these tools, walkable in game, native and wasm.
- **Agent**: `.claude/agents/scene-designer.md`, which uses the toolkit.

## Capabilities

### New Capabilities
- `tooling/tile-library`: the paged generated-tile library, tile identity, provenance, dedup and the usage index.
- `tooling/scene-inspect`: rendering scenes and regions as images with metadata, per-cell JSON, usage lookup and diffs.
- `tooling/scene-edit`: pixel edits, export/import round trip, copy-on-write, collision/material marking, safety and undo.
- `tooling/scene-generate`: region generation and inpainting with the local FLUX.2 klein backend.

### Modified Capabilities
- `world/map`: multi-layer, multi-tileset rendering and collision, flip bits, the above-player layer and start-map selection. The `world/map` spec is still an unarchived change (`tiled-map-integration`), so the delta is written as ADDED.

## Non-Goals

- Replacing Tiled as the master format, or a custom scene file format.
- Wang/auto-tiling for generated tiles (generated scenes are painted per cell; Wang sets stay possible on hand-made tilesets).
- Animated tiles, lighting, and parallax.
- Doors and transitions between maps (phase 5 / a later change; listed here only so the data model allows them).
- Changing or re-paging the hand-made forest tileset.
- A GUI. Humans keep using Tiled; agents use the CLI.

## Impact

- **Tools**: new `tools/scenekit/` (CLI, compositor, library, index, journal); small shared changes in `tools/mapgen/tmjlib.py` (multi-tileset gid resolution helpers, flip handling); a new artgen entry point for inpaint/img2img (`backends/flux2_klein_pixel_lora.py` gains an `inpaint` method, same weights, no download).
- **Assets**: new `assets/library/tilesets/gen/` (pages + manifest), new `assets/maps/apartment.tmj` (demo), `assets/library/LIBRARY.md` entry.
- **Code**: `src/world/map/tiled_map.rs`, `chunk_manager.rs`, `collision.rs`, `mod.rs`, `src/assets.rs`; possibly `Cargo.toml` (`bevy_asset_loader` feature `standard_dynamic_assets`) for start-map selection.
- **Agents**: new `.claude/agents/scene-designer.md`.
- **Dependencies**: no new Python packages beyond the artgen venv (torch, diffusers, numpy, Pillow) and the mise python (Pillow). No new Rust crates.
- **Web build**: tile pages are limited to 256 tiles each because of the WebGPU texture-array-layer guarantee (see design D2). `tiles.json` ships with the assets folder (`push_to_itch.sh` copies all of `assets/`); it is small, but can be excluded later.
