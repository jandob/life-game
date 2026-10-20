#!/usr/bin/env python3
"""Hand-drawn props for "the second Thursday" in route1_flat, drawn with Pillow.

Reproducible (no image model): first export the 3A door as the reference for the shop door,
    python3 tools/scenekit/scene.py export assets/maps/route1_flat.tmj --region 7,22,4,5 --composite --out DIR/door3a.png
(must be taken from a map where the 3A door is unchanged), then run
    python3 art/props/thursday2_props.py --out DIR --door-ref DIR/door3a.png
and stamp the PNGs with `tools/scenekit/scene.py edit ... paste`.
Style of the scene: 3/4 top-down (front + top), 1 px dark outline, flat two-tone shading,
colours only from art/palettes/interior.hex (the shop door keeps the existing door's pixels).
One art px = one map px (48 px tiles).

Outputs (size, layer, intended top-left map px in route1_flat, paste mode):
  recycling_bag.png  48x80    Decor  (480,920)   over   landing, right of 3A's doormat (col 10, rows 19-20)
  chest_drawers.png  64x96    Decor  (316,176)   over   3B bedroom, north wall (cols 6-7, rows 3-5)
  moving_box.png     48x64    Decor  (96,560)    over   3B bedroom floor (col 2, rows 11-12)
  drying_rack.png    96x80    Decor  (432,544)   over   3B kitchen (cols 9-10, rows 11-12)
  notebook.png       24x24    Decor  (200,1404)  over   3A table, left of the plates
  shop_wall.png      480x192  Walls  (96,1680)   replace  shop wall face (cols 2-11, rows 35-38)
  shop_door.png      96x162   Walls  (144,1710)  over   after the wall (cols 3-4)
  shop_floor.png     480x384  Floor  (96,1872)   replace  shop lino (cols 2-11, rows 39-46)
  wine_shelf.png     144x176  Decor  (288,1728)  over   shop north wall (cols 6-8, rows 36-39)
  tulips.png         48x80    Decor  (96,2072)   over   shop, west wall (col 2, rows 43-44)
  choc_rack.png      48x104   Decor  (384,1960)  over   shop, left of the counter (col 8, rows 40-42)
  counter.png        144x128  Decor  (432,1936)  over   shop counter with till and sign (cols 9-11, rows 40-42)
"""
import argparse
import os
import random

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
PALETTE_FILE = os.path.join(HERE, "..", "palettes", "interior.hex")

OUT = "#1c1a1f"       # outline
INK = "#2a2a32"
WD0 = "#3a2a1a"
WD1 = "#4a3426"
WD2 = "#5a3b20"
WD3 = "#7a5230"
WD4 = "#8a6d4b"
WD5 = "#a07a50"
WD6 = "#b88a5a"
WD7 = "#c99a66"
CREAM = "#f0ebe0"
CREAM_M = "#ddd5c4"
CREAM_S = "#c4baa6"
STONE = "#a89e8c"
PAPER = "#d8d0bc"
KRAFT = "#c8b08a"
KRAFT_L = "#e3c9a0"
NAVY = "#3b3e4f"
SLATE = "#5b5f73"
GREY = "#7b8095"
STEEL = "#a4a9b8"
GREEN = "#6d8b74"
GREEN_L = "#9bb59e"
RUST = "#8c4a3a"


def load_palette():
    with open(PALETTE_FILE) as f:
        return {"#" + l.strip().lower() for l in f if l.strip()}


def new(w, h):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def box(d, x0, y0, x1, y1, fill, outline=OUT):
    """Filled rectangle with a 1 px outline; coordinates inclusive."""
    d.rectangle([x0, y0, x1, y1], fill=outline)
    if x1 - x0 >= 2 and y1 - y0 >= 2:
        d.rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], fill=fill)


def bottle(d, x, ybot, glass, label, hi, cap=RUST, h=22):
    """Wine bottle standing on ybot, 7 px wide body."""
    body_top = ybot - 13
    box(d, x, body_top, x + 6, ybot, glass)
    d.line([x + 1, body_top + 1, x + 1, ybot - 1], fill=hi)
    d.rectangle([x + 1, body_top + 5, x + 5, body_top + 9], fill=label)
    box(d, x + 2, ybot - h, x + 4, body_top, glass)        # neck
    d.rectangle([x + 2, ybot - h, x + 4, ybot - h + 2], fill=cap)


