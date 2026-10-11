"""Shared base for tools/scenekit: errors, hashing, pixels, and the Scene context (reads, staged writes, journal)."""
import glob
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mapgen"))

from PIL import Image  # noqa: E402

import tmjlib as T  # noqa: E402

ROOT = os.path.abspath(os.environ.get("SCENEKIT_ROOT") or os.path.join(HERE, "..", ".."))
LIB_DIR = os.path.abspath(os.environ.get("SCENEKIT_LIB") or os.path.join(ROOT, "assets", "library", "tilesets", "gen"))
OUT_DIR = os.path.abspath(os.environ.get("SCENEKIT_OUT") or os.path.join(HERE, "out"))
MAPS_GLOB = "assets/maps/**/*.tmj"
TILE = 16
PAGE_TILES = 256
PAGE_COLS = 16
PAGE_PX = 256

FLIP_H, FLIP_V, FLIP_D, FLIP_MASK = T.FLIP_H, T.FLIP_V, T.FLIP_D, T.FLIP_MASK


class SceneError(Exception):
    def __init__(self, message, code="error", **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


# --------------------------------------------------------------------------- hashing and pixels

def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def norm_bytes(img):
    """RGBA bytes with every fully transparent pixel normalised to (0,0,0,0)."""
    b = bytearray(img.convert("RGBA").tobytes())
    for i in range(3, len(b), 4):
        if b[i] == 0:
            b[i - 3] = b[i - 2] = b[i - 1] = 0
    return bytes(b)


def tile_hash(img):
    return sha(norm_bytes(img))


def is_blank(img):
    return img.convert("RGBA").getchannel("A").getextrema()[1] == 0


def blank_tile():
    return Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))


def normalised(img):
    img = img.convert("RGBA")
    return Image.frombytes("RGBA", img.size, norm_bytes(img))


def apply_flags(img, flags):
    """Tiled semantics: diagonal flip (transpose) first, then horizontal, then vertical."""
    if flags & FLIP_D:
        img = img.transpose(Image.TRANSPOSE)
    if flags & FLIP_H:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if flags & FLIP_V:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    return img


def undo_flags(img, flags):
    if flags & FLIP_V:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    if flags & FLIP_H:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if flags & FLIP_D:
        img = img.transpose(Image.TRANSPOSE)
    return img


def flags_str(flags):
    return "".join(k for k, b in (("h", FLIP_H), ("v", FLIP_V), ("d", FLIP_D)) if flags & b)


def flags_from_str(s):
    return sum(b for k, b in (("h", FLIP_H), ("v", FLIP_V), ("d", FLIP_D)) if k in s)


def parse_colour(text, default_alpha=255):
    s = str(text).strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", s):
        raise SceneError(f"bad colour '{text}' (use #rrggbb or #rrggbbaa)", "bad_input")
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    a = int(s[6:8], 16) if len(s) == 8 else default_alpha
    return (r, g, b, a)


def png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def parse_region(text, what="region"):
    try:
        v = [int(p) for p in str(text).split(",")]
    except ValueError:
        v = []
    if len(v) != 4 or v[2] <= 0 or v[3] <= 0:
        raise SceneError(f"{what} must be 'x,y,w,h' in tiles with w,h > 0, got '{text}'", "bad_input")
    return tuple(v)


def rel(path):
    """Path relative to ROOT when inside it, else absolute."""
    p = os.path.abspath(path)
    if p == ROOT or p.startswith(ROOT + os.sep):
        return os.path.relpath(p, ROOT).replace(os.sep, "/")
    return p


