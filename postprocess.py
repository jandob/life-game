"""Backend-agnostic post-processing: model output -> game-ready pixel art.

Stages (each usable on its own):

1. ``remove_background``: alpha from the image if it has real alpha,
   else flood fill from the border through pixels close to the border colours.
   Handles the fake grey checkerboard many models paint for "transparent".
2. ``detect_grid``: find the effective pixel size and phase of upscaled
   "pixel art" by scoring how much colour-edge energy falls on a regular comb.
3. ``downscale``: one true pixel per grid cell, taking the dominant (mode)
   colour of the cell centre. Alpha is a majority vote, so the result is binary.
4. ``quantize``: adaptive N colours, or snap to a fixed palette (.hex/.gpl/.png).
5. ``cleanup``: drop small opaque islands and recolour orphan pixels.
6. ``add_outline``: 1px outline in the project outline colour.
7. ``fit_cell``: place into a fixed cell (e.g. 64x128) with the feet on an
   anchor row, optionally under the project drop-shadow ellipse.

All outputs use alpha 0 or 255 only, except the optional drop shadow, which
uses the reference's alpha 125.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

# Project constants (from assets/library/characters/player/player.png).
OUTLINE = (34, 32, 52)
SHADOW_FILL = (63, 63, 116, 125)
SHADOW_RIM = (92, 92, 169, 125)
CHAR_CELL = (64, 128)
CHAR_FEET_ROW = 105   # lowest opaque row of the feet
CHAR_TOP_ROW = 17     # top of the head in the reference
SHADOW_CENTRE = (31.5, 102)
SHADOW_RADII = (22.5, 11.5)


# --------------------------------------------------------------- helpers
def to_rgba_array(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("RGBA"))


def _shift(m: np.ndarray, dy: int, dx: int, fill=False) -> np.ndarray:
    out = np.full_like(m, fill)
    h, w = m.shape[:2]
    ys = slice(max(dy, 0), h + min(dy, 0))
    yd = slice(max(-dy, 0), h + min(-dy, 0))
    xs = slice(max(dx, 0), w + min(dx, 0))
    xd = slice(max(-dx, 0), w + min(-dx, 0))
    out[ys, xs] = m[yd, xd]
    return out


def _dilate4(m: np.ndarray) -> np.ndarray:
    return m | _shift(m, 1, 0) | _shift(m, -1, 0) | _shift(m, 0, 1) | _shift(m, 0, -1)


def _components(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """4-connected components of a boolean mask (small images only)."""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    comps = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        comp, q = [], deque([(y0, x0)])
        seen[y0, x0] = True
        while q:
            y, x = q.popleft()
            comp.append((y, x))
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    q.append((ny, nx))
        comps.append(comp)
    return comps


# ------------------------------------------------------- 1. background
def border_colours(rgb: np.ndarray, max_colours: int = 4, min_share: float = 0.04,
                   bucket: int = 24) -> list[np.ndarray]:
    """Dominant colours along the image border (bucketed, then averaged)."""
    b = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]).astype(int)
    keys = [tuple(k) for k in (b // bucket)]
    cnt = Counter(keys)
    out = []
    for k, c in cnt.most_common(max_colours):
        if c / len(keys) < min_share:
            break
        sel = np.all((b // bucket) == np.array(k), axis=1)
        out.append(b[sel].mean(0))
    return out


def remove_background(img: Image.Image, tol: float = 38.0, max_colours: int = 4,
                      hole_share: float = 0.88) -> tuple[Image.Image, dict]:
    """Return RGBA with background alpha 0 (binary alpha)."""
    a = to_rgba_array(img)
    info: dict = {}
    if img.mode in ("RGBA", "LA") and (a[..., 3] < 250).mean() > 0.02:
        a[..., 3] = np.where(a[..., 3] >= 128, 255, 0)
        info["method"] = "alpha"
        return Image.fromarray(a), info
    rgb = a[..., :3].astype(np.float32)
    cols = border_colours(a[..., :3], max_colours=max_colours)
    info["method"] = "border_flood"
    info["bg_colours"] = [[int(round(v)) for v in c] for c in cols]
    close = np.zeros(rgb.shape[:2], bool)
    for c in cols:
        close |= np.sqrt(((rgb - c) ** 2).sum(-1)) <= tol
    seed = np.zeros_like(close)
    seed[0, :] = seed[-1, :] = seed[:, 0] = seed[:, -1] = True
    region = seed & close
    while True:
        nxt = _dilate4(region) & close
        if (nxt == region).all():
            break
        region = nxt
    # Enclosed pockets (between legs, arm and body) are not reached by the
    # flood fill. Remove those whose pixels almost all (>= ``hole_share``)
    # sit within 8 of a border colour. White or grey clothing with shading
    # stays below that (measured 0.6-0.81 vs 0.89-0.96 for real gaps).
    holes = close & ~region
    removed = 0
    if holes.any():
        small = holes[::2, ::2]  # label at half resolution for speed
        for comp in _components(small):
            if len(comp) < 25:
                continue
            ys, xs = np.array(comp).T * 2
            px = rgb[ys, xs]
            d = np.stack([np.sqrt(((px - c) ** 2).sum(-1)) for c in cols], 1).min(1)
            if (d < 8).mean() >= hole_share:
                m = np.zeros_like(small)
                m[tuple(np.array(comp).T)] = True
                full = np.kron(m, np.ones((2, 2), bool))[:holes.shape[0], :holes.shape[1]]
                region |= full & holes
                removed += len(comp) * 4
    info["enclosed_removed_px"] = removed
    a[..., 3] = np.where(region, 0, 255)
    info["bg_fraction"] = round(float(region.mean()), 3)
    return Image.fromarray(a), info


# -------------------------------------------------------- 2. grid detect
@dataclass
class Grid:
    scale_x: float
    scale_y: float
    off_x: float
    off_y: float
    score: float

    def to_dict(self):
        return {k: round(float(v), 3) for k, v in self.__dict__.items()}


def _edge_profile(a: np.ndarray, axis: int) -> np.ndarray:
    f = a[..., :3].astype(np.float32)
    if a.shape[-1] == 4:
        f = np.concatenate([f, a[..., 3:4].astype(np.float32)], -1)
    d = np.abs(np.diff(f, axis=axis)).sum(-1)
    prof = d.sum(axis=1 - axis) if axis == 1 else d.sum(axis=1)
    # Profile index i is the edge between pixel i and i+1, i.e. at x = i + 1.
    return np.concatenate([[0.0], prof])


def _best_comb(prof: np.ndarray, smin: float, smax: float, step: float):
    n = len(prof)
    mean = prof.mean() + 1e-6
    results = []
    for s in np.arange(smin, smax + 1e-9, step):
        best = (0.0, 0.0)
        for o in np.arange(0, s, 0.5):
            idx = np.round(np.arange(o, n, s)).astype(int)
            idx = idx[(idx > 0) & (idx < n)]
            if len(idx) < 4:
                continue
            sc = prof[idx].mean() / mean
            if sc > best[0]:
                best = (sc, o)
        results.append((s, best[0], best[1]))
    return results


def _ac_peaks(prof: np.ndarray, max_lag: float, up: int = 4) -> list[tuple[float, float]]:
    """Autocorrelation peaks at 1/up px resolution: (lag_px, value)."""
    x = np.arange(len(prof))
    fine = np.interp(np.arange(0, len(prof) - 1, 1 / up), x, prof)
    p = fine - fine.mean()
    ac = np.correlate(p, p, "full")[len(p) - 1:]
    ac = ac / (ac[0] + 1e-9)
    hi = min(int(max_lag * up), len(ac) - 1)
    return [(i / up, float(ac[i])) for i in range(2 * up, hi)
            if ac[i] > ac[i - 1] and ac[i] >= ac[i + 1]]


def detect_grid(img: Image.Image, smin: float = 2.0, smax: float = 32.0,
                rel: float = 0.7) -> Grid:
    """Estimate the pixel-art grid.

    1. Per axis, autocorrelate the colour-edge profile (at 1/4 px lag
       resolution). Multiples of the true period also peak, and generated
       art rarely holds one phase across the image, so the strongest peak is
       often a multiple: take the smallest peak within ``rel`` of the
       strongest as the fundamental.
    2. Pixels are square: if the axes agree within 25 % use their mean,
       else the smaller one.
    3. A comb search within +-0.5 px of that period finds the phase (and
       fine-tunes the scale) for each axis.
    """
    a = to_rgba_array(img)
    profs = [_edge_profile(a, 1), _edge_profile(a, 0)]
    fund = []
    for prof in profs:
        pk = [(l, v) for l, v in _ac_peaks(prof, smax + 1) if l >= smin and v > 0]
        if not pk:
            fund.append((None, 0.0))
            continue
        top = max(v for _, v in pk)
        fund.append(min(((l, v) for l, v in pk if v >= rel * top), key=lambda t: t[0]))
    lags = [l for l, _ in fund if l]
    if not lags:
        return Grid(1.0, 1.0, 0.0, 0.0, 0.0)
    lag = sum(lags) / len(lags) if max(lags) / min(lags) < 1.25 else min(lags)
    out = []
    for prof in profs:
        res = _best_comb(prof, max(smin, lag - 0.5), lag + 0.5, 0.02)
        out.append(max(res, key=lambda r: r[1]))
    (sx, scx, ox), (sy, scy, oy) = out
    s = (sx + sy) / 2
    return Grid(s, s, ox, oy, float(np.mean([v for _, v in fund])))


# ---------------------------------------------------------- 3. downscale
def downscale(img: Image.Image, scale_x: float, scale_y: float | None = None,
              off_x: float = 0.0, off_y: float = 0.0, centre: float = 0.6,
              bucket: int = 16, keep_dark: float | None = None,
              dark_lum: float = 70.0) -> Image.Image:
    """One output pixel per grid cell: dominant colour of the cell centre.

    ``keep_dark``: if at least this share of the *whole* cell is dark
    (luminance < ``dark_lum``), use the dark pixels instead. This keeps thin
    outlines and eyes that fall between cell centres when the sampling pitch
    does not match the model's own pseudo-pixel grid."""
    scale_y = scale_y or scale_x
    a = to_rgba_array(img)
    h, w = a.shape[:2]
    xs = np.arange(off_x - scale_x * np.ceil(off_x / scale_x), w, scale_x)
    ys = np.arange(off_y - scale_y * np.ceil(off_y / scale_y), h, scale_y)
    ow, oh = len(xs), len(ys)
    out = np.zeros((oh, ow, 4), np.uint8)
    mx, my = (1 - centre) / 2 * scale_x, (1 - centre) / 2 * scale_y
    for j, y0 in enumerate(ys):
        ya, yb = int(round(max(0, y0 + my))), int(round(min(h, y0 + scale_y - my)))
        if yb <= ya:
            ya, yb = int(max(0, np.floor(y0))), int(min(h, np.ceil(y0 + scale_y)))
        for i, x0 in enumerate(xs):
            xa, xb = int(round(max(0, x0 + mx))), int(round(min(w, x0 + scale_x - mx)))
            if xb <= xa:
                xa, xb = int(max(0, np.floor(x0))), int(min(w, np.ceil(x0 + scale_x)))
            cell = a[ya:yb, xa:xb].reshape(-1, 4)
            if len(cell) == 0:
                continue
            op = cell[cell[:, 3] >= 128]
            if len(op) * 2 < len(cell):
                continue
            if keep_dark:
                full = a[int(max(0, np.floor(y0))):int(min(h, np.ceil(y0 + scale_y))),
                         int(max(0, np.floor(x0))):int(min(w, np.ceil(x0 + scale_x)))].reshape(-1, 4)
                full = full[full[:, 3] >= 128]
                lum = full[:, :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
                dark = full[lum < dark_lum]
                if len(full) and len(dark) >= keep_dark * len(full):
                    op = dark
            keys = (op[:, :3] // bucket).astype(np.int32)
            k = keys[:, 0] * 4096 + keys[:, 1] * 64 + keys[:, 2]
            vals, counts = np.unique(k, return_counts=True)
            sel = op[k == vals[counts.argmax()]]
            out[j, i, :3] = np.round(sel[:, :3].mean(0)).astype(np.uint8)
            out[j, i, 3] = 255
    return Image.fromarray(out)


def downscale_fixed(img: Image.Image, factor: int, phase: tuple[int, int] = (0, 0),
                    keep_dark: float | None = None) -> Image.Image:
    """Downscale by a known integer factor on a known grid: one output pixel per ``factor`` x ``factor`` block.

    Use this when the grid is fixed by construction (the canvas was upscaled by nearest neighbour, so the model's
    pixels lie on factor-sized blocks starting at ``phase``). Each output pixel is the mode colour of its whole
    block (``centre=1``): no grid detection, no drift. Pixels left of / above the phase are dropped, and a partial
    block at the right / bottom edge is dropped, so the output is ``(W - px) // factor`` wide."""
    if factor < 1 or int(factor) != factor:
        raise ValueError(f"factor must be a positive integer, got {factor}")
    factor = int(factor)
    px, py = phase
    if not (0 <= px < factor and 0 <= py < factor):
        raise ValueError(f"phase {phase} must be inside one block (0..{factor - 1})")
    w = (img.width - px) // factor * factor
    h = (img.height - py) // factor * factor
    if w <= 0 or h <= 0:
        raise ValueError(f"image {img.size} is smaller than one block of {factor}")
    crop = img.convert("RGBA").crop((px, py, px + w, py + h))
    return downscale(crop, factor, factor, 0, 0, centre=1.0, keep_dark=keep_dark)


def key_to_alpha(img: Image.Image, key: tuple[int, int, int], tol: float = 60.0) -> Image.Image:
    """Make pixels within ``tol`` (euclidean RGB) of the flat key colour transparent."""
    a = to_rgba_array(img)
    d = np.sqrt(((a[..., :3].astype(np.float32) - np.array(key, np.float32)) ** 2).sum(-1))
    a[..., 3] = np.where(d <= tol, 0, 255)
    return Image.fromarray(a)


def snap_fixed(img: Image.Image, factor: int, *, palette: list[tuple[int, int, int]] | None = None,
               colours: int | None = None, cleanup_level: int = 1, key: tuple[int, int, int] | None = None,
               key_tol: float = 60.0, grid: str = "fixed", target: tuple[int, int] | None = None
               ) -> tuple[Image.Image, dict]:
    """Model output -> game pixels on a fixed grid, then palette and cleanup. Returns (image, report).

    ``grid="fixed"``: exact block downscale by ``factor``. ``grid="detect"``: fallback when the model drifted
    off the grid; ``detect_grid`` finds the real pitch and offset, the image is sampled there and then resized
    (nearest) to ``target`` (the cell-exact size the canvas should have)."""
    rep: dict = {"mode": grid, "factor": factor}
    if grid == "detect":
        g = detect_grid(img.convert("RGBA"), smin=max(1.0, factor / 2), smax=factor * 2.0)
        rep["detected"] = g.to_dict()
        small = downscale(img.convert("RGBA"), g.scale_x, g.scale_y, g.off_x, g.off_y, centre=1.0)
        if target and small.size != tuple(target):
            small = small.resize(tuple(target), Image.NEAREST)
            rep["resized_to"] = list(target)
    else:
        small = downscale_fixed(img, factor)
    if key is not None:
        small = key_to_alpha(small, key, key_tol)
    if palette:
        small = quantize(small, palette=palette)
        rep["palette"] = f"fixed-{len(palette)}"
    elif colours:
        small = quantize(small, colours=colours)
        rep["palette"] = f"adaptive-{colours}"
    else:
        rep["palette"] = "none"
    if cleanup_level:
        small = cleanup(small, min_island=4 if cleanup_level == 1 else 8, orphans=True)
    a = to_rgba_array(small)
    rep["colours_used"] = int(len(np.unique(a[a[..., 3] == 255][:, :3], axis=0)))
    rep["size"] = list(small.size)
    return small, rep


def scale_for_height(img: Image.Image, target_h: int) -> float:
    """Grid size that maps the opaque bounding box height onto ``target_h``."""
    a = to_rgba_array(img)
    ys = np.nonzero(a[..., 3].max(1) >= 128)[0]
    if len(ys) == 0:
        raise ValueError("image is fully transparent")
    return (ys[-1] - ys[0] + 1) / target_h


def opaque_bbox(a: np.ndarray):
    ys, xs = np.nonzero(a[..., 3] >= 128)
    if len(ys) == 0:
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


# ----------------------------------------------------------- 4. palette
def load_palette(path: str | Path) -> list[tuple[int, int, int]]:
    p = Path(path)
    cols: list[tuple[int, int, int]] = []
    if p.suffix.lower() == ".png":
        a = to_rgba_array(Image.open(p))
        u = np.unique(a[a[..., 3] == 255][:, :3], axis=0)
        return [tuple(int(v) for v in c) for c in u]
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";", "GIMP", "Name:", "Columns:")):
            continue
        if p.suffix.lower() == ".gpl":
            parts = line.split()
            if len(parts) >= 3 and all(x.isdigit() for x in parts[:3]):
                cols.append(tuple(int(x) for x in parts[:3]))
        else:
            h = line.lstrip("#")[:6]
            cols.append((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
    return cols


def save_palette_hex(cols, path) -> None:
    Path(path).write_text("".join(f"{r:02x}{g:02x}{b:02x}\n" for r, g, b in cols))


def quantize(img: Image.Image, colours: int | None = 16,
             palette: list[tuple[int, int, int]] | None = None) -> Image.Image:
    """Quantise opaque pixels, no dithering. Alpha is kept as is."""
    a = to_rgba_array(img)
    op = a[..., 3] == 255
    if not op.any():
        return img
    if palette:
        pal = np.array(palette, np.float32)
        px = a[op][:, :3].astype(np.float32)
        d = ((px[:, None, :] - pal[None]) ** 2).sum(-1)
        a[op, :3] = pal[d.argmin(1)].astype(np.uint8)
        return Image.fromarray(a)
    px = a[op][:, :3]
    strip = Image.fromarray(px.reshape(1, -1, 3))
    n = min(colours or 16, len(np.unique(px, axis=0)))
    q = strip.quantize(colors=max(n, 1), method=Image.Quantize.MEDIANCUT,
                       kmeans=2, dither=Image.Dither.NONE).convert("RGB")
    a[op, :3] = np.array(q).reshape(-1, 3)
    return Image.fromarray(a)


# ----------------------------------------------------------- 5. cleanup
def cleanup(img: Image.Image, min_island: int = 4, orphans: bool = True,
            keep_largest: bool = False, fill_holes: int = 2) -> Image.Image:
    a = to_rgba_array(img)
    op = a[..., 3] == 255
    comps = _components(op)
    if comps:
        biggest = max(len(c) for c in comps)
        for c in comps:
            if len(c) < min_island or (keep_largest and len(c) < biggest):
                for y, x in c:
                    a[y, x, 3] = 0
    # tiny enclosed transparent holes -> fill with the neighbour colour
    tr = a[..., 3] == 0
    if fill_holes:
        for c in _components(tr):
            if len(c) <= fill_holes:
                ys, xs = zip(*c)
                if min(ys) > 0 and min(xs) > 0 and max(ys) < a.shape[0] - 1 and max(xs) < a.shape[1] - 1:
                    for y, x in c:
                        nb = [tuple(a[y + dy, x + dx]) for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1))
                              if a[y + dy, x + dx, 3] == 255]
                        if nb:
                            a[y, x] = Counter(nb).most_common(1)[0][0]
    if orphans:
        h, w = a.shape[:2]
        src = a.copy()
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                if src[y, x, 3] != 255:
                    continue
                me = tuple(src[y, x])
                nb = [tuple(src[y + dy, x + dx]) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                      if (dy or dx)]
                if me in nb:
                    continue
                col, cnt = Counter(nb).most_common(1)[0]
                if cnt >= 6 and col[3] == 255:
                    a[y, x] = col
    return Image.fromarray(a)


