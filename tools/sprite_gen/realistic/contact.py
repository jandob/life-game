#!/usr/bin/env python3
"""Task 2.5 contact sheets for the realistic character sheets.

Usage (repo root): python tools/sprite_gen/realistic/contact.py OUT_DIR MAP_RENDER.png
  OUT_DIR/rows_3x_<char>.png  every row of the sheet at 3x, with the feet row 157 (red) and the head-top rows
                              26 (green, man) and 32 (blue, woman) marked, row labels on the left
  OUT_DIR/door_720p.png       both characters at 1x (1 art px = 1 screen px) on the landing in front of the
                              3B door of a `scene.py render` of route1_flat.tmj (48 px tiles), 1280x720
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[3]
CHARS = {"player": REPO / "assets/library/characters/player/player.png",
         "samantha": REPO / "assets/library/characters/samantha/samantha.png"}
ROWS = ["idle down", "idle left", "idle right", "idle up", "walk down", "walk left", "walk right", "walk up",
        "run down", "run left", "run right", "run up"]


def rows_3x(sheet, out, z=3):
    lab = 110
    W, H = 960 * z + lab, 192 * 12 * z
    o = Image.new("RGBA", (W, H), (150, 150, 150, 255))
    big = sheet.resize((960 * z, 2304 * z), Image.NEAREST)
    o.alpha_composite(big, (lab, 0))
    d = ImageDraw.Draw(o)
    for r in range(12):
        y0 = r * 192 * z
        d.text((6, y0 + 90 * z), f"{r}: {ROWS[r]}", fill=(0, 0, 0, 255))
        for yy, c in ((157, (255, 0, 0, 255)), (26, (0, 150, 0, 255)), (32, (0, 90, 255, 255))):
            d.line([(lab, y0 + (yy + 1) * z), (W, y0 + (yy + 1) * z)], fill=c)
        d.line([(0, y0), (W, y0)], fill=(90, 90, 90, 255))
        for c in range(11):
            d.line([(lab + c * 96 * z, y0), (lab + c * 96 * z, y0 + 192 * z)], fill=(110, 110, 110, 255))
    o.save(out)


def door_720p(map_png, out):
    world = Image.open(map_png).convert("RGBA")
    # 3B door leaf: tiles x 5-6, rows 14.5-17.5 of the 48 px map; landing floor below it
    door_cx, floor_y = 288, 930
    W, H = 1280, 720
    left, top = door_cx - W // 2, floor_y - 520
    canvas = Image.new("RGBA", (W, H), (40, 40, 52, 255))
    canvas.paste(world, (-left, -top), world)
    P = Image.open(CHARS["player"]).convert("RGBA").crop((0, 0, 96, 192))
    S = Image.open(CHARS["samantha"]).convert("RGBA").crop((0, 0, 96, 192))
    for spr, fx in ((P, door_cx - 70), (S, door_cx + 70)):
        canvas.alpha_composite(spr, (fx - 48 - left, floor_y - 157 - top))
    d = ImageDraw.Draw(canvas)
    d.text((8, 8), "1280x720 at 1x: route1_flat.tmj (48 px tiles), 3B door leaf 144 px; player 132 rows, Samantha 126",
           fill=(255, 255, 255, 255))
    canvas.save(out)


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for c, p in CHARS.items():
        rows_3x(Image.open(p).convert("RGBA"), out / f"rows_3x_{c}.png")
    door_720p(sys.argv[2], out / "door_720p.png")
    print("wrote", out)


if __name__ == "__main__":
    main()