# --------------------------------------------------------------------------- landing

def recycling_bag():
    im, d = new(48, 80)
    # newspaper and a flattened carton peeking out at the back
    d.polygon([(8, 36), (18, 26), (24, 34), (14, 42)], fill=OUT)
    d.polygon([(10, 36), (18, 28), (22, 34), (14, 40)], fill=CREAM_M)
    d.line([(13, 35), (18, 30)], fill=STONE)
    d.line([(15, 37), (19, 33)], fill=STONE)
    box(d, 22, 28, 30, 40, KRAFT_L)
    # empty red-wine bottle, tilted, sticking out of the bag
    d.polygon([(25, 50), (34, 50), (38, 22), (30, 21)], fill=OUT)
    d.polygon([(27, 49), (33, 49), (36, 23), (31, 22)], fill=INK)
    d.line([(29, 47), (32, 25)], fill=SLATE)                  # glass highlight
    d.polygon([(30, 30), (35, 30), (34, 36), (29, 36)], fill=KRAFT_L)   # label
    d.point([(31, 32), (32, 33)], fill=RUST)
    d.polygon([(31, 22), (36, 22), (39, 5), (35, 4)], fill=OUT)        # neck
    d.line([(34, 20), (37, 6)], fill=INK)
    d.line([(35, 20), (38, 7)], fill=INK)
    d.polygon([(35, 4), (39, 5), (39, 10), (35, 9)], fill=RUST)       # foil
    # bag: dark inside, crumpled folded rim, front with handle slot, right side in shade
    box(d, 5, 38, 42, 44, WD2)
    d.polygon([(4, 43), (10, 40), (16, 43), (23, 40), (30, 43), (37, 40), (43, 43), (43, 49), (4, 49)], fill=OUT)
    d.polygon([(5, 44), (10, 42), (16, 45), (23, 42), (30, 45), (37, 42), (42, 44), (42, 48), (5, 48)], fill=KRAFT_L)
    box(d, 5, 48, 42, 77, KRAFT)
    d.rectangle([35, 49, 41, 76], fill=WD5)                    # side in shade
    d.line([6, 49, 6, 76], fill=KRAFT_L)
    d.line([34, 49, 34, 76], fill=WD6)                         # side fold
    box(d, 15, 51, 25, 54, WD2)                                # handle slot
    # recycling mark
    d.polygon([(20, 60), (25, 69), (15, 69)], outline=GREEN)
    d.point([(20, 64)], fill=GREEN)
    d.line([6, 76, 41, 76], fill=WD5)                          # ground contact
    return im


# --------------------------------------------------------------------------- 3B

def chest_drawers():
    im, d = new(64, 96)
    L, R = 2, 61
    # things on top: a small dish with keys and a framed photo leaning on the wall
    box(d, 40, 1, 52, 14, WD2)
    box(d, 42, 3, 50, 12, CREAM_M)
    d.rectangle([43, 7, 49, 11], fill=GREEN_L)
    d.point([(45, 5), (47, 6)], fill=STEEL)
    # top face (30 deep)
    box(d, L, 4 + 10, R, 34, WD5)
    d.line([L + 1, 15, R - 1, 15], fill=WD6)
    d.line([L + 1, 33, R - 1, 33], fill=WD4)
    d.ellipse([12, 20, 26, 27], fill=OUT)
    d.ellipse([13, 21, 25, 26], fill=CREAM)
    d.point([(17, 23), (20, 24)], fill=STEEL)                 # keys in the dish
    d.line([18, 23, 21, 23], fill=GREY)
    # carcass front
    box(d, L, 34, R, 92, WD3)
    d.line([L + 1, 35, L + 1, 91], fill=WD6)
    d.line([R - 1, 35, R - 1, 91], fill=WD2)
    # three drawers
    for i in range(3):
        y0 = 37 + i * 17
        box(d, L + 4, y0, R - 4, y0 + 14, WD4)
        d.line([L + 5, y0 + 1, R - 5, y0 + 1], fill=WD6)
        d.line([L + 5, y0 + 13, R - 5, y0 + 13], fill=WD2)
        for kx in (18, 44):
            box(d, kx, y0 + 6, kx + 3, y0 + 8, WD7)
    # plinth and feet
    d.rectangle([L + 1, 89, R - 1, 91], fill=WD1)
    box(d, L + 2, 91, L + 6, 95, WD1)
    box(d, R - 6, 91, R - 2, 95, WD1)
    return im


