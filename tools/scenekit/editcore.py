"""Editing: pixel ops, the import core (dedup, copy-on-write, global edits), export/import, collide/material."""
import json
import os

from PIL import Image

import tmjlib as T
from common import (FLIP_MASK, PAGE_TILES, ROOT, TILE, Scene, SceneError, abspath_from_root, apply_meta_to_entry, atomic_write,
                    flags_str, is_blank, json_bytes, key_of, layer_above, load_materials, make_meta, meta_sig,
                    normalize_key, parse_colour, parse_region, parse_shape, png_bytes, rel, sha, tile_hash, undo_flags)
from compose import Resolver, UsageIndex, cell_crop, cell_image, composite_image, layer_image, tile_layers
from viewcmds import clip_region


class Opts:
    def __init__(self, a=None, **kw):
        g = (lambda n, d=None: getattr(a, n, d)) if a is not None else (lambda n, d=None: d)
        self.global_ = bool(g("global_", False))
        self.expect_uses = g("expect_uses")
        self.allow_foreign = bool(g("allow_foreign", False))
        self.near = parse_near(g("near"))
        self.inherit = not g("no_inherit", False)
        self.force = bool(g("force", False))
        self.origin = "edit"
        self.job = None
        self.gen = None
        for k, v in kw.items():
            setattr(self, k, v)


def parse_near(text):
    if not text:
        return None
    try:
        n, _, t = str(text).partition(":")
        return int(n), int(t) if t else 8
    except ValueError:
        raise SceneError(f"--near must be N or N:T, got '{text}'", "bad_input")


# --------------------------------------------------------------------------- pixel ops

def _check_rect(i, name, x, y, w, h, W, H):
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > W or y + h > H:
        raise SceneError(f"op {i}: {name} {x},{y},{w},{h} is outside the {W}x{H} pixel area", "bad_input")


def _ints(i, name, v, n):
    if not isinstance(v, (list, tuple)) or len(v) < n or any(isinstance(c, bool) or not isinstance(c, int) for c in v[:n]):
        raise SceneError(f"op {i}: {name} needs {n} integers first, got {v!r}", "bad_input")


def load_ops(text):
    if text is None:
        raise SceneError("--ops is required", "bad_input")
    s = text.strip()
    if s.startswith("["):
        src = s
    else:
        p = abspath_from_root(text)
        if not os.path.isfile(p):
            raise SceneError(f"ops file not found: {text}", "not_found")
        with open(p) as f:
            src = f.read()
    try:
        ops = json.loads(src)
    except ValueError as e:
        raise SceneError(f"ops are not valid JSON: {e}", "bad_input")
    if not isinstance(ops, list):
        raise SceneError("ops must be a JSON list", "bad_input")
    return ops


def _bresenham(x0, y0, x1, y1):
    return T._bresenham(x0, y0, x1, y1)


def _region_of(i, name, arg, key, W, H):
    r = arg.get(key)
    if r is None:
        return 0, 0, W, H
    _ints(i, f"{name}.{key}", r, 4)
    _check_rect(i, f"{name}.{key}", *r[:4], W, H)
    return tuple(r[:4])