# ----------------------------------------------------------- 6. outline
def add_outline(img: Image.Image, colour=OUTLINE, mode: str = "outer") -> Image.Image:
    """``outer``: grow 1px (canvas padded by 1). ``inner``: recolour the
    silhouette's boundary pixels instead (size unchanged)."""
    a = to_rgba_array(img)
    if mode == "outer":
        a = np.pad(a, ((1, 1), (1, 1), (0, 0)))
        op = a[..., 3] == 255
        ring = _dilate4(op) & ~op
        a[ring] = (*colour, 255)
    else:
        op = a[..., 3] == 255
        inner = op & _shift(op, 1, 0) & _shift(op, -1, 0) & _shift(op, 0, 1) & _shift(op, 0, -1)
        a[op & ~inner] = (*colour, 255)
    return Image.fromarray(a)


# -------------------------------------------------------------- 7. cell
def cell_scale(cell) -> float:
    """Size factor of a character cell relative to the 64x128 reference (96x192 -> 1.5)."""
    return cell[0] / CHAR_CELL[0]


def char_top_row(cell=CHAR_CELL) -> int:
    """Top of the head in a cell, scaled from the 64x128 reference (17 -> 26 at 96x192)."""
    return int(round(CHAR_TOP_ROW * cell_scale(cell)))


