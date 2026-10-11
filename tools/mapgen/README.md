# mapgen: author Tiled maps tile by tile, without the Tiled GUI

You say exactly which tile goes where; the tool owns the file format, validation and previews.
There is no room/level spec. Output is exactly what `src/world/map/tiled_map.rs` reads: `.tmj` with
JSON-array layer data (no compression) and EXTERNAL `.tsj` tilesets referenced by relative path.

Run from the repo root:

```
mise exec -- python3 tools/mapgen/tmj.py <command> ...      # alias: t
```

Needs Pillow (in the mise python) and Tiled from mise (`tmxrasterizer`, `tiled`; found via `mise which tiled`,
or point the `TMXRASTERIZER` / `TILED` env vars at the binaries).
Every command prints one JSON line and exits non-zero on error (`{"ok": false, "error": ...}`).
`show` prints text (use `--json` for JSON). Writes are atomic (temp file + rename).

## Concepts

- Coordinates are Tiled tile coordinates: origin top-left, x right, y down. Object positions are pixels.
- A **tile** is a global gid (`17`), or `"tilesetname:localid"` (`"tileset:16"`; the name is the `name` field of
  the .tsj, shown by `layer`/`tileset`/`new`). `0`/`null` = empty. Flip flags: `"tileset:7|h"`, `|v`, `|d`
  (combinable: `"tileset:7|h|d"`). Flags are written to the file, but **the game loader does not mask them yet**,
  so flipped tiles render wrong in game (validate warns). Tiled and tmxrasterizer render them correctly.
- Property values (`--prop k=v`) are parsed as JSON where possible: `true`, `12`, `1.5`, else string (`'"12"'` forces string).

## Game-loader limits (validate warns about them)

- Only the LAST tile layer is used; only the first tileset's collision/first gid is used.
- Object layers `Spawn` (object named `SpawnPoint`), `NPCs`, `Flora` are read by name. The loader treats object x,y as a
  point and ignores size, so point objects placed with `--tile` land on the tile centre.
- Tile collision comes from the tileset's per-tile collision shapes.

## Commands

### new
`new MAP --width W --height H [--tile 16] --tileset PATH.tsj [--tileset ...] [--no-default-layer] [--force]`
Creates an empty map with a tile layer `Ground` (opt out with `--no-default-layer`). Tileset paths are stored relative to MAP;
firstgids are assigned in order.

### layer
`layer MAP list`
`layer MAP add NAME [--type tile|object] [--index N] [--prop k=v ...]` (index 0 = bottom of stack; default top)
`layer MAP remove NAME` / `rename OLD NEW` / `move NAME --index N` / `set-prop NAME [--prop k=v] [--unset k]`

### paint
`paint MAP --layer L --ops OPS.json` (or ops on stdin, or `--ops -`). Atomic: if any op fails (bad tile, out of
bounds), nothing is written. Ops are a JSON list, one key per op, applied in order (later ops overwrite):

| op | meaning |
|---|---|
| `{"set": [x, y, tile]}` | one cell |
| `{"rect": [x, y, w, h, tile]}` | filled rectangle |
| `{"outline": [x, y, w, h, tile]}` | hollow rectangle; optional 6th value = thickness |
| `{"line": [x1, y1, x2, y2, tile]}` | Bresenham line, inclusive |
| `{"erase": [x, y, w, h]}` | set cells to empty |
| `{"stamp": {"at": [x, y], "rows": [[tile, ...], ...]}}` | paste a block; 0/null cells are skipped |
| `{"fill": [x, y, tile]}` | flood fill (4-neighbour) of the cells matching the start cell |

### object
`object MAP --layer L list`
`object MAP --layer L add --name N [--type T] (--tile X Y | --px X Y) [--size-tiles W H | --size-px W H] [--prop k=v ...]`
`object MAP --layer L move (--id N | --name N) (--tile X Y | --px X Y)`
`object MAP --layer L remove (--id N | --name N)`
`object MAP --layer L set-prop (--id N | --name N) [--prop k=v] [--unset k] [--rename NEW] [--type T]`
Without a size, an object is a Tiled point, and `--tile` puts it at the tile centre. With a size it is a rectangle and
`--tile` is its top-left corner.

### show
`show MAP [--layer L] [--region x,y,w,h] [--gid] [--json]` : text grid of `tileset:id` (`.` = empty) with x/y headers,
plus the objects inside the region. Default: every tile layer.

### tileset
`tileset FILE.tsj [--all] [--sheet OUT.png] [--sheet-scale 4]` : JSON with tile count, `collision_ids`, per-tile
type/properties/shapes (only tiles that have metadata; `--all` lists every id) and Wang sets. `--sheet` writes a
contact sheet with the id on every tile (red border = has collision, yellow id = has type/properties). Look at it before painting.

### render
`render MAP OUT.png [--scale 2] [--grid [N]] [--debug] [--region x,y,w,h]`
Base image from `tmxrasterizer` (object layers hidden). `--grid N` adds lines and coordinate labels every N tiles
(plain `--grid` = every tile; a margin is added). `--debug` adds translucent red collision shapes, labelled objects and the
layer list. Collision overlay ignores flip flags. Use `--region` on big maps.

### validate
`validate MAP [--no-tiled]` : checks orthogonal/finite, tileset files and images exist, every gid resolves to a tileset,
layer data is a JSON array of length w*h, exactly one `SpawnPoint` inside the map and not on a collision tile, objects
in bounds, and that `tiled --export-map` can load the file. Exit 1 on errors. Warnings (do not fail): multiple tile
layers, multiple tilesets, flip flags, SpawnPoint outside layer `Spawn`, duplicate object ids.

`validate` also errors on tilesets above 256 tiles, library pages (`page-NNN.tsj`) that are not 256x256, `gen` gids missing
from the neighbouring `tiles.json`, and a non-bool `above` layer property. See `tools/scenekit/` for the library tools.

## Worked example

```
t=tools/mapgen/tmj.py
TS=assets/library/tilesets/forest/tileset.tsj
mise exec -- python3 $t tileset $TS --sheet /tmp/sheet.png          # then look at the sheet
mise exec -- python3 $t new assets/maps/demo.tmj --width 20 --height 15 --tileset $TS
mise exec -- python3 $t layer assets/maps/demo.tmj add Spawn --type object
cat > ops.json <<'EOF'
[
 {"rect": [0, 0, 20, 15, "tileset:9"]},
 {"rect": [1, 1, 18, 13, "tileset:16"]},
 {"rect": [1, 7, 18, 1, "tileset:18"]},
 {"set": [4, 3, "tileset:97"]}
]
EOF
mise exec -- python3 $t paint assets/maps/demo.tmj --layer Ground --ops ops.json
mise exec -- python3 $t object assets/maps/demo.tmj --layer Spawn add --name SpawnPoint --tile 4 7
mise exec -- python3 $t show assets/maps/demo.tmj --region 0,5,8,5
mise exec -- python3 $t render assets/maps/demo.tmj demo.png --scale 4 --grid 5 --debug
mise exec -- python3 $t validate assets/maps/demo.tmj
```

Working loop: look at the tileset sheet, `new`, paint in batches, `show` a region to verify, `render --debug` to
see it, `validate` before finishing.

## Limitations

- Orthogonal, finite, tile layers + object layers only (no image/group layers, no infinite maps, no Wang auto-tiling).
- Object shapes: points and rectangles only. Embedded tilesets are read but `new` only creates external refs.
- Flip flags are not supported by the game loader yet. Rotated collision shapes are not drawn rotated.
