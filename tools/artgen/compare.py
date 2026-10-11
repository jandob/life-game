#!/usr/bin/env python
"""Side-by-side comparison of bench runs (variants of one backend, or
different backends): one row per item, one column per run, showing the raw
image (256 px) above the processed result (nearest-zoomed into 256 px wide).

    compare.py RUN_DIR [RUN_DIR ...] --seed 11 --out compare.png [--items a,b]

RUN_DIR is a bench output folder such as OUT/<backend>/<variant>.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from bench import BG, font

COL = 256


def tile_for(run: Path, item: str, seed: int) -> Image.Image:
    out = Image.new("RGBA", (COL, COL * 2 + 4), (255, 255, 255, 255))
    raw_p = run / "raw" / f"{item}_s{seed}.png"
    px_p = run / "px" / f"{item}_s{seed}_px.png"
    if raw_p.exists():
        out.paste(Image.open(raw_p).convert("RGBA").resize((COL, COL), Image.LANCZOS), (0, 0))
    if px_p.exists():
        px = Image.open(px_p).convert("RGBA")
        k = max(1, min(COL // px.width, COL // px.height))
        z = px.resize((px.width * k, px.height * k), Image.NEAREST)
        bg = Image.new("RGBA", (COL, COL), BG)
        bg.alpha_composite(z, ((COL - z.width) // 2, (COL - z.height) // 2))
        out.paste(bg, (0, COL + 4))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--items", help="comma-separated item ids (default: all in the first run)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    runs = [Path(r) for r in a.runs]
    if a.items:
        items = a.items.split(",")
    else:
        items = sorted({p.name.rsplit("_s", 1)[0] for p in (runs[0] / "raw").glob("*.png")})
    lw, hh = 170, 28
    W = lw + len(runs) * (COL + 8)
    H = hh + len(items) * (COL * 2 + 16)
    sheet = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for j, r in enumerate(runs):
        d.text((lw + j * (COL + 8), 4), f"{r.parent.name}/{r.name}", fill=(0, 0, 0), font=font(14))
    for i, item in enumerate(items):
        y = hh + i * (COL * 2 + 16)
        d.text((6, y + 4), item, fill=(0, 0, 0), font=font(16))
        for j, r in enumerate(runs):
            sheet.paste(tile_for(r, item, a.seed), (lw + j * (COL + 8), y))
    sheet.save(a.out)
    print(a.out)


if __name__ == "__main__":
    main()
