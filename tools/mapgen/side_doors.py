#!/usr/bin/env python3
"""Door leaves for the painted side-view rooms of `maps/side/route1.tmj`.

The painted backgrounds show every doorway open (dark). The game draws a leaf image over
the opening while a door is closed (an image layer named like the door, see
`src/world/side_view/mod.rs`). Each leaf is sized to the dark opening of its door and
coloured from the frame beside it.

    python tools/mapgen/side_doors.py   # writes assets/library/rooms/doors/*.png
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets/library/rooms/doors"

# name -> (width, height, wood colour sampled from the painted frame)
LEAVES = {
    "door_landing_3b": (131, 244, (146, 104, 66)),
    "door_landing_3a": (129, 244, (146, 104, 66)),
    "door_3b_inside": (84, 219, (150, 112, 84)),
    "door_3a_inside": (140, 255, (123, 77, 41)),
}


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def leaf(w, h, wood, seed):
    rng = random.Random(seed)
    img = Image.new("RGBA", (w, h), shade(wood, 0.3) + (255,))
    d = ImageDraw.Draw(img)
    dark, light = shade(wood, 0.55), shade(wood, 1.18)
    d.rectangle((1, 1, w - 2, h - 2), fill=wood + (255,))
    # Faint vertical grain.
    for x in range(3, w - 3):
        if rng.random() < 0.35:
            y0 = rng.randrange(2, h - 40)
            d.line((x, y0, x, y0 + rng.randrange(10, 60)), fill=shade(wood, rng.choice((0.93, 1.07))) + (255,))
    # Bevel: light on the top and hinge side, dark on the bottom and handle side.
    d.line((1, 1, w - 2, 1), fill=light + (255,))
    d.line((1, 1, 1, h - 2), fill=light + (255,))
    d.line((2, h - 2, w - 2, h - 2), fill=dark + (255,))
    d.line((w - 2, 2, w - 2, h - 2), fill=dark + (255,))
    # Two recessed panels, tall upper one and a shorter lower one.
    m = max(10, w // 9)
    top_h = int((h - 3 * m) * 0.58)
    for y0, y1 in ((m, m + top_h), (2 * m + top_h, h - m)):
        d.rectangle((m, y0, w - 1 - m, y1), outline=dark + (255,))
        d.line((m + 1, y1 - 1, w - 2 - m, y1 - 1), fill=light + (255,))
        d.line((w - 2 - m, y0 + 1, w - 2 - m, y1 - 1), fill=light + (255,))
        d.rectangle((m + 3, y0 + 3, w - 4 - m, y1 - 3), outline=shade(wood, 0.8) + (255,))
    # Hinges on the left, brass handle and lock plate on the right.
    for y in (int(h * 0.12), int(h * 0.5), int(h * 0.88)):
        d.rectangle((0, y, 3, y + 9), fill=(70, 60, 50, 255))
    hx, hy = w - 5 - max(10, w // 10), int(h * 0.55)
    brass, brass_dark = (214, 176, 84, 255), (120, 92, 40, 255)
    d.rectangle((hx - 1, hy - 14, hx + 7, hy + 22), fill=shade(wood, 0.45) + (255,))
    d.rectangle((hx, hy, hx + 5, hy + 18), fill=brass, outline=brass_dark)
    d.rectangle((hx - 14, hy + 2, hx + 3, hy + 6), fill=brass, outline=brass_dark)
    d.ellipse((hx, hy - 10, hx + 5, hy - 5), fill=brass_dark)
    # Outline.
    d.rectangle((0, 0, w - 1, h - 1), outline=shade(wood, 0.32) + (255,))
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (name, (w, h, wood)) in enumerate(LEAVES.items()):
        path = OUT / f"{name}.png"
        leaf(w, h, wood, i).save(path)
        print(f"{path.relative_to(ROOT)}: {w}x{h}")


if __name__ == "__main__":
    main()
