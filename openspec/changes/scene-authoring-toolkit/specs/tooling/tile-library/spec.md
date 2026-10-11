## ADDED Requirements

### Requirement: Paged generated-tile library

Generated tiles SHALL be stored in a shared library directory (default `assets/library/tilesets/gen/`) as pages. Each page SHALL be a 256x256-pixel RGBA PNG holding 16 columns by 16 rows of 16x16 tiles, with unused slots fully transparent, plus an external Tiled tileset `page-NNN.tsj` with `tilecount` 256 and `columns` 16 that references it. Pages SHALL be append-only: new tiles go into the first free slot of the newest page, and a new page SHALL be created when it is full. Tile slots SHALL never be reused or renumbered.

#### Scenario: Appending to a full page
- **WHEN** a new tile is inserted and the newest page has no free slot
- **THEN** the tool SHALL create the next page (PNG and `.tsj`) and place the tile in its slot 0

#### Scenario: Pages stay loadable
- **WHEN** any page is written
- **THEN** its PNG SHALL be exactly 256x256 pixels and its `.tsj` SHALL open in Tiled 1.12 and pass `tiled --export-map` for a map that references it

### Requirement: Tile identity and provenance

Every library tile SHALL have a stable id `gen:N` (page `N / 256`, slot `N % 256`) and a manifest entry in `tiles.json` with its content hash, creation time, origin (`generate`, `fill`, `edit`, `import` or `fork`), parent tile (if any), job id and source cell. Model-made tiles SHALL additionally record backend, model ids, LoRA scale, full prompt, seed, strength, steps, scale, reference-image hashes, layout hash and palette. The content hash SHALL be the sha256 of the 16x16 RGBA bytes with every fully transparent pixel normalised to `(0,0,0,0)`.

#### Scenario: Provenance of a generated tile
- **WHEN** an agent applies a generation job
- **THEN** every new tile's manifest entry SHALL contain enough parameters to re-run the job that created it

#### Scenario: Manifest and pages agree
- **WHEN** `scene.py library check` runs
- **THEN** it SHALL report every slot whose pixel hash differs from the manifest, every manifest entry without a slot, and every page with the wrong image size or tile count

### Requirement: Dedup on insert

Inserting a tile SHALL reuse an existing tile when its pixel hash and its metadata signature (collision shapes, `type`, `material`) both match. Pixel-identical tiles with different metadata SHALL be stored as separate tiles. Near-duplicate reuse SHALL happen only when requested (`--near N[:T]`), and every near match SHALL be reported with its pixel difference. Identical new tiles within one batch SHALL be stored once. Fully transparent tiles SHALL never be stored; their cells become empty.

#### Scenario: Exact duplicate
- **WHEN** an import produces a cell whose pixels and inherited metadata equal an existing tile
- **THEN** the cell SHALL reference the existing tile and no tile SHALL be appended

#### Scenario: Near duplicate not requested
- **WHEN** a new tile differs from an existing tile in one pixel and `--near` is not given
- **THEN** the new tile SHALL be appended

### Requirement: Cross-scene usage index

The tools SHALL compute, on demand, an index from every tile (of every tileset, not only the library) to its uses `(map, layer, x, y, flip)` across `assets/maps/**/*.tmj`, with flip bits masked before resolving gids. The index SHALL NOT be stored in git or under `assets/`.

#### Scenario: Index reflects a hand edit
- **WHEN** a human paints a tile in Tiled and saves, then an agent queries that tile's uses
- **THEN** the result SHALL include the newly painted cell without any rebuild step

### Requirement: Maps gain pages without shifting gids

When a map first uses a tile from a page it doesn't reference yet, the tool SHALL append that page's tileset to the end of the map's `tilesets` list with the next free `firstgid`. The tools SHALL NOT remove or reorder a map's tilesets automatically.

#### Scenario: First use of a new page
- **WHEN** an edit places a tile from `page-003` into a map that references only the forest tileset and `page-000`
- **THEN** `page-003.tsj` SHALL be appended to the map's tilesets and every existing gid in the map SHALL be unchanged