def moving_box():
    im, d = new(48, 64)
    L, R = 3, 45
    # top (flaps closed, taped) and front
    box(d, L, 26, R, 46, KRAFT)
    d.line([L + 1, 27, R - 1, 27], fill=KRAFT_L)
    d.line([L + 1, 36, R - 1, 36], fill=WD6)                  # flap seam
    box(d, L, 46, R, 62, WD5)
    d.line([L + 1, 47, R - 1, 47], fill=WD6)
    d.rectangle([R - 4, 47, R - 1, 61], fill=WD4)             # side in shade
    # tape across the seam and down the front
    d.rectangle([L + 1, 34, R - 1, 38], fill=WD7)
    d.line([L + 1, 34, R - 1, 34], fill=KRAFT_L)
    d.rectangle([21, 46, 26, 61], fill=WD7)
    d.line([21, 47, 21, 61], fill=KRAFT_L)
    # handwritten marker label on the front
    d.line([8, 51, 12, 50], fill=NAVY)
    d.line([12, 50, 14, 53], fill=NAVY)
    d.line([9, 55, 16, 55], fill=NAVY)
    d.point([(30, 51), (31, 50), (33, 52), (35, 51), (36, 53)], fill=NAVY)
    d.line([30, 56, 38, 55], fill=NAVY)
    # handle slot
    d.rectangle([30, 41, 38, 42], fill=WD2)
    return im


def drying_rack():
    im, d = new(96, 80)
    # back legs (behind everything)
    for (x0, x1) in ((10, 6), (84, 88)):
        d.line([x0, 22, x1, 76], fill=SLATE, width=2)
    # top frame: rails seen from above (between y 18 and 32)
    box(d, 4, 18, 91, 21, GREY)
    d.line([5, 19, 90, 19], fill=STEEL)
    for y in (23, 26, 29):
        d.line([6, y, 89, y], fill=STEEL)
        d.point([(6, y), (89, y)], fill=SLATE)
    box(d, 4, 31, 91, 33, GREY)
    d.line([5, 32, 90, 32], fill=STEEL)
    d.line([4, 18, 4, 33], fill=OUT)
    d.line([91, 18, 91, 33], fill=OUT)
    # laundry hanging over the front rails
    # towel (green with a light stripe)
    box(d, 12, 22, 34, 58, GREEN)
    d.line([13, 23, 13, 57], fill=GREEN_L)
    d.rectangle([13, 48, 33, 50], fill=GREEN_L)
    d.line([13, 33, 33, 33], fill=GREY)                       # rail over the towel
    # t-shirt (grey-blue)
    d.polygon([(40, 24), (66, 24), (70, 32), (64, 34), (64, 54), (42, 54), (42, 34), (36, 32)], fill=OUT)
    d.polygon([(41, 25), (65, 25), (68, 31), (63, 33), (63, 53), (43, 53), (43, 33), (38, 31)], fill=GREY)
    d.line([44, 34, 44, 52], fill=STEEL)
    d.line([62, 34, 62, 52], fill=SLATE)
    d.arc([48, 22, 58, 29], 0, 180, fill=SLATE)              # neckline
    # tea towel (cream with a rust stripe)
    box(d, 72, 22, 86, 48, CREAM_M)
    d.line([73, 23, 73, 47], fill=CREAM)
    d.rectangle([73, 40, 85, 41], fill=RUST)
    # front legs (in front of the laundry)
    for (x0, x1) in ((6, 2), (89, 93)):
        d.line([x0, 33, x1, 78], fill=OUT, width=3)
        d.line([x0, 34, x1, 77], fill=STEEL)
    # cross bar between the front legs
    d.line([5, 64, 90, 64], fill=OUT)
    d.line([5, 65, 90, 65], fill=GREY)
    return im


