"""Generation building blocks without any model: layouts, block-out, canvas, mask, scale, previews, palette.

Everything here uses Pillow only, so it runs (and is tested) with the mise python."""
import os

from PIL import Image, ImageDraw

from common import TILE, SceneError, parse_colour, sha
from compose import composite_image, tile_layers

BG = (127, 127, 127)          # canvas colour of empty cells (the model needs RGB)
KEY = (255, 0, 255)           # flat key colour for --alpha layers
MIN_SCALE, MAX_SCALE, MAX_SIDE = 2, 8, 1024
TEXTURES = {"planks", "wall", "none"}


# --------------------------------------------------------------------------- layout

def material_chars(materials):
    """char -> material name. A material without 'char' can still be used from a PNG layout or a '@ X = name' line."""
    out = {}
    for name, m in materials.items():
        c = m.get("char")
        if c:
            if len(c) != 1:
                raise SceneError(f"material '{name}': char must be one character, got '{c}'", "bad_input")
            if c in out:
                raise SceneError(f"materials '{out[c]}' and '{name}' both use the char '{c}'", "bad_input")
            out[c] = name
    return out


def legend_material(ln, line, toks, materials):
    """'wall #ddd5c4 texture=none' -> a per-job variant of material 'wall' with another block-out colour / texture.

    The variant is added to `materials` (the caller's per-job copy) as 'wall@ddd5c4/none' with "base": "wall"; it keeps
    the base material's shape, hint and layer, and is written to the map as the base material. materials.json is never
    touched. Plain 'name' returns the name unchanged."""
    name, over = toks[0], toks[1:]
    if not over:
        return name
    spec = dict(materials[name])
    key = name
    for t in over:
        if t.startswith("texture="):
            tex = t[len("texture="):]
            if tex not in TEXTURES:
                raise SceneError(f"layout line {ln}: unknown texture '{tex}' in '{line}' (use {', '.join(sorted(TEXTURES))})",
                                 "bad_input")
            spec["texture"] = tex
            key += f"/{tex}"
        else:
            try:
                r, g, b = parse_colour(t)[:3]
            except Exception:
                raise SceneError(f"layout line {ln}: '{t}' in '{line}' is neither a colour (#rrggbb) nor texture=NAME",
                                 "bad_input")
            spec["colour"] = "#%02x%02x%02x" % (r, g, b)
            key += "@%02x%02x%02x" % (r, g, b)
    spec["base"] = name
    materials[key] = spec
    return key


def base_material(name, materials):
    """Material name that is written to the map for a layout material (variants map back to their base)."""
    return materials[name].get("base", name)


def parse_layout_text(text, rw, rh, materials):
    """Text grid -> rows of material names (None = keep the current pixels). One character per cell.

    Lines starting with '@' add legend entries ('@ X = wall', or with a per-job colour / texture override:
    '@ X = wall #ddd5c4 texture=none'; the override variants are added to `materials`); blank lines and lines starting with '//' are skipped.
    ' ' and '_' mean "no block-out: keep what is there". Rows must be exactly rw wide, rh tall."""
    chars = material_chars(materials)
    rows = []
    for ln, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r\n")
        if line.startswith("@"):
            lhs, _, rhs = line[1:].partition("=")
            c, toks = lhs.strip(), rhs.split()
            if len(c) != 1 or not toks or toks[0] not in materials:
                raise SceneError(f"layout line {ln}: bad legend '{line}' (use '@ X = material [#rrggbb] [texture=planks|wall|none]'; "
                                 f"known: {sorted(materials)})", "bad_input")
            chars[c] = legend_material(ln, line, toks, materials)
        elif line.strip() and not line.startswith("//"):
            rows.append((ln, line))
    if len(rows) != rh:
        raise SceneError(f"layout has {len(rows)} row(s), the region is {rh} cells tall", "bad_input")
    grid = []
    for ln, line in rows:
        if len(line) != rw:
            raise SceneError(f"layout line {ln} is {len(line)} wide, the region is {rw} cells wide", "bad_input")
        row = []
        for c in line:
            if c in " _":
                row.append(None)
            elif c in chars:
                row.append(chars[c])
            else:
                raise SceneError(f"layout line {ln}: character '{c}' is not in the legend "
                                 f"({', '.join(f'{k}={v}' for k, v in sorted(chars.items()))}, space = keep)", "bad_input")
        grid.append(row)
    return grid


