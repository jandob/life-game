# tools/aseprite: hand-editable art in Aseprite

The game loads `.aseprite` files directly (bevy_aseprite_ultra), so saving in Aseprite is all it
takes to change in-game art. No export step.

## Layout of a look file

`assets/library/characters/looks/<look>/<look>.aseprite`, canvas 128x256 (one look cell, feet on row 245).

| Layer | What it holds |
|---|---|
| `gen` (locked) | generated pixels, written only by `sync_gen.py` |
| `paint` | your hand edits, drawn over `gen`; never touched by scripts |

Tags are `<clip>_<facing>`: `idle_down`, `idle_right`, `idle_up`, `walk_right`. Left is the right
tag mirrored in code (`mirror_left` in `look.ron`). Frame durations come from the file.

Rules of thumb:

- Draw fixes on `paint`. A paint layer can only add or cover pixels.
- To remove pixels, unlock `gen` and edit it, then open that cel's properties and set its user data
  text to `frozen`. `sync_gen.py` will then leave that frame's gen pixels alone (and say so).
- Don't add hidden layers: bevy_aseprite_ultra 0.9 renders all layers, hidden or not.
- Extra layers are fine (they all show in game); only `gen` is written by the script.
- Keep the frame and tag layout. If it must change, update `LOOKS` in `sync_gen.py` too.
- With `cargo run --features bevy/file_watcher` the running game reloads the file on save.

## Regenerating

artgen and `tools/sprite_gen/looks/build_looks.py` write strips to `art/characters/<name>/looks/<look>/`.
Then:

```sh
python tools/aseprite/sync_gen.py            # create missing .aseprite files, refresh gen layers
python tools/aseprite/sync_gen.py --check    # report only (also run by art/test_art.py)
python tools/aseprite/test_sync_gen.py       # tests for the file reader/writer
```

`asefile.py` is a small reader/writer for the Aseprite format, so none of this needs Aseprite
installed (it also runs in cloud sessions). Reading keeps every chunk as is, so files saved by
Aseprite round-trip unchanged apart from the replaced gen cels.
