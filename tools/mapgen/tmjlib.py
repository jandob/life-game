"""Core model for tools/mapgen: reading/writing .tmj, tilesets, tile specs, paint ops."""
import copy
import json
import os
import re

FLIP_H = 0x80000000
FLIP_V = 0x40000000
FLIP_D = 0x20000000
FLIP_MASK = FLIP_H | FLIP_V | FLIP_D
FLAG_BITS = {"h": FLIP_H, "v": FLIP_V, "d": FLIP_D}


class MapError(Exception):
    pass


# --------------------------------------------------------------------------- properties

def parse_value(text):
    """'true' -> True, '12' -> 12, '1.5' -> 1.5, '"12"' -> '12', anything else -> str."""
    try:
        v = json.loads(text)
    except ValueError:
        return text
    if isinstance(v, (bool, int, float, str)):
        return v
    return text


def parse_kv(items):
    out = {}
    for item in items or []:
        if "=" not in item:
            raise MapError(f"property '{item}' must look like key=value")
        k, v = item.split("=", 1)
        out[k] = parse_value(v)
    return out


def _ptype(v):
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    return "string"


def set_props(container, props):
    lst = container.setdefault("properties", [])
    for k, v in props.items():
        for p in lst:
            if p["name"] == k:
                p["type"], p["value"] = _ptype(v), v
                break
        else:
            lst.append({"name": k, "type": _ptype(v), "value": v})


def unset_props(container, keys):
    lst = container.get("properties", [])
    container["properties"] = [p for p in lst if p["name"] not in keys]
    if not container["properties"]:
        container.pop("properties")


def props_dict(container):
    return {p["name"]: p.get("value") for p in container.get("properties", [])}


# --------------------------------------------------------------------------- tilesets

class Tileset:
    def __init__(self, path, data, firstgid=0, source=None):
        self.path = path          # absolute .tsj path (or None if embedded)
        self.data = data
        self.firstgid = firstgid
        self.source = source      # path string as written in the map
        self.name = data.get("name") or (os.path.splitext(os.path.basename(path))[0] if path else "tileset")
        self.tilecount = int(data.get("tilecount", 0))
        self.columns = int(data.get("columns", 0))
        self.tilew = int(data.get("tilewidth", 16))
        self.tileh = int(data.get("tileheight", 16))

    @classmethod
    def load(cls, path, firstgid=0, source=None):
        if not os.path.isfile(path):
            raise MapError(f"tileset not found: {path}")
        try:
            with open(path) as f:
                data = json.load(f)
        except ValueError as e:
            raise MapError(f"tileset {path} is not valid JSON: {e}")
        return cls(os.path.abspath(path), data, firstgid, source)

    def image_path(self):
        img = self.data.get("image")
        if not img or not self.path:
            return None
        return os.path.join(os.path.dirname(self.path), img)

    def tile_entry(self, tid):
        for t in self.data.get("tiles", []):
            if t.get("id") == tid:
                return t
        return None

    def collision_shapes(self, tid):
        """Collision objects of a tile (Tiled objectgroup objects), tile-local pixels."""
        t = self.tile_entry(tid)
        if not t:
            return []
        return t.get("objectgroup", {}).get("objects", [])

    def has_collision(self, tid):
        return bool(self.collision_shapes(tid))

    def wangsets(self):
        out = []
        for ws in self.data.get("wangsets", []):
            out.append({
                "name": ws.get("name"),
                "type": ws.get("type"),
                "colors": [c.get("name") for c in ws.get("colors", [])],
                "tiles": len(ws.get("wangtiles", [])),
            })
        return out


# --------------------------------------------------------------------------- map

TILE_RE = re.compile(r"^(?:(?P<ts>[^:|]+):)?(?P<id>\d+)(?P<flags>(?:\|[hvd])*)$")


