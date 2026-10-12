# scenekit: see, query and edit Tiled scenes as images

Phase 1 of the `scene-authoring-toolkit` change. Tiled `.tmj`/`.tsj` stays the master copy. You edit pixels; the tool
turns them into tiles in a shared paged library (`assets/library/tilesets/gen/`), dedups them and never changes other
scenes by accident. Phase 2 adds model-backed `generate`, `fill` and `apply` (FLUX.2 klein in `tools/artgen/.venv`, as a subprocess).

Run from the repo root with the mise python (Pillow only):

```
mise exec -- python3 tools/scenekit/scene.py <command> ...
```

Every command prints ONE JSON object (`{"ok": true, ...}` or `{"ok": false, "error", "code", ...}`) and exits non-zero
on error. Codes: `bad_input`, `not_found`, `stale`, `conflict`, `impact`, `refused`, `locked`, `mismatch`,
`check_failed`, `unsupported`, `too_large`. Tests (`TestTile48`, `TestRecipes` cover the 48 px library and the recipes): `mise exec -- python3 tools/scenekit/test_scenekit.py` and `test_generate.py` (stub model).

## Concepts

- Cells are Tiled tile coordinates (origin top-left, y down). Regions are `x,y,w,h` in tiles. Pixel coordinates in
  `edit` ops are **map pixels** (`tile*TILE`, `TILE` = 16 or 48, see Libraries), never game coordinates.
- Tile refs: `gen:N` (library; page `N/256`, slot `N%256`), `tileset:local` (tileset name from the .tsj, e.g.
  `tileset:16` for the forest), `gen-003:7`, or a raw gid with `--map`. Flip suffixes `|h|v|d` are accepted and ignored for identity.
- Library = pages `page-NNN.png` (16x16 tiles: 256x256 at 16 px, 768x768 at 48 px) + `page-NNN.tsj` (+ `tiles.json` manifest with hash, parent,
  origin, source cell, revisions; `materials.json` with materials). Append-only: ids are never reused or renumbered.
  A page is added to a map's `tilesets` the first time the map uses it; existing gids never shift.
- **Copy-on-write is the default.** Changing a cell makes a new (or deduplicated) tile whose `parent` is the old tile and
  that inherits its collision/type/material. Other cells and maps keep the old tile. Unchanged cells keep their gid and flips.
- Dedup: same pixels AND same metadata (collision, type, material) reuse the tile; same pixels with other metadata is a
  separate tile (`meta_variants`). `--near N[:T]` (off by default) also reuses tiles differing in at most N pixels by more than T (default 8) and lists each match.
- Mutating commands take `--dry-run` and `--if-hash SHA` (fails with `stale` if the map changed since you looked;
  always pass it, the hash comes back as `map_hash` from `cells`, `render`, `edit`, ...).
  `--if-hash auto` compares against the hash this tool's own journal recorded after its last write (or undo) of that file,
  so chained writes need no shell bookkeeping. It never trusts anything else: if the file differs from that hash (hand edit
  in Tiled, another agent) it fails with `stale` exactly like a wrong explicit hash, and with no journal entry for the file
  it fails too. Take the `map_hash` from `cells`/`render` after you or a human changed the file outside the tool.
- `--quiet` (on `edit`, `import`, `apply`, `collide`, `material`) drops the per-cell and per-tile lists and keeps the summary:
  `counts` (`cells_changed`, `tiles_new`, `tiles_reused`, `near_matches`, and `tiles_updated` for collide/material), `map_hash`,
  `map_hash_before`, `changed_files`, `journal`, plus `quiet: true`.
- Writes are atomic, in the order page PNG, page .tsj, manifest, map, under `assets/library/tilesets/gen/.lock`. Every
  write is journaled in `tools/scenekit/out/journal/`. The tools never run git commands that change anything.
- If a human has the map open in Tiled with unsaved changes and saves, that overwrites the tool's write. Tell them to
  reload first (Tiled offers it); the tool cannot prevent it.

## Libraries and tile sizes (16 px `gen`, 48 px `gen48`)

