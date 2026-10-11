## 0. Decisions (user)

- [x] 0.1 Confirm or change the defaults in design.md "Open Questions" (page size 256, one `gen` library, near-dedup off, manifest next to pages, start map via dynamic asset `.ron`, furniture as tiles, serialised library writes, `above=true` property, no global edits on hand-made tilesets, 3/4 interior perspective) — user accepted all defaults on 2026-10-11 (3/4 view, furniture as tiles for the demo)

## 1. Phase 1: tile library, index, inspect, pixel edit, round trip (on `assets/maps/sandbox.tmj`)

- [x] 1.1 `tools/scenekit/` skeleton: `scene.py` CLI (one JSON object per command, error codes), imports `tools/mapgen/tmjlib.py`; add `tools/scenekit/out/`, `.cache/` and `assets/library/tilesets/gen/.lock` to `.gitignore`
- [x] 1.2 `tmjlib.py`: multi-tileset gid resolution with flip masking (`0xF0000000`), append-a-tileset helper that never shifts existing firstgids
- [x] 1.3 Library: page create/append (256x256 PNG, `.tsj` with tilecount 256), `tiles.json` manifest, content hash, insert with dedup (exact + metadata signature, batch dedup, `--near`), lock file
- [x] 1.4 Compositor: layers, visibility, opacity, Tiled flip semantics; `render --check-tmx`
- [x] 1.5 Index: on-demand scan of `assets/maps/**/*.tmj`
- [x] 1.6 Inspect commands: `render` (grid, ids, uses, collision, material, highlight), `cells`, `where` (+ `--sheet`), `diff` (paths and `git:REV:path`), `tile`, `library stats|sheet|check|orphans`
- [x] 1.7 Import core: per-cell diff, keep unchanged gids and flips, copy-on-write with inheritance, `--global` with `--expect-uses`, `--allow-foreign`
- [x] 1.8 `edit` ops (`px`, `rect`, `line`, `paste`, `copy`, `replace`, `remap`, `quantize`) and `tile edit`
- [x] 1.9 `export` / `import` with sidecar, conflict detection, `--flatten-into`
- [x] 1.10 `collide` and `material` (tile and region, fork on shared tiles), `materials.json` with the initial materials (floor, wall, wall_top, water, furniture, counter, door)
- [x] 1.11 Safety: atomic writes in the fixed order, read-hash re-check, `--if-hash`, `--dry-run`, journal, `undo`, `journal`
- [x] 1.12 `tools/mapgen/validate.py`: page image size and tile count checks, `gen` gids present in the manifest, `above` must be bool
- [x] 1.13 `tools/scenekit/README.md` with a worked example (same style as `tools/mapgen/README.md`)

Phase 1 acceptance (on a copy of `sandbox.tmj`):
- [x] 1.A1 `render --check-tmx` reports 0 differing pixels on sandbox and forest
- [x] 1.A2 `where tileset:16` lists the uses in both sandbox and forest; `cells` shows `uses.maps = 2` for a tile used in both
- [x] 1.A3 Setting 3 pixels in one cell changes exactly that cell to a new `gen:0` tile with parent `tileset:...`; `forest.tmj` is byte-identical; `diff git:HEAD:...` shows one cell
- [x] 1.A4 Export + import without edits leaves the map byte-identical; an edited export with two identical changed cells adds one tile
- [x] 1.A5 `edit --global` on a shared `gen` tile without `--expect-uses` fails and writes nothing; with the right count it rewrites the slot and records a revision
- [x] 1.A6 `undo` restores the last edit; after a manual change to the map, `undo` refuses
- [x] 1.A7 `validate` passes (the multi-tileset warning is expected until phase 3); the map opens in Tiled 1.12

## 2. Phase 2: generate region and inpaint with FLUX.2 klein

- [x] 2.1 `tools/artgen`: `inpaint` command and backend method using `Flux2KleinInpaintPipeline` (image, mask_image, image_reference, strength, size), same weights and LoRA handling, sidecar like `generate`
- [x] 2.2 `postprocess.downscale` with a given fixed grid (factor S, phase 0), reused by scenekit
- [x] 2.3 Canvas builder: context ring, block-out from a text or PNG layout via `materials.json`, auto scale, mask
- [x] 2.4 `generate` -> job dir (candidates, previews, `job.json`); `--palette scene|hex|none`; `--alpha`
- [x] 2.5 `fill` (`--cells`, `--mask`, `--empty`, `--like`, `--ring`)
- [x] 2.6 `apply JOB --pick K` through the import core with full provenance and layout materials/collision

