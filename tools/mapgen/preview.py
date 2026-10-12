"""Rendering for tools/mapgen: tmxrasterizer base image + Pillow overlays, tileset contact sheets."""
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

from tmjlib import MapError, FLIP_MASK


def find_tool(name):
    env = os.environ.get(name.upper())
    if env and os.path.isfile(env):
        return env
    p = shutil.which(name)
    if p:
        return p
    mise = shutil.which("mise")
    if mise:
        try:
            tiled = subprocess.run([mise, "which", "tiled"], capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception:
            tiled = ""
        if tiled:
            cand = os.path.join(os.path.dirname(tiled), name)
            if os.path.isfile(cand):
                return cand
    return None


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def text_outlined(d, xy, s, f, fill, outline=(0, 0, 0)):
    x, y = xy
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                d.text((x + dx, y + dy), s, font=f, fill=outline)
    d.text((x, y), s, font=f, fill=fill)


def rasterize(map_path, scale):
    exe = find_tool("tmxrasterizer")
    if not exe:
        raise MapError("tmxrasterizer not found (set TMXRASTERIZER, or install Tiled via mise)")
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    env = dict(os.environ)
    r = subprocess.run([exe, "--scale", str(scale), "--no-smoothing", "--hide-object-layers", map_path, tmp],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        os.remove(tmp)
        raise MapError(f"tmxrasterizer failed: {r.stderr.strip() or r.stdout.strip()}")
    img = Image.open(tmp).convert("RGBA")
    img.load()
    os.remove(tmp)
    return img


def render(m, out, scale=2, grid=None, debug=False, region=None):
    base = rasterize(m.path, scale)
    tw, th = m.tilew * scale, m.tileh * scale
    expected = (m.width * tw, m.height * th)
    if base.size != expected:
        # tmxrasterizer may crop to content; place it on a full-size canvas
        canvas = Image.new("RGBA", expected, (0, 0, 0, 0))
        canvas.paste(base, (0, 0))
        base = canvas
    if region:
        rx, ry, rw, rh = region
        base = base.crop((rx * tw, ry * th, (rx + rw) * tw, (ry + rh) * th))
    else:
        rx, ry, rw, rh = 0, 0, m.width, m.height

    # checker background so empty cells are visible
    bg = Image.new("RGBA", base.size, (40, 40, 48, 255))
    bd = ImageDraw.Draw(bg)
    for cy in range(rh):
        for cx in range(rw):
            if (cx + cy) % 2:
                bd.rectangle([cx * tw, cy * th, (cx + 1) * tw - 1, (cy + 1) * th - 1], fill=(52, 52, 60, 255))
    img = Image.alpha_composite(bg, base)

    margin = 28 if grid else 0
    footer = []
    if debug:
        footer.append("layers (bottom to top): " + ", ".join(
            f"{l['name']}[{'tile' if l['type'] == 'tilelayer' else 'obj'}]" for l in m.layers))
    foot_h = 18 * len(footer) + (6 if footer else 0)
    canvas = Image.new("RGBA", (img.width + margin, img.height + margin + foot_h), (20, 20, 24, 255))
    canvas.paste(img, (margin, margin))
    over = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)

    def cell_px(cx, cy):
        return margin + (cx - rx) * tw, margin + (cy - ry) * th

    if debug:
        for layer in m.tile_layers():
            data = layer["data"]
            for cy in range(ry, ry + rh):
                for cx in range(rx, rx + rw):
                    gid = data[cy * m.width + cx]
                    if not gid:
                        continue
                    ts = m.tileset_for_gid(gid)
                    if ts is None:
                        continue
                    ox, oy = cell_px(cx, cy)
                    for s in ts.collision_shapes((gid & ~FLIP_MASK) - ts.firstgid):
                        sx, sy = s.get("x", 0), s.get("y", 0)
                        col = (255, 40, 40, 110)
                        if "polygon" in s:
                            pts = [(ox + (sx + p["x"]) * scale, oy + (sy + p["y"]) * scale) for p in s["polygon"]]
                            d.polygon(pts, fill=col, outline=(255, 80, 80, 255))
                        elif s.get("ellipse"):
                            d.ellipse([ox + sx * scale, oy + sy * scale, ox + (sx + s["width"]) * scale,
                                       oy + (sy + s["height"]) * scale], fill=col, outline=(255, 80, 80, 255))
                        else:
                            d.rectangle([ox + sx * scale, oy + sy * scale, ox + (sx + s.get("width", 0)) * scale - 1,
                                         oy + (sy + s.get("height", 0)) * scale - 1], fill=col, outline=(255, 80, 80, 255))

    if grid:
        gf = font(max(9, min(13, tw // 2 + 4)))
        line = (255, 255, 255, 70)
        for cx in range(rx, rx + rw + 1):
            if cx % grid == 0:
                x = margin + (cx - rx) * tw
                d.line([(x, margin), (x, margin + rh * th)], fill=line)
                if cx < rx + rw:
                    d.text((x + 2, 2), str(cx), font=gf, fill=(255, 255, 140, 255))
        for cy in range(ry, ry + rh + 1):
            if cy % grid == 0:
                y = margin + (cy - ry) * th
                d.line([(margin, y), (margin + rw * tw, y)], fill=line)
                if cy < ry + rh:
                    d.text((2, y + 2), str(cy), font=gf, fill=(255, 255, 140, 255))

    if debug:
        of = font(12)
        colors = [(80, 200, 255), (255, 200, 60), (120, 255, 120), (255, 120, 220), (255, 160, 80)]
        n = 0
        for layer in m.layers:
            if layer["type"] != "objectgroup":
                continue
            c = colors[n % len(colors)]
            n += 1
            for o in layer["objects"]:
                px = margin + (o["x"] - rx * m.tilew) * scale
                py = margin + (o["y"] - ry * m.tileh) * scale
                if not (margin <= px <= canvas.width and margin <= py <= margin + rh * th):
                    continue
                ow, oh = o.get("width", 0) * scale, o.get("height", 0) * scale
                if o.get("polyline"):
                    pl = [(px + q["x"] * scale, py + q["y"] * scale) for q in o["polyline"]]
                    d.line(pl, fill=c + (255,), width=2)
                    for vx, vy in pl[1:]:
                        d.ellipse([vx - 3, vy - 3, vx + 3, vy + 3], outline=c + (255,), width=1)
                if ow and oh and not o.get("point"):
                    d.rectangle([px, py, px + ow, py + oh], outline=c + (255,), width=2)
                r = max(3, scale * 2)
                d.ellipse([px - r, py - r, px + r, py + r], fill=c + (200,), outline=(0, 0, 0, 255))
                label = o["name"] or o.get("type") or "?"
                if o.get("type") and o["name"]:
                    label += f" ({o['type']})"
                text_outlined(d, (px + r + 2, py - 6), label, of, c + (255,))
        ff = font(13)
        for i, t in enumerate(footer):
            d.text((6, margin + img.height + 4 + 18 * i), t, font=ff, fill=(230, 230, 230, 255))

    out_img = Image.alpha_composite(canvas, over).convert("RGB")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    out_img.save(out)
    return out_img.size


def contact_sheet(ts, out, scale=4, cols=None):
    img_path = ts.image_path()
    if not img_path or not os.path.isfile(img_path):
        raise MapError(f"tileset image not found: {img_path}")
    sheet = Image.open(img_path).convert("RGBA")
    columns = ts.columns or (sheet.width // ts.tilew)
    rows = (ts.tilecount + columns - 1) // columns
    tw, th = ts.tilew * scale, ts.tileh * scale
    pad = 2
    W, H = columns * (tw + pad) + pad, rows * (th + pad) + pad
    canvas = Image.new("RGBA", (W, H), (30, 30, 36, 255))
    d = ImageDraw.Draw(canvas)
    f = font(max(9, scale * 3))
    for tid in range(ts.tilecount):
        cx, cy = tid % columns, tid // columns
        x, y = pad + cx * (tw + pad), pad + cy * (th + pad)
        for yy in range(th // 8):
            for xx in range(tw // 8):
                if (xx + yy) % 2:
                    d.rectangle([x + xx * 8, y + yy * 8, x + xx * 8 + 7, y + yy * 8 + 7], fill=(44, 44, 52, 255))
        tile = sheet.crop((cx * ts.tilew, cy * ts.tileh, (cx + 1) * ts.tilew, (cy + 1) * ts.tileh))
        tile = tile.resize((tw, th), Image.NEAREST)
        canvas.alpha_composite(tile, (x, y))
        entry = ts.tile_entry(tid)
        has_col = ts.has_collision(tid)
        if has_col:
            d.rectangle([x, y, x + tw - 1, y + th - 1], outline=(255, 50, 50, 255), width=2)
        meta = entry and (entry.get("type") or entry.get("class") or entry.get("properties"))
        text_outlined(d, (x + 2, y + 1), str(tid), f, (255, 230, 80, 255) if meta else (255, 255, 255, 255))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    canvas.convert("RGB").save(out)
    return canvas.size
