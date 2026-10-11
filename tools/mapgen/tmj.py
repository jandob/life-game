#!/usr/bin/env python3
"""tmj.py - author Tiled .tmj maps tile by tile without the Tiled GUI. See README.md."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tmjlib as T  # noqa: E402


def out(obj):
    print(json.dumps(obj))


# --------------------------------------------------------------------------- commands

def cmd_new(a):
    if os.path.exists(a.map) and not a.force:
        raise T.MapError(f"{a.map} exists (use --force to overwrite)")
    m = T.new_map(a.map, a.width, a.height, a.tile, a.tileset, None if a.no_default_layer else "Ground")
    os.makedirs(os.path.dirname(os.path.abspath(a.map)), exist_ok=True)
    m.save()
    out({"ok": True, "map": a.map, "size": [a.width, a.height],
         "tilesets": [{"name": t.name, "firstgid": t.firstgid, "tiles": t.tilecount, "source": t.source} for t in m.tilesets],
         "layers": [l["name"] for l in m.layers]})


def layer_info(l):
    info = {"name": l["name"], "type": "tile" if l["type"] == "tilelayer" else "object", "id": l["id"],
            "visible": l.get("visible", True)}
    p = T.props_dict(l)
    if p:
        info["properties"] = p
    if l["type"] == "objectgroup":
        info["objects"] = len(l["objects"])
    else:
        info["non_empty"] = sum(1 for v in l["data"] if v)
    return info


def cmd_layer(a):
    m = T.TiledMap.load(a.map)
    act = a.action
    if act == "list":
        out({"ok": True, "layers": [dict(layer_info(l), index=i) for i, l in enumerate(m.layers)]})
        return
    if act == "add":
        l = T.add_layer(m, a.name, a.type, a.index, T.parse_kv(a.prop))
    elif act == "remove":
        l = m.layer(a.name)
        m.layers.remove(l)
    elif act == "rename":
        l = m.layer(a.name)
        if any(x["name"] == a.new_name for x in m.layers):
            raise T.MapError(f"layer '{a.new_name}' already exists")
        l["name"] = a.new_name
    elif act == "move":
        l = m.layer(a.name)
        m.layers.remove(l)
        m.layers.insert(max(0, min(a.index, len(m.layers))), l)
    elif act == "set-prop":
        l = m.layer(a.name)
        T.set_props(l, T.parse_kv(a.prop))
        T.unset_props(l, a.unset or [])
    m.save()
    out({"ok": True, "action": act, "layers": [x["name"] for x in m.layers]})


def read_ops(a):
    src = a.ops
    text = sys.stdin.read() if src in (None, "-") else open(src).read()
    try:
        ops = json.loads(text)
    except ValueError as e:
        raise T.MapError(f"ops are not valid JSON: {e}")
    if isinstance(ops, dict) and "ops" in ops:
        ops = ops["ops"]
    return ops


def cmd_paint(a):
    m = T.TiledMap.load(a.map)
    layer = m.layer(a.layer, "tilelayer")
    ops = read_ops(a)
    data, changed = T.apply_ops(m, layer, ops)
    layer["data"] = data
    m.save()
    out({"ok": True, "layer": a.layer, "ops": len(ops), "cells_changed": changed})


def obj_pos(m, a, size_default_point):
    """Return (x, y, w, h, is_point) in pixels from --tile/--px and --size-tiles/--size-px."""
    if a.size_tiles:
        w, h = a.size_tiles[0] * m.tilew, a.size_tiles[1] * m.tileh
    elif a.size_px:
        w, h = a.size_px
    else:
        w = h = 0
    if a.tile:
        x, y = a.tile[0] * m.tilew, a.tile[1] * m.tileh
        if not (w or h):  # a point goes to the tile centre; the game treats x,y as a point
            x, y = x + m.tilew / 2, y + m.tileh / 2
    elif a.px:
        x, y = a.px
    else:
        x = y = None
    return x, y, w, h


def object_json(m, layer, o):
    d = {"id": o["id"], "name": o["name"], "type": o.get("type", ""), "x": o["x"], "y": o["y"],
         "tile": list(T.object_tile(m, o))}
    if o.get("width") or o.get("height"):
        d["size_px"] = [o["width"], o["height"]]
    else:
        d["point"] = True
    p = T.props_dict(o)
    if p:
        d["properties"] = p
    return d


def cmd_object(a):
    m = T.TiledMap.load(a.map)
    layer = m.layer(a.layer, "objectgroup")
    act = a.action
    if act == "list":
        out({"ok": True, "layer": a.layer, "objects": [object_json(m, layer, o) for o in layer["objects"]]})
        return
    if act == "add":
        x, y, w, h = obj_pos(m, a, True)
        if x is None:
            raise T.MapError("give a position with --tile X Y or --px X Y")
        o = {"height": h, "id": m.next_object_id(), "name": a.name, "rotation": 0, "type": a.type or "",
             "visible": True, "width": w, "x": x, "y": y}
        if not (w or h):
            o["point"] = True
        if a.prop:
            T.set_props(o, T.parse_kv(a.prop))
        layer["objects"].append(o)
    else:
        o = T.find_object(m, layer, a.id, a.name)
        if act == "remove":
            layer["objects"].remove(o)
        elif act == "move":
            x, y, w, h = obj_pos(m, a, False)
            if x is None:
                raise T.MapError("give a position with --tile X Y or --px X Y")
            # keep the object's own size: a point stays a point, a rect keeps its width/height
            if o.get("point") and a.tile:
                x, y = a.tile[0] * m.tilew + m.tilew / 2, a.tile[1] * m.tileh + m.tileh / 2
            elif not o.get("point") and a.tile and not (w or h):
                x, y = a.tile[0] * m.tilew, a.tile[1] * m.tileh
            o["x"], o["y"] = x, y
        elif act == "set-prop":
            T.set_props(o, T.parse_kv(a.prop))
            T.unset_props(o, a.unset or [])
            if a.rename:
                o["name"] = a.rename
            if a.type is not None:
                o["type"] = a.type
    m.save()
    out({"ok": True, "action": act, "object": object_json(m, layer, o)})


def parse_region(s, m):
    if not s:
        return None
    try:
        x, y, w, h = [int(v) for v in s.split(",")]
    except ValueError:
        raise T.MapError("--region must be x,y,w,h")
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, m.width), min(y + h, m.height)
    if x1 <= x0 or y1 <= y0:
        raise T.MapError("region is outside the map")
    return x0, y0, x1 - x0, y1 - y0


def cmd_show(a):
    m = T.TiledMap.load(a.map)
    region = parse_region(a.region, m) or (0, 0, m.width, m.height)
    rx, ry, rw, rh = region
    layers = [m.layer(a.layer, "tilelayer")] if a.layer else m.tile_layers()
    if a.json:
        res = {"ok": True, "region": list(region), "layers": {}}
        for l in layers:
            res["layers"][l["name"]] = [[m.format_tile(l["data"][y * m.width + x], a.gid) for x in range(rx, rx + rw)]
                                        for y in range(ry, ry + rh)]
        out(res)
        return
    lines = []
    for l in layers:
        cells = [[m.format_tile(l["data"][y * m.width + x], a.gid) for x in range(rx, rx + rw)] for y in range(ry, ry + rh)]
        cw = max([len(c) for row in cells for c in row] + [len(str(rx + rw - 1))])
        lw = len(str(ry + rh - 1))
        lines.append(f"layer '{l['name']}' region x={rx} y={ry} w={rw} h={rh}  ('.' = empty)")
        lines.append(" " * (lw + 1) + " ".join(str(rx + i).rjust(cw) for i in range(rw)))
        for j, row in enumerate(cells):
            lines.append(str(ry + j).rjust(lw) + " " + " ".join(c.rjust(cw) for c in row))
        lines.append("")
    objs = []
    for l in m.layers:
        if l["type"] != "objectgroup":
            continue
        for o in l["objects"]:
            tx, ty = T.object_tile(m, o)
            if rx <= tx < rx + rw and ry <= ty < ry + rh:
                p = T.props_dict(o)
                objs.append(f"  [{l['name']}] id={o['id']} {o['name'] or '-'} type={o.get('type') or '-'} tile=({tx},{ty})"
                            + (f" props={json.dumps(p)}" if p else ""))
    if objs:
        lines.append("objects in region:")
        lines += objs
    print("\n".join(lines).rstrip())


def cmd_tileset(a):
    ts = T.Tileset.load(a.tsj)
    tiles = []
    for tid in range(ts.tilecount):
        e = ts.tile_entry(tid)
        col = ts.has_collision(tid)
        if not a.all and not e:
            continue
        item = {"id": tid, "collision": col}
        if e:
            if e.get("type") or e.get("class"):
                item["type"] = e.get("type") or e.get("class")
            if e.get("properties"):
                item["properties"] = {p["name"]: p.get("value") for p in e["properties"]}
            if e.get("animation"):
                item["animation_frames"] = len(e["animation"])
            if col:
                item["shapes"] = [
                    {k: s[k] for k in ("x", "y", "width", "height") if k in s}
                    | ({"polygon": [[p["x"], p["y"]] for p in s["polygon"]]} if "polygon" in s else {})
                    for s in ts.collision_shapes(tid)]
        tiles.append(item)
    res = {"ok": True, "name": ts.name, "tilecount": ts.tilecount, "columns": ts.columns,
           "tile_size": [ts.tilew, ts.tileh], "image": ts.data.get("image"),
           "collision_ids": [t for t in range(ts.tilecount) if ts.has_collision(t)],
           "wangsets": ts.wangsets(), "tiles": tiles}
    if a.sheet:
        from preview import contact_sheet
        res["sheet"] = {"path": a.sheet, "size": list(contact_sheet(ts, a.sheet, a.sheet_scale))}
    out(res)


def cmd_render(a):
    from preview import render
    m = T.TiledMap.load(a.map)
    region = parse_region(a.region, m)
    size = render(m, a.out, a.scale, a.grid, a.debug, region)
    out({"ok": True, "out": a.out, "size": list(size), "scale": a.scale, "grid": a.grid, "debug": a.debug,
         "region": list(region) if region else None})


def cmd_validate(a):
    from validate import validate
    m = T.TiledMap.load(a.map)
    res = validate(m, not a.no_tiled)
    out(res)
    if not res["ok"]:
        sys.exit(1)


# --------------------------------------------------------------------------- argparse

def pos_args(p):
    p.add_argument("--tile", nargs=2, type=int, metavar=("X", "Y"), help="position in tile coordinates")
    p.add_argument("--px", nargs=2, type=float, metavar=("X", "Y"), help="position in pixels")
    p.add_argument("--size-tiles", nargs=2, type=int, metavar=("W", "H"))
    p.add_argument("--size-px", nargs=2, type=float, metavar=("W", "H"))


def build():
    ap = argparse.ArgumentParser(prog="tmj.py", description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("new", help="create an empty map")
    p.add_argument("map")
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--height", type=int, required=True)
    p.add_argument("--tile", type=int, default=16)
    p.add_argument("--tileset", action="append", required=True, help="path to a .tsj (repeatable)")
    p.add_argument("--no-default-layer", action="store_true", help="do not create the 'Ground' tile layer")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_new)

    p = sp.add_parser("layer", help="add|remove|rename|move|set-prop|list layers")
    p.add_argument("map")
    ls = p.add_subparsers(dest="action", required=True)
    q = ls.add_parser("list")
    q = ls.add_parser("add")
    q.add_argument("name")
    q.add_argument("--type", choices=["tile", "object"], default="tile")
    q.add_argument("--index", type=int, help="position in the layer stack (0 = bottom)")
    q.add_argument("--prop", action="append", metavar="K=V")
    q = ls.add_parser("remove")
    q.add_argument("name")
    q = ls.add_parser("rename")
    q.add_argument("name")
    q.add_argument("new_name")
    q = ls.add_parser("move")
    q.add_argument("name")
    q.add_argument("--index", type=int, required=True)
    q = ls.add_parser("set-prop")
    q.add_argument("name")
    q.add_argument("--prop", action="append", metavar="K=V")
    q.add_argument("--unset", action="append", metavar="K")
    p.set_defaults(fn=cmd_layer)

    p = sp.add_parser("paint", help="apply a batch of tile ops to a tile layer (atomic)")
    p.add_argument("map")
    p.add_argument("--layer", required=True)
    p.add_argument("--ops", help="ops JSON file; '-' or omitted reads stdin")
    p.set_defaults(fn=cmd_paint)

    p = sp.add_parser("object", help="add|move|remove|set-prop|list objects")
    p.add_argument("map")
    p.add_argument("--layer", required=True)
    os_ = p.add_subparsers(dest="action", required=True)
    q = os_.add_parser("list")
    q = os_.add_parser("add")
    q.add_argument("--name", required=True)
    q.add_argument("--type")
    q.add_argument("--prop", action="append", metavar="K=V")
    pos_args(q)
    for act in ("move", "remove", "set-prop"):
        q = os_.add_parser(act)
        q.add_argument("--id", type=int)
        q.add_argument("--name")
        if act == "move":
            pos_args(q)
        if act == "set-prop":
            q.add_argument("--prop", action="append", metavar="K=V")
            q.add_argument("--unset", action="append", metavar="K")
            q.add_argument("--rename")
            q.add_argument("--type")
    p.set_defaults(fn=cmd_object)

    p = sp.add_parser("show", help="text dump of a region of a tile layer")
    p.add_argument("map")
    p.add_argument("--layer")
    p.add_argument("--region", help="x,y,w,h in tiles")
    p.add_argument("--gid", action="store_true", help="show raw gids instead of tileset:id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_show)

    p = sp.add_parser("tileset", help="inspect a .tsj")
    p.add_argument("tsj")
    p.add_argument("--all", action="store_true", help="list every tile id, not only tiles with metadata/collision")
    p.add_argument("--sheet", help="write a labelled contact sheet PNG")
    p.add_argument("--sheet-scale", type=int, default=4)
    p.set_defaults(fn=cmd_tileset)

    p = sp.add_parser("render", help="render a map to PNG")
    p.add_argument("map")
    p.add_argument("out")
    p.add_argument("--scale", type=int, default=2)
    p.add_argument("--grid", type=int, nargs="?", const=1, metavar="N", help="grid lines + labels every N tiles")
    p.add_argument("--debug", action="store_true", help="collision shapes, labelled objects, layer list")
    p.add_argument("--region", help="x,y,w,h in tiles (crop)")
    p.set_defaults(fn=cmd_render)

    p = sp.add_parser("validate", help="check the map against the game loader's expectations")
    p.add_argument("map")
    p.add_argument("--no-tiled", action="store_true", help="skip the tiled --export-map check")
    p.set_defaults(fn=cmd_validate)
    return ap


def main():
    a = build().parse_args()
    try:
        a.fn(a)
    except T.MapError as e:
        out({"ok": False, "error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