Phase 2 acceptance (on a scratch map):
- [x] 2.A1 A 10x8 floor region with a layout produces 4 candidates in one run; every candidate lies on the 16 px grid (no half-pixels when shown at 4x) and uses only palette colours
- [x] 2.A2 `apply` changes only cells inside the region (`diff`); every new tile has complete provenance; `library check` passes
- [x] 2.A3 A 2x2 hole filled with `fill` changes only those cells; seams judged acceptable in the 4x preview (agent and user review)
- [x] 2.A4 Re-applying the same candidate adds 0 tiles (dedup)

## 3. Phase 3: engine changes and the demo apartment room

- [x] 3.1 E1: `TiledMap` keeps all tile layers (`above`, `collides` properties); chunk manager renders each layer at its own z below YSort
- [x] 3.2 E2: loader reads all tilesets, loads their images as map dependencies; `tile_at(layer, x, y)` returns (tileset, local, flip); one tilemap per (chunk, layer, tileset used); collision from every tileset and every colliding layer; warn above `max_texture_array_layers`
- [x] 3.3 E3: mask flip bits, set `TileFlip`; verify the diagonal flag against Tiled with an asymmetric tile; warn on flipped tiles with collision
- [x] 3.4 E4: `above = true` layers at a fixed z above every YSort value, no colliders by default
- [x] 3.5 E5: start map via `bevy_asset_loader` dynamic assets (`assets/start.assets.ron`); check flora, NPC, wanderer and ending systems tolerate a map without `Flora`/`NPCs`
- [x] 3.6 `cargo check` (native) and `cargo check --target wasm32-unknown-unknown`
- [x] 3.7 Forest regression: forest map renders and collides as before (F3 off)
- [x] 3.8 Demo: `assets/maps/apartment.tmj` (about 20x14 tiles; layers `Floor`, `Walls`, `Decor`, `Above` with `above=true`; `Spawn` with `SpawnPoint`) built only with scenekit commands by an agent; materials and collision set through `material`/`collide`; `validate` passes; opens in Tiled 1.12
- [x] 3.9 Run native with the apartment as start map: player spawns inside, collides with walls and furniture (F3 off), can't leave the room, south wall top covers the player
- [x] 3.10 Wasm build via `push_to_itch.sh` steps (without publishing) and a browser run on WebGPU: the room renders, console has no errors
- [x] 3.11 `assets/library/LIBRARY.md` entry for `tilesets/gen/`

## 5. Toolkit feedback from the first real use (apartment build)

- [x] 5.1 `generate --alpha` composes only the target layer (`--compose none|below|all`, default `below` = unchanged; named `--compose` because `--context` is already the ring size) so furniture on `Decor` isn't baked onto the floor; no layer reordering needed
- [x] 5.2 Per-job material colour/texture overrides in the layout (e.g. `@ # = wall #ddd5c4`) without editing `materials.json`
- [x] 5.3 `generate --init PNG`: use a block-out image as the canvas without writing it to the map or library
- [x] 5.4 `--quiet` (summary only) for `edit`, `apply`, `material`, `collide`; and `--if-hash auto` that uses the hash the journal recorded after the agent's last write, refusing if the file changed since
- [x] 5.5 `material`/`collide` report `tiles_updated` (metadata changed in place) next to `cells_changed`
- [x] 5.6 `generate --rerun JOB --seed N` (same inputs, new seed); queued jobs only go stale when a layer they read or write changed, not on any map write
- [x] 5.7 README and scene-designer.md updated for 5.1–5.6

## 4. Phase 4: scene-designer agent

- [ ] 4.1 `.claude/agents/scene-designer.md`: scope (scenes under `assets/maps/`, the `gen` library), tools (Bash, Read; Edit/Write only for ops/layout files and maps through the CLI), conventions (always `--if-hash`; inspect before and after every write; candidates reviewed before `apply`; copy-on-write by default; never `--global` or `--allow-foreign` without the lead's approval; no commits; adults only), working loop, report format (files changed, previews, verification, decisions stopped on)
- [ ] 4.2 Trial: brief the agent with "a small kitchen next to the apartment room"; it delivers using only scenekit and reports; the lead reviews renders and `diff`
