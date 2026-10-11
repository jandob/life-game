## ADDED Requirements

### Requirement: Pixel-exact scene rendering

`scene.py render` SHALL render a map or a region of it from its tile layers (bottom to top, honouring `visible`, layer `opacity` and Tiled flip semantics) to a PNG at an integer scale. At scale 1 the output SHALL match `tmxrasterizer` pixel for pixel for the supported map subset. Overlays SHALL be optional: grid with coordinate labels, per-cell tile ids, usage tint, collision shapes, materials, and outlines around the cells that use given tiles. The JSON result SHALL include the image path, the region, the scale, the pixel origin and the overlay legend.

#### Scenario: Region with ids
- **WHEN** an agent runs `render MAP --region 4,2,8,6 --scale 4 --grid --ids --out r.png`
- **THEN** `r.png` SHALL show the 8x6-cell region at 4x with grid lines, Tiled coordinates in the margin and the tile ref in every non-empty cell

#### Scenario: Compositor check
- **WHEN** `render --check-tmx` runs on a map with several layers and flipped tiles
- **THEN** the tool SHALL report zero differing pixels against `tmxrasterizer`, or list the differing cells

### Requirement: Per-cell metadata

`scene.py cells` SHALL return, for a map or region, every tile layer with its `above` flag and, per cell, the tile ref, gid, flip flags, content hash, collision presence, material, and use counts (in this map, in total, number of maps), plus a legend with short provenance for every distinct tile.

#### Scenario: Shared tile is visible as shared
- **WHEN** a cell's tile is also used in another map
- **THEN** that cell's `uses.maps` SHALL be at least 2

### Requirement: Tile usage lookup

`scene.py where TILE` SHALL list every use of the tile across the scanned maps, and SHALL optionally write a contact sheet showing each use with surrounding context cells.

#### Scenario: Unused tile
- **WHEN** an agent queries a library tile no map uses
- **THEN** the result SHALL have `count: 0` and an empty `uses` list

### Requirement: Diff of two map versions

`scene.py diff A B` SHALL compare two versions of a map, where each side is a path or `git:REV:path` read without changing the working tree, and SHALL report the changed cells per layer (old and new tile), the number of changed pixels and the library tiles added, plus an optional image with both versions and the changed cells highlighted.

#### Scenario: Diff against the last commit
- **WHEN** an agent runs `diff git:HEAD:assets/maps/apartment.tmj assets/maps/apartment.tmj --out d.png`
- **THEN** the result SHALL list exactly the cells the agent changed since HEAD, and `git status` SHALL be unchanged by the command