The tile size is a property of the **library**, read from `tile_size` in its `tiles.json`. There are two libraries:
`assets/library/tilesets/gen/` (16 px, pages 256x256; the engine fixtures and `sandbox`) and `assets/library/tilesets/gen48/`
(48 px, pages 768x768 with 16x16 tiles, `.tsj` with `tilewidth = tileheight = 48`; the world of `route1_flat`, 74 art px
per metre). One command works on one library:

- `--lib gen|gen48|PATH` (anywhere on the command line) or `SCENEKIT_LIB=DIR` picks it explicitly;
- otherwise it follows the **map**: the first `.tmj` argument with `tilewidth` 48 selects `gen48`, 16 or none selects `gen`.
- A map whose tile size differs from the active library gives `mismatch` and names the `--lib` to use.

Everything scales with `TILE`: `edit` pixels, `export`/`import`, `--init` canvases, collision shapes (`full` is 48x48,
`bottom` 48x24, `bottom-quarter` 48x12), the block-out textures (plank boards TILE/4 px), `render` and `--check-tmx`.
`tmj.py new --tile 48 --tileset assets/library/tilesets/gen48/page-000.tsj` scaffolds a 48 px map. `tmj.py validate` refuses
maps that mix tile sizes. Pages are added on demand, `library check --lib gen48` verifies sizes and manifest.

Model canvases: a region is upscaled by an integer S (<= 8) with the long side <= 1024 raw px, so one `generate` covers at
most about 128 art px per side at S = 8, i.e. **2 cells of 48 px**. Use `generate` for small patches and touch-ups at 48 px.
Props and textures at the world's density are made one by one with `recipe` below, never as whole rooms.

### recipe: textures and props at 48 px (design D6)

`recipe texture --name N --kind floor|wall --size 48|96 --prompt "oak planks" [--grid 8] [--palette FILE.hex] [--seed S] [--n 4]`
`recipe prop --name N --size W,H --prompt "white fridge" [--grid G] [--palette FILE.hex] [--seed S] [--n 4]`

Print a plan (`steps[]` with the exact command lines; nothing is run or written) with these fixed choices:
- **Style suffix** of the characters: `anime style pixel art, thick dark outlines, flat cel shading with two tones`; **shared
  palette** `tools/artgen/palettes/interior.hex` (override with `--palette`), snapped in the same step as the grid.
