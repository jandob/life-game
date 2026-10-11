"""Pixel-exact map compositor (Tiled semantics), tmxrasterizer comparison, and the on-demand usage index."""
import glob
import json
import os

from PIL import Image, ImageChops

import tmjlib as T
from common import (FLIP_MASK, ROOT, TILE, SceneError, apply_flags, blank_tile, flags_str, key_of, normalised, rel,
                    tile_hash)


def check_layer_supported(layer):
    for k in ("offsetx", "offsety"):
        if layer.get(k, 0):
            raise SceneError(f"layer '{layer['name']}' has {k}; scenekit does not support layer offsets", "unsupported")
    for k in ("parallaxx", "parallaxy"):
        if layer.get(k, 1) != 1:
            raise SceneError(f"layer '{layer['name']}' has {k}; scenekit does not support parallax", "unsupported")


def tile_layers(m, names=None):
    """Tile layers in file order. names=None -> visible ones; names given -> exactly those (even if hidden)."""
    out = []
    if names:
        for n in names:
            out.append(m.layer(n, "tilelayer"))
        out.sort(key=lambda l: m.layers.index(l))
        return out
    for l in m.layers:
        if l["type"] == "tilelayer" and l.get("visible", True):
            out.append(l)
    return out


class Resolver:
    """gid -> (tileset, local, flags), cached per map."""

    def __init__(self, m):
        self.m = m
        self.cache = {}

    def __call__(self, gid):
        if gid not in self.cache:
            self.cache[gid] = self.m.resolve_gid(gid)
        return self.cache[gid]


def layer_image(scene, m, layer, region=None, resolver=None):
    """RGBA image of one tile layer alone, region (x,y,w,h in cells) default whole map. Flips applied."""
    check_layer_supported(layer)
    rx, ry, rw, rh = region or (0, 0, m.width, m.height)
    res = resolver or Resolver(m)
    img = Image.new("RGBA", (rw * TILE, rh * TILE), (0, 0, 0, 0))
    data = layer["data"]
    cache = {}
    for cy in range(ry, ry + rh):
        for cx in range(rx, rx + rw):
            if not (0 <= cx < m.width and 0 <= cy < m.height):
                continue
            gid = data[cy * m.width + cx]
            if not gid:
                continue
            r = res(gid)
            if r is None:
                raise SceneError(f"layer '{layer['name']}' cell ({cx},{cy}): gid {gid & ~FLIP_MASK} resolves to no tileset",
                                 "bad_input")
            ts, local, flags = r
            ck = (id(ts), local, flags)
            if ck not in cache:
                cache[ck] = apply_flags(scene.tile_image(ts, local), flags)
            img.paste(cache[ck], ((cx - rx) * TILE, (cy - ry) * TILE))
    return img


def composite_image(scene, m, layers, region=None):
    rx, ry, rw, rh = region or (0, 0, m.width, m.height)
    out = Image.new("RGBA", (rw * TILE, rh * TILE), (0, 0, 0, 0))
    res = Resolver(m)
    for l in layers:
        li = layer_image(scene, m, l, region, res)
        op = l.get("opacity", 1)
        out = Image.alpha_composite(out, li) if op >= 1 else blend_with_opacity(out, li, op)
    return out


