## ADDED Requirements

### Requirement: Image-space pixel edits translated to tiles

`scene.py edit` SHALL apply pixel operations (`px`, `rect`, `line`, `paste`, `copy`, `replace`, `remap`, `quantize`) given in map pixel coordinates to one tile layer and SHALL write the result back as tiles. Cells whose pixels are unchanged SHALL keep their gid including flip bits. Cells that become fully transparent SHALL become empty. Every other changed cell SHALL get a tile through library insert with dedup.

#### Scenario: Three-pixel fix
- **WHEN** an agent sets three pixels inside one cell of layer `Floor`
- **THEN** exactly that cell SHALL change, to a new or deduplicated tile whose parent is the previous tile, and no other cell in any map SHALL change

### Requirement: Copy-on-write by default

An edit, import or apply that changes a cell SHALL NOT modify the tile it previously referenced. The new tile SHALL inherit the old tile's collision, `type` and `material` unless `--no-inherit` is given.

#### Scenario: Shared floor tile edited in one place
- **WHEN** a tile used in 40 cells across two maps is edited in one cell without `--global`
- **THEN** that cell SHALL reference a new tile and the other 39 uses SHALL keep the original tile

### Requirement: Explicit global edits with impact report

With `--global`, the tool SHALL overwrite the edited library tile's pixels in its page and record a revision in the manifest. If the tile is used outside the edited cells, the command SHALL require `--expect-uses N` equal to the tile's total use count; otherwise it SHALL fail with an `impact` error listing every use and SHALL write nothing. Global edits of tiles from tilesets outside the library SHALL be refused unless `--allow-foreign` is given. A global edit that gives different new pixels to cells of the same tile SHALL fail.

#### Scenario: Global edit without acknowledgement
- **WHEN** an agent runs `edit --global` on a tile with 12 uses in three maps and omits `--expect-uses`
- **THEN** the command SHALL exit non-zero, list the 12 uses and leave every file unchanged

### Requirement: Export and import round trip

`scene.py export` SHALL write a region of one layer (or the composite) as a PNG at scale 1 with a sidecar JSON holding the map hash, layer, region, gids and per-cell hashes. `scene.py import` SHALL diff the PNG against the exported state, apply changed cells through copy-on-write, and fail with `conflict` if a changed cell also changed in the map since export, unless `--force`. Composite PNGs SHALL only be written back with `--flatten-into L`, which reports every cell it clears on other layers.

#### Scenario: Unchanged round trip
- **WHEN** an agent exports a region and imports the PNG without editing it
- **THEN** the map file SHALL be byte-identical and no tile SHALL be added

#### Scenario: Two identical edits
- **WHEN** an edited PNG gives two cells the same new pixels
- **THEN** both cells SHALL reference one new tile

### Requirement: Collision and material marking

`scene.py collide` and `scene.py material` SHALL set per-tile collision shapes (presets or explicit rectangles and polygons in tile-local pixels) and `material` properties in the page `.tsj`, either for one tile (global, requiring `--expect-uses`) or for a map region. For a region, a tile also used outside the region SHALL be forked (same pixels, new id) for the region's cells unless `--global` is given. Materials SHALL map to default collision shapes through `materials.json`.

#### Scenario: Marking a wall band
- **WHEN** an agent marks the top two rows of a room as `wall` and one of those tiles is also used elsewhere
- **THEN** the tiles used only in the region SHALL gain a full collision shape in place, and the shared tile SHALL be forked for the region's cells

### Requirement: Safe writes and undo

Every mutating command SHALL write files atomically, in the order page PNG, page `.tsj`, manifest, maps; SHALL abort with `conflict` if a file it read changed before its write; SHALL fail with `stale` if `--if-hash` doesn't match the map; SHALL support `--dry-run`; and SHALL journal the previous version of every file it writes. `scene.py undo` SHALL restore the latest journal entry only if every file still has the hash the command wrote, and SHALL otherwise refuse and list the files changed since. The tools SHALL NOT run git commands that change the repository.

#### Scenario: Undo after a hand edit
- **WHEN** an agent edits a map, a human then saves the same map in Tiled, and the agent runs `undo`
- **THEN** `undo` SHALL refuse, name the map as changed since, and leave all files unchanged

#### Scenario: Stale plan
- **WHEN** an agent passes `--if-hash` from an earlier `cells` call and the map has since changed
- **THEN** the command SHALL fail with `stale` and write nothing