def shadow_geometry(cell=CHAR_CELL, feet_row: int | None = None):
    """(centre, radii) of the drop shadow for ``cell``. The centre sits ``3 * k`` rows above
    ``feet_row``. A 64x128 cell always gets exactly SHADOW_CENTRE / SHADOW_RADII;
    for any other cell it scales with the width; for 96x192 and feet row 157 it is (47.5, 152.5) with radii (33.75, 17.25)."""
    if tuple(cell) == CHAR_CELL:
        return SHADOW_CENTRE, SHADOW_RADII
    k = cell_scale(cell)
    if feet_row is None:
        feet_row = int(round(CHAR_FEET_ROW * k))
    return ((cell[0] - 1) / 2, feet_row - 3 * k), (SHADOW_RADII[0] * k, SHADOW_RADII[1] * k)


def shadow_layer(cell=CHAR_CELL, centre=None, radii=None, feet_row: int | None = None) -> np.ndarray:
    w, h = cell
    c0, r0 = shadow_geometry(cell, feet_row)
    centre = centre or c0
    radii = radii or r0
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((xx - centre[0]) / radii[0]) ** 2 + ((yy - centre[1]) / radii[1]) ** 2 <= 1.0
    inner = m & _shift(m, 1, 0) & _shift(m, -1, 0) & _shift(m, 0, 1) & _shift(m, 0, -1)
    sh = np.zeros((h, w, 4), np.uint8)
    sh[m] = SHADOW_FILL
    sh[m & ~inner & (yy < centre[1])] = SHADOW_RIM
    return sh