# --------------------------------------------------------------------------- 3A

def notebook():
    im, d = new(24, 24)
    # closed notebook (portrait), rust cover, elastic band, page edges
    box(d, 4, 4, 16, 20, RUST)
    d.line([5, 5, 5, 19], fill=WD2)                           # spine
    d.line([16, 5, 16, 20], fill=CREAM)                       # page edge
    d.line([5, 20, 16, 20], fill=CREAM)
    d.line([4, 21, 17, 21], fill=OUT)
    d.line([17, 5, 17, 21], fill=OUT)
    d.line([13, 4, 13, 20], fill=INK)                         # elastic band
    # pen lying diagonally next to it
    d.line([(19, 6), (21, 18)], fill=OUT, width=2)
    d.line([(19, 7), (20, 17)], fill=NAVY)
    d.point([(21, 19)], fill=STEEL)                            # nib
    d.point([(19, 6)], fill=STEEL)
    return im


# --------------------------------------------------------------------------- shop

def shop_wall():
    """Corner-shop wall face, 4 tiles high: mint paint above, white subway tiles below."""
    im, d = new(480, 192)
    d.rectangle([0, 0, 479, 1], fill=CREAM)                   # top lip
    d.line([0, 2, 479, 2], fill=CREAM_S)
    d.rectangle([0, 3, 479, 104], fill=GREEN_L)
    d.rectangle([0, 3, 479, 6], fill=GREEN)                   # shade under the lip
    # trim rail
    d.rectangle([0, 105, 479, 109], fill=STEEL)
    d.line([0, 105, 479, 105], fill=CREAM)
    d.line([0, 109, 479, 109], fill=GREY)
    # subway tiles 24x12, staggered by 12
    d.rectangle([0, 110, 479, 179], fill=CREAM)
    for r, y in enumerate(range(110, 180, 12)):
        d.line([0, y + 11, 479, y + 11], fill=CREAM_S)
        off = 0 if r % 2 == 0 else 12
        for x in range(off, 480 + 24, 24):
            d.line([x, y, x, y + 10], fill=CREAM_S)
    # baseboard
    d.rectangle([0, 180, 479, 191], fill=SLATE)
    d.line([0, 180, 479, 180], fill=GREY)
    d.line([0, 191, 479, 191], fill=NAVY)
    return im


