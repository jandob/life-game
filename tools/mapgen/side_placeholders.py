#!/usr/bin/env python3
"""Placeholder art for the side-view rooms of `maps/side/route1.tmj`.

Each room's back wall is already drawn face-on in the top-down `route1_flat.tmj`, so the
rooms are cut from its layers: a clean wall-and-floor column repeated across the strip,
then the furniture of the `Decor` layer (transparent, so it pastes cleanly) placed along
the wall. A side-on table and bed are drawn. The door leaves are separate images so the
game can hide them while a door is open. Stage 3 of the side-view plan replaces all of
this with painted rooms.

    python tools/mapgen/side_placeholders.py   # writes assets/library/rooms/*
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "assets/maps/route1_flat.tmj"
OUT = ROOT / "assets/library/rooms"

T = 48
WIDTH, HEIGHT = 27 * T, 12 * T
# Where every room's wall top lands in its strip, and the wall height (4 tiles).
TOP = 96
WALL = 4 * T
# Furniture stands with its bottom here, a little behind the characters' feet line.
STANDS_AT = 348
# The characters' feet line (the `Floor` polyline of every room).
FEET = 368
# Floor seen below the wall, in px.
FLOOR_DEPTH = 128
DOORWAY = (30, 22, 26)


def render_layers():
    m = json.loads(MAP.read_text())
    tileset_path = (MAP.parent / m["tilesets"][0]["source"]).resolve()
    tileset = json.loads(tileset_path.read_text())
    sheet = Image.open(tileset_path.parent / tileset["image"]).convert("RGBA")
    cols = tileset["columns"]
    layers = {}
    for layer in m["layers"]:
        if layer["type"] != "tilelayer":
            continue
        out = Image.new("RGBA", (m["width"] * T, m["height"] * T))
        for i, gid in enumerate(layer["data"]):
            gid &= 0x0FFFFFFF
            if not gid:
                continue
            gid -= 1
            tile = sheet.crop(((gid % cols) * T, (gid // cols) * T, (gid % cols + 1) * T, (gid // cols + 1) * T))
            out.alpha_composite(tile, ((i % m["width"]) * T, (i // m["width"]) * T))
        layers[layer["name"]] = out
    base = layers["Floor"].copy()
    base.alpha_composite(layers["Walls"])
    return base, layers


def tight(layer, box):
    """The part of `layer` inside `box` that isn't transparent."""
    piece = layer.crop(box)
    return piece.crop(piece.getbbox())


def side_table(draw, x):
    """A small table with a chair either side, seen side-on."""
    wood, dark, seat = (122, 82, 50), (74, 48, 30), (98, 140, 118)
    top = STANDS_AT - 66
    draw.rectangle((x, top, x + 112, top + 7), fill=wood, outline=dark)
    for lx in (x + 8, x + 98):
        draw.rectangle((lx, top + 8, lx + 5, STANDS_AT), fill=dark)
    draw.rectangle((x + 30, top - 3, x + 50, top - 1), fill=(236, 232, 220))
    draw.rectangle((x + 64, top - 3, x + 84, top - 1), fill=(236, 232, 220))
    draw.rectangle((x + 92, top - 10, x + 96, top - 1), fill=(120, 160, 140))
    for cx, back in ((x - 40, x - 40), (x + 124, x + 152)):
        seat_y = STANDS_AT - 42
        draw.rectangle((cx, seat_y, cx + 32, seat_y + 5), fill=seat, outline=dark)
        draw.rectangle((back, seat_y - 46, back + 4, STANDS_AT), fill=dark)
        front = cx + 28 if back == cx else cx
        draw.rectangle((front, seat_y + 6, front + 4, STANDS_AT), fill=dark)


def side_bed(draw, x):
    """The bare bed frame the last tenant left in 3B, seen side-on."""
    pale, dark = (196, 160, 104), (120, 88, 50)
    draw.rectangle((x, STANDS_AT - 70, x + 8, STANDS_AT), fill=pale, outline=dark)
    draw.rectangle((x + 192, STANDS_AT - 46, x + 200, STANDS_AT), fill=pale, outline=dark)
    draw.rectangle((x, STANDS_AT - 34, x + 200, STANDS_AT - 24), fill=pale, outline=dark)
    for sx in range(x + 16, x + 190, 22):
        draw.line((sx, STANDS_AT - 34, sx + 10, STANDS_AT - 24), fill=dark)


