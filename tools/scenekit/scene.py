#!/usr/bin/env python3
"""scene.py - see, query and edit Tiled scenes as images, backed by a shared paged tile library. See README.md."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common  # noqa: E402
from common import SceneError  # noqa: E402


def emit(obj):
    print(json.dumps(obj))


def mutating(p):
    p.add_argument("--dry-run", action="store_true", help="compute everything, write nothing")
    p.add_argument("--if-hash", help="fail with 'stale' unless the map's current sha256 matches")


def edit_flags(p):
    p.add_argument("--global", dest="global_", action="store_true", help="overwrite tile slots in place (needs --expect-uses)")
    p.add_argument("--expect-uses", type=int, help="total use count of the tile(s) a global edit changes")
    p.add_argument("--allow-foreign", action="store_true", help="allow global edits of hand-made tilesets (needs lead approval)")
    p.add_argument("--near", help="N[:T] reuse tiles that differ in at most N pixels by more than T (default 8)")
    p.add_argument("--no-inherit", action="store_true", help="do not copy collision/type/material from the old tile")


def build():
    ap = argparse.ArgumentParser(prog="scene.py", description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("render", help="pixel-exact render with overlays")
    p.add_argument("map")
    p.add_argument("--out")
    p.add_argument("--region")
    p.add_argument("--layers", help="A,B or all (default: visible tile layers)")
    p.add_argument("--scale", type=int, default=1)
    p.add_argument("--grid", type=int, nargs="?", const=1, default=0)
    p.add_argument("--ids", action="store_true")
    p.add_argument("--uses", action="store_true")
    p.add_argument("--collision", action="store_true")
    p.add_argument("--material", action="store_true")
    p.add_argument("--highlight", nargs="+", help="tile refs whose cells get outlined")
    p.add_argument("--context", type=int, default=0, help="show K extra cells around --region")
    p.add_argument("--check-tmx", action="store_true", help="compare the compositor with tmxrasterizer")
    p.set_defaults(fn="view.cmd_render")

    p = sp.add_parser("cells", help="per-cell metadata as JSON")
    p.add_argument("map")
    p.add_argument("--region")
    p.add_argument("--layers")
    p.set_defaults(fn="view.cmd_cells")

    p = sp.add_parser("where", help="every use of a tile")
    p.add_argument("tile")
    p.add_argument("--maps", help="comma separated globs (default assets/maps/**/*.tmj)")
    p.add_argument("--map", help="map to resolve raw gids against")
    p.add_argument("--sheet", help="write a contact sheet of the uses")
    p.add_argument("--context", type=int, help="cells of context in the sheet (default 2)")
    p.set_defaults(fn="view.cmd_where")

    p = sp.add_parser("diff", help="compare two map versions (paths or git:REV:path)")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--region")
    p.add_argument("--out")
    p.set_defaults(fn="view.cmd_diff")

    p = sp.add_parser("tile", help="provenance and usage of a tile; `tile edit TILE --ops ...` edits it globally")
    p.add_argument("args", nargs="+", metavar="[edit] TILE")
    p.add_argument("--map")
    p.add_argument("--out")
    p.add_argument("--scale", type=int, default=8)
    p.add_argument("--ops")
    mutating(p)
    edit_flags(p)
    p.set_defaults(fn="tile")

    p = sp.add_parser("library", help="stats | sheet | check | orphans")
    p.add_argument("action", choices=["stats", "sheet", "check", "orphans"])
    p.add_argument("--page", type=int)
    p.add_argument("--out")
    p.add_argument("--scale", type=int, default=4)
    p.set_defaults(fn="view.cmd_library")

    p = sp.add_parser("edit", help="pixel ops on one tile layer")
    p.add_argument("map")
    p.add_argument("--layer", required=True)
    p.add_argument("--ops", required=True, help="JSON file or inline JSON list")
    mutating(p)
    edit_flags(p)
    p.set_defaults(fn="edit.cmd_edit")

    p = sp.add_parser("export", help="write a region as PNG + sidecar JSON")
    p.add_argument("map")
    p.add_argument("--region", required=True)
    p.add_argument("--layer")
    p.add_argument("--composite", action="store_true")
    p.add_argument("--out", required=True)
    p.add_argument("--scale", type=int, default=1)
    p.set_defaults(fn="edit.cmd_export")

    p = sp.add_parser("import", help="apply an edited export PNG back to the map")
    p.add_argument("png")
    p.add_argument("--sidecar")
    p.add_argument("--layer")
    p.add_argument("--flatten-into", help="layer that receives a composite export")
    p.add_argument("--force", action="store_true", help="overwrite cells that changed since the export")
    mutating(p)
    edit_flags(p)
    p.set_defaults(fn="edit.cmd_import")

    for kind in ("collide", "material"):
        p = sp.add_parser(kind, help=f"set {kind} on one tile or a map region")
        ss = p.add_subparsers(dest="mode", required=True)
        t = ss.add_parser("tile")
        t.add_argument("tile")
        r = ss.add_parser("region")
        r.add_argument("map")
        r.add_argument("--layer", required=True)
        r.add_argument("--region", required=True)
        r.add_argument("--global", dest="global_", action="store_true")
        for q in (t, r):
            if kind == "collide":
                q.add_argument("--shape", required=True)
            else:
                q.add_argument("name")
                q.add_argument("--no-shape", action="store_true", help="set the material but keep the collision")
            q.add_argument("--expect-uses", type=int)
            q.add_argument("--allow-foreign", action="store_true")
            mutating(q)
        p.set_defaults(fn=f"meta.{kind}")

    p = sp.add_parser("undo", help="restore the latest journal entry if nothing changed since")
    p.add_argument("--steps", type=int, default=1)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn="undo")

    p = sp.add_parser("journal", help="list journal entries")
    p.set_defaults(fn="journal")
    return ap


def dispatch(a):
    fn = a.fn
    if fn == "undo":
        return dict(ok=True, **common.undo(a.steps, a.dry_run))
    if fn == "journal":
        return {"ok": True, "entries": [{"name": e["name"], "command": e["command"], "time": e["time"], "undone": e["undone"],
                                         "files": [f["path"] for f in e["files"]]} for e in common.journal_entries()]}
    if fn == "tile":
        import viewcmds
        import editcore
        if a.args[0] == "edit":
            if len(a.args) != 2:
                raise SceneError("usage: tile edit TILE --ops OPS --expect-uses N", "bad_input")
            a.tile = a.args[1]
            return editcore.cmd_tile_edit(a)
        if len(a.args) != 1:
            raise SceneError("usage: tile TILE", "bad_input")
        a.tile = a.args[0]
        return viewcmds.cmd_tile(a)
    mod, name = fn.split(".", 1)
    if mod == "view":
        import viewcmds
        return getattr(viewcmds, name)(a)
    import editcore
    if mod == "edit":
        return getattr(editcore, name)(a)
    if mod == "meta":
        if a.mode == "tile":
            return editcore.cmd_meta_tile(name, a)
        return editcore.cmd_meta_region(name, a)
    raise SceneError(f"unknown command {fn}", "bad_input")


def main(argv=None):
    ap = build()
    a = ap.parse_args(argv)
    try:
        res = dispatch(a)
    except SceneError as e:
        emit(dict({"ok": False, "error": str(e), "code": e.code}, **e.extra))
        return 1
    except (common.T.MapError, OSError) as e:
        emit({"ok": False, "error": str(e), "code": "error"})
        return 1
    emit(res)
    return 0 if res.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
