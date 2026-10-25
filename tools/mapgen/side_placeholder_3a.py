#!/usr/bin/env python3
"""Placeholder background for the side-view spike room `maps/side/flat3a.tmj`.

Cuts Samantha's flat (3A) out of the top-down `route1_flat.tmj` render (its back wall is
already drawn face-on), widens it to a side-on strip and draws a side-on table. Stage 3
of the side-view plan replaces this with a painted background.

    python tools/mapgen/side_placeholder_3a.py   # writes assets/library/rooms/flat3a/background.png
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "assets/maps/route1_flat.tmj"
OUT = ROOT / "assets/library/rooms/flat3a/background.png"

T = 48
WIDTH, HEIGHT = 27 * T, 12 * T
# Tiled px of 3A's back wall top and the first floor row below the furniture.
WALL_TOP = 1056
FLOOR_BOTTOM = 1376
# Where 3A's wall top lands in the strip.
TOP = 96


def render_flat():
    m = json.loads(MAP.read_text())
    tileset_path = (MAP.parent / m["tilesets"][0]["source"]).resolve()
    tileset = json.loads(tileset_path.read_text())
    sheet = Image.open(tileset_path.parent / tileset["image"]).convert("RGBA")
    cols = tileset["columns"]
    out = Image.new("RGBA", (m["width"] * T, m["height"] * T))
    for layer in m["layers"]:
        if layer["type"] != "tilelayer" or not layer.get("visible", True):
            continue
        for i, gid in enumerate(layer["data"]):
            gid &= 0x0FFFFFFF
            if not gid:
                continue
            gid -= 1
            tile = sheet.crop(((gid % cols) * T, (gid // cols) * T, (gid % cols + 1) * T, (gid // cols + 1) * T))
            out.alpha_composite(tile, ((i % m["width"]) * T, (i // m["width"]) * T))
    return out


def side_table(draw, x, floor_y):
    """A small table with a chair either side, seen side-on, its feet on `floor_y`."""
    wood, dark, seat = (122, 82, 50), (74, 48, 30), (98, 140, 118)
    top = floor_y - 66
    draw.rectangle((x, top, x + 112, top + 7), fill=wood, outline=dark)
    for lx in (x + 8, x + 98):
        draw.rectangle((lx, top + 8, lx + 5, floor_y), fill=dark)
    # Plates and a glass on the table top.
    draw.rectangle((x + 30, top - 3, x + 50, top - 1), fill=(236, 232, 220))
    draw.rectangle((x + 64, top - 3, x + 84, top - 1), fill=(236, 232, 220))
    draw.rectangle((x + 92, top - 10, x + 96, top - 1), fill=(120, 160, 140))
    for cx, back in ((x - 40, x - 40), (x + 124, x + 152)):
        seat_y = floor_y - 42
        draw.rectangle((cx, seat_y, cx + 32, seat_y + 5), fill=seat, outline=dark)
        draw.rectangle((back, seat_y - 46, back + 4, floor_y), fill=dark)
        front = cx + 28 if back == cx else cx
        draw.rectangle((front, seat_y + 6, front + 4, floor_y), fill=dark)


def main():
    flat = render_flat()
    dark = flat.getpixel((4, 4))
    bg = Image.new("RGBA", (WIDTH, HEIGHT), dark)

    def cut(x0, x1, y1=FLOOR_BOTTOM):
        return flat.crop((x0, WALL_TOP, x1, y1))

    # A clean wall-and-floor tile column between her door and the shelf, repeated.
    column = cut(480, 528)
    for x in range(T, WIDTH - T, T):
        bg.alpha_composite(column, (x, TOP))
    furniture_bottom = 1308
    bg.alpha_composite(cut(48, 336, furniture_bottom), (T, TOP))  # sink, stove, fridge, window
    bg.alpha_composite(cut(384, 480, 1268), (17 * T, TOP))  # her front door
    bg.alpha_composite(cut(528, 624, furniture_bottom), (23 * T, TOP))  # bookshelf

    floor_y = TOP + (furniture_bottom - WALL_TOP) + 20
    side_table(ImageDraw.Draw(bg), 11 * T, floor_y)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    bg.save(OUT)
    print(f"{OUT.relative_to(ROOT)}: {WIDTH}x{HEIGHT}, floor line at y={floor_y}")


if __name__ == "__main__":
    main()