class TiledMap:
    def __init__(self, path, data):
        self.path = os.path.abspath(path)
        self.dir = os.path.dirname(self.path)
        self.data = data
        self.tilesets = []
        for ref in data.get("tilesets", []):
            fg = ref.get("firstgid", 1)
            if "source" in ref:
                p = os.path.normpath(os.path.join(self.dir, ref["source"]))
                try:
                    ts = Tileset.load(p, fg, ref["source"])
                except MapError:
                    # keep the map readable even if a tileset went missing; validate reports it
                    ts = Tileset(p, {"name": os.path.splitext(os.path.basename(p))[0]}, fg, ref["source"])
                    ts.missing = True
            else:
                ts = Tileset(None, ref, fg)
            self.tilesets.append(ts)

    @classmethod
    def load(cls, path):
        if not os.path.isfile(path):
            raise MapError(f"map not found: {path}")
        try:
            with open(path) as f:
                data = json.load(f)
        except ValueError as e:
            raise MapError(f"{path} is not valid JSON: {e}")
        return cls(path, data)

    # -- basic accessors
    @property
    def width(self):
        return self.data["width"]

    @property
    def height(self):
        return self.data["height"]

    @property
    def tilew(self):
        return self.data["tilewidth"]

    @property
    def tileh(self):
        return self.data["tileheight"]

    @property
    def layers(self):
        return self.data["layers"]

    def layer(self, name, kind=None):
        for l in self.layers:
            if l["name"] == name:
                if kind and l["type"] != kind:
                    raise MapError(f"layer '{name}' is a {l['type']}, expected {kind}")
                return l
        names = [l["name"] for l in self.layers]
        raise MapError(f"no layer named '{name}' (layers: {names})")

    def tile_layers(self):
        return [l for l in self.layers if l["type"] == "tilelayer"]

    def next_layer_id(self):
        n = self.data.get("nextlayerid", 1 + max([l["id"] for l in self.layers], default=0))
        self.data["nextlayerid"] = n + 1
        return n

    def next_object_id(self):
        used = [o["id"] for l in self.layers if l["type"] == "objectgroup" for o in l["objects"]]
        n = max(self.data.get("nextobjectid", 1), 1 + max(used, default=0))
        self.data["nextobjectid"] = n + 1
        return n

    # -- tile specs
    def tileset_by_name(self, name):
        for ts in self.tilesets:
            if ts.name == name:
                return ts
        # allow the file stem as an alias
        for ts in self.tilesets:
            if ts.path and os.path.splitext(os.path.basename(ts.path))[0] == name:
                return ts
        raise MapError(f"unknown tileset '{name}' (map has: {[t.name for t in self.tilesets]})")

    def tileset_for_gid(self, gid):
        g = gid & ~FLIP_MASK
        best = None
        for ts in self.tilesets:
            if ts.firstgid <= g < ts.firstgid + ts.tilecount:
                best = ts
        return best

    def resolve_gid(self, gid):
        """raw gid (flags in the high bits) -> (tileset, local id, flag bits); None for empty or unresolved gids."""
        if not gid:
            return None
        ts = self.tileset_for_gid(gid)
        if ts is None:
            return None
        base = gid & ~FLIP_MASK
        return ts, base - ts.firstgid, gid & FLIP_MASK

    def parse_tile(self, spec):
        """int gid | 'name:id[|h|v|d]' | '12[|h]' | None -> raw gid (flags in the high bits)."""
        if spec is None or spec is False:
            return 0
        if isinstance(spec, bool):
            raise MapError(f"bad tile {spec!r}")
        if isinstance(spec, int):
            gid = spec
        elif isinstance(spec, str):
            m = TILE_RE.match(spec.strip())
            if not m:
                raise MapError(f"bad tile '{spec}' (use a gid or 'tileset:localid[|h|v|d]')")
            flags = 0
            for f in m.group("flags").split("|")[1:]:
                flags |= FLAG_BITS[f]
            n = int(m.group("id"))
            if m.group("ts") is not None:
                ts = self.tileset_by_name(m.group("ts"))
                if n >= ts.tilecount:
                    raise MapError(f"tile '{spec}': tileset '{ts.name}' has only {ts.tilecount} tiles")
                gid = ts.firstgid + n
            else:
                gid = n
            gid |= flags
        else:
            raise MapError(f"bad tile {spec!r}")
        if gid < 0 or gid > 0xFFFFFFFF:
            raise MapError(f"gid out of range: {spec!r}")
        if gid and self.tileset_for_gid(gid) is None:
            raise MapError(f"gid {gid & ~FLIP_MASK} does not belong to any tileset")
        return gid

    def format_tile(self, gid, as_gid=False):
        if gid == 0:
            return "."
        base = gid & ~FLIP_MASK
        flags = "".join("|" + k for k, b in FLAG_BITS.items() if gid & b)
        if as_gid:
            return f"{base}{flags}"
        ts = self.tileset_for_gid(gid)
        if ts is None:
            return f"?{base}{flags}"
        return f"{ts.name}:{base - ts.firstgid}{flags}"

    # -- saving
    def save(self, path=None):
        path = path or self.path
        text = dumps_map(self.data)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, path)