def parse_layout_png(path, rw, rh, materials):
    """One pixel per cell; the pixel colour must equal a material's block-out colour. Transparent = keep."""
    im = Image.open(path).convert("RGBA")
    if im.size != (rw, rh):
        raise SceneError(f"layout PNG is {im.size[0]}x{im.size[1]}, the region is {rw}x{rh} cells (one pixel per cell)",
                         "bad_input")
    by_colour = {parse_colour(m["colour"])[:3]: n for n, m in materials.items() if m.get("colour")}
    grid = []
    for y in range(rh):
        row = []
        for x in range(rw):
            r, g, b, a = im.getpixel((x, y))
            if a < 128:
                row.append(None)
            elif (r, g, b) in by_colour:
                row.append(by_colour[(r, g, b)])
            else:
                raise SceneError(f"layout PNG pixel ({x},{y}) is #{r:02x}{g:02x}{b:02x}, which is no material colour "
                                 f"({', '.join(f'{n}={m.get('colour')}' for n, m in materials.items())})", "bad_input")
        grid.append(row)
    return grid


def load_layout(path, rw, rh, materials):
    if not os.path.isfile(path):
        raise SceneError(f"layout not found: {path}", "not_found")
    if path.lower().endswith(".png"):
        return parse_layout_png(path, rw, rh, materials), sha(open(path, "rb").read())
    data = open(path, "rb").read()
    return parse_layout_text(data.decode("utf-8"), rw, rh, materials), sha(data)


def load_init(path, rw, rh):
    """--init PNG: the block-out canvas of the region, exactly (rw*16) x (rh*16) pixels, RGBA (transparent = keep)."""
    if not os.path.isfile(path):
        raise SceneError(f"--init image not found: {path}", "not_found")
    im = Image.open(path).convert("RGBA")
    if im.size != (rw * TILE, rh * TILE):
        raise SceneError(f"--init image is {im.size[0]}x{im.size[1]}, the region is {rw * TILE}x{rh * TILE} px "
                         f"({rw}x{rh} cells at 16 px)", "bad_input")
    return im


def blockout_tile(material, materials):
    c = materials[material].get("colour")
    if not c:
        raise SceneError(f"material '{material}' has no block-out colour in materials.json", "bad_input")
    return Image.new("RGBA", (TILE, TILE), parse_colour(c))


def shade(rgb, f):
    return tuple(max(0, min(255, int(round(c * f)))) for c in rgb[:3]) + (255,)


def blockout_region(layout, region, materials):
    """Block-out of a whole layout as an RGBA image of the region (transparent where the layout says 'keep').

    Each material is a flat colour; an optional "texture" in materials.json adds structure the model can refine
    instead of inventing it (it keeps the layout and perspective better at strength < 1):
    - "planks": horizontal boards 4 px tall with staggered end joints (drawn from absolute map pixels, so they run
      on across cells and regions),
    - "wall": a 3/4 front face: lit top lip where the wall starts, a dark baseboard where it ends,
    - "none" / missing: flat."""
    rx, ry, rw, rh = region
    img = Image.new("RGBA", (rw * TILE, rh * TILE), (0, 0, 0, 0))
    px = img.load()
    for j in range(rh):
        for i in range(rw):
            mat = layout[j][i]
            if not mat:
                continue
            spec = materials[mat]
            base = parse_colour(spec["colour"])
            tex = spec.get("texture", "none")
            above = layout[j - 1][i] if j > 0 else None
            below = layout[j + 1][i] if j + 1 < rh else None
            for y in range(TILE):
                for x in range(TILE):
                    ax, ay = (rx + i) * TILE + x, (ry + j) * TILE + y
                    c = base
                    if tex == "planks":
                        band = ay // 4
                        if ay % 4 == 3:
                            c = shade(base, 0.74)
                        elif ay % 4 == 0:
                            c = shade(base, 1.07)
                        elif (ax + band * 11) % 32 == 0:
                            c = shade(base, 0.74)
                    elif tex == "wall":
                        if above != mat and y < 2:
                            c = shade(base, 1.28 if y == 0 else 1.12)
                        elif below != mat and y >= TILE - 4:
                            c = shade(base, 0.58 if y == TILE - 4 else 0.75)
                    px[x + i * TILE, y + j * TILE] = c
    return img