def abspath_from_root(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def atomic_write(path, data):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f".{os.path.basename(path)}.{os.getpid()}.tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def json_bytes(obj, **kw):
    return (json.dumps(obj, **kw) + "\n").encode()


# --------------------------------------------------------------------------- lock

class Lock:
    """Create-exclusive lock file (pid + time), stale after 10 minutes."""

    def __init__(self, path, stale=600):
        self.path, self.stale, self.held = path, stale, False

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "time": time.time()}).encode())
                os.close(fd)
                self.held = True
                return self
            except FileExistsError:
                try:
                    age = time.time() - os.path.getmtime(self.path)
                except OSError:
                    continue
                if age > self.stale:
                    try:
                        os.remove(self.path)
                    except OSError:
                        pass
                    continue
                raise SceneError(f"library is locked by another scenekit command ({self.path}); "
                                 f"retry, or delete the file if it is stale (> {self.stale}s)", "locked")
        raise SceneError(f"could not take lock {self.path}", "locked")

    def __exit__(self, *a):
        if self.held:
            try:
                os.remove(self.path)
            except OSError:
                pass


# --------------------------------------------------------------------------- tile keys

GEN_RE = re.compile(r"^gen-(\d+):(\d+)$")
GENID_RE = re.compile(r"^gen:(\d+)$")
PAGE_RE = re.compile(r"^page-(\d+)\.tsj$")


def gen_key(page, local):
    return f"gen:{page * PAGE_TILES + local}"


def split_flags(spec):
    spec = str(spec).strip()
    flags = 0
    while True:
        m = re.search(r"\|([hvd])$", spec)
        if not m:
            return spec, flags
        flags |= {"h": FLIP_H, "v": FLIP_V, "d": FLIP_D}[m.group(1)]
        spec = spec[:m.start()]


def normalize_key(spec, m=None):
    """'gen:5' | 'gen-000:5' | 'tileset:16' | gid (needs a map) [|flags] -> (canonical key, flags)."""
    if isinstance(spec, int):
        base, flags = str(spec), 0
    else:
        base, flags = split_flags(spec)
    mm = GEN_RE.match(base)
    if mm:
        return f"gen:{int(mm.group(1)) * PAGE_TILES + int(mm.group(2))}", flags
    if GENID_RE.match(base):
        return base, flags
    if re.fullmatch(r"\d+", base):
        if m is None:
            raise SceneError(f"raw gid '{base}' needs a map (--map)", "bad_input")
        gid = int(base)
        r = m.resolve_gid(gid)
        if not r:
            raise SceneError(f"gid {gid} resolves to no tileset in {rel(m.path)}", "bad_input")
        return key_of(r[0], r[1]), flags | r[2]
    if re.fullmatch(r"[^:|]+:\d+", base):
        return base, flags
    raise SceneError(f"bad tile ref '{spec}' (use gen:N, tileset:local, or a gid with --map)", "bad_input")


def is_gen_tileset(ts):
    return bool(ts.path) and os.path.dirname(os.path.abspath(ts.path)) == LIB_DIR and bool(PAGE_RE.match(os.path.basename(ts.path)))


def page_of(ts):
    return int(PAGE_RE.match(os.path.basename(ts.path)).group(1))


def key_of(ts, local):
    if is_gen_tileset(ts):
        return gen_key(page_of(ts), local)
    return f"{ts.name}:{local}"


def short_key(key):
    return key


# --------------------------------------------------------------------------- metadata

def norm_num(v):
    return int(v) if isinstance(v, float) and v == int(v) else v


def norm_shape(o):
    if "polygon" in o:
        return {"x": norm_num(o.get("x", 0)), "y": norm_num(o.get("y", 0)),
                "polygon": [{"x": norm_num(p["x"]), "y": norm_num(p["y"])} for p in o["polygon"]]}
    out = {"x": norm_num(o.get("x", 0)), "y": norm_num(o.get("y", 0)),
           "width": norm_num(o.get("width", 0)), "height": norm_num(o.get("height", 0))}
    if o.get("ellipse"):
        out["ellipse"] = True
    return out


def make_meta(collision=None, type_="", material=""):
    shapes = sorted((norm_shape(o) for o in (collision or [])), key=lambda s: json.dumps(s, sort_keys=True))
    return {"collision": shapes, "type": type_ or "", "material": material or ""}