def append_tileset(m, tsj_path, data=None):
    """Append a tileset to the END of the map's tileset list with the next free firstgid.

    Existing firstgids (and therefore every existing gid) never change. Returns the Tileset; if the map already
    references that file, returns the existing one. `data` lets the caller pass tileset JSON that is not on disk yet."""
    tsj_path = os.path.abspath(tsj_path)
    for ts in m.tilesets:
        if ts.path and os.path.abspath(ts.path) == tsj_path:
            return ts
    firstgid = max([t.firstgid + t.tilecount for t in m.tilesets], default=1)
    source = os.path.relpath(tsj_path, m.dir).replace(os.sep, "/")
    ts = Tileset(tsj_path, data, firstgid, source) if data is not None else Tileset.load(tsj_path, firstgid, source)
    m.data.setdefault("tilesets", []).append({"firstgid": firstgid, "source": source})
    m.tilesets.append(ts)
    return ts


def dumps_map(data):
    """Tiled-like JSON; tile layer data is written as one row per line."""
    d = dict(data)
    tokens = {}
    layers = []
    for i, l in enumerate(d["layers"]):
        if l["type"] == "tilelayer" and isinstance(l.get("data"), list):
            l = dict(l)
            tok = f"@@DATA{i}@@"
            w = l["width"]
            rows = [", ".join(str(v) for v in l["data"][r:r + w]) for r in range(0, len(l["data"]), w)]
            tokens[tok] = "[\n" + ",\n".join("   " + r for r in rows) + "\n  ]"
            l["data"] = tok
        layers.append(l)
    d["layers"] = layers
    text = json.dumps(d, indent=1)
    for tok, body in tokens.items():
        text = text.replace(json.dumps(tok), body)
    return text + "\n"


def new_map(path, width, height, tile, tileset_paths, default_layer="Ground"):
    mapdir = os.path.dirname(os.path.abspath(path))
    data = {
        "compressionlevel": -1,
        "height": height,
        "infinite": False,
        "layers": [],
        "nextlayerid": 1,
        "nextobjectid": 1,
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "tiledversion": "1.12.2",
        "tileheight": tile,
        "tilesets": [],
        "tilewidth": tile,
        "type": "map",
        "version": "1.10",
        "width": width,
    }
    firstgid = 1
    names = set()
    for tp in tileset_paths:
        ts = Tileset.load(tp)
        if ts.name in names:
            raise MapError(f"duplicate tileset name '{ts.name}'")
        names.add(ts.name)
        if (ts.tilew, ts.tileh) != (tile, tile):
            raise MapError(f"tileset {tp} has tile size {ts.tilew}x{ts.tileh}, map uses {tile}")
        data["tilesets"].append({"firstgid": firstgid, "source": os.path.relpath(ts.path, mapdir)})
        firstgid += ts.tilecount
    m = TiledMap(path, data)
    if default_layer:
        add_layer(m, default_layer, "tile")
    return m


def add_layer(m, name, kind, index=None, props=None):
    if any(l["name"] == name for l in m.layers):
        raise MapError(f"layer '{name}' already exists")
    lid = m.next_layer_id()
    if kind == "tile":
        layer = {"data": [0] * (m.width * m.height), "height": m.height, "id": lid, "name": name,
                 "opacity": 1, "type": "tilelayer", "visible": True, "width": m.width, "x": 0, "y": 0}
    elif kind == "object":
        layer = {"draworder": "topdown", "id": lid, "name": name, "objects": [], "opacity": 1,
                 "type": "objectgroup", "visible": True, "x": 0, "y": 0}
    else:
        raise MapError("layer type must be 'tile' or 'object'")
    if props:
        set_props(layer, props)
    if index is None or index >= len(m.layers):
        m.layers.append(layer)
    else:
        m.layers.insert(max(index, 0), layer)
    return layer


# --------------------------------------------------------------------------- paint

def _bresenham(x0, y0, x1, y1):
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _ints(op, key, vals, n):
    if not isinstance(vals, (list, tuple)) or len(vals) < n:
        raise MapError(f"{key}: expected a list of {n} values, got {vals!r}")
    for v in vals[:n]:
        if isinstance(v, bool) or not isinstance(v, int):
            raise MapError(f"{key}: coordinates must be integers, got {v!r}")


