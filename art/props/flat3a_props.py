#!/usr/bin/env python3
"""Hand-drawn props for Samantha's flat (3A) in route1_flat, drawn with Pillow.

Reproducible (no image model): run
    python3 art/props/flat3a_props.py --out DIR
and stamp the PNGs with `tools/scenekit/scene.py edit ... paste` on the Decor layer.
Style of the scene: 3/4 top-down (front + top), 1 px dark outline, flat two-tone shading,
colours only from art/palettes/interior.hex. One art px = one map px (48 px tiles).

Outputs (size, intended top-left map px in route1_flat, paste order):
  chair_north.png  48x144  at (216,1296)  first  (backrest peeks over the table, seat tucked behind it)
  table.png        96x96   at (192,1392)  second (2x2 tiles, cols 4-5 rows 29-30)
  chair_south.png  48x96   at (216,1440)  third  (seen from behind, in front of the table)
  bookshelf.png    96x192  at (528,1104)  any    (cols 11-12, bottom on floor row 26)
"""
import argparse
import os
import random

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
PALETTE_FILE = os.path.join(HERE, "..", "palettes", "interior.hex")

OUT = "#1c1a1f"       # outline
WD0 = "#3a2a1a"       # deepest wood shadow
WD1 = "#4a3426"       # wood shadow
WD2 = "#5a3b20"
WD3 = "#7a5230"       # wood mid
WD4 = "#8a6d4b"
WD5 = "#a07a50"       # table top
WD6 = "#b88a5a"       # wood light
WD7 = "#c99a66"       # highlight
CREAM = "#f0ebe0"
CREAM_S = "#c4baa6"
CREAM_M = "#ddd5c4"
GREEN = "#6d8b74"
GREEN_L = "#9bb59e"
STEEL = "#a4a9b8"
BOOKS = ["#8c4a3a", "#6d8b74", "#3b3e4f", "#5b5f73", "#c8b08a", "#e3c9a0", "#9bb59e", "#7b8095", "#ddd5c4"]


def load_palette():
    with open(PALETTE_FILE) as f:
        return {"#" + l.strip().lower() for l in f if l.strip()}


def box(d, x0, y0, x1, y1, fill, outline=OUT):
    """Filled rectangle with a 1 px outline; coordinates inclusive."""
    d.rectangle([x0, y0, x1, y1], fill=outline)
    if x1 - x0 >= 2 and y1 - y0 >= 2:
        d.rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], fill=fill)


def table():
    im = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    L, R = 8, 87
    # back legs (short stubs under the apron, inset)
    for x in (14, 77):
        box(d, x, 50, x + 4, 60, WD1)
    # front legs
    for x in (L + 2, R - 8):
        box(d, x, 50, x + 6, 94, WD3)
        d.line([x + 1, 52, x + 1, 92], fill=WD6)         # lit left edge
        d.line([x + 5, 52, x + 5, 93], fill=WD2)         # shadow right edge
    # apron (front face of the top)
    box(d, L, 42, R, 52, WD3)
    d.line([L + 1, 43, R - 1, 43], fill=WD4)
    d.line([L + 1, 51, R - 1, 51], fill=WD2)
    # top surface
    box(d, L, 8, R, 43, WD5)
    d.rectangle([L + 1, 9, R - 1, 10], fill=WD6)         # lit back edge
    for y, x0, x1 in ((17, 14, 40), (25, 52, 80), (33, 18, 30), (36, 60, 76)):
        d.line([x0, y, x1, y], fill=WD4)                 # grain
    d.line([L + 1, 41, R - 1, 41], fill=WD4)              # shade toward the front
    # two place settings (north and south) + a small vase
    for cy in (17, 34):
        d.ellipse([36, cy - 4, 59, cy + 4], fill=OUT)
        d.ellipse([37, cy - 3, 58, cy + 3], fill=CREAM)
        d.ellipse([41, cy - 2, 54, cy + 2], fill=CREAM_M)
        d.line([62, cy - 3, 62, cy + 3], fill=STEEL)      # knife
        d.line([33, cy - 3, 33, cy + 3], fill=STEEL)      # fork
    box(d, 70, 20, 75, 29, GREEN)                         # vase
    d.line([71, 21, 71, 28], fill=GREEN_L)
    d.point([(72, 18), (74, 17), (71, 17)], fill="#8c4a3a")
    d.point([(73, 19)], fill=GREEN)
    return im


def chair_back(d, x0, y0, w, h, fill=WD3, light=WD6, dark=WD2):
    """Backrest: two posts + two rails, seen from the front or behind."""
    x1 = x0 + w - 1
    box(d, x0, y0, x0 + 4, y0 + h, fill)
    box(d, x1 - 4, y0, x1, y0 + h, fill)
    box(d, x0, y0, x1, y0 + 8, fill)                      # top rail
    d.line([x0 + 1, y0 + 1, x1 - 1, y0 + 1], fill=light)
    d.line([x0 + 1, y0 + 7, x1 - 1, y0 + 7], fill=dark)
    box(d, x0 + 4, y0 + 18, x1 - 4, y0 + 22, fill)        # middle rail
    d.line([x0 + 1, y0 + 9, x0 + 1, y0 + h - 1], fill=light)
    d.line([x1 - 1, y0 + 9, x1 - 1, y0 + h - 1], fill=dark)