def meta_sig(meta):
    return json.dumps(make_meta(meta.get("collision"), meta.get("type"), meta.get("material")), sort_keys=True)


def meta_from_tsj_entry(entry):
    if not entry:
        return make_meta()
    mat = ""
    for p in entry.get("properties", []):
        if p.get("name") == "material":
            mat = p.get("value", "")
    return make_meta(entry.get("objectgroup", {}).get("objects", []), entry.get("type") or entry.get("class") or "", mat)


def apply_meta_to_entry(entry, meta):
    """Write collision/type/material into a tsj `tiles` entry (dict with 'id'). Returns True if the entry has content."""
    meta = make_meta(meta.get("collision"), meta.get("type"), meta.get("material"))
    for k in ("objectgroup", "type", "class"):
        entry.pop(k, None)
    props = [p for p in entry.get("properties", []) if p.get("name") != "material"]
    if meta["material"]:
        props.append({"name": "material", "type": "string", "value": meta["material"]})
    if props:
        entry["properties"] = props
    else:
        entry.pop("properties", None)
    if meta["type"]:
        entry["type"] = meta["type"]
    if meta["collision"]:
        objs = []
        for i, s in enumerate(meta["collision"], 1):
            o = {"id": i, "name": "", "rotation": 0, "type": "", "visible": True, "x": s["x"], "y": s["y"]}
            if "polygon" in s:
                o["polygon"] = s["polygon"]
                o["width"] = 0
                o["height"] = 0
            else:
                o["width"], o["height"] = s["width"], s["height"]
                if s.get("ellipse"):
                    o["ellipse"] = True
            objs.append(o)
        entry["objectgroup"] = {"draworder": "index", "id": len(objs) + 1, "name": "", "objects": objs,
                                "opacity": 1, "type": "objectgroup", "visible": True, "x": 0, "y": 0}
    return len(entry) > 1


SHAPES = {
    "none": [],
    "full": [{"x": 0, "y": 0, "width": 16, "height": 16}],
    "top": [{"x": 0, "y": 0, "width": 16, "height": 8}],
    "bottom": [{"x": 0, "y": 8, "width": 16, "height": 8}],
    "left": [{"x": 0, "y": 0, "width": 8, "height": 16}],
    "right": [{"x": 8, "y": 0, "width": 8, "height": 16}],
    "top-quarter": [{"x": 0, "y": 0, "width": 16, "height": 4}],
    "bottom-quarter": [{"x": 0, "y": 12, "width": 16, "height": 4}],
}


def parse_shape(spec):
    spec = spec.strip()
    if spec in SHAPES:
        return [dict(s) for s in SHAPES[spec]]
    try:
        if spec.startswith("rect:"):
            x, y, w, h = [int(v) for v in spec[5:].split(",")]
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > TILE or y + h > TILE:
                raise ValueError
            return [{"x": x, "y": y, "width": w, "height": h}]
        if spec.startswith("poly:"):
            v = [int(p) for p in spec[5:].split(",")]
            if len(v) < 6 or len(v) % 2:
                raise ValueError
            return [{"x": 0, "y": 0, "polygon": [{"x": v[i], "y": v[i + 1]} for i in range(0, len(v), 2)]}]
    except ValueError:
        pass
    raise SceneError(f"bad shape '{spec}' (none, full, top, bottom, left, right, top-quarter, bottom-quarter, "
                     f"rect:x,y,w,h, poly:x1,y1,x2,y2,...)", "bad_input")