def blend_with_opacity(dst, src, opacity):
    """Source-over of `src` onto `dst` with layer opacity, in Tiled/Qt integer arithmetic.

    Verified bit-exact against tmxrasterizer for opaque destinations (the usual case: a floor under the layer).
    Over partly transparent destinations the result can be off by one in a channel."""
    A = (int(opacity * 256) * 255) >> 8
    out = bytearray(dst.tobytes())
    sb = src.tobytes()
    for i in range(0, len(sb), 4):
        sa0 = sb[i + 3]
        if not sa0:
            continue
        sa = (sa0 * A + 127) // 255
        da = out[i + 3]
        if da == 255:
            for c in range(3):
                out[i + c] = (sb[i + c] * sa + out[i + c] * (255 - sa) + 127) // 255
        elif da == 0:
            if sa:
                out[i:i + 3] = sb[i:i + 3]
                out[i + 3] = sa
        else:
            oa = sa + (da * (255 - sa) + 127) // 255
            if oa:
                for c in range(3):
                    out[i + c] = min(255, (sb[i + c] * sa * 255 + out[i + c] * da * (255 - sa) + (255 * oa) // 2) // (255 * oa))
                out[i + 3] = min(255, oa)
    return Image.frombytes("RGBA", dst.size, bytes(out))


def cell_image(scene, m, layer, x, y, resolver=None):
    """One cell of one layer (flips applied) as a 16x16 image."""
    return layer_image(scene, m, layer, (x, y, 1, 1), resolver)


def cell_crop(img, cx, cy):
    return img.crop((cx * TILE, cy * TILE, (cx + 1) * TILE, (cy + 1) * TILE))


# --------------------------------------------------------------------------- tmxrasterizer check

def check_against_tmx(scene, m):
    from preview import rasterize
    ours = composite_image(scene, m, tile_layers(m))
    ref = rasterize(m.path, 1)
    if ref.size != ours.size:
        canvas = Image.new("RGBA", ours.size, (0, 0, 0, 0))
        canvas.paste(ref, (0, 0))
        ref = canvas
    a, b = _zero_transparent(ours), _zero_transparent(ref)
    diff = ImageChops.difference(a, b)
    r, g, bl, al = diff.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), ImageChops.lighter(bl, al))
    hist = mx.histogram()
    differing = sum(hist[1:])
    max_diff = max((i for i, c in enumerate(hist) if c), default=0)
    cells = []
    if differing:
        bbox_cells = set()
        for cy in range(m.height):
            for cx in range(m.width):
                if cell_crop(mx, cx, cy).getbbox():
                    bbox_cells.add((cx, cy))
        cells = sorted(bbox_cells)
    return {"map": rel(m.path), "size": list(ours.size), "differing_pixels": differing, "max_channel_diff": max_diff,
            "differing_cells": [list(c) for c in cells[:200]]}


def _zero_transparent(img):
    mask = img.getchannel("A").point(lambda v: 255 if v == 0 else 0)
    return Image.composite(Image.new("RGBA", img.size, (0, 0, 0, 0)), img, mask)


# --------------------------------------------------------------------------- usage index

def scan_map_paths(globs=None):
    pats = globs or [os.path.join(ROOT, "assets", "maps", "**", "*.tmj")]
    out = []
    for g in pats:
        g = g if os.path.isabs(g) else os.path.join(ROOT, g)
        out += glob.glob(g, recursive=True)
    return sorted({os.path.abspath(p) for p in out})


class UsageIndex:
    """tile key -> list of uses (map, layer, x, y, flip). Built from disk on demand; never stored."""

    def __init__(self, scene, globs=None):
        self.uses = {}
        self.maps = []
        for p in scan_map_paths(globs):
            try:
                with open(p) as f:
                    m = T.TiledMap(p, json.load(f))
            except (ValueError, OSError, T.MapError):
                continue
            mp = rel(p)
            self.maps.append(mp)
            res = Resolver(m)
            for l in m.tile_layers():
                if not isinstance(l.get("data"), list):
                    continue
                for i, gid in enumerate(l["data"]):
                    if not gid:
                        continue
                    r = res(gid)
                    if r is None:
                        continue
                    ts, local, flags = r
                    self.uses.setdefault(key_of(ts, local), []).append(
                        {"map": mp, "layer": l["name"], "x": i % m.width, "y": i // m.width, "flip": flags_str(flags)})

    def of(self, key):
        return self.uses.get(key, [])

    def counts(self, key, map_rel):
        u = self.of(key)
        return {"map": sum(1 for x in u if x["map"] == map_rel), "total": len(u), "maps": len({x["map"] for x in u})}