- **Fixed grid**: `--grid` is the raw px per art px (default 8, the generator's own pixel). A texture is `size x grid` px
  square (384 or 768). A prop canvas is `(W+4) x (H+4)` art px times the grid, rounded to 16. If the long side would exceed
  1024 raw px the grid drops to 7 or 6 and a warning says so; beyond that `too_large` (split the prop). Never `--grid auto|fit`:
  every prop of a scene keeps one pixel size.
- **Textures** are made seamless by shifting the generated image by half in x and y (`texture roll`), repainting the centre
  cross where the old wrap-around seams now meet (`artgen mask` + `inpaint`), then `snap`. `texture seam IMG` checks the
  wrap-around edge against the 95th percentile of the interior edges (`ratio <= 1.5` or `check_failed`).
  `texture size IMG` prints the opaque box (props: crop to the table size before stamping).
- **Stamping**: an `edit` with a `paste` op (textures with `copy` ops across the area; props `mode: over` on `Decor`, bottom edge
  on a cell boundary), then `collide region` / `material`. Size table (art px): door leaf 63x148, wall face 192 high, bed 104x148,
  fridge 44x133, window 89x104, counter 67+44 per 0.65 m; room floors 333x370 (main), 185x222 (kitchen).
  Props above about 120 art px per side run at grid 6 or 7: check the render, or generate them in two parts.

## Inspect

| command | what |
|---|---|
| `render MAP --out PNG [--region x,y,w,h] [--layers A,B\|all] [--scale N] [--grid [N]] [--ids] [--uses] [--collision] [--material] [--highlight TILE...] [--context K]` | Pixel-exact render (own compositor: layer order, `visible`, `opacity`, flips). `--ids` prints refs at scale >= 4, else letter codes with a legend in the JSON. `--uses`: green unique, yellow shared in this map, red shared with other maps. JSON has `px_origin`, `margin`, `legend`. |
| `render MAP --check-tmx` | Compare with `tmxrasterizer` at scale 1; `differing_pixels` must be 0 (else exit 1, `differing_cells` listed). Opacity < 1 over a partly transparent backdrop can be off by one channel level. |
| `cells MAP [--region] [--layers]` | JSON per cell: tile, gid, flip, hash, `uses {map,total,maps}`, collision, material; legend with provenance. |
| `where TILE [--maps GLOBS] [--sheet PNG --context K]` | Every use across `assets/maps/**/*.tmj` (scanned on demand, flips masked, nothing cached). |
| `diff A B [--region] [--out PNG]` | A/B are paths or `git:REV:path` (read with `git show`). Changed cells per layer, `pixels_changed`, `tiles_added`. |
| `tile TILE [--out PNG --scale 8]` | Provenance, metadata, uses. |
| `library stats\|sheet --page N --out PNG\|check\|orphans` | `check` verifies page sizes, tilecount, manifest vs slot hashes (exit 1 on problems). `orphans` never deletes. |

## Edit

`edit MAP --layer L --ops OPS.json|'[...]' [--global --expect-uses N] [--near N] [--no-inherit] [--if-hash H] [--dry-run]`

Ops (map pixels, applied in order, any error aborts with nothing written; colours `#rrggbb[aa]`, `#00000000` erases):
`{"px":[x,y,c]}`, `{"rect":[x,y,w,h,c]}`, `{"line":[x1,y1,x2,y2,c]}`, `{"paste":{"at":[x,y],"image":"a.png","mode":"over|replace"}}`,
`{"copy":{"from":[x,y,w,h],"to":[x,y]}}`, `{"replace":{"from":c,"to":c,"region":[...]}}`, `{"remap":{"map":{"#a":"#b"},"region":[...]}}`,
`{"quantize":{"palette":"file.hex","region":[...]}}`. A cell that becomes fully transparent becomes empty (gid 0).

`export MAP --region R (--layer L | --composite) --out PNG` writes the PNG (scale 1) and `PNG.json` (map hash, gids, per-cell
hashes). `import PNG [--layer L] [--force] [--flatten-into L]` diffs against the export, applies only changed cells, and
fails with `conflict` if a changed cell also changed in the map since (unless `--force`). An unchanged round trip
does not touch any file. Composite exports are context only; `--flatten-into L` writes them to layer L, clears the same
cells on other non-`above` layers (listed in `cleared`) and merges their collision.

**Global edits** (`--global`, `tile edit TILE --ops ... --expect-uses N`) overwrite a library tile's slot in place and
record a revision. If the tile is used outside the edited cells, `--expect-uses N` must equal its total use count, else
`impact` with every use listed and nothing written. Hand-made tilesets (forest) are refused unless `--allow-foreign`
(needs the lead's approval). Different new pixels for cells of the same tile fail.

`collide tile TILE --shape S --expect-uses N` / `collide region MAP --layer L --region R --shape S`,
`material tile TILE NAME --expect-uses N` / `material region MAP --layer L --region R NAME [--no-shape]`.
Shapes: `none full top bottom left right top-quarter bottom-quarter rect:x,y,w,h poly:x1,y1,...`. Materials come
from `materials.json` and set their default shape (floor none, wall full, wall_top none, water full, furniture full,
counter bottom, door none). For a region, a tile also used elsewhere is **forked** (same pixels, new id, origin `fork`)
for the region's cells; hand-made tiles are always forked.
Result: `cells_changed` (cells that now point at another tile) and `tiles_updated` (tiles whose metadata was changed **in place**, a
tile used only inside the region; `counts.tiles_updated`). A region call that reports `cells_changed: 0` but `tiles_updated: N` did its job. `--global --expect-uses N` (N = summed total uses) changes tiles in place everywhere.

`undo [--steps N]` restores the latest journal entry only if every file still has the hash the command wrote;
otherwise it refuses (`refused`) and names the files changed since. `journal` lists entries.

## Generate, fill, apply (phase 2)

Needs `tools/artgen/.venv` and the cached FLUX.2 klein weights (no downloads). Every other command still runs without them.
`generate` and `fill` write ONLY a job directory (`tools/scenekit/out/jobs/<id>/`: `canvas.png`, `mask.png`, `raw-K.png`,
`cand-K.png` (region at 1x), `preview-K.png` (before | after, 4x, grid + yellow outline of the generated cells), `contact.png`,
`job.json`, `model.log`); they never touch the map or the library. `apply` commits one candidate.

`generate MAP --layer L --region x,y,w,h [--layout FILE] --prompt TEXT [--n 4] [--seed 1] [--strength 0.75] [--context 2]
[--scale auto|2..8] [--palette scene|none|FILE.hex] [--colours 32] [--alpha] [--compose below|none|all] [--init PNG] [--ref PNG...]
[--grid fixed|detect] [--near N] [--dry-run] [--if-hash H]` and `generate --rerun JOB [--seed N] [--n K]`

- Canvas = (by default) the composite of layers up to L around the region plus `--context` cells (clipped; shrinks if too big), the
  block-out drawn inside the region, upscaled by an integer S (nearest). `auto` = largest S with the long side <= 1024 px.
  Region more than 512 px (32 cells) on a side: error `too_large`, split it. Mask: white on the region.
- `--layout`: text grid, one char per cell, chars from `materials.json` (`.` floor `#` wall `^` wall_top `~` water `F` furniture
  `c` counter `D` door; space or `_` = keep what is there; `@ X = material` adds a legend line), or a PNG with one pixel per cell
  in a material's `colour`. Materials may have `"texture": "planks"|"wall"`, which draws structure into the block-out
  (boards, a lit top lip and baseboard for 3/4 wall faces) so the model refines instead of inventing the layout. Material
  `hint`s are appended to the prompt.
- `--compose below|none|all` (default `below`, the behaviour above) chooses which layers the canvas shows around the region:
  `none` = only layer L, so `--alpha` furniture on `Decor` is generated without the floor baked into it (the context ring is
  transparent/key colour; the palette still follows the scene); `all` = every visible tile layer, also those above L. The
  job records it as `compose`. No layer reordering needed.
- Per-job material colours: a text-layout legend line may override the colour and/or texture of a material:
  `@ O = wall #ddd5c4` or `@ O = wall #ddd5c4 texture=none` (textures `planks`, `wall`, `none`). The variant keeps the base
  material's shape, hint and layer, is written to the map as the base material (`wall`), and `materials.json` is never
  touched. The job lists them as `layout_variants`.
- `--init PNG`: a block-out image of the region (exactly `w*TILE` x `h*TILE` px, RGBA) used as the canvas inside the region
  (opaque pixels win over `--layout`/the current pixels; transparent keeps them). It exists only in the job directory, so no
  block-out tiles are written to the map or the library and none are left as orphans. The job records its hash as `init`.
- Output is snapped by an exact S x S block mode (no grid detection; `--grid detect` is only a fallback), locked to a palette
  (`scene` = colours of the map outside the region; adaptive `--colours` when the map has < 8), cleaned up, cut to the region.
  `--alpha` generates on a key colour and cuts it out. `--dry-run` writes only canvas and mask: look at them first.
- Strength: ~0.75 keeps the block-out almost as is (recolours it); 0.9 lets the model add detail; 1.0 is pure inpaint.
  One model process makes all `--n` candidates (about 45-70 s each at 600-900 px on this machine, plus about 30 s load/encode):
  run it in the background.
- Warnings: a layout material whose `layer` hint differs from `--layer` is written to `--layer` anyway.

`fill MAP --layer L (--cells "x,y;x,y" | --mask PNG | --empty --region R) [--like TILE] [--ring 1] [--context 3] [--strength 1.0] ...`
is the same pipeline for any cell set; only those cells are candidate pixels (`--ring 1` adds the first context ring, which then
goes through copy-on-write like any other cell). `--like` passes the tile (upscaled) as a reference image. `--mask` is one
pixel per cell (map-sized, or `--region`-sized).

`apply JOB --pick K [--force] [--near N[:T]] [--if-hash H|auto|job] [--quiet] [--dry-run]` runs the import core (dedup, copy-on-write): origin
`generate`/`fill`, `gen` provenance (prompt, seed, strength, steps, scale, refs, layout hash, palette), the layout cell's
material and its collision shape. Cells that changed since the job was made give `conflict` unless they already show the
candidate, so re-applying a candidate is a no-op (0 new tiles).

**Retry and staleness.** `generate --rerun JOB [--seed N] [--n K]` (and `fill --rerun JOB ...`) repeats a job with the same inputs
(layer, region, prompt, layout, `--init`, refs and every parameter; layout, mask and init files are copied into the job
directory, so they may be gone or edited) and new seeds (default: the job's seed plus its `n`). Only `--seed`, `--n`,
`--if-hash` and `--dry-run` may be combined with it. It reads the map as it is now. The result has `rerun_of`.
`apply --if-hash job` checks the job's recorded **scope** instead of the whole map hash: `job.json` has `scope.layers` (a hash of
every tile layer the job read for its canvas, per `--compose`, plus the layer it writes) and `scope.structure` (map size, layer
list, tileset list). The job is `stale` (with `reasons`) only if one of those layers changed or the structure did (layer
added/removed/renamed/reordered, tileset list changed, which includes the first use of a new library page). Writes to unrelated
layers don't stale it; with `--compose none` a job on `Decor` survives any `Ground` edit. A stale job: `generate --rerun`.
Without `--if-hash job`, `apply` still refuses (`conflict`) when cells of the job's region changed on its layer. The scene
palette is not part of the scope.

Always LOOK at `contact.png` and `preview-K.png` before `apply`.

## Objects and paths (mapgen)

Object layers are written with `tools/mapgen/tmj.py object` (scenekit edits pixels only). Scene paths are polylines:

```
t="mise exec -- python3 tools/mapgen/tmj.py"
$t layer MAP add Paths --type object
$t object MAP --layer Paths add --name SamanthaToKitchen --polyline "188,292 160,260 160,144 312,144 392,104"
$t object MAP --layer Paths list            # vertices printed in absolute map pixels
```

Vertices are absolute **map pixels** (not tiles, not game coordinates), at least two. They are stored the Tiled way: the
object's `x`/`y` is the first vertex and `polyline` holds every vertex relative to it (the first is `0,0`). `validate`
reports a vertex outside the map; `tmj.py render --debug` draws the lines. To change a path, `remove` it and `add` it again.
Game convention (opening-viewing D7): path vertices are feet positions, each segment at least 8 px clear of colliders.

## Worked example

```
s="mise exec -- python3 tools/scenekit/scene.py"
cp assets/maps/sandbox.tmj assets/maps/work.tmj
$s render assets/maps/work.tmj --region 0,0,8,6 --scale 4 --grid --ids --out /tmp/r.png      # look at it
H=$($s cells assets/maps/work.tmj --region 0,0,1,1 | python3 -c 'import json,sys;print(json.load(sys.stdin)["map_hash"])')
$s edit assets/maps/work.tmj --layer Ground --if-hash $H \
   --ops '[{"rect":[32,32,16,2,"#5a3b20"]},{"px":[40,40,"#ffffff"]}]'                         # cells -> gen tiles
$s material region assets/maps/work.tmj --layer Ground --region 2,2,1,1 wall                  # wall + full collision
$s diff git:HEAD:assets/maps/sandbox.tmj assets/maps/work.tmj --out /tmp/d.png
$s render assets/maps/work.tmj --check-tmx
$s library check
mise exec -- python3 tools/mapgen/tmj.py validate assets/maps/work.tmj
$s undo                                                                                       # take it back
```

Working loop: render + `cells` first, `--dry-run` or `--if-hash` on every write, render and `diff` after, `library check`
and `validate` before finishing.

## Limits (phase 1)

Orthogonal finite maps, tile layers only for pixels; layer offsets/parallax are refused. The game loader reads all
layers and tilesets (and `above=true` layers). `gen` pages are 256 tiles (WebGPU array-layer limit).
Library writes are serialised; do not run two agents on the library in parallel branches (binary page merges).