def apply_ops(m, layer, ops):
    """Apply ops to a copy of the layer data; returns (new_data, changed_cells). Raises on any error."""
    if not isinstance(ops, list):
        raise MapError("ops must be a JSON list")
    w, h = m.width, m.height
    data = list(layer["data"])

    def put(i, x, y, gid):
        if not (0 <= x < w and 0 <= y < h):
            raise MapError(f"op {i}: cell ({x},{y}) is outside the {w}x{h} map")
        data[y * w + x] = gid

    for i, op in enumerate(ops):
        try:
            if not isinstance(op, dict) or len(op) != 1:
                raise MapError("each op must be an object with exactly one key")
            (kind, arg), = op.items()
            if kind == "set":
                _ints(op, kind, arg, 2)
                put(i, arg[0], arg[1], m.parse_tile(arg[2] if len(arg) > 2 else None))
            elif kind == "rect":
                _ints(op, kind, arg, 4)
                x, y, rw, rh = arg[:4]
                g = m.parse_tile(arg[4] if len(arg) > 4 else None)
                for yy in range(y, y + rh):
                    for xx in range(x, x + rw):
                        put(i, xx, yy, g)
            elif kind == "outline":
                _ints(op, kind, arg, 4)
                x, y, rw, rh = arg[:4]
                g = m.parse_tile(arg[4] if len(arg) > 4 else None)
                t = arg[5] if len(arg) > 5 else 1
                for yy in range(y, y + rh):
                    for xx in range(x, x + rw):
                        if xx - x < t or x + rw - 1 - xx < t or yy - y < t or y + rh - 1 - yy < t:
                            put(i, xx, yy, g)
            elif kind == "line":
                _ints(op, kind, arg, 4)
                g = m.parse_tile(arg[4] if len(arg) > 4 else None)
                for xx, yy in _bresenham(*arg[:4]):
                    put(i, xx, yy, g)
            elif kind == "erase":
                _ints(op, kind, arg, 4)
                x, y, rw, rh = arg[:4]
                for yy in range(y, y + rh):
                    for xx in range(x, x + rw):
                        put(i, xx, yy, 0)
            elif kind == "fill":
                _ints(op, kind, arg, 2)
                g = m.parse_tile(arg[2] if len(arg) > 2 else None)
                x, y = arg[:2]
                if not (0 <= x < w and 0 <= y < h):
                    raise MapError(f"cell ({x},{y}) is outside the map")
                target = data[y * w + x]
                if target != g:
                    stack = [(x, y)]
                    while stack:
                        cx, cy = stack.pop()
                        if 0 <= cx < w and 0 <= cy < h and data[cy * w + cx] == target:
                            data[cy * w + cx] = g
                            stack += [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]
            elif kind == "stamp":
                if not isinstance(arg, dict) or "at" not in arg or "rows" not in arg:
                    raise MapError("stamp needs {'at': [x, y], 'rows': [[...], ...]}")
                _ints(op, "stamp.at", arg["at"], 2)
                x0, y0 = arg["at"][:2]
                for ry, row in enumerate(arg["rows"]):
                    for rx, t in enumerate(row):
                        g = m.parse_tile(t)
                        if g:
                            put(i, x0 + rx, y0 + ry, g)
            else:
                raise MapError(f"unknown op '{kind}' (set, rect, outline, line, erase, fill, stamp)")
        except MapError as e:
            msg = str(e)
            raise MapError(msg if msg.startswith("op ") else f"op {i}: {msg}")
    changed = sum(1 for a, b in zip(layer["data"], data) if a != b)
    return data, changed


# --------------------------------------------------------------------------- objects

def object_tile(m, o):
    return int(o["x"] // m.tilew), int(o["y"] // m.tileh)


def find_object(m, layer, oid=None, name=None):
    matches = [o for o in layer["objects"] if (oid is not None and o["id"] == oid) or (oid is None and o["name"] == name)]
    if not matches:
        raise MapError(f"no object {'id ' + str(oid) if oid is not None else repr(name)} in layer '{layer['name']}'")
    if len(matches) > 1:
        raise MapError(f"{len(matches)} objects are named '{name}', use --id")
    return matches[0]


def copy_data(m):
    return copy.deepcopy(m.data)