def chair_north():
    """Chair behind the table, facing the viewer. Bottom part is hidden by the table (pasted later)."""
    im = Image.new("RGBA", (48, 144), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx0, w = 6, 36
    # backrest (from local y 52 = map 1348) down to the seat
    chair_back(d, cx0, 52, w, 38)
    # seat top (cushion) + front edge, mostly behind the table top
    box(d, cx0 - 1, 86, cx0 + w, 100, GREEN)
    d.line([cx0, 87, cx0 + w - 1, 87], fill=GREEN_L)
    box(d, cx0 - 1, 100, cx0 + w, 105, WD3)
    for x in (cx0, cx0 + w - 5):                          # front legs (hidden by the table)
        box(d, x, 105, x + 4, 130, WD3)
    return im


def chair_south():
    """Chair in front of the table, seen from behind (backrest toward the viewer)."""
    im = Image.new("RGBA", (48, 96), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx0, w = 6, 36
    x1 = cx0 + w - 1
    # back legs (near the viewer) and front legs (far, shorter)
    for x in (cx0 + 3, x1 - 7):
        box(d, x, 60, x + 4, 84, WD2)
    # seat seen from above, behind the backrest
    box(d, cx0 - 1, 52, x1 + 1, 66, GREEN)
    d.line([cx0, 53, x1, 53], fill=GREEN_L)
    box(d, cx0 - 1, 66, x1 + 1, 71, WD3)
    d.line([cx0, 70, x1, 70], fill=WD2)
    # rear legs down to the floor (local 94 = map 1534)
    for x in (cx0, x1 - 4):
        box(d, x, 71, x + 4, 94, WD3)
        d.line([x + 1, 72, x + 1, 92], fill=WD6)
    # backrest rising from the seat's back edge
    chair_back(d, cx0, 22, w, 49)
    return im


def bookshelf(seed=3):
    im = Image.new("RGBA", (96, 192), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rnd = random.Random(seed)
    L, R = 6, 89
    top0, top1, bot = 34, 48, 186
    # top face
    box(d, L + 3, top0, R - 3, top1, WD4)
    d.polygon([(L, top1), (L + 3, top0), (L + 3, top1)], fill=OUT)
    d.polygon([(R, top1), (R - 3, top0), (R - 3, top1)], fill=OUT)
    d.line([L + 4, top0 + 1, R - 4, top0 + 1], fill=WD6)
    # a plant and a small box on top
    box(d, 66, 22, 77, 36, "#8c4a3a")
    d.line([67, 23, 67, 35], fill="#c99a66")
    for (x, y) in ((64, 14), (70, 8), (76, 12), (80, 18), (61, 20), (72, 16)):
        d.ellipse([x - 3, y - 3, x + 4, y + 4], fill=OUT)
    for (x, y) in ((64, 14), (70, 8), (76, 12), (80, 18), (61, 20), (72, 16)):
        d.ellipse([x - 2, y - 2, x + 3, y + 3], fill=GREEN)
        d.point([(x - 1, y - 1)], fill=GREEN_L)
    box(d, 18, 28, 38, 36, CREAM_M)
    d.line([19, 29, 37, 29], fill=CREAM)
    # carcass front
    box(d, L, top1, R, bot, WD3)
    d.line([L + 1, top1 + 1, L + 1, bot - 1], fill=WD6)
    d.line([R - 1, top1 + 1, R - 1, bot - 1], fill=WD2)
    box(d, L, bot - 8, R, bot, WD2)                      # plinth
    # compartments: inner back panel + shelves
    ix0, ix1 = L + 5, R - 5
    shelves = [top1 + 5, top1 + 37, top1 + 69, top1 + 101]
    for i, sy in enumerate(shelves):
        y0, y1 = sy, sy + 26
        d.rectangle([ix0, y0, ix1, y1], fill=OUT)
        d.rectangle([ix0 + 1, y0 + 1, ix1 - 1, y1], fill=WD1)
        d.line([ix0 + 1, y0 + 1, ix1 - 1, y0 + 1], fill=WD0)   # shadow under the board above
        # books standing on the shelf (bottom at y1)
        x = ix0 + 2
        while x < ix1 - 3:
            if rnd.random() < 0.12 and x < ix1 - 14:          # a gap / leaning stack
                x += rnd.randint(4, 8)
                continue
            bw = rnd.randint(3, 6)
            bh = rnd.randint(14, 22)
            if x + bw > ix1 - 1:
                break
            c = rnd.choice(BOOKS)
            box(d, x, y1 - bh, x + bw, y1, c)
            if bw >= 4:
                d.line([x + 1, y1 - bh + 3, x + bw - 1, y1 - bh + 3], fill=CREAM_M)
            x += bw + 1
        # shelf board front
        box(d, ix0 - 1, y1 + 1, ix1 + 1, y1 + 5, WD4)
        d.line([ix0, y1 + 2, ix1, y1 + 2], fill=WD6)
    return im


def check_palette(im, pal, name):
    bad = {"#%02x%02x%02x" % p[:3] for p in (im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata()) if p[3]} - pal
    if bad:
        raise SystemExit(f"{name}: colours outside the palette: {sorted(bad)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="output directory for the PNGs")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    pal = load_palette()
    for name, fn in (("table", table), ("chair_north", chair_north), ("chair_south", chair_south),
                     ("bookshelf", bookshelf)):
        im = fn()
        check_palette(im, pal, name)
        p = os.path.join(a.out, name + ".png")
        im.save(p)
        print(p, im.size)


if __name__ == "__main__":
    main()