def fit_cell(img: Image.Image, cell=CHAR_CELL, feet_row: int | None = CHAR_FEET_ROW,
             shadow: bool = False) -> tuple[Image.Image, dict]:
    """Crop to content and paste into ``cell``: centred horizontally, the
    lowest opaque row on ``feet_row`` (or vertically centred if None).
    Content larger than the cell is clipped and reported, never resampled."""
    a = to_rgba_array(img)
    w, h = cell
    bb = opaque_bbox(a)
    out = np.zeros((h, w, 4), np.uint8)
    info = {"clipped": False}
    if bb is None:
        return Image.fromarray(out), info
    x0, y0, x1, y1 = bb
    sub = a[y0:y1, x0:x1]
    sh, sw = sub.shape[:2]
    dx = (w - sw) // 2
    dy = (feet_row + 1 - sh) if feet_row is not None else (h - sh) // 2
    info.update(content_size=[int(sw), int(sh)], offset=[int(dx), int(dy)])
    ys0, xs0 = max(0, -dy), max(0, -dx)
    ys1, xs1 = min(sh, h - dy), min(sw, w - dx)
    if ys0 or xs0 or ys1 < sh or xs1 < sw:
        info["clipped"] = True
    if shadow:
        out[:] = shadow_layer(cell, feet_row=feet_row)
    part = sub[ys0:ys1, xs0:xs1]
    dst = out[dy + ys0:dy + ys1, dx + xs0:dx + xs1]
    m = part[..., 3] == 255
    dst[m] = part[m]
    return Image.fromarray(out), info