class Room:
    def __init__(self, base, wall_top, column_x, dark):
        self.img = Image.new("RGBA", (WIDTH, HEIGHT), dark)
        column = base.crop((column_x, wall_top, column_x + T, wall_top + WALL + FLOOR_DEPTH))
        for x in range(T, WIDTH - T, T):
            self.img.alpha_composite(column, (x, TOP))
        self.draw = ImageDraw.Draw(self.img)

    def on_wall(self, piece, x, y_from_wall_top):
        self.img.alpha_composite(piece, (x, TOP + y_from_wall_top))

    def standing(self, piece, x):
        self.img.alpha_composite(piece, (x, STANDS_AT - piece.height))

    def doorway(self, x):
        """The dark opening an open door leaves (the leaf is its own image)."""
        self.draw.rectangle((x + 10, TOP + 30, x + 86, TOP + WALL), fill=DOORWAY)

    def save(self, name):
        path = OUT / name / "background.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.img.save(path)
        print(f"{path.relative_to(ROOT)}: {WIDTH}x{HEIGHT}")


def main():
    base, layers = render_layers()
    decor = layers["Decor"]
    dark = base.getpixel((4, 4))

    door = layers["Door3B"].crop((240, 672, 336, 864))
    (OUT / "doors").mkdir(parents=True, exist_ok=True)
    door.save(OUT / "doors/door.png")
    print(f"{(OUT / 'doors/door.png').relative_to(ROOT)}: {door.width}x{door.height}, top at wall top")

    # Landing: stairs down on the left, 3B and 3A side by side, her recycling.
    landing = Room(base, 672, 480, dark)
    landing.standing(tight(decor, (48, 864, 160, 1008)), 64)
    landing.doorway(432)
    landing.doorway(816)
    landing.standing(tight(decor, (470, 900, 540, 1008)), 1020)
    landing.save("landing")

    # 3B: the door in from the landing, the bedroom, then the kitchen corner.
    flat3b = Room(base, 48, 96, dark)
    flat3b.doorway(96)
    flat3b.standing(tight(decor, (430, 540, 532, 624)), 240)  # clothes rack
    flat3b.on_wall(tight(decor, (150, 90, 230, 170)), 420, 52)  # window
    side_bed(flat3b.draw, 380)
    flat3b.standing(tight(decor, (310, 180, 384, 276)), 640)  # drawers
    flat3b.standing(tight(decor, (90, 570, 150, 624)), 760)  # moving box
    flat3b.standing(tight(decor, (430, 180, 624, 292)), 900)  # sink, stove, fridge
    flat3b.save("flat3b")

    # 3A: kitchen corner, window, table, her front door, bookshelf.
    flat3a = Room(base, 1056, 480, dark)
    flat3a.standing(tight(decor, (48, 1170, 250, 1310)), 52)
    flat3a.on_wall(tight(decor, (250, 1090, 330, 1170)), 256, 52)
    side_table(flat3a.draw, 11 * T)
    flat3a.doorway(816)
    flat3a.standing(tight(decor, (520, 1100, 630, 1310)), 1110)
    flat3a.save("flat3a")

    # The corner shop: its door, the wine shelf, chocolates, the till, flowers.
    shop = Room(base, 1680, 336, dark)
    shop.on_wall(base.crop((144, 1710, 240, 1872)), 96, 30)
    shop.standing(tight(decor, (280, 1720, 440, 1910)), 330)
    shop.standing(tight(decor, (380, 1950, 432, 2070)), 640)
    shop.standing(tight(decor, (432, 1930, 580, 2070)), 720)
    shop.standing(tight(decor, (90, 2070, 150, 2160)), 1000)
    shop.save("shop")


if __name__ == "__main__":
    main()
