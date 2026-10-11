"""Map validation for tools/mapgen."""
import json
import os
import re
import subprocess
import tempfile

from PIL import Image

from preview import find_tool
from tmjlib import FLIP_MASK, TiledMap, object_tile

PAGE_RE = re.compile(r"^page-(\d+)\.tsj$")
PAGE_TILES = 256


def _page_no(ts):
    """Library page number when the tileset is a generated-library page (page-NNN.tsj), else None."""
    if not ts.path:
        return None
    mm = PAGE_RE.match(os.path.basename(ts.path))
    return int(mm.group(1)) if mm else None


def _manifest_ids(ts, cache):
    p = os.path.join(os.path.dirname(ts.path), "tiles.json")
    if p not in cache:
        try:
            with open(p) as f:
                cache[p] = set(int(k) for k in json.load(f).get("tiles", {}))
        except (OSError, ValueError):
            cache[p] = None
    return cache[p]


def validate(m, run_tiled=True):
    errors, warnings = [], []
    d = m.data
    w, h = d.get("width"), d.get("height")

    if d.get("orientation") != "orthogonal":
        errors.append(f"orientation is {d.get('orientation')!r}, loader needs orthogonal")
    if d.get("infinite"):
        errors.append("infinite maps are not supported")
    if not d.get("tilesets"):
        errors.append("map references no tileset (loader requires one)")

    # tilesets
    ranges = []
    for ts in m.tilesets:
        label = ts.source or ts.name
        if getattr(ts, "missing", False):
            errors.append(f"tileset file missing: {label} (resolved to {ts.path})")
            continue
        if (ts.tilew, ts.tileh) != (m.tilew, m.tileh):
            errors.append(f"tileset '{ts.name}' tile size {ts.tilew}x{ts.tileh} differs from map {m.tilew}x{m.tileh}")
        img = ts.image_path()
        if img:
            if not os.path.isfile(img):
                errors.append(f"tileset '{ts.name}' image missing: {img}")
            else:
                iw, ih = Image.open(img).size
                if ts.columns and ts.columns * ts.tilew > iw:
                    errors.append(f"tileset '{ts.name}' image {iw}x{ih} is smaller than its columns/tilewidth")
        if ts.tilecount > PAGE_TILES:
            errors.append(f"tileset '{ts.name}' has {ts.tilecount} tiles; more than {PAGE_TILES} breaks the "
                          f"WebGPU 256-array-layer guarantee (use pages of {PAGE_TILES})")
        if _page_no(ts) is not None:
            if ts.tilecount != PAGE_TILES:
                errors.append(f"library page '{ts.name}' has tilecount {ts.tilecount}, expected {PAGE_TILES}")
            if img and os.path.isfile(img) and Image.open(img).size != (256, 256):
                errors.append(f"library page '{ts.name}' image must be exactly 256x256, is {Image.open(img).size}")
        ranges.append((ts.firstgid, ts.firstgid + ts.tilecount, ts.name))
    ranges.sort()
    for a, b in zip(ranges, ranges[1:]):
        if b[0] < a[1]:
            errors.append(f"tilesets '{a[2]}' and '{b[2]}' have overlapping gid ranges")

    # layers
    tls = m.tile_layers()
    if not tls:
        errors.append("map has no tile layer (loader needs one)")
    for l in m.layers:
        for p in l.get("properties", []):
            if p.get("name") == "above" and not (isinstance(p.get("value"), bool) and p.get("type", "bool") == "bool"):
                errors.append(f"layer '{l['name']}': property 'above' must be a bool, is {p.get('value')!r} ({p.get('type')})")
    ids = [l.get("id") for l in m.layers]
    if len(set(ids)) != len(ids):
        errors.append("duplicate layer ids")
    names = [l["name"] for l in m.layers]
    if len(set(names)) != len(names):
        errors.append("duplicate layer names")

    for l in tls:
        data = l.get("data")
        if not isinstance(data, list):
            errors.append(f"layer '{l['name']}': data is not a JSON array (compressed/encoded?)")
            continue
        if len(data) != w * h:
            errors.append(f"layer '{l['name']}': data length {len(data)} != width*height {w * h}")
        if (l.get("width"), l.get("height")) != (w, h):
            errors.append(f"layer '{l['name']}': size {l.get('width')}x{l.get('height')} != map {w}x{h}")
        bad = {}
        manifest_cache = {}
        missing_gen = {}
        for i, gid in enumerate(data):
            if not isinstance(gid, int) or gid < 0:
                errors.append(f"layer '{l['name']}': bad value {gid!r} at cell {i}")
                break
            if gid and m.tileset_for_gid(gid) is None:
                bad.setdefault(gid & ~FLIP_MASK, []).append((i % w, i // w))
            elif gid:
                ts = m.tileset_for_gid(gid)
                pn = _page_no(ts)
                if pn is not None:
                    gen_id = pn * PAGE_TILES + (gid & ~FLIP_MASK) - ts.firstgid
                    ids_ = _manifest_ids(ts, manifest_cache)
                    if ids_ is None or gen_id not in ids_:
                        missing_gen.setdefault(gen_id, []).append((i % w, i // w))
        for gen_id, cells in missing_gen.items():
            errors.append(f"layer '{l['name']}': gen:{gen_id} is not in the library manifest tiles.json "
                          f"(first at {cells[0]}, {len(cells)} cells)")
        for gid, cells in bad.items():
            errors.append(f"layer '{l['name']}': gid {gid} resolves to no tileset (first at {cells[0]}, {len(cells)} cells)")

    # objects
    seen_ids = set()
    spawns = []
    for l in m.layers:
        if l["type"] != "objectgroup":
            continue
        for o in l["objects"]:
            if o["id"] in seen_ids:
                warnings.append(f"duplicate object id {o['id']} (Tiled expects ids unique per map; the game ignores ids)")
            seen_ids.add(o["id"])
            if not (0 <= o["x"] <= w * m.tilew and 0 <= o["y"] <= h * m.tileh):
                errors.append(f"object '{o['name']}' (id {o['id']}) at ({o['x']},{o['y']}) is outside the map")
            if o["name"] == "SpawnPoint":
                spawns.append((l, o))
    if len(spawns) != 1:
        errors.append(f"expected exactly one SpawnPoint object, found {len(spawns)}")
    elif w and h:
        l, o = spawns[0]
        if l["name"] != "Spawn":
            warnings.append(f"SpawnPoint is in layer '{l['name']}', the game reads layer 'Spawn'")
        tx, ty = object_tile(m, o)
        if not (0 <= tx < w and 0 <= ty < h):
            pass  # already reported as outside the map
        else:
            for tl in tls:
                data = tl.get("data")
                if not isinstance(data, list) or len(data) != w * h:
                    continue
                gid = data[ty * w + tx]
                if not gid:
                    continue
                ts = m.tileset_for_gid(gid)
                if ts and ts.has_collision((gid & ~FLIP_MASK) - ts.firstgid):
                    errors.append(f"SpawnPoint stands on tile ({tx},{ty}) with collision "
                                  f"({m.format_tile(gid)} in layer '{tl['name']}')")

    # Tiled round trip as a format oracle
    tiled_result = "skipped"
    if run_tiled:
        exe = find_tool("tiled")
        if not exe:
            warnings.append("tiled binary not found, skipped --export-map check")
            tiled_result = "unavailable"
        else:
            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "out.tmj")
                env = dict(os.environ)
                r = subprocess.run([exe, "--export-map", "json", m.path, out], capture_output=True, text=True, env=env, timeout=120)
                if r.returncode != 0:
                    tiled_result = "failed"
                    errors.append(f"tiled --export-map failed: {(r.stderr or r.stdout).strip()}")
                else:
                    tiled_result = "ok"
                    # sanity: Tiled should see the same cell count
                    try:
                        with open(out) as f:
                            ex = json.load(f)
                        if ex.get("width") != w or ex.get("height") != h:
                            errors.append("tiled re-export changed the map size")
                    except Exception as e:
                        errors.append(f"tiled export unreadable: {e}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "tiled_export": tiled_result}
