"""The paged generated-tile library: pages (256x256 PNG + .tsj), manifest tiles.json, insert with dedup."""
import io
import json
import os
import re
import time

from PIL import Image

from common import (LIB_DIR, PAGE_COLS, PAGE_PX, PAGE_TILES, TILE, SceneError, apply_meta_to_entry, is_blank, json_bytes,
                    make_meta, meta_from_tsj_entry, meta_sig, norm_bytes, normalised, png_bytes, tile_hash)

PAGE_RE = re.compile(r"^page-(\d+)\.png$")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_manifest():
    return {"version": 1, "library": os.path.basename(LIB_DIR), "tile_size": TILE, "page_tiles": PAGE_TILES, "next_id": 0, "tiles": {}}


def new_tsj(page):
    return {"columns": PAGE_COLS, "image": f"page-{page:03d}.png", "imageheight": PAGE_PX, "imagewidth": PAGE_PX,
            "margin": 0, "name": f"gen-{page:03d}", "spacing": 0, "tilecount": PAGE_TILES, "tiledversion": "1.12.2",
            "tileheight": TILE, "tilewidth": TILE, "type": "tileset", "version": "1.10"}


class Library:
    def __init__(self, scene, dir):
        self.scene = scene
        self.dir = os.path.abspath(dir)
        self.manifest_path = os.path.join(self.dir, "tiles.json")
        raw = scene.read_bytes(self.manifest_path)
        try:
            self.manifest = json.loads(raw) if raw else new_manifest()
        except ValueError as e:
            raise SceneError(f"{self.manifest_path} is not valid JSON: {e}", "bad_input")
        self.dirty_manifest = False
        self.pages = {}       # n -> {"img", "tsj", "dirty_png", "dirty_tsj"}
        self.problems = []    # page files that could not be read (reported by `library check`)
        self._by_hash = None
        for name in sorted(os.listdir(self.dir)) if os.path.isdir(self.dir) else []:
            m = PAGE_RE.match(name)
            if m:
                self._load_page(int(m.group(1)))

    # -- pages
    def page_png_path(self, n):
        return os.path.join(self.dir, f"page-{n:03d}.png")

    def page_tsj_path(self, n):
        return os.path.join(self.dir, f"page-{n:03d}.tsj")

    def _load_page(self, n):
        raw = self.scene.read_bytes(self.page_png_path(n))
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        raw_t = self.scene.read_bytes(self.page_tsj_path(n))
        tsj = json.loads(raw_t) if raw_t else new_tsj(n)
        self.pages[n] = {"img": img, "tsj": tsj, "dirty_png": False, "dirty_tsj": raw_t is None}
        if img.size != (PAGE_PX, PAGE_PX):
            self.problems.append(f"page {n}: image is {img.size[0]}x{img.size[1]}, expected {PAGE_PX}x{PAGE_PX}")

    def _new_page(self, n):
        if n != len(self.pages) or n not in range(len(self.pages) + 1):
            raise SceneError(f"cannot create page {n}: pages must be contiguous (have {len(self.pages)})", "bad_input")
        self.pages[n] = {"img": Image.new("RGBA", (PAGE_PX, PAGE_PX), (0, 0, 0, 0)), "tsj": new_tsj(n),
                         "dirty_png": True, "dirty_tsj": True}

    def tileset_data(self, n):
        return self.pages[n]["tsj"] if n in self.pages else new_tsj(n)

    @property
    def next_id(self):
        return self.manifest["next_id"]

    def entry(self, tid):
        return self.manifest["tiles"].get(str(tid))

    def has(self, tid):
        return self.entry(tid) is not None

    def _box(self, tid):
        s = tid % PAGE_TILES
        x, y = (s % PAGE_COLS) * TILE, (s // PAGE_COLS) * TILE
        return x, y, x + TILE, y + TILE

    def tile_image(self, tid):
        n = tid // PAGE_TILES
        if n not in self.pages:
            raise SceneError(f"library page {n} does not exist (tile gen:{tid})", "not_found")
        return self.pages[n]["img"].crop(self._box(tid))

    # -- metadata (lives in the page .tsj)
    def _tsj_entry(self, tid, create=False):
        page = self.pages[tid // PAGE_TILES]
        local = tid % PAGE_TILES
        for e in page["tsj"].get("tiles", []):
            if e.get("id") == local:
                return e
        if create:
            e = {"id": local}
            page["tsj"].setdefault("tiles", []).append(e)
            page["tsj"]["tiles"].sort(key=lambda t: t["id"])
            return e
        return None

    def meta(self, tid):
        if tid // PAGE_TILES not in self.pages:
            return make_meta()
        return meta_from_tsj_entry(self._tsj_entry(tid))

    def set_meta(self, tid, meta):
        page = self.pages[tid // PAGE_TILES]
        e = self._tsj_entry(tid, create=True)
        if not apply_meta_to_entry(e, meta):
            page["tsj"]["tiles"] = [t for t in page["tsj"].get("tiles", []) if t is not e]
            if not page["tsj"]["tiles"]:
                page["tsj"].pop("tiles")
        page["dirty_tsj"] = True
        ent = self.entry(tid)
        if ent is not None:
            mat = make_meta(meta.get("collision"), meta.get("type"), meta.get("material"))["material"]
            if mat:
                ent["material"] = mat
            else:
                ent.pop("material", None)
            self.dirty_manifest = True

    # -- hash index
    def by_hash(self):
        if self._by_hash is None:
            self._by_hash = {}
            for k, e in self.manifest["tiles"].items():
                self._by_hash.setdefault(e["hash"], []).append(int(k))
        return self._by_hash

    def find(self, img, meta):
        """Existing tile with identical pixels and identical metadata signature, or None."""
        h = tile_hash(img)
        sig = meta_sig(meta)
        for i in self.by_hash().get(h, []):
            if meta_sig(self.meta(i)) == sig:
                return i
        return None

    # -- insert
    def insert(self, img, meta=None, *, origin, parent=None, job=None, source=None, gen=None, near=None):
        """Returns (id, status, extra). status: new | reused | meta_variant | near. extra: pixel diff for near."""
        img = img.convert("RGBA")
        if img.size != (TILE, TILE):
            raise SceneError(f"tile image must be {TILE}x{TILE}, got {img.size}", "bad_input")
        if is_blank(img):
            raise SceneError("fully transparent tiles are never stored (use gid 0)", "bad_input")
        meta = make_meta((meta or {}).get("collision"), (meta or {}).get("type"), (meta or {}).get("material"))
        h = tile_hash(img)
        sig = meta_sig(meta)
        same_pixels = self.by_hash().get(h, [])
        for i in same_pixels:
            if meta_sig(self.meta(i)) == sig:
                return i, "reused", None
        status = "meta_variant" if same_pixels else "new"
        if near and not same_pixels:
            n_px, thr = near
            best = None
            raw = norm_bytes(img)
            for k, e in self.manifest["tiles"].items():
                i = int(k)
                if meta_sig(self.meta(i)) != sig:
                    continue
                other = norm_bytes(self.tile_image(i))
                d = 0
                for p in range(0, len(raw), 4):
                    if max(abs(raw[p + c] - other[p + c]) for c in range(4)) > thr:
                        d += 1
                        if d > n_px:
                            break
                if d <= n_px and (best is None or d < best[1]):
                    best = (i, d)
            if best:
                return best[0], "near", best[1]
        tid = self.manifest["next_id"]
        page = tid // PAGE_TILES
        if page not in self.pages:
            self._new_page(page)
        self.pages[page]["img"].paste(normalised(img), self._box(tid)[:2])
        self.pages[page]["dirty_png"] = True
        self.manifest["next_id"] = tid + 1
        ent = {"hash": h, "created": now(), "origin": origin, "parent": parent, "job": job, "source": source}
        if gen:
            ent["gen"] = gen
        if meta["material"]:
            ent["material"] = meta["material"]
        self.manifest["tiles"][str(tid)] = ent
        self.dirty_manifest = True
        self.by_hash().setdefault(h, []).append(tid)
        if meta["collision"] or meta["type"] or meta["material"]:
            self.set_meta(tid, meta)
        return tid, status, None

    def set_pixels(self, tid, img, op, job=None):
        """In-place overwrite of a tile's slot (global edit). Records a revision."""
        img = img.convert("RGBA")
        if is_blank(img):
            raise SceneError("a global edit cannot make a tile fully transparent", "bad_input")
        ent = self.entry(tid)
        if ent is None:
            raise SceneError(f"gen:{tid} is not in the manifest", "not_found")
        old = ent["hash"]
        h = tile_hash(img)
        if h == old:
            return False
        page = self.pages[tid // PAGE_TILES]
        page["img"].paste(normalised(img), self._box(tid)[:2])
        page["dirty_png"] = True
        ids = self.by_hash().get(old, [])
        if tid in ids:
            ids.remove(tid)
        self.by_hash().setdefault(h, []).append(tid)
        ent["hash"] = h
        ent.setdefault("revisions", []).append({"hash": h, "previous": old, "at": now(), "op": op, "job": job})
        self.dirty_manifest = True
        return True

    # -- staging
    def stage(self):
        sc = self.scene
        for n in sorted(self.pages):
            p = self.pages[n]
            if p["dirty_png"]:
                sc.stage(self.page_png_path(n), png_bytes(p["img"]))
            if p["dirty_tsj"]:
                p["tsj"]["tilecount"] = PAGE_TILES
                sc.stage(self.page_tsj_path(n), json_bytes(p["tsj"], indent=1, sort_keys=True))
        if self.dirty_manifest:
            sc.stage(self.manifest_path, json_bytes(self.manifest, indent=1))