DEFAULT_MATERIALS = {
    "floor": {"char": ".", "shape": "none", "colour": "#8a6d4b", "hint": "wooden floor planks", "texture": "planks", "layer": "Floor"},
    "wall": {"char": "#", "shape": "full", "colour": "#5b5f73", "hint": "wall face", "texture": "wall", "layer": "Walls"},
    "wall_top": {"char": "^", "shape": "none", "colour": "#3b3e4f", "hint": "top edge of a wall", "layer": "Above", "above": True},
    "water": {"char": "~", "shape": "full", "colour": "#3d6fb5", "hint": "water", "layer": "Floor"},
    "furniture": {"char": "F", "shape": "full", "colour": "#a0522d", "hint": "furniture", "layer": "Decor"},
    "counter": {"char": "c", "shape": "bottom", "colour": "#c8b08a", "hint": "counter top", "layer": "Decor"},
    "door": {"char": "D", "shape": "none", "colour": "#7a4b2a", "hint": "door", "layer": "Walls"},
}


def load_materials(scene=None):
    p = os.path.join(LIB_DIR, "materials.json")
    if os.path.isfile(p):
        try:
            with open(p) as f:
                return json.load(f)
        except ValueError as e:
            raise SceneError(f"{p} is not valid JSON: {e}", "bad_input")
    return DEFAULT_MATERIALS


def layer_above(layer):
    return bool(T.props_dict(layer).get("above", False))


# --------------------------------------------------------------------------- scene context

JOURNAL_DIR = os.path.join(OUT_DIR, "journal")


def _order(path):
    base = os.path.basename(path)
    if base.endswith(".png"):
        return 0
    if base.endswith(".tsj"):
        return 1
    if base == "tiles.json":
        return 2
    if base.endswith(".tmj"):
        return 3
    return 4