# --------------------------------------------------------- full pipeline
def run_pipeline(img: Image.Image, *, grid: str = "auto", bg: str = "auto",
                 colours: int | None = 16, palette: str | None = None,
                 outline: str | None = "outer", cell: tuple[int, int] | None = None,
                 feet_row: int | None = None, shadow: bool = False,
                 keep_largest: bool = False, cleanup_level: int = 1,
                 tile: bool = False, tile_mode: str = "crop",
                 keep_dark: float | None = 0.3,
                 grid_max: float = 32.0) -> tuple[Image.Image, dict]:
    """Run every stage. ``grid``: "auto", a number (pixel size) or "fit"
    (choose the pixel size so the subject fills ``cell``'s character height,
    or the cell itself for tiles). Returns (image, report)."""
    rep: dict = {}
    work = img
    if bg != "none" and not tile:
        work, rep["background"] = remove_background(work)
    else:
        work = work.convert("RGBA")

    if tile:
        # Tiles: whole image becomes exactly cell (e.g. 16x16), mode per cell.
        # tile_mode "resample": the whole image becomes one cell-sized tile.
        # tile_mode "crop": snap to the detected native grid, then take the
        # centre cell-sized crop (keeps the model's pixel detail; not seamless
        # unless the texture happens to be).
        tw, th = cell or (16, 16)
        if tile_mode == "resample":
            sx, sy = work.width / tw, work.height / th
            small = downscale(work, sx, sy, 0, 0)
            rep["grid"] = {"scale_x": round(sx, 3), "scale_y": round(sy, 3), "mode": "tile-resample"}
        else:
            g = detect_grid(work, smax=grid_max) if grid == "auto" else None
            s_ = g.scale_x if g else float(grid)
            big = downscale(work, s_, s_, g.off_x if g else 0, g.off_y if g else 0)
            cx, cy = (big.width - tw) // 2, (big.height - th) // 2
            small = big.crop((cx, cy, cx + tw, cy + th))
            rep["grid"] = (g.to_dict() if g else {"scale": s_}) | {"mode": "tile-crop",
                                                                 "native_texture": list(big.size)}
    else:
        if grid == "auto":
            g = detect_grid(work, smax=grid_max)
            rep["grid"] = g.to_dict() | {"mode": "auto"}
            small = downscale(work, g.scale_x, g.scale_y, g.off_x, g.off_y, keep_dark=keep_dark)
        elif grid == "fit":
            if cell is None:
                raise ValueError("grid=fit needs a cell")
            target_h = (feet_row - char_top_row(cell) + 1) if feet_row is not None else cell[1]
            target_h -= 2 if outline == "outer" else 0
            s = scale_for_height(work, target_h)
            bb = opaque_bbox(to_rgba_array(work))
            s = max(s, (bb[2] - bb[0]) / (cell[0] - (2 if outline == "outer" else 0)))
            small = downscale(work, s, s, bb[0], bb[1], keep_dark=keep_dark)
            rep["grid"] = {"scale": round(float(s), 3), "mode": "fit", "target_h": target_h}
        else:
            s = float(grid)
            small = downscale(work, s, s, 0, 0, keep_dark=keep_dark)
            rep["grid"] = {"scale": s, "mode": "fixed"}
    rep["native_size"] = list(small.size)

    pal = load_palette(palette) if palette else None
    small = quantize(small, colours=colours, palette=pal)
    rep["palette"] = palette or f"adaptive-{colours}"
    if cleanup_level and not tile:
        small = cleanup(small, min_island=4 if cleanup_level == 1 else 8,
                        orphans=True, keep_largest=keep_largest)
    if outline and not tile:
        small = add_outline(small, mode=outline)
    if cell and not tile:
        small, rep["cell"] = fit_cell(small, cell, feet_row, shadow)
    a = to_rgba_array(small)
    rep["colours_used"] = int(len(np.unique(a[a[..., 3] == 255][:, :3], axis=0)))
    rep["final_size"] = list(small.size)
    return small, rep
