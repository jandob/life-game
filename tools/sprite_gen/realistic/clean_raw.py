#!/usr/bin/env python3
"""Cut a raw FLUX character frame (white background) out to RGBA, dropping the painted floor shadow.

Usage: clean_raw.py IN.png OUT.png

`artgen.py post`'s own background flood (tolerance 38 from white) leaks into white sneakers through
small gaps in their outline. Here the background is flooded from the border through "background-like"
pixels (near-white, or the light lavender/grey floor shadow in the lower 20 %), with every other pixel
grown by GAP px as a barrier, so gaps up to about 2*GAP px don't leak. The flood is then grown back over
background-like pixels next to it. The result has real alpha, which `postprocess.run_pipeline` uses as is.
"""
import sys
from collections import deque

import numpy as np
from PIL import Image

GAP = 2


def _dilate(m, n):
    for _ in range(n):
        g = m.copy()
        g[1:] |= m[:-1]
        g[:-1] |= m[1:]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m


def clean(a, grey=True):
    """a: HxWx3 uint8. Returns (HxWx4 uint8 with alpha, number of floor-shadow px removed).
    grey=False: only the lavender shadow counts as shadow (keeps light grey sneakers)."""
    h, w = a.shape[:2]
    rgb = a[..., :3].astype(int)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    white = rgb.min(-1) > 238
    low = np.zeros((h, w), bool)
    low[int(h * 0.8):] = True
    bluish = (b > g + 8) & (r > 130) & (b > 160) & (rgb.mean(-1) > 140)
    greyish = (np.abs(r - g) < 14) & (np.abs(g - b) < 18) & (rgb.mean(-1) > 185)
    shadow = low & (bluish | (greyish if grey else False))
    bglike = white | shadow
    barrier = _dilate(~bglike, GAP)
    passable = bglike & ~barrier
    seen = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        q.append((0, x))
        q.append((h - 1, x))
    for y in range(h):
        q.append((y, 0))
        q.append((y, w - 1))
    while q:
        y, x = q.popleft()
        if seen[y, x] or not passable[y, x]:
            continue
        seen[y, x] = True
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < h and 0 <= xx < w and not seen[yy, xx]:
                q.append((yy, xx))
    bg = seen
    for _ in range(GAP + 1):
        bg = bg | (_dilate(bg, 1) & bglike)
    out = np.dstack([a[..., :3], np.where(bg, 0, 255)]).astype(np.uint8)
    return out, int((bg & shadow).sum())


if __name__ == "__main__":
    im = np.array(Image.open(sys.argv[1]).convert("RGB"))
    out, n = clean(im)
    Image.fromarray(out, "RGBA").save(sys.argv[2])
    print(f"{sys.argv[1]}: {n} floor-shadow px removed")
