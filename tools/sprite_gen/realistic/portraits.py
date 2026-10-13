#!/usr/bin/env python3
"""64x64 dialogue portraits cropped from the raw FLUX standing fronts of the realistic characters.

Usage (from the repo root, any Python with numpy + Pillow; tools/artgen/.venv works):
    python tools/sprite_gen/realistic/portraits.py player OUT.png
    python tools/sprite_gen/realistic/portraits.py samantha OUT.png

A square head-and-shoulders crop of the raw front (sized so the head is about 34 px tall, the
shoulders run off the bottom edge) is cut out (clean_raw), downscaled to 64x64 with artgen's
postprocess (block mode, 32 colours, inner outline) and gets the 1 px white sticker border of the
existing portraits in assets/library/portraits/.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools" / "artgen"))
sys.path.insert(0, str(HERE))
import postprocess as pp  # noqa: E402
from build_sheets import RECIPES  # noqa: E402
from clean_raw import clean  # noqa: E402

S = 64
HEAD_PX = 34  # head height in the portrait
HEAD_ROWS = {"player": 19, "samantha": 18}  # head height in sprite rows (design D1)


def portrait(char):
    rec = RECIPES[char]
    raw = np.array(Image.open(REPO / rec["raw"] / rec["frames"]["front"]).convert("RGB"))
    cut, _ = clean(raw, rec.get("clean_grey", True))
    op = cut[..., 3] == 255
    ys = np.where(op.any(1))[0]
    top = ys.min()
    head_raw = HEAD_ROWS[char] * rec["N"]["front"]
    side = int(round(head_raw * S / HEAD_PX))
    band = op[top: top + int(head_raw)]
    xs = np.nonzero(band)[1]
    cx = (xs.min() + xs.max()) / 2
    x0 = int(round(cx - side / 2))
    y0 = int(top - round(side * 0.12))
    crop = np.zeros((side, side, 4), np.uint8)
    sy0, sx0 = max(0, y0), max(0, x0)
    sy1, sx1 = min(cut.shape[0], y0 + side), min(cut.shape[1], x0 + side)
    crop[sy0 - y0: sy1 - y0, sx0 - x0: sx1 - x0] = cut[sy0:sy1, sx0:sx1]
    img = Image.fromarray(crop, "RGBA")
    small, rep = pp.run_pipeline(img, grid=str(side / S), bg="auto", colours=32, outline="inner",
                                 keep_largest=True, keep_dark=0.3)
    a = np.array(small.convert("RGBA"))
    out = np.zeros((S, S, 4), np.uint8)
    h, w = min(S, a.shape[0]), min(S, a.shape[1])
    out[:h, :w] = a[:h, :w]
    # bust runs off the bottom edge: extend the last opaque row down if the crop ended short
    # white sticker border (4-neighbour), not along the bottom edge
    m = out[..., 3] == 255
    g = m.copy()
    g[1:] |= m[:-1]
    g[:-1] |= m[1:]
    g[:, 1:] |= m[:, :-1]
    g[:, :-1] |= m[:, 1:]
    ring = g & ~m
    ring[-1] = False
    out[ring] = (255, 255, 255, 255)
    return out


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in RECIPES:
        print(__doc__)
        sys.exit(1)
    out = portrait(sys.argv[1])
    Image.fromarray(out).save(sys.argv[2])
    print("wrote", sys.argv[2], out.shape[1], "x", out.shape[0])


if __name__ == "__main__":
    main()