def apply_pixel_ops(img, ops, base_dir=None):
    """Apply ops (map/tile pixel coordinates) to a copy of an RGBA image. Any error aborts with nothing applied."""
    img = img.convert("RGBA").copy()
    W, H = img.size
    px = img.load()
    for i, op in enumerate(ops):
        if not isinstance(op, dict) or len(op) != 1:
            raise SceneError(f"op {i}: each op must be an object with exactly one key", "bad_input")
        (kind, arg), = op.items()
        if kind == "px":
            _ints(i, kind, arg, 2)
            x, y = arg[:2]
            _check_rect(i, "px", x, y, 1, 1, W, H)
            px[x, y] = parse_colour(arg[2])
        elif kind == "rect":
            _ints(i, kind, arg, 4)
            x, y, w, h = arg[:4]
            _check_rect(i, "rect", x, y, w, h, W, H)
            c = parse_colour(arg[4])
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    px[xx, yy] = c
        elif kind == "line":
            _ints(i, kind, arg, 4)
            c = parse_colour(arg[4])
            for xx, yy in _bresenham(*arg[:4]):
                _check_rect(i, "line point", xx, yy, 1, 1, W, H)
                px[xx, yy] = c
        elif kind == "paste":
            if not isinstance(arg, dict) or "at" not in arg or "image" not in arg:
                raise SceneError(f"op {i}: paste needs {{'at': [x, y], 'image': path, 'mode': 'over|replace'}}", "bad_input")
            _ints(i, "paste.at", arg["at"], 2)
            p = arg["image"] if os.path.isabs(arg["image"]) else os.path.join(base_dir or os.getcwd(), arg["image"])
            if not os.path.isfile(p):
                p = abspath_from_root(arg["image"])
            if not os.path.isfile(p):
                raise SceneError(f"op {i}: image not found: {arg['image']}", "not_found")
            src = Image.open(p).convert("RGBA")
            x, y = arg["at"][:2]
            _check_rect(i, "paste", x, y, src.width, src.height, W, H)
            mode = arg.get("mode", "over")
            if mode == "over":
                img.alpha_composite(src, (x, y))
            elif mode == "replace":
                img.paste(src, (x, y))
            else:
                raise SceneError(f"op {i}: paste mode must be over or replace", "bad_input")
            px = img.load()
        elif kind == "copy":
            if not isinstance(arg, dict) or "from" not in arg or "to" not in arg:
                raise SceneError(f"op {i}: copy needs {{'from': [x, y, w, h], 'to': [x, y]}}", "bad_input")
            _ints(i, "copy.from", arg["from"], 4)
            _ints(i, "copy.to", arg["to"], 2)
            x, y, w, h = arg["from"][:4]
            _check_rect(i, "copy.from", x, y, w, h, W, H)
            tx, ty = arg["to"][:2]
            _check_rect(i, "copy.to", tx, ty, w, h, W, H)
            img.paste(img.crop((x, y, x + w, y + h)), (tx, ty))
            px = img.load()
        elif kind in ("replace", "remap", "quantize"):
            if not isinstance(arg, dict):
                raise SceneError(f"op {i}: {kind} needs an object", "bad_input")
            x, y, w, h = _region_of(i, kind, arg, "region", W, H)
            if kind == "replace":
                if "from" not in arg or "to" not in arg:
                    raise SceneError(f"op {i}: replace needs 'from' and 'to'", "bad_input")
                f, t = parse_colour(arg["from"]), parse_colour(arg["to"])
                table = {f: t}
            elif kind == "remap":
                if not isinstance(arg.get("map"), dict) or not arg["map"]:
                    raise SceneError(f"op {i}: remap needs a non-empty 'map'", "bad_input")
                table = {parse_colour(k): parse_colour(v) for k, v in arg["map"].items()}
            else:
                pal = load_palette(i, arg.get("palette"), base_dir)
                table = None
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    c = px[xx, yy]
                    if table is not None:
                        if c in table:
                            px[xx, yy] = table[c]
                    elif c[3] > 0:
                        best = min(pal, key=lambda p: (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2)
                        px[xx, yy] = (best[0], best[1], best[2], c[3])
        else:
            raise SceneError(f"op {i}: unknown op '{kind}' (px, rect, line, paste, copy, replace, remap, quantize)", "bad_input")
    return img


def load_palette(i, path, base_dir):
    if not path:
        raise SceneError(f"op {i}: quantize needs a 'palette' .hex file", "bad_input")
    p = path if os.path.isabs(path) else os.path.join(base_dir or os.getcwd(), path)
    if not os.path.isfile(p):
        p = abspath_from_root(path)
    if not os.path.isfile(p):
        raise SceneError(f"op {i}: palette file not found: {path}", "not_found")
    pal = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith((";", "#!", "//")):
                pal.append(parse_colour(line))
    if not pal:
        raise SceneError(f"op {i}: palette {path} is empty", "bad_input")
    return pal


# --------------------------------------------------------------------------- import core

def new_result():
    return {"cells_changed": [], "tiles_new": [], "tiles_reused": [], "near_matches": [], "meta_variants": [],
            "global": None}


def cell_ref(resolver, gid):
    if not gid:
        return None
    r = resolver(gid)
    if not r:
        return f"?{gid & ~FLIP_MASK}"
    f = flags_str(r[2])
    return key_of(r[0], r[1]) + (f"|{f}" if f else "")


def apply_cells(sc, m, layer, new_cells, o, old_override=None, meta_override=None, res=None):
    """Write new 16x16 pixels for cells of one layer. Unchanged cells keep their gid (flips too); fully transparent
    cells become empty; others get a tile through library insert (copy-on-write); --global rewrites tile slots."""
    res = res if res is not None else new_result()
    mp = rel(m.path)
    resolver = Resolver(m)
    data = layer["data"]
    changes = []
    for (x, y), new in sorted(new_cells.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if not (0 <= x < m.width and 0 <= y < m.height):
            raise SceneError(f"cell ({x},{y}) is outside the {m.width}x{m.height} map", "bad_input")
        i = y * m.width + x
        old = old_override[(x, y)] if old_override is not None else cell_image(sc, m, layer, x, y, resolver)
        if tile_hash(new) == tile_hash(old):
            continue
        changes.append((x, y, i, data[i], new))
    if o.global_:
        _apply_global(sc, m, layer, changes, o, res)
        return res
    lib = sc.library
    new_ids = set()
    for x, y, i, old_gid, new in changes:
        rec = {"x": x, "y": y, "old": cell_ref(resolver, old_gid)}
        if is_blank(new):
            data[i] = 0
            rec["new"] = None
            res["cells_changed"].append(rec)
            continue
        r = resolver(old_gid) if old_gid else None
        parent = key_of(r[0], r[1]) if r else None
        meta = make_meta()
        if o.inherit:
            if meta_override and (x, y) in meta_override:
                meta = meta_override[(x, y)]
            elif r:
                meta = sc.tile_meta(r[0], r[1])
        tid, status, extra = lib.insert(new, meta, origin=o.origin, parent=parent, job=o.job,
                                        source={"map": mp, "layer": layer["name"], "x": x, "y": y}, gen=o.gen, near=o.near)
        key = f"gen:{tid}"
        if status in ("new", "meta_variant"):
            res["tiles_new"].append(key)
            new_ids.add(tid)
            if status == "meta_variant":
                res["meta_variants"].append(key)
        elif status == "near":
            res["near_matches"].append({"cell": [x, y], "tile": key, "pixel_diff": extra})
        elif key not in res["tiles_reused"]:
            res["tiles_reused"].append(key)
        data[i] = sc.gid_for_gen(m, tid)
        rec["new"] = key
        res["cells_changed"].append(rec)
    return res


def _use_id(u):
    return (u["map"], u["layer"], u["x"], u["y"])


def global_set_key(sc, key, new_img, inside, o, op, require=False, idx=None):
    """Overwrite a tile's pixels in place. `inside` = set of (map, layer, x, y) cells being edited."""
    gen = key.startswith("gen:")
    if not gen and not o.allow_foreign:
        raise SceneError(f"{key} belongs to a hand-made tileset; global edits are refused unless --allow-foreign", "refused")
    if is_blank(new_img):
        raise SceneError(f"a global edit cannot make {key} fully transparent", "bad_input")
    idx = idx or UsageIndex(sc)
    uses = list(idx.of(key))
    known = {_use_id(u) for u in uses}
    for c in sorted(inside):
        if c not in known:
            uses.append({"map": c[0], "layer": c[1], "x": c[2], "y": c[3], "flip": ""})
    outside = [u for u in uses if _use_id(u) not in inside]
    total = len(uses)
    if (outside or require) and o.expect_uses is None:
        raise SceneError(f"global edit of {key} affects {total} use(s), {len(outside)} outside the edited cells; "
                         f"pass --expect-uses {total} to confirm. Nothing was written.", "impact", tile=key, total=total, uses=uses)
    if o.expect_uses is not None and o.expect_uses != total:
        raise SceneError(f"--expect-uses {o.expect_uses} but {key} has {total} use(s). Nothing was written.", "impact",
                         tile=key, total=total, uses=uses)
    ts, local = sc.resolve_key(key)
    if gen:
        changed = sc.library.set_pixels(int(key.split(":")[1]), new_img, op, o.job)
    else:
        changed = set_foreign_pixels(sc, ts, local, new_img)
    return {"tile": key, "uses": uses, "total": total, "pixels_changed": changed}


def set_foreign_pixels(sc, ts, local, img):
    p = ts.image_path()
    sheet = Image.open(__import__("io").BytesIO(sc.read_bytes(p))).convert("RGBA")
    cols = ts.columns or (sheet.width // ts.tilew)
    sp, mg = int(ts.data.get("spacing", 0)), int(ts.data.get("margin", 0))
    x, y = mg + (local % cols) * (ts.tilew + sp), mg + (local // cols) * (ts.tileh + sp)
    old = sheet.crop((x, y, x + TILE, y + TILE))
    if tile_hash(old) == tile_hash(img):
        return False
    sheet.paste(img, (x, y))
    sc.stage(p, png_bytes(sheet))
    return True


def _apply_global(sc, m, layer, changes, o, res):
    mp = rel(m.path)
    resolver = Resolver(m)
    groups = {}
    for x, y, i, old_gid, new in changes:
        r = resolver(old_gid) if old_gid else None
        if not r:
            raise SceneError(f"--global cannot edit empty cell ({x},{y}); there is no tile to overwrite", "bad_input")
        groups.setdefault(key_of(r[0], r[1]), []).append((x, y, r[2], new))
    idx = UsageIndex(sc)
    plans = []
    for key, cells in groups.items():
        locals_ = {tile_hash(undo_flags(new, flags)): undo_flags(new, flags) for (_x, _y, flags, new) in cells}
        if len(locals_) > 1:
            raise SceneError(f"--global: cells of {key} were given different new pixels ({len(locals_)} variants); "
                             f"a tile has one picture. Nothing was written.", "bad_input", tile=key,
                             cells=[[x, y] for x, y, _f, _n in cells])
        inside = {(mp, layer["name"], x, y) for x, y, _f, _n in cells}
        plans.append((key, next(iter(locals_.values())), inside, cells))
    for key, img, inside, cells in plans:
        info = global_set_key(sc, key, img, inside, o, "edit --global", idx=idx)
        res["global"] = (res["global"] or [])
        res["global"].append({k: info[k] for k in ("tile", "uses", "total", "pixels_changed")})
        for x, y, _f, _n in cells:
            res["cells_changed"].append({"x": x, "y": y, "old": key, "new": key, "global": True})


def finish(sc, m, res, map_dirty):
    before = sc.map_hash(m) if m is not None else None
    if m is not None and map_dirty:
        sc.stage_map(m)
    info = sc.commit()
    res.update(info)
    if m is not None:
        res["map"] = rel(m.path)
        if map_dirty and m.path in sc.writes:
            res["map_hash"] = sha(sc.writes[m.path])
        else:
            res["map_hash"] = before
        res["map_hash_before"] = before
    res["ok"] = True
    return res


QUIET_LISTS = ("cells_changed", "tiles_new", "tiles_reused", "near_matches", "meta_variants", "tiles_updated", "in_place",
               "forked", "unchanged")


def summarize(res, quiet=False):
    """Add `counts`. With quiet, drop the per-cell / per-tile lists so only the summary (counts, hashes, files) remains."""
    res["counts"] = {"cells_changed": len(res["cells_changed"]), "tiles_new": len(res["tiles_new"])}
    if "tiles_updated" in res:
        res["counts"]["tiles_updated"] = len(res["tiles_updated"])
    if quiet:
        res["counts"].update(tiles_reused=len(res.get("tiles_reused", [])), near_matches=len(res.get("near_matches", [])))
        for k in QUIET_LISTS:
            res.pop(k, None)
        res["quiet"] = True
    return res


# --------------------------------------------------------------------------- edit

def cmd_edit(a):
    sc = Scene("edit", a.dry_run)
    m = sc.load_map(abspath_from_root(a.map), a.if_hash)
    layer = m.layer(a.layer, "tilelayer")
    ops = load_ops(a.ops)
    o = Opts(a)
    old_img = layer_image(sc, m, layer)
    new_img = apply_pixel_ops(old_img, ops, os.getcwd())
    new_cells = {}
    for cy in range(m.height):
        for cx in range(m.width):
            c = cell_crop(new_img, cx, cy)
            if c.tobytes() != cell_crop(old_img, cx, cy).tobytes():
                new_cells[(cx, cy)] = c
    res = apply_cells(sc, m, layer, new_cells, o)
    dirty = bool(res["cells_changed"]) and not o.global_
    return summarize(finish(sc, m, res, dirty), getattr(a, "quiet", False))


def cmd_tile_edit(sc_args):
    a = sc_args
    sc = Scene("tile-edit", a.dry_run)
    key, _ = normalize_key(a.tile)
    ts, local = sc.resolve_key(key)
    ops = load_ops(a.ops)
    o = Opts(a)
    if a.expect_uses is None:
        raise SceneError("tile edit is a global edit; pass --expect-uses N (the tile's total use count)", "impact")
    new = apply_pixel_ops(sc.tile_image(ts, local), ops, os.getcwd())
    info = global_set_key(sc, key, new, set(), o, "tile edit", require=True)
    res = {"cells_changed": [], "global": [info], "tiles_new": []}
    return finish(sc, None, res, False)


# --------------------------------------------------------------------------- export / import

def cmd_export(a):
    sc = Scene("export")
    m = sc.load_map(abspath_from_root(a.map))
    region = clip_region(m, parse_region(a.region))
    if bool(a.layer) == bool(a.composite):
        raise SceneError("export needs exactly one of --layer L or --composite", "bad_input")
    rx, ry, rw, rh = region
    side = {"map": rel(m.path), "map_hash": sc.map_hash(m), "region": list(region), "px_origin": [rx * TILE, ry * TILE],
            "scale": a.scale}
    if a.composite:
        layers = tile_layers(m)
        img = composite_image(sc, m, layers, region)
        side["composite"] = True
        side["layers"] = {l["name"]: [[l["data"][y * m.width + x] for x in range(rx, rx + rw)] for y in range(ry, ry + rh)]
                          for l in layers}
    else:
        layer = m.layer(a.layer, "tilelayer")
        img = layer_image(sc, m, layer, region)
        side["layer"] = layer["name"]
        side["cells"] = [[layer["data"][y * m.width + x] for x in range(rx, rx + rw)] for y in range(ry, ry + rh)]
    side["cell_hashes"] = [[tile_hash(cell_crop(img, x, y)) for x in range(rw)] for y in range(rh)]
    outp = abspath_from_root(a.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    out_img = img if a.scale == 1 else img.resize((img.width * a.scale, img.height * a.scale), Image.NEAREST)
    atomic_write(outp, png_bytes(out_img))
    atomic_write(outp + ".json", json_bytes(side, indent=1))
    return {"ok": True, "image": outp, "sidecar": outp + ".json", "region": list(region), "scale": a.scale,
            "size": list(out_img.size), "map_hash": side["map_hash"], "kind": "composite" if a.composite else "layer"}


def cmd_import(a):
    sc = Scene("import", a.dry_run)
    png = abspath_from_root(a.png)
    side_path = abspath_from_root(a.sidecar) if a.sidecar else png + ".json"
    if not os.path.isfile(png):
        raise SceneError(f"image not found: {png}", "not_found")
    if not os.path.isfile(side_path):
        raise SceneError(f"sidecar not found: {side_path} (pass --sidecar)", "not_found")
    with open(side_path) as f:
        side = json.load(f)
    if side.get("scale", 1) != 1:
        raise SceneError("this export was written at a scale other than 1; import needs a scale-1 PNG "
                         "(export again without --scale)", "bad_input")
    m = sc.load_map(abspath_from_root(side["map"]), a.if_hash)
    rx, ry, rw, rh = side["region"]
    im = Image.open(png).convert("RGBA")
    if im.size != (rw * TILE, rh * TILE):
        raise SceneError(f"image is {im.size[0]}x{im.size[1]}, the exported region needs {rw * TILE}x{rh * TILE}", "bad_input")
    composite = bool(side.get("composite"))
    if composite and not a.flatten_into:
        raise SceneError("composite exports are context only; write them back with --flatten-into LAYER", "bad_input")
    target = m.layer(a.flatten_into if composite else (a.layer or side["layer"]), "tilelayer")
    resolver = Resolver(m)
    changed, conflicts = {}, []
    cur_comp = composite_image(sc, m, tile_layers(m), (rx, ry, rw, rh)) if composite else None
    for r in range(rh):
        for c in range(rw):
            new = cell_crop(im, c, r)
            if tile_hash(new) == side["cell_hashes"][r][c]:
                continue
            x, y = rx + c, ry + r
            changed[(x, y)] = new
            if composite:
                cur_hash = tile_hash(cell_crop(cur_comp, c, r))
                bad = cur_hash != side["cell_hashes"][r][c]
            else:
                gid = target["data"][y * m.width + x]
                bad = gid != side["cells"][r][c] or tile_hash(cell_image(sc, m, target, x, y, resolver)) != side["cell_hashes"][r][c]
            if bad:
                conflicts.append([x, y])
    if conflicts and not a.force:
        raise SceneError(f"{len(conflicts)} changed cell(s) were also changed in the map since the export "
                         f"(use --force to overwrite): {conflicts[:20]}", "conflict", cells=conflicts)
    o = Opts(a, origin="import")
    old_override = meta_override = None
    cleared = []
    if composite:
        old_override = {(x, y): cell_crop(cur_comp, x - rx, y - ry) for (x, y) in changed}
        meta_override = {}
        for (x, y) in changed:
            shapes, mat, typ = [], "", ""
            for l in tile_layers(m):
                if layer_above(l):
                    continue
                r = resolver(l["data"][y * m.width + x])
                if r:
                    mt = sc.tile_meta(r[0], r[1])
                    shapes += mt["collision"]
                    mat = mat or mt["material"]
                    typ = typ or mt["type"]
            uniq = {json.dumps(s, sort_keys=True): s for s in shapes}
            meta_override[(x, y)] = make_meta(list(uniq.values()), typ, mat)
    res = apply_cells(sc, m, target, changed, o, old_override, meta_override)
    if composite:
        for rec in res["cells_changed"]:
            x, y = rec["x"], rec["y"]
            for l in m.tile_layers():
                if l is target or layer_above(l):
                    continue
                i = y * m.width + x
                if l["data"][i]:
                    cleared.append({"layer": l["name"], "x": x, "y": y, "old": cell_ref(resolver, l["data"][i])})
                    l["data"][i] = 0
        res["cleared"] = cleared
    res["conflicts_overridden"] = conflicts if a.force else []
    return summarize(finish(sc, m, res, bool(res["cells_changed"]) and not o.global_), getattr(a, "quiet", False))


# --------------------------------------------------------------------------- collide / material

def materials_or_fail(name):
    mats = load_materials()
    if name not in mats:
        raise SceneError(f"unknown material '{name}' (known: {sorted(mats)}; add it to materials.json)", "bad_input")
    return mats[name]


def set_foreign_meta(sc, ts, local, meta):
    raw = sc.read_bytes(ts.path)
    data = json.loads(raw)
    tiles = data.setdefault("tiles", [])
    e = next((t for t in tiles if t.get("id") == local), None)
    if e is None:
        e = {"id": local}
        tiles.append(e)
        tiles.sort(key=lambda t: t["id"])
    if not apply_meta_to_entry(e, meta):
        data["tiles"] = [t for t in tiles if t is not e]
    sc.stage(ts.path, json_bytes(data, indent=1))


def check_tile_uses(sc, key, expect, idx=None):
    idx = idx or UsageIndex(sc)
    total = len(idx.of(key))
    if expect is None:
        raise SceneError(f"this changes {key} everywhere ({total} use(s)); pass --expect-uses {total}", "impact",
                         tile=key, total=total, uses=idx.of(key))
    if expect != total:
        raise SceneError(f"--expect-uses {expect} but {key} has {total} use(s). Nothing was written.", "impact",
                         tile=key, total=total, uses=idx.of(key))
    return total


def meta_changer(kind, a):
    if kind == "collide":
        shape = parse_shape(a.shape)
        return lambda meta: make_meta(shape, meta["type"], meta["material"]), {"shape": a.shape}
    mat = materials_or_fail(a.name)
    if a.no_shape:
        return lambda meta: make_meta(meta["collision"], meta["type"], a.name), {"material": a.name}
    shape = parse_shape(mat.get("shape", "none"))
    return lambda meta: make_meta(shape, meta["type"], a.name), {"material": a.name, "shape": mat.get("shape", "none")}


def cmd_meta_tile(kind, a):
    sc = Scene(kind + "-tile", a.dry_run)
    key, _ = normalize_key(a.tile)
    gen = key.startswith("gen:")
    if not gen and not a.allow_foreign:
        raise SceneError(f"{key} belongs to a hand-made tileset; refused unless --allow-foreign "
                         f"(or mark a map region instead, which forks it)", "refused")
    ts, local = sc.resolve_key(key)
    total = check_tile_uses(sc, key, a.expect_uses)
    change, what = meta_changer(kind, a)
    old = sc.tile_meta(ts, local)
    new = change(old)
    if gen:
        sc.library.set_meta(int(key.split(":")[1]), new)
    else:
        set_foreign_meta(sc, ts, local, new)
    res = {"tile": key, "uses": total, "meta": new, **what, "cells_changed": [], "tiles_new": [],
           "tiles_updated": [key] if meta_sig(new) != meta_sig(old) else []}
    return summarize(finish(sc, None, res, False), getattr(a, "quiet", False))


def cmd_meta_region(kind, a):
    sc = Scene(kind + "-region", a.dry_run)
    m = sc.load_map(abspath_from_root(a.map), a.if_hash)
    layer = m.layer(a.layer, "tilelayer")
    x0, y0, rw, rh = clip_region(m, parse_region(a.region))
    change, what = meta_changer(kind, a)
    resolver = Resolver(m)
    mp = rel(m.path)
    by_key = {}
    for y in range(y0, y0 + rh):
        for x in range(x0, x0 + rw):
            gid = layer["data"][y * m.width + x]
            r = resolver(gid) if gid else None
            if r:
                by_key.setdefault(key_of(r[0], r[1]), []).append((x, y, gid, r))
    idx = UsageIndex(sc)
    plan = []
    global_total = 0
    for key, cells in by_key.items():
        ts, local = cells[0][3][0], cells[0][3][1]
        old = sc.tile_meta(ts, local)
        new = change(old)
        if meta_sig(new) == meta_sig(old):
            plan.append((key, "unchanged", cells, ts, local, new))
            continue
        inside = {(mp, layer["name"], x, y) for x, y, _g, _r in cells}
        uses = idx.of(key)
        outside = [u for u in uses if _use_id(u) not in inside]
        gen = key.startswith("gen:")
        if a.global_:
            if not gen and not a.allow_foreign:
                raise SceneError(f"{key} belongs to a hand-made tileset; --global is refused unless --allow-foreign", "refused")
            global_total += max(len(uses), len(inside))
            plan.append((key, "in_place", cells, ts, local, new))
        elif not outside and (gen or a.allow_foreign):
            plan.append((key, "in_place", cells, ts, local, new))
        else:
            plan.append((key, "fork", cells, ts, local, new))
    if a.global_ and any(p[1] == "in_place" for p in plan):
        if a.expect_uses is None or a.expect_uses != global_total:
            raise SceneError(f"--global changes {global_total} use(s) in total; pass --expect-uses {global_total}. "
                             f"Nothing was written.", "impact", total=global_total)
    res = new_result()
    res.update(in_place=[], forked=[], unchanged=[], tiles_updated=[])
    for key, how, cells, ts, local, new in plan:
        if how == "unchanged":
            res["unchanged"].append(key)
        elif how == "in_place":
            if key.startswith("gen:"):
                sc.library.set_meta(int(key.split(":")[1]), new)
            else:
                set_foreign_meta(sc, ts, local, new)
            res["in_place"].append(key)
            res["tiles_updated"].append(key)
        else:
            tid, status, _ = sc.library.insert(sc.tile_image(ts, local), new, origin="fork", parent=key,
                                               source={"map": mp, "layer": layer["name"], "x": cells[0][0], "y": cells[0][1]})
            gid = sc.gid_for_gen(m, tid)
            for x, y, g, r in cells:
                layer["data"][y * m.width + x] = gid | r[2]
                res["cells_changed"].append({"x": x, "y": y, "old": key, "new": f"gen:{tid}"})
            res["forked"].append({"from": key, "to": f"gen:{tid}", "status": status})
            if status in ("new", "meta_variant"):
                res["tiles_new"].append(f"gen:{tid}")
    res.update(what)
    return summarize(finish(sc, m, res, bool(res["cells_changed"])), getattr(a, "quiet", False))