class Scene:
    """One command's view of the files: tracks the hash of every file read, stages writes, commits atomically."""

    def __init__(self, command="scene", dry_run=False):
        self.command = command
        self.dry_run = dry_run
        self.reads = {}
        self.writes = {}
        self._sheets = {}
        self._lib = None

    # -- reading
    def read_bytes(self, path):
        path = os.path.abspath(path)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            data = None
        self.reads.setdefault(path, sha(data) if data is not None else None)
        return data

    def load_map(self, path, if_hash=None):
        path = os.path.abspath(path)
        data = self.read_bytes(path)
        if data is None:
            raise SceneError(f"map not found: {path}", "not_found")
        if if_hash:
            if if_hash == "auto":
                want = journal_hash_after_last_write(path)
                if want is None:
                    raise SceneError(f"--if-hash auto: the journal has no write to {rel(path)}, so there is no hash to trust; "
                                     f"pass the map_hash you looked at (current: {self.reads[path]})",
                                     "stale", map_hash=self.reads[path])
            else:
                want = if_hash if if_hash.startswith("sha256:") else "sha256:" + if_hash
            if want != self.reads[path]:
                raise SceneError(f"{rel(path)} changed since you looked (hash is {self.reads[path]}, you passed {want})",
                                 "stale", map_hash=self.reads[path])
        try:
            return T.TiledMap(path, json.loads(data))
        except ValueError as e:
            raise SceneError(f"{path} is not valid JSON: {e}", "bad_input")

    def map_hash(self, m):
        return self.reads.get(m.path) or sha(open(m.path, "rb").read())

    @property
    def library(self):
        if self._lib is None:
            from tilelib import Library
            self._lib = Library(self, LIB_DIR)
        return self._lib

    # -- tiles
    def sheet(self, ts):
        p = ts.image_path()
        if not p or not os.path.isfile(p):
            raise SceneError(f"tileset '{ts.name}' has no readable image ({p})", "bad_input")
        if p not in self._sheets:
            self._sheets[p] = Image.open(p).convert("RGBA")
        return self._sheets[p]

    def tile_image(self, ts, local):
        """16x16 RGBA of one tile, unflipped. Library pages come from the library (including uncommitted changes)."""
        if is_gen_tileset(ts):
            return self.library.tile_image(page_of(ts) * PAGE_TILES + local)
        d = ts.data
        sheet = self.sheet(ts)
        cols = ts.columns or (sheet.width // ts.tilew)
        sp, mg = int(d.get("spacing", 0)), int(d.get("margin", 0))
        x = mg + (local % cols) * (ts.tilew + sp)
        y = mg + (local // cols) * (ts.tileh + sp)
        return sheet.crop((x, y, x + ts.tilew, y + ts.tileh))

    def tile_meta(self, ts, local):
        if is_gen_tileset(ts):
            return self.library.meta(page_of(ts) * PAGE_TILES + local)
        return meta_from_tsj_entry(ts.tile_entry(local))

    def gid_for_gen(self, m, gen_id):
        """Raw gid (no flags) of library tile `gen_id` in map m; appends the page tileset to the map if needed."""
        lib = self.library
        page, local = gen_id // PAGE_TILES, gen_id % PAGE_TILES
        path = lib.page_tsj_path(page)
        for ts in m.tilesets:
            if ts.path and os.path.abspath(ts.path) == path:
                return ts.firstgid + local
        ts = T.append_tileset(m, path, lib.tileset_data(page))
        return ts.firstgid + local

    def locate_tileset(self, name):
        """Find a tileset .tsj by its name under assets/library (library pages: gen-NNN)."""
        mm = re.fullmatch(r"gen-(\d+)", name)
        if mm:
            return T.Tileset.load(self.library.page_tsj_path(int(mm.group(1))))
        for p in sorted(glob.glob(os.path.join(ROOT, "assets", "**", "*.tsj"), recursive=True)):
            try:
                ts = T.Tileset.load(p)
            except T.MapError:
                continue
            if ts.name == name:
                return ts
        raise SceneError(f"no tileset named '{name}' under assets/", "not_found")

    def resolve_key(self, key, m=None):
        """canonical key -> (tileset, local)."""
        if GENID_RE.match(key):
            n = int(key.split(":")[1])
            lib = self.library
            if n >= lib.next_id:
                raise SceneError(f"library has no tile {key} (next id is {lib.next_id})", "not_found")
            return T.Tileset(lib.page_tsj_path(n // PAGE_TILES), lib.tileset_data(n // PAGE_TILES), 0), n % PAGE_TILES
        name, local = key.rsplit(":", 1)
        local = int(local)
        if m is not None:
            for ts in m.tilesets:
                if ts.name == name:
                    return ts, local
        ts = self.locate_tileset(name)
        if local >= ts.tilecount:
            raise SceneError(f"tileset '{name}' has only {ts.tilecount} tiles", "not_found")
        return ts, local

    # -- writing
    def stage(self, path, data):
        path = os.path.abspath(path)
        if path not in self.reads:
            self.read_bytes(path)
        self.writes[path] = data

    def stage_map(self, m):
        self.stage(m.path, T.dumps_map(m.data).encode())

    def commit(self):
        """Write staged files atomically in the order page PNG, page .tsj, manifest, maps. Returns a result dict."""
        if self.library_loaded:
            self.library.stage()
        paths = sorted(self.writes, key=lambda p: (_order(p), p))
        # drop writes that don't change anything
        paths = [p for p in paths if sha(self.writes[p]) != self.reads.get(p)]
        info = {"changed_files": [rel(p) for p in paths], "journal": None}
        if not paths or self.dry_run:
            info["dry_run"] = self.dry_run
            return info
        touches_lib = any(os.path.abspath(p).startswith(LIB_DIR + os.sep) for p in paths)
        lock = Lock(os.path.join(LIB_DIR, ".lock")) if touches_lib else None
        if lock:
            lock.__enter__()
        try:
            for p, h in self.reads.items():
                cur = sha(open(p, "rb").read()) if os.path.isfile(p) else None
                if cur != h:
                    raise SceneError(f"{rel(p)} changed while the command ran; nothing was written", "conflict",
                                     files=[rel(p)])
            seq, jdir = self._journal(paths)
            for p in paths:
                atomic_write(p, self.writes[p])
            info["journal"] = seq
            return info
        finally:
            if lock:
                lock.__exit__()

    @property
    def library_loaded(self):
        return self._lib is not None

    def _journal(self, paths):
        os.makedirs(JOURNAL_DIR, exist_ok=True)
        seqs = [int(n.split("-")[0]) for n in os.listdir(JOURNAL_DIR) if re.match(r"^\d+-", n)]
        seq = max(seqs, default=0) + 1
        name = f"{seq:04d}-{re.sub(r'[^a-z0-9]+', '-', self.command.lower()).strip('-')}"
        jdir = os.path.join(JOURNAL_DIR, name)
        os.makedirs(os.path.join(jdir, "old"))
        files = []
        for i, p in enumerate(paths):
            old = self.reads.get(p)
            backup = None
            if old is not None:
                backup = f"old/{i}-{os.path.basename(p)}"
                shutil.copyfile(p, os.path.join(jdir, backup))
            files.append({"path": rel(p), "abs": p, "old_sha": old, "new_sha": sha(self.writes[p]), "backup": backup})
        meta = {"seq": seq, "command": self.command, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "files": files, "undone": False}
        with open(os.path.join(jdir, "entry.json"), "w") as f:
            json.dump(meta, f, indent=1)
        return name, jdir


def journal_entries():
    out = []
    if not os.path.isdir(JOURNAL_DIR):
        return out
    for n in sorted(os.listdir(JOURNAL_DIR)):
        p = os.path.join(JOURNAL_DIR, n, "entry.json")
        if os.path.isfile(p):
            with open(p) as f:
                e = json.load(f)
            e["dir"] = os.path.join(JOURNAL_DIR, n)
            e["name"] = n
            out.append(e)
    return out


def journal_hash_after_last_write(path):
    """sha256 this tool's journal says `path` had after its own last write (or undo) of it; None if it never wrote it.

    This is what `--if-hash auto` compares against: if anybody else touched the file since (hand edit in Tiled, another
    agent), the current hash differs and the command refuses like a stale explicit hash."""
    path = os.path.abspath(path)
    for e in reversed(journal_entries()):
        for f in e["files"]:
            if f["abs"] == path:
                return f["old_sha"] if e["undone"] else f["new_sha"]
    return None


def undo(steps=1, dry_run=False):
    todo = [e for e in journal_entries() if not e["undone"]][-steps:][::-1]
    if not todo:
        raise SceneError("nothing to undo", "not_found")
    # check everything first, across all steps, so a refusal leaves every file alone
    expect = {}
    restore = []
    for e in todo:
        for f in e["files"]:
            cur = sha(open(f["abs"], "rb").read()) if os.path.isfile(f["abs"]) else None
            want = expect.get(f["abs"], f["new_sha"])
            if cur != want:
                restore.append({"entry": e["name"], "path": f["path"]})
            expect[f["abs"]] = f["old_sha"]
    if restore:
        raise SceneError("refusing to undo: these files changed since the command wrote them: "
                         + ", ".join(sorted({r['path'] for r in restore})), "refused", changed_since=restore)
    restored = []
    if dry_run:
        return {"would_restore": sorted({f["path"] for e in todo for f in e["files"]}), "entries": [e["name"] for e in todo],
                "dry_run": True}
    touches_lib = any(f["abs"].startswith(LIB_DIR + os.sep) for e in todo for f in e["files"])
    lock = Lock(os.path.join(LIB_DIR, ".lock")) if touches_lib else None
    if lock:
        lock.__enter__()
    try:
        for e in todo:
            for f in reversed(e["files"]):
                if f["backup"]:
                    with open(os.path.join(e["dir"], f["backup"]), "rb") as fh:
                        atomic_write(f["abs"], fh.read())
                elif os.path.isfile(f["abs"]):
                    os.remove(f["abs"])
                restored.append(f["path"])
            e["undone"] = True
            with open(os.path.join(e["dir"], "entry.json"), "w") as fh:
                json.dump({k: v for k, v in e.items() if k not in ("dir", "name")}, fh, indent=1)
    finally:
        if lock:
            lock.__exit__()
    return {"restored": restored, "entries": [e["name"] for e in todo]}