def shop_floor():
    """Checkered lino, 24 px squares, with a contact shadow along the north wall."""
    im, d = new(480, 384)
    for y in range(0, 384, 24):
        for x in range(0, 480, 24):
            light = ((x // 24) + (y // 24)) % 2 == 0
            d.rectangle([x, y, x + 23, y + 23], fill=PAPER if light else STONE)
            if light:
                d.line([x, y, x + 23, y], fill=CREAM_M)
    d.rectangle([0, 0, 479, 3], fill=CREAM_S)                 # shadow under the baseboard
    d.line([0, 0, 479, 0], fill=GREY)
    return im


def shop_door(ref):
    """The existing flat door (frame + leaf), glazed in the upper half, with an OPEN card."""
    src = Image.open(ref).convert("RGBA")
    im = src.crop((48, 30, 144, 192))                          # 96x162: frame and leaf
    d = ImageDraw.Draw(im)
    # glass pane over the two upper panels and the stile between them
    x0, y0, x1, y1 = 24, 41, 72, 89
    box(d, x0, y0, x1, y1, STEEL)
    d.rectangle([x0 + 1, y0 + 30, x1 - 1, y1 - 1], fill=GREY)   # darker lower glass (reflection)
    for k in range(3):                                         # diagonal highlights
        xa = x0 + 6 + k * 14
        d.line([(xa, y0 + 18), (xa + 14, y0 + 2)], fill=CREAM)
    d.line([x0 + 1, y0 + 1, x1 - 1, y0 + 1], fill=SLATE)
    # OPEN card hanging on a string
    d.line([(44, y0 + 2), (40, y0 + 10)], fill=INK)
    d.line([(52, y0 + 2), (56, y0 + 10)], fill=INK)
    box(d, 36, y0 + 10, 60, y0 + 20, CREAM)
    for i, x in enumerate(range(39, 58, 5)):                   # O P E N in red marker
        d.rectangle([x, y0 + 13, x + 2, y0 + 17], outline=RUST)
    # push plate
    box(d, 66, 92, 70, 104, STEEL)
    return im


def wine_shelf(seed=7):
    im, d = new(144, 176)
    rnd = random.Random(seed)
    L, R = 2, 141
    top0, top1, bot = 4, 18, 175
    # top face
    box(d, L + 2, top0, R - 2, top1, WD4)
    d.line([L + 3, top0 + 1, R - 3, top0 + 1], fill=WD6)
    # handwritten header card on top: "WINE"
    box(d, 50, 0, 94, 10, CREAM)
    for x in range(54, 90, 9):
        d.line([(x, 3), (x + 2, 7), (x + 4, 3), (x + 6, 7)], fill=RUST)
    # carcass
    box(d, L, top1, R, bot, WD3)
    d.line([L + 1, top1 + 1, L + 1, bot - 1], fill=WD6)
    d.line([R - 1, top1 + 1, R - 1, bot - 1], fill=WD2)
    box(d, L, bot - 8, R, bot, WD2)                            # plinth
    ix0, ix1 = L + 5, R - 5
    rows = [(top1 + 4, top1 + 30), (top1 + 36, top1 + 62), (top1 + 68, top1 + 94),
            (top1 + 100, top1 + 126), (top1 + 132, top1 + 148)]
    reds = [(INK, KRAFT_L), (NAVY, CREAM), (INK, CREAM_M), (NAVY, KRAFT)]
    whites = [(GREEN, CREAM), (GREEN, KRAFT_L)]
    for i, (y0, y1) in enumerate(rows):
        d.rectangle([ix0, y0, ix1, y1], fill=OUT)
        d.rectangle([ix0 + 1, y0 + 1, ix1 - 1, y1], fill=WD1)
        d.line([ix0 + 1, y0 + 1, ix1 - 1, y0 + 1], fill=WD0)
        if i == 4:                                             # bottom: boxes / crates
            for bx in range(ix0 + 3, ix1 - 20, 30):
                box(d, bx, y1 - 13, bx + 24, y1, KRAFT)
                d.line([bx + 1, y1 - 12, bx + 23, y1 - 12], fill=KRAFT_L)
                d.line([bx + 12, y1 - 12, bx + 12, y1 - 1], fill=WD5)
        elif i == 1:                                           # eye level: the three featured reds
            feats = [(26, INK, WD7, RUST),       # Red Fox (orange fox label)
                     (62, NAVY, KRAFT_L, KRAFT),  # reserve with the gold label
                     (98, INK, CREAM, RUST)]     # house red, plain label
            for fx, glass, label, cap in feats:
                bottle(d, fx, y1 - 1, glass, label, SLATE, cap)
                bottle(d, fx + 9, y1 - 1, glass, label, SLATE, cap)
                # shelf talker card under each pair
            d.point([(28, y1 - 8), (37, y1 - 8)], fill=RUST)   # fox ears on the label
            d.line([63, y1 - 7, 67, y1 - 7], fill="#c99a66")
            d.line([72, y1 - 7, 76, y1 - 7], fill="#c99a66")
        else:
            x = ix0 + 3
            kind = reds if i in (0, 2) else whites + reds[:1]
            while x < ix1 - 8:
                g, lab = rnd.choice(kind)
                bottle(d, x, y1 - 1, g, lab, GREY if g == GREEN else SLATE)
                x += 8 + (rnd.random() < 0.15) * 4
        # shelf board front with price tags
        box(d, ix0 - 1, y1 + 1, ix1 + 1, y1 + 5, WD4)
        d.line([ix0, y1 + 2, ix1, y1 + 2], fill=WD6)
        if i < 4:
            tags = (24, 60, 96) if i == 1 else (14, 50, 86, 116)
            for tx in tags:
                d.rectangle([tx, y1 + 2, tx + 12, y1 + 4], fill=CREAM)
                d.point([(tx + 2, y1 + 3), (tx + 4, y1 + 3)], fill=INK)
                if i == 1:
                    d.point([(tx + 8, y1 + 3)], fill=RUST)
    return im


def tulips(seed=11):
    im, d = new(48, 80)
    rnd = random.Random(seed)
    heads = []
    for i in range(11):
        hx = 7 + i * 3 + rnd.randint(-1, 1)
        hy = 4 + rnd.randint(0, 12) + (abs(i - 5) * 2)
        heads.append((hx, hy))
    # stems and leaves
    for hx, hy in heads:
        d.line([(hx + 2, hy + 6), (24 + (hx - 24) // 3, 50)], fill=GREEN)
    for (lx, ly, rx) in ((14, 30, 8), (32, 28, 40), (22, 34, 18)):
        d.polygon([(lx, ly), (rx, ly - 10), (lx + 3, ly + 8)], fill=GREEN_L, outline=GREEN)
    # tulip heads (red, cream and orange), cup shapes
    cols = [RUST, CREAM, RUST, WD7, RUST, CREAM, RUST, WD7, RUST, CREAM, RUST]
    for (hx, hy), c in zip(heads, cols):
        d.rectangle([hx - 1, hy, hx + 5, hy + 7], fill=OUT)
        d.rectangle([hx, hy + 1, hx + 4, hy + 6], fill=c)
        d.point([(hx - 1, hy), (hx + 2, hy), (hx + 5, hy)], fill=c)   # petal tips
        d.point([(hx, hy + 2)], fill=CREAM_M if c != CREAM else CREAM_S)
        d.line([hx + 4, hy + 2, hx + 4, hy + 6], fill=WD2 if c == RUST else (CREAM_S if c == CREAM else WD5))
    # galvanised bucket
    d.polygon([(8, 48), (40, 48), (37, 77), (11, 77)], fill=OUT)
    d.polygon([(9, 50), (39, 50), (36, 76), (12, 76)], fill=STEEL)
    d.polygon([(30, 50), (39, 50), (36, 76), (30, 76)], fill=GREY)
    d.line([10, 58, 38, 58], fill=GREY)
    d.line([11, 69, 37, 69], fill=GREY)
    box(d, 7, 46, 41, 50, CREAM_S)                             # rim
    d.line([9, 47, 39, 47], fill=SLATE)                       # water inside
    # price card on a stick
    d.line([40, 30, 37, 50], fill=WD3)
    box(d, 34, 22, 46, 31, CREAM)
    d.line([36, 25, 43, 25], fill=INK)
    d.line([36, 28, 41, 28], fill=RUST)
    return im


def choc_rack():
    im, d = new(48, 104)
    L, R = 6, 41
    # header card
    box(d, L - 1, 0, R + 1, 12, RUST)
    d.line([L, 1, R, 1], fill=WD7)
    for x in range(L + 4, R - 4, 6):
        d.line([(x, 5), (x + 2, 8), (x + 4, 5)], fill=CREAM)
    # wire frame uprights
    d.rectangle([L, 12, L + 1, 100], fill=SLATE)
    d.rectangle([R - 1, 12, R, 100], fill=SLATE)
    d.line([L, 12, L, 100], fill=OUT)
    d.line([R, 12, R, 100], fill=OUT)
    wrappers = [RUST, NAVY, GREEN, KRAFT, KRAFT_L, SLATE, CREAM_M, WD3]
    rnd = random.Random(5)
    for t in range(4):
        y1 = 30 + t * 18
        # bars standing in the tray
        x = L + 3
        while x < R - 6:
            c = rnd.choice(wrappers)
            box(d, x, y1 - 13, x + 5, y1, c)
            d.line([x + 1, y1 - 10, x + 4, y1 - 10], fill=CREAM if c not in (CREAM_M, KRAFT_L) else RUST)
            x += 6
        # tray lip
        d.rectangle([L, y1 + 1, R, y1 + 3], fill=OUT)
        d.line([L + 1, y1 + 2, R - 1, y1 + 2], fill=STEEL)
    # base
    box(d, L - 2, 98, R + 2, 103, SLATE)
    d.line([L - 1, 99, R + 1, 99], fill=GREY)
    return im


def counter():
    im, d = new(144, 128)
    L, R = 1, 142
    top0, top1, bot = 17, 61, 127
    # top surface (laminate)
    box(d, L, top0, R, top1, CREAM_M)
    d.line([L + 1, top0 + 1, R - 1, top0 + 1], fill=CREAM)
    d.line([L + 1, top1 - 1, R - 1, top1 - 1], fill=CREAM_S)
    # front (wood panels) with kick plate
    box(d, L, top1, R, bot, WD3)
    d.line([L + 1, top1 + 1, R - 1, top1 + 1], fill=WD6)
    d.line([L + 1, top1 + 2, R - 1, top1 + 2], fill=WD2)
    for x in range(10, 130, 26):
        box(d, x, top1 + 8, x + 16, bot - 12, WD4)
        d.line([x + 1, top1 + 9, x + 15, top1 + 9], fill=WD6)
    box(d, L, bot - 6, R, bot, WD0)
    # small change mat and a few coins
    box(d, 66, 44, 84, 54, GREEN)
    d.point([(70, 48), (75, 50), (79, 47)], fill=KRAFT_L)
    # handwritten sign on a little easel, left
    d.polygon([(16, 50), (20, 28), (22, 28), (18, 50)], fill=WD2)
    box(d, 8, 22, 44, 44, CREAM)
    d.line([(12, 28), (16, 26), (20, 29), (25, 27), (30, 29), (36, 27), (40, 28)], fill=INK)
    d.line([(12, 34), (17, 33), (22, 35), (28, 33), (33, 35)], fill=INK)
    d.line([(12, 39), (18, 38), (24, 40)], fill=RUST)
    d.ellipse([33, 36, 39, 41], outline=RUST)                  # a little heart-ish doodle
    # till: base, cash drawer front, keypad, display on a post
    box(d, 96, 30, 134, 52, NAVY)                              # body top (keys)
    for ky in (34, 39, 44):
        for kx in range(100, 122, 5):
            d.rectangle([kx, ky, kx + 3, ky + 2], fill=STEEL)
    d.rectangle([124, 34, 130, 47], fill=SLATE)
    box(d, 94, 52, 136, 64, SLATE)                             # drawer front
    d.line([95, 53, 135, 53], fill=GREY)
    box(d, 110, 56, 120, 59, STEEL)                            # drawer handle
    d.rectangle([112, 18, 116, 30], fill=OUT)                  # display post
    box(d, 102, 4, 128, 19, INK)                               # display
    d.rectangle([105, 7, 125, 15], fill=GREEN_L)
    d.line([107, 11, 120, 11], fill=GREEN)
    # receipt roll
    box(d, 130, 22, 138, 30, CREAM)
    return im


def check_palette(im, pal, name):
    data = im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata()
    bad = {"#%02x%02x%02x" % p[:3] for p in data if p[3]} - pal
    if bad:
        raise SystemExit(f"{name}: colours outside the palette: {sorted(bad)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="output directory for the PNGs")
    ap.add_argument("--door-ref", required=True, help="composite export of the 3A door (region 7,22,4,5)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    pal = load_palette()
    props = (("recycling_bag", recycling_bag), ("chest_drawers", chest_drawers), ("moving_box", moving_box),
             ("drying_rack", drying_rack), ("notebook", notebook), ("shop_wall", shop_wall),
             ("shop_floor", shop_floor), ("wine_shelf", wine_shelf), ("tulips", tulips),
             ("choc_rack", choc_rack), ("counter", counter))
    for name, fn in props:
        im = fn()
        check_palette(im, pal, name)
        p = os.path.join(a.out, name + ".png")
        im.save(p)
        print(p, im.size)
    im = shop_door(a.door_ref)
    p = os.path.join(a.out, "shop_door.png")
    im.save(p)
    print(p, im.size)


if __name__ == "__main__":
    main()
