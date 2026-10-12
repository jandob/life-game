"""Inspect commands: render, cells, where, diff, tile, library."""
import json
import os
import subprocess

from PIL import Image, ImageDraw

import tmjlib as T
from common import (FLIP_MASK, LIB_DIR, PAGE_COLS, PAGE_PX, PAGE_TILES, ROOT, TILE, Scene, SceneError, abspath_from_root,
                    apply_flags, flags_str, is_blank, key_of, layer_above, load_materials, normalize_key, parse_region,
                    png_bytes, rel, tile_hash, atomic_write)
from compose import (Resolver, UsageIndex, cell_crop, check_against_tmx, composite_image, layer_image, scan_map_paths,
                     tile_layers)
from preview import font, text_outlined


def clip_region(m, region):
    x, y, w, h = region
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(m.width, x + w), min(m.height, y + h)
    if x1 <= x0 or y1 <= y0:
        raise SceneError(f"region {x},{y},{w},{h} lies outside the {m.width}x{m.height} map", "bad_input")
    return x0, y0, x1 - x0, y1 - y0


def layer_names(text):
    if not text or text == "all":
        return None
    return [t for t in text.split(",") if t]


def short_code(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


# --------------------------------------------------------------------------- render

def cmd_render(a):
    sc = Scene("render")
    m = sc.load_map(abspath_from_root(a.map))
    res = {"ok": True, "map": rel(m.path), "map_hash": sc.map_hash(m)}
    if a.check_tmx:
        chk = check_against_tmx(sc, m)
        res["check_tmx"] = chk
        if chk["differing_pixels"]:
            res.update(ok=False, error=f"{chk['differing_pixels']} pixels differ from tmxrasterizer", code="mismatch")
        if not a.out:
            return res
    if not a.out:
        raise SceneError("render needs --out PNG (or --check-tmx)", "bad_input")
    scale = a.scale
    if scale < 1:
        raise SceneError("--scale must be >= 1", "bad_input")
    full = (0, 0, m.width, m.height)
    inner = clip_region(m, parse_region(a.region)) if a.region else full
    region = inner
    if a.context:
        k = a.context
        region = clip_region(m, (inner[0] - k, inner[1] - k, inner[2] + 2 * k, inner[3] + 2 * k))
    rx, ry, rw, rh = region
    layers = tile_layers(m, layer_names(a.layers))
    S = scale * TILE
    base = composite_image(sc, m, layers, region).resize((rw * S, rh * S), Image.NEAREST) if scale != 1 else composite_image(sc, m, layers, region)
    bg = Image.new("RGBA", base.size, (40, 40, 48, 255))
    bd = ImageDraw.Draw(bg)
    for cy in range(rh):
        for cx in range(rw):
            if (cx + cy) % 2:
                bd.rectangle([cx * S, cy * S, (cx + 1) * S - 1, (cy + 1) * S - 1], fill=(52, 52, 60, 255))
    img = Image.alpha_composite(bg, base)
    margin = 28 if a.grid else 0
    canvas = Image.new("RGBA", (img.width + margin, img.height + margin), (20, 20, 24, 255))
    canvas.paste(img, (margin, margin))
    over = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    legend = {}
    resolver = Resolver(m)

    def origin(cx, cy):
        return margin + (cx - rx) * S, margin + (cy - ry) * S

    # top-most non-empty gid per cell among the rendered layers
    top = {}
    for l in layers:
        for cy in range(ry, ry + rh):
            for cx in range(rx, rx + rw):
                gid = l["data"][cy * m.width + cx]
                if gid and resolver(gid):
                    top[(cx, cy)] = (l, gid)
    keys = {c: key_of(resolver(g)[0], resolver(g)[1]) for c, (l, g) in top.items()}

    if a.uses:
        idx = UsageIndex(sc)
        mp = rel(m.path)
        legend["uses"] = {"unique": "green", "shared in this map": "yellow", "shared with other maps": "red"}
        for c, k in keys.items():
            cnt = idx.counts(k, mp)
            col = (230, 40, 40, 140) if cnt["maps"] >= 2 else (240, 210, 60, 140) if cnt["total"] > 1 else (60, 220, 100, 140)
            ox, oy = origin(*c)
            d.rectangle([ox, oy, ox + S - 1, oy + S - 1], fill=col)

    if a.material:
        mats = load_materials()
        used = {}
        for c, (l, g) in top.items():
            ts, local, _ = resolver(g)
            mat = sc.tile_meta(ts, local)["material"]
            if not mat:
                continue
            col = T_hex(mats.get(mat, {}).get("colour", "#ffffff"))
            ox, oy = origin(*c)
            d.rectangle([ox, oy, ox + S - 1, oy + S - 1], fill=col + (95,))
            used[mat] = "#%02x%02x%02x" % col
            if scale >= 3:
                text_outlined(d, (ox + 2, oy + S - 14), mat[:8], font(10), (255, 255, 255, 255))
        legend["material"] = used

    if a.collision:
        legend["collision"] = "red"
        for l in layers:
            shapes_cache = {}
            for cy in range(ry, ry + rh):
                for cx in range(rx, rx + rw):
                    gid = l["data"][cy * m.width + cx]
                    r = gid and resolver(gid)
                    if not r:
                        continue
                    ts, local, flags = r
                    if (id(ts), local, flags) not in shapes_cache:
                        shapes = sc.tile_meta(ts, local)["collision"]
                        t = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                        td = ImageDraw.Draw(t)
                        for s in shapes:
                            col, ol = (255, 40, 40, 110), (255, 80, 80, 255)
                            if "polygon" in s:
                                td.polygon([((s["x"] + p["x"]) * scale, (s["y"] + p["y"]) * scale) for p in s["polygon"]],
                                           fill=col, outline=ol)
                            elif s.get("ellipse"):
                                td.ellipse([s["x"] * scale, s["y"] * scale, (s["x"] + s["width"]) * scale - 1,
                                            (s["y"] + s["height"]) * scale - 1], fill=col, outline=ol)
                            else:
                                td.rectangle([s["x"] * scale, s["y"] * scale, (s["x"] + s["width"]) * scale - 1,
                                              (s["y"] + s["height"]) * scale - 1], fill=col, outline=ol)
                        shapes_cache[(id(ts), local, flags)] = apply_flags(t, flags) if shapes else None
                    t = shapes_cache[(id(ts), local, flags)]
                    if t is not None:
                        over.alpha_composite(t, origin(cx, cy))

    if a.highlight:
        want = {normalize_key(h, m)[0] for h in a.highlight}
        found = 0
        for c, k in keys.items():
            if k in want:
                ox, oy = origin(*c)
                d.rectangle([ox, oy, ox + S - 1, oy + S - 1], outline=(255, 235, 0, 255), width=max(2, scale))
                found += 1
        legend["highlight"] = {"tiles": sorted(want), "cells": found}

    if a.ids:
        ids = {}
        codes = {}
        for c, k in keys.items():
            ox, oy = origin(*c)
            if scale >= 4:
                name, num = k.rsplit(":", 1)
                f = font(max(9, min(14, S // 5)))
                text_outlined(d, (ox + 3, oy + 2), name[:8], f, (255, 255, 255, 255))
                text_outlined(d, (ox + 3, oy + 2 + max(11, S // 5 + 2)), num, f, (255, 235, 120, 255))
            else:
                code = codes.setdefault(k, short_code(len(codes)))
                text_outlined(d, (ox + 1, oy), code, font(max(8, S - 4)), (255, 255, 255, 255))
        if scale < 4:
            ids = {v: k for k, v in codes.items()}
            legend["ids"] = ids

    if a.grid:
        step = a.grid
        gf = font(11)
        line = (255, 255, 255, 70)
        for cx in range(rx, rx + rw + 1):
            if cx % step == 0:
                x = margin + (cx - rx) * S
                d.line([(x, margin), (x, margin + rh * S)], fill=line)
                if cx < rx + rw:
                    d.text((x + 2, 4), str(cx), font=gf, fill=(255, 255, 140, 255))
        for cy in range(ry, ry + rh + 1):
            if cy % step == 0:
                y = margin + (cy - ry) * S
                d.line([(margin, y), (margin + rw * S, y)], fill=line)
                if cy < ry + rh:
                    d.text((2, y + 2), str(cy), font=gf, fill=(255, 255, 140, 255))
    if a.context:
        ox, oy = origin(inner[0], inner[1])
        d.rectangle([ox, oy, ox + inner[2] * S - 1, oy + inner[3] * S - 1], outline=(80, 220, 255, 255), width=2)

    out = Image.alpha_composite(canvas, over).convert("RGB")
    outp = abspath_from_root(a.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    out.save(outp)
    res.update(image=outp, region=list(region), scale=scale, px_origin=[rx * TILE, ry * TILE], margin=margin,
               image_size=list(out.size), layers=[l["name"] for l in layers], legend=legend)
    if a.context:
        res["inner_region"] = list(inner)
    return res


def T_hex(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# --------------------------------------------------------------------------- cells

def tile_summary(sc, key, ts, local):
    if key.startswith("gen:"):
        ent = sc.library.entry(int(key.split(":")[1])) or {}
        prompt = (ent.get("gen") or {}).get("prompt") or ""
        return {"origin": ent.get("origin"), "prompt_short": prompt[:60], "parent": ent.get("parent")}
    return {"origin": "hand-made", "tileset": ts.name, "prompt_short": "", "parent": None}


def cmd_cells(a):
    sc = Scene("cells")
    m = sc.load_map(abspath_from_root(a.map))
    region = clip_region(m, parse_region(a.region)) if a.region else (0, 0, m.width, m.height)
    rx, ry, rw, rh = region
    idx = UsageIndex(sc)
    mp = rel(m.path)
    resolver = Resolver(m)
    legend = {}
    hashes = {}
    layers_out = []
    names = layer_names(a.layers)
    for l in (tile_layers(m, names) if names else m.tile_layers()):
        rows = []
        for cy in range(ry, ry + rh):
            row = []
            for cx in range(rx, rx + rw):
                gid = l["data"][cy * m.width + cx]
                r = resolver(gid) if gid else None
                if not r:
                    row.append(None)
                    continue
                ts, local, flags = r
                k = key_of(ts, local)
                if k not in hashes:
                    meta = sc.tile_meta(ts, local)
                    hashes[k] = (tile_hash(sc.tile_image(ts, local)), meta)
                    legend[k] = tile_summary(sc, k, ts, local)
                h, meta = hashes[k]
                row.append({"tile": k, "gid": gid & ~FLIP_MASK, "flip": flags_str(flags), "hash": h,
                            "uses": idx.counts(k, mp), "collision": bool(meta["collision"]), "material": meta["material"] or None})
            rows.append(row)
        layers_out.append({"name": l["name"], "above": layer_above(l), "cells": rows})
    return {"ok": True, "map": mp, "map_hash": sc.map_hash(m), "region": list(region), "layers": layers_out, "tiles": legend}


# --------------------------------------------------------------------------- where

def cmd_where(a):
    sc = Scene("where")
    m = None
    if a.map:
        m = sc.load_map(abspath_from_root(a.map))
    key, _ = normalize_key(a.tile, m)
    idx = UsageIndex(sc, a.maps.split(",") if a.maps else None)
    uses = idx.of(key)
    h = None
    try:
        ts, local = sc.resolve_key(key, m)
        h = tile_hash(sc.tile_image(ts, local))
    except (SceneError, T.MapError):
        pass
    res = {"ok": True, "tile": key, "hash": h, "uses": uses, "count": len(uses), "maps": sorted({u["map"] for u in uses})}
    if a.sheet:
        res["sheet"] = write_use_sheet(sc, uses, a.sheet, a.context or 2)
    return res


def write_use_sheet(sc, uses, out, k):
    shown = uses[:48]
    scale = 4
    S = TILE * scale
    tiles = []
    maps = {}
    for u in shown:
        if u["map"] not in maps:
            maps[u["map"]] = sc.load_map(os.path.join(ROOT, u["map"]))
        m = maps[u["map"]]
        x0, y0 = max(0, u["x"] - k), max(0, u["y"] - k)
        x1, y1 = min(m.width, u["x"] + k + 1), min(m.height, u["y"] + k + 1)
        reg = (x0, y0, x1 - x0, y1 - y0)
        img = composite_image(sc, m, tile_layers(m), reg).resize((reg[2] * S, reg[3] * S), Image.NEAREST)
        bg = Image.new("RGBA", img.size, (40, 40, 48, 255))
        img = Image.alpha_composite(bg, img)
        ImageDraw.Draw(img).rectangle([(u["x"] - x0) * S, (u["y"] - y0) * S, (u["x"] - x0 + 1) * S - 1, (u["y"] - y0 + 1) * S - 1],
                                      outline=(255, 235, 0, 255), width=2)
        tiles.append((img, f"{os.path.basename(u['map'])} {u['layer']} ({u['x']},{u['y']})"))
    if not tiles:
        sheet = Image.new("RGB", (200, 40), (20, 20, 24))
        ImageDraw.Draw(sheet).text((6, 12), "no uses", font=font(14), fill=(230, 230, 230))
    else:
        cw = max(t[0].width for t in tiles) + 8
        ch = max(t[0].height for t in tiles) + 24
        cols = min(4, len(tiles))
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cw + 8, rows * ch + 8), (20, 20, 24))
        sd = ImageDraw.Draw(sheet)
        for i, (im, cap) in enumerate(tiles):
            x, y = 8 + (i % cols) * cw, 8 + (i // cols) * ch
            sd.text((x, y), cap, font=font(12), fill=(230, 230, 230))
            sheet.paste(im.convert("RGB"), (x, y + 18))
    outp = abspath_from_root(out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    sheet.save(outp)
    return {"image": outp, "shown": len(shown), "total": len(uses)}


# --------------------------------------------------------------------------- diff

def load_side(sc, spec):
    if spec.startswith("git:"):
        try:
            _, revn, path = spec.split(":", 2)
        except ValueError:
            raise SceneError(f"bad git spec '{spec}' (git:REV:path)", "bad_input")
        p = path if not os.path.isabs(path) else os.path.relpath(path, ROOT)
        r = subprocess.run(["git", "-C", ROOT, "show", f"{revn}:{p}"], capture_output=True)
        if r.returncode != 0:
            raise SceneError(f"git show {revn}:{p} failed: {r.stderr.decode().strip()}", "not_found")
        try:
            data = json.loads(r.stdout)
        except ValueError as e:
            raise SceneError(f"{spec} is not valid JSON: {e}", "bad_input")
        return T.TiledMap(os.path.join(ROOT, p), data), spec
    p = abspath_from_root(spec)
    return sc.load_map(p), spec


def cmd_diff(a):
    sc = Scene("diff")
    A, la = load_side(sc, a.a)
    B, lb = load_side(sc, a.b)
    region = parse_region(a.region) if a.region else (0, 0, min(A.width, B.width), min(A.height, B.height))
    region = clip_region(B, clip_region(A, region))
    rx, ry, rw, rh = region
    ra, rb = Resolver(A), Resolver(B)
    notes = []
    if (A.width, A.height) != (B.width, B.height):
        notes.append(f"map sizes differ ({A.width}x{A.height} vs {B.width}x{B.height}); compared the overlap")
    an = {l["name"]: l for l in A.tile_layers()}
    bn = {l["name"]: l for l in B.tile_layers()}
    per_layer = {}
    changed_cells = set()
    gen_a, gen_b = set(), set()

    def ref(m, res, gid):
        if not gid:
            return None
        r = res(gid)
        if not r:
            return f"?{gid & ~FLIP_MASK}"
        f = flags_str(r[2])
        return key_of(r[0], r[1]) + (f"|{f}" if f else "")

    for name in list(an) + [n for n in bn if n not in an]:
        la_, lb_ = an.get(name), bn.get(name)
        if la_ is None or lb_ is None:
            notes.append(f"layer '{name}' exists only in {'B' if la_ is None else 'A'}")
        ch = []
        for cy in range(ry, ry + rh):
            for cx in range(rx, rx + rw):
                ga = la_["data"][cy * A.width + cx] if la_ else 0
                gb = lb_["data"][cy * B.width + cx] if lb_ else 0
                ka, kb = ref(A, ra, ga), ref(B, rb, gb)
                if ka != kb:
                    ch.append({"x": cx, "y": cy, "old": ka, "new": kb})
                    changed_cells.add((cx, cy))
        per_layer[name] = {"changed": ch}
    for l in B.tile_layers():
        for gid in l["data"]:
            r = rb(gid) if gid else None
            if r and key_of(r[0], r[1]).startswith("gen:"):
                gen_b.add(key_of(r[0], r[1]))
    for l in A.tile_layers():
        for gid in l["data"]:
            r = ra(gid) if gid else None
            if r and key_of(r[0], r[1]).startswith("gen:"):
                gen_a.add(key_of(r[0], r[1]))
    # pixel difference of the visible result in the changed cells
    ia = composite_image(sc, A, tile_layers(A), region)
    ib = composite_image(sc, B, tile_layers(B), region)
    pixels = 0
    for (cx, cy) in changed_cells:
        ca, cb = cell_crop(ia, cx - rx, cy - ry), cell_crop(ib, cx - rx, cy - ry)
        pa, pb = ca.tobytes(), cb.tobytes()
        for i in range(0, len(pa), 4):
            if pa[i + 3] == 0 and pb[i + 3] == 0:
                continue
            if pa[i:i + 4] != pb[i:i + 4]:
                pixels += 1
    res = {"ok": True, "a": la, "b": lb, "region": list(region), "layers": per_layer,
           "cells_changed": len(changed_cells), "pixels_changed": pixels, "tiles_added": sorted(gen_b - gen_a),
           "notes": notes}
    if a.out:
        scale = 2
        S = TILE * scale
        wa = ia.resize((rw * S, rh * S), Image.NEAREST)
        wb = ib.resize((rw * S, rh * S), Image.NEAREST)
        sheet = Image.new("RGBA", (rw * S * 2 + 24, rh * S + 24), (20, 20, 24, 255))
        for i, im in enumerate((wa, wb)):
            bgi = Image.new("RGBA", im.size, (40, 40, 48, 255))
            sheet.paste(Image.alpha_composite(bgi, im), (8 + i * (rw * S + 8), 16))
        dd = ImageDraw.Draw(sheet)
        dd.text((8, 2), "A: " + la, font=font(11), fill=(230, 230, 230, 255))
        dd.text((16 + rw * S, 2), "B: " + lb, font=font(11), fill=(230, 230, 230, 255))
        for (cx, cy) in changed_cells:
            for i in (0, 1):
                ox = 8 + i * (rw * S + 8) + (cx - rx) * S
                oy = 16 + (cy - ry) * S
                dd.rectangle([ox, oy, ox + S - 1, oy + S - 1], outline=(255, 60, 60, 255), width=1)
        outp = abspath_from_root(a.out)
        os.makedirs(os.path.dirname(outp), exist_ok=True)
        sheet.convert("RGB").save(outp)
        res["image"] = outp
    return res


# --------------------------------------------------------------------------- tile

def cmd_tile(a):
    sc = Scene("tile")
    m = sc.load_map(abspath_from_root(a.map)) if a.map else None
    key, _ = normalize_key(a.tile, m)
    ts, local = sc.resolve_key(key, m)
    img = sc.tile_image(ts, local)
    meta = sc.tile_meta(ts, local)
    idx = UsageIndex(sc)
    uses = idx.of(key)
    res = {"ok": True, "tile": key, "tileset": ts.name, "local": local, "hash": tile_hash(img), "meta": meta,
           "uses": {"total": len(uses), "maps": sorted({u["map"] for u in uses})}}
    if key.startswith("gen:"):
        res["manifest"] = sc.library.entry(int(key.split(":")[1]))
    else:
        res["manifest"] = None
    if a.out:
        s = a.scale
        big = img.resize((TILE * s, TILE * s), Image.NEAREST)
        bg = Image.new("RGBA", big.size, (40, 40, 48, 255))
        outp = abspath_from_root(a.out)
        os.makedirs(os.path.dirname(outp), exist_ok=True)
        Image.alpha_composite(bg, big).convert("RGB").save(outp)
        res["image"] = outp
    return res


# --------------------------------------------------------------------------- library

def cmd_library(a):
    sc = Scene("library")
    lib = sc.library
    if a.action == "stats":
        origins, mats, with_col = {}, {}, 0
        for k, e in lib.manifest["tiles"].items():
            origins[e.get("origin")] = origins.get(e.get("origin"), 0) + 1
            meta = lib.meta(int(k))
            if meta["material"]:
                mats[meta["material"]] = mats.get(meta["material"], 0) + 1
            if meta["collision"]:
                with_col += 1
        n = len(lib.pages)
        return {"ok": True, "library": rel(lib.dir), "pages": n, "tiles": len(lib.manifest["tiles"]),
                "next_id": lib.next_id, "free_in_newest_page": (n * PAGE_TILES - lib.next_id) if n else 0,
                "origins": origins, "materials": mats, "with_collision": with_col}
    if a.action == "sheet":
        if a.page is None or not a.out:
            raise SceneError("library sheet needs --page N --out PNG", "bad_input")
        if a.page not in lib.pages:
            raise SceneError(f"no page {a.page} (pages: {len(lib.pages)})", "not_found")
        scale = a.scale
        S = TILE * scale
        pad = 2
        img = Image.new("RGBA", (PAGE_COLS * (S + pad) + pad, PAGE_COLS * (S + pad) + pad), (30, 30, 36, 255))
        d = ImageDraw.Draw(img)
        f = font(max(8, scale * 2 + 2))
        page = lib.pages[a.page]["img"]
        for s in range(PAGE_TILES):
            tid = a.page * PAGE_TILES + s
            x, y = pad + (s % PAGE_COLS) * (S + pad), pad + (s // PAGE_COLS) * (S + pad)
            for yy in range(S // 8):
                for xx in range(S // 8):
                    if (xx + yy) % 2:
                        d.rectangle([x + xx * 8, y + yy * 8, x + xx * 8 + 7, y + yy * 8 + 7], fill=(44, 44, 52, 255))
            t = page.crop(lib._box(tid)).resize((S, S), Image.NEAREST)
            img.alpha_composite(t, (x, y))
            if lib.has(tid):
                if lib.meta(tid)["collision"]:
                    d.rectangle([x, y, x + S - 1, y + S - 1], outline=(255, 50, 50, 255), width=2)
                text_outlined(d, (x + 2, y + 1), str(tid), f, (255, 230, 80, 255))
        outp = abspath_from_root(a.out)
        os.makedirs(os.path.dirname(outp), exist_ok=True)
        img.convert("RGB").save(outp)
        return {"ok": True, "image": outp, "page": a.page, "tiles_on_page": sum(1 for s in range(PAGE_TILES) if lib.has(a.page * PAGE_TILES + s))}
    if a.action == "check":
        return library_check(sc, lib)
    if a.action == "orphans":
        idx = UsageIndex(sc)
        orphans = [f"gen:{k}" for k in lib.manifest["tiles"] if not idx.of(f"gen:{k}")]
        return {"ok": True, "orphans": orphans, "count": len(orphans), "scanned_maps": idx.maps,
                "note": "orphans are never deleted"}
    raise SceneError("library action must be stats, sheet, check or orphans", "bad_input")


def library_check(sc, lib):
    problems = list(lib.problems)
    if lib.manifest.get("tile_size") != TILE:
        problems.append(f"manifest tile_size is {lib.manifest.get('tile_size')!r}, expected {TILE}")
    for n, p in sorted(lib.pages.items()):
        t = p["tsj"]
        if (t.get("tilewidth"), t.get("tileheight")) != (TILE, TILE):
            problems.append(f"page {n}: .tsj tile size is {t.get('tilewidth')}x{t.get('tileheight')}, expected {TILE}x{TILE}")
        if t.get("tilecount") != PAGE_TILES or t.get("columns") != PAGE_COLS:
            problems.append(f"page {n}: .tsj has tilecount {t.get('tilecount')} / columns {t.get('columns')}, expected {PAGE_TILES} / {PAGE_COLS}")
        if t.get("image") != f"page-{n:03d}.png":
            problems.append(f"page {n}: .tsj image is {t.get('image')!r}")
        if (t.get("imagewidth"), t.get("imageheight")) != (PAGE_PX, PAGE_PX):
            problems.append(f"page {n}: .tsj imagewidth/imageheight are {t.get('imagewidth')}x{t.get('imageheight')}")
        for e in t.get("tiles", []):
            if not (0 <= e.get("id", -1) < PAGE_TILES):
                problems.append(f"page {n}: .tsj has a tile entry with id {e.get('id')} outside 0..{PAGE_TILES - 1}")
    seen = set()
    for k, e in lib.manifest["tiles"].items():
        tid = int(k)
        seen.add(tid)
        n = tid // PAGE_TILES
        if n not in lib.pages or lib.pages[n]["img"].size != (PAGE_PX, PAGE_PX):
            problems.append(f"gen:{tid}: manifest entry without a slot (page {n} missing or wrong size)")
            continue
        if tid >= lib.next_id:
            problems.append(f"gen:{tid}: id is >= next_id {lib.next_id}")
        h = tile_hash(lib.tile_image(tid))
        if h != e["hash"]:
            problems.append(f"gen:{tid}: slot pixels hash {h} but manifest says {e['hash']}")
    for n, p in lib.pages.items():
        if p["img"].size != (PAGE_PX, PAGE_PX):
            continue
        for s in range(PAGE_TILES):
            tid = n * PAGE_TILES + s
            if tid not in seen and not is_blank(lib.tile_image(tid)):
                problems.append(f"gen:{tid}: slot has pixels but no manifest entry")
    mx = max(seen, default=-1)
    if lib.next_id <= mx:
        problems.append(f"next_id {lib.next_id} is not above the highest id {mx}")
    res = {"ok": not problems, "pages": len(lib.pages), "tiles": len(seen), "problems": problems}
    if problems:
        res.update(error=f"{len(problems)} problem(s) in the library", code="check_failed")
    return res