def layout_hints(grid, materials):
    """Prompt hints of the materials a layout uses, most frequent first."""
    count = {}
    for row in grid:
        for m in row:
            if m:
                count[m] = count.get(m, 0) + 1
    out = []
    for m, _n in sorted(count.items(), key=lambda kv: -kv[1]):
        h = materials[m].get("hint")
        if h and h not in out:
            out.append(h)
    return out


# --------------------------------------------------------------------------- geometry

def bbox_of(cells):
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


def pick_scale(rw_px, rh_px, requested="auto"):
    """Integer upscale S for a canvas of rw_px x rh_px game pixels. auto = largest S in 2..8 with the long side <= 1024.

    Every canvas side is a multiple of 16 (whole cells), so S*side is a multiple of 16 for any integer S."""
    long_side = max(rw_px, rh_px)
    if requested in (None, "auto"):
        s = min(MAX_SCALE, MAX_SIDE // long_side)
        return s if s >= MIN_SCALE else None
    s = int(requested)
    if s < 1 or s > MAX_SCALE:
        raise SceneError(f"--scale must be an integer 1..{MAX_SCALE} or auto, got {requested}", "bad_input")
    if s * long_side > MAX_SIDE:
        raise SceneError(f"scale {s} makes the canvas {s * long_side}px on its long side (max {MAX_SIDE}); "
                         f"use a smaller --scale or split the region", "too_large")
    return s


def fit_box(map_w, map_h, region, ring, requested_scale="auto"):
    """Canvas box = region + `ring` context cells, clipped to the map. If it is too big for scale >= 2 the ring shrinks
    (down to 0); a region that alone does not fit is refused. Returns (box, ring_used, scale)."""
    rx, ry, rw, rh = region
    for k in range(ring, -1, -1):
        x0, y0 = max(0, rx - k), max(0, ry - k)
        x1, y1 = min(map_w, rx + rw + k), min(map_h, ry + rh + k)
        box = (x0, y0, x1 - x0, y1 - y0)
        s = pick_scale(box[2] * TILE, box[3] * TILE, requested_scale)
        if s is not None:
            return box, k, s
    raise SceneError(f"the region {rw}x{rh} cells ({rw * TILE}x{rh * TILE} px) does not fit the model canvas at scale 2 "
                     f"(max {MAX_SIDE // MIN_SCALE}px = {MAX_SIDE // MIN_SCALE // TILE} cells per side); split it into smaller regions",
                     "too_large")


# --------------------------------------------------------------------------- canvas

class Canvas:
    """The model input: `image` (RGB, scaled), `mask` (L, white = repaint), and the 1x pieces needed to cut results."""

    def __init__(self, box, scale, region, cells, base, image, mask, ring):
        self.box, self.scale, self.region, self.cells, self.base, self.image, self.mask, self.ring = \
            box, scale, region, cells, base, image, mask, ring


COMPOSE_MODES = ("below", "none", "all")


def compose_layers(m, layer, compose="below"):
    """Visible tile layers the canvas shows around the region: below (default) = up to and including `layer`; none = only
    `layer`; all = every visible tile layer (plus `layer`)."""
    if compose not in COMPOSE_MODES:
        raise SceneError(f"--compose must be one of {', '.join(COMPOSE_MODES)}, got '{compose}'", "bad_input")
    idx = m.layers.index(layer)
    if compose == "none":
        return [layer]
    layers = [l for l in tile_layers(m) if compose == "all" or m.layers.index(l) <= idx]
    if layer not in layers:
        layers.append(layer)
        layers.sort(key=lambda l: m.layers.index(l))
    return layers


def build_canvas(sc, m, layer, cells, region, layout, ring, scale="auto", alpha=False, compose="below", init=None,
                 materials=None):
    """Composite the layers up to and including `layer` around `cells`, draw the block-out inside the region, scale
    by an integer with nearest neighbour and make the mask.

    `cells`: set of (x, y) to regenerate. `region`: bounding box (x, y, w, h) of `cells`. `layout`: rows of material
    names for `region` (or None). The block-out replaces the pixels of region cells it names (they are repainted
    anyway); cells without a layout entry keep their current pixels. Empty pixels become grey (or the key colour for
    --alpha)."""
    from common import load_materials
    materials = materials if materials is not None else load_materials()
    box, ring_used, s = fit_box(m.width, m.height, region, ring, scale)
    bx, by, bw, bh = box
    layers = compose_layers(m, layer, compose)
    base = composite_image(sc, m, layers, box)
    rx, ry, _rw, _rh = region
    flat = Image.new("RGBA", base.size, KEY + (255,) if alpha else BG + (255,))
    work = base.copy()
    if layout is not None:
        bo = blockout_region(layout, region, materials)
        for j, row in enumerate(layout):
            for i, mat in enumerate(row):
                x, y = rx + i, ry + j
                if mat and (x, y) in cells:
                    work.paste(bo.crop((i * TILE, j * TILE, (i + 1) * TILE, (j + 1) * TILE)),
                               ((x - bx) * TILE, (y - by) * TILE))
    if init is not None:
        # --init: a block-out image (region size, RGBA); its opaque pixels replace the region's pixels on the canvas only
        for (x, y) in cells:
            ix, iy = (x - rx) * TILE, (y - ry) * TILE
            piece = init.crop((ix, iy, ix + TILE, iy + TILE))
            if piece.getchannel("A").getbbox() is None:
                continue
            cx, cy = (x - bx) * TILE, (y - by) * TILE
            tile = work.crop((cx, cy, cx + TILE, cy + TILE))
            work.paste(Image.alpha_composite(tile, piece), (cx, cy))
    if layout is None and not alpha:
        work = smear_fill(work, box, cells)
    img = Image.alpha_composite(flat, work).convert("RGB")
    img = img.resize((img.width * s, img.height * s), Image.NEAREST)
    mask = Image.new("L", (bw * TILE, bh * TILE), 0)
    d = ImageDraw.Draw(mask)
    for (x, y) in cells:
        px, py = (x - bx) * TILE, (y - by) * TILE
        d.rectangle((px, py, px + TILE - 1, py + TILE - 1), fill=255)
    mask = mask.resize((mask.width * s, mask.height * s), Image.NEAREST)
    return Canvas(box, s, region, set(cells), base, img, mask, ring_used)


def smear_fill(img, box, cells):
    """Give empty pixels of the cells to regenerate a plausible start: copy the nearest opaque pixel on the same row
    (left first, then right, then up/down). An img2img start that already looks like the surroundings is far better
    than flat grey (at strength 1.0 the model otherwise paints something unrelated into the hole)."""
    bx, by = box[0], box[1]
    out = img.copy()
    px, src = out.load(), img.load()
    W, H = img.size
    for (x, y) in cells:
        for yy in range((y - by) * TILE, (y - by + 1) * TILE):
            for xx in range((x - bx) * TILE, (x - bx + 1) * TILE):
                if src[xx, yy][3]:
                    continue
                found = None
                for dx in range(1, W):
                    for sx in (xx - dx, xx + dx):
                        if 0 <= sx < W and src[sx, yy][3]:
                            found = src[sx, yy]
                            break
                    if found:
                        break
                if found:
                    px[xx, yy] = found
    return out


def cut_cells(snapped, box, cells):
    """Cut a 1x snapped canvas into 16x16 cells -> {(x, y): RGBA image}."""
    bx, by, bw, bh = box
    if snapped.size != (bw * TILE, bh * TILE):
        raise SceneError(f"snapped canvas is {snapped.size}, expected {(bw * TILE, bh * TILE)}", "error")
    return {(x, y): snapped.crop(((x - bx) * TILE, (y - by) * TILE, (x - bx + 1) * TILE, (y - by + 1) * TILE))
            for (x, y) in cells}


def region_image(cells_img, region, cells):
    """Candidate image of the region box: the generated cells, everything else transparent."""
    rx, ry, rw, rh = region
    out = Image.new("RGBA", (rw * TILE, rh * TILE), (0, 0, 0, 0))
    for (x, y) in cells:
        out.paste(cells_img[(x, y)], ((x - rx) * TILE, (y - ry) * TILE))
    return out


# --------------------------------------------------------------------------- palette

def scene_palette(sc, m, exclude_cells, limit=96, min_colours=8):
    """Colours of the visible map layers outside `exclude_cells`, most frequent first (at most `limit`).
    Returns [] when the map has fewer than `min_colours` of them (an empty map: use an adaptive palette instead)."""
    full = composite_image(sc, m, tile_layers(m))
    px = full.load()
    for (x, y) in exclude_cells:
        for yy in range(y * TILE, y * TILE + TILE):
            for xx in range(x * TILE, x * TILE + TILE):
                px[xx, yy] = (0, 0, 0, 0)
    counts = {}
    for p in full.getdata():
        if p[3] == 255:
            counts[p[:3]] = counts.get(p[:3], 0) + 1
    if len(counts) < min_colours:
        return []
    return [c for c, _n in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]


def write_hex(path, colours):
    with open(path, "w") as f:
        for r, g, b in colours:
            f.write(f"{r:02x}{g:02x}{b:02x}\n")


def read_hex(path):
    out = []
    with open(path) as f:
        for line in f:
            h = line.strip().lstrip("#")[:6]
            if len(h) == 6 and not line.startswith((";", "//")):
                out.append((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
    return out


def image_colours(img):
    """Set of RGB colours of the opaque pixels."""
    im = img.convert("RGBA")
    return {im.getpixel((x, y))[:3] for y in range(im.height) for x in range(im.width) if im.getpixel((x, y))[3] == 255}


# --------------------------------------------------------------------------- previews

def draw_grid(img, step, colour=(255, 255, 255, 60)):
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for x in range(0, img.width, step):
        d.line((x, 0, x, img.height), fill=colour)
    for y in range(0, img.height, step):
        d.line((0, y, img.width, y), fill=colour)
    return Image.alpha_composite(img.convert("RGBA"), ov)


def outline_cells(img, box, cells, zoom, colour=(255, 220, 0, 255)):
    """Outline the edge of the cell set (edges between a member and a non-member cell)."""
    bx, by, _bw, _bh = box
    d = ImageDraw.Draw(img)
    step = TILE * zoom
    for (x, y) in cells:
        px, py = (x - bx) * step, (y - by) * step
        for dx, dy, line in ((0, -1, (px, py, px + step - 1, py)), (0, 1, (px, py + step - 1, px + step - 1, py + step - 1)),
                             (-1, 0, (px, py, px, py + step - 1)), (1, 0, (px + step - 1, py, px + step - 1, py + step - 1))):
            if (x + dx, y + dy) not in cells:
                d.line(line, fill=colour, width=2)
    return img


def preview_image(base, box, region_cells_img, cells, zoom=4, label=None):
    """Before | after at `zoom`x with a 16-px cell grid and the generated cells outlined in yellow.
    `base`: 1x composite of the box before; `region_cells_img`: {(x, y): 16x16} the new cells."""
    after = base.copy()
    bx, by = box[0], box[1]
    for (x, y), tile in region_cells_img.items():
        after.paste(tile, ((x - bx) * TILE, (y - by) * TILE))
    # checker under transparency so empty cells are visible
    def show(im):
        bgc = Image.new("RGBA", im.size, (60, 60, 60, 255))
        for yy in range(0, im.height, 8):
            for xx in range(0, im.width, 8):
                if (xx // 8 + yy // 8) % 2:
                    ImageDraw.Draw(bgc).rectangle((xx, yy, xx + 7, yy + 7), fill=(84, 84, 84, 255))
        z = Image.alpha_composite(bgc, im.convert("RGBA")).resize((im.width * zoom, im.height * zoom), Image.NEAREST)
        z = draw_grid(z, TILE * zoom)
        return outline_cells(z, box, set(cells), zoom)
    b, a = show(base), show(after)
    gap = 12
    out = Image.new("RGBA", (b.width + gap + a.width, b.height + 14), (20, 20, 20, 255))
    out.paste(b, (0, 14))
    out.paste(a, (b.width + gap, 14))
    d = ImageDraw.Draw(out)
    d.text((2, 1), "before", fill=(255, 255, 255, 255))
    d.text((b.width + gap + 2, 1), "after" + (f"  {label}" if label else ""), fill=(255, 255, 255, 255))
    return out
