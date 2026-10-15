#!/usr/bin/env python3
"""Build the realistic 96x192 character sheets (player, Samantha) from raw FLUX key frames.

Usage (any Python with numpy + Pillow; tools/artgen/.venv works):
    python tools/sprite_gen/realistic/build_sheets.py player OUT.png [--raw DIR] [--work DIR]
    python tools/sprite_gen/realistic/build_sheets.py samantha OUT.png ...

Spec: openspec/changes/realistic-character-sprites design D1, D2, D4.
  960x2304 sheet, 96x192 cells, 10 columns x 12 rows (idle 0-3, walk 4-7, run 8-11; down, left, right, up).
  Feet (lowest opaque row) on row 157, figure centred on x = 47.5, project drop shadow (artgen postprocess).

Per raw frame (equivalent to
`artgen.py post RAW --grid N --cell 96x192 --feet-row 157 --shadow --outline inner --colours 24 --keep-largest`,
run through artgen's postprocess module so the steps below can be added):
  1. clean_raw: the painted floor shadow is turned into background white.
  2. eye boost: the model's thin eyes vanish at N ~ 7.3, so on front/side frames each iris blob is
     repainted as a grid-aligned 2-row block (dark lid row over an iris row) before downscaling.
  3. postprocess.run_pipeline with grid N (one N per character and view, RECIPES below), the shared
     character palette (pass 1 builds it from the three standing frames with 24 adaptive colours).
  4. horizontal re-centring on the head/shoulder mass instead of the bounding box (no torso jitter
     when an arm or leg swings out); the project shadow is added after that.

Frames (design D2): side walk = generated contact/passing poses (A, A' second contact seed, P, P');
front/back walk = scripted warps of the standing frame (leg shortening = foot lift, 1 px bob,
arm swing), A'/P' are horizontal mirrors. Left rows are mirrors of right rows. Idle columns 4-7 are
the breathing still (head and shoulders 1 row lower). Run rows reuse walk poses (A A P P A' A' P' P').

Raw frames live in art/characters/<name>/keys/ (tracked project data, not in assets/); the generation job lists are kept next
to this script (art/jobs/*.json) so they can be regenerated with tools/artgen/out/sam_art/flux_batch.py.
"""
import argparse
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "artgen"))
import postprocess as pp  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_raw import clean  # noqa: E402

CW, CH, COLS, ROWS = 96, 192, 10, 12
FEET = 157
CELL = (CW, CH)
LASH = (34, 28, 40)
MATS_HAIR_DARK = (74, 46, 36)
MOUTH = (176, 104, 98)

# N: raw px per art px, measured on the standing FLUX frame of each view (height / target rows).
RECIPES = {
    "player": {
        "target_h": 132,
        "raw": "art/characters/player/keys",
        "N": {"front": 7.36, "side": 7.36, "back": 7.36},  # 972/132; views agree within 0.5 %
        "iris": "green",
        "frames": {
            "front": "player_front_idle_s11.png",
            "side": "player_side_idle_s11.png",
            "back": "player_back_idle_s11.png",
            "side_A": "player_side_contact_s11.png",
            "side_A2": "player_side_contact_s12.png",
            "side_P": "player_side_passing_s11.png",
            "side_P2": "player_side_passing_s12.png",
        },
    },
    "samantha": {
        "target_h": 126,
        "raw": "art/characters/samantha/keys",
        "N": {"front": 7.48, "side": 7.29, "back": 7.33},  # per view: 943/919/924 raw rows / 126 (views differ 2.6 %)
        "iris": "blue",
        "clean_grey": False,  # white sneakers
        "frames": {
            "front": "sam_front_idle_s11.png",  # grey top, jacket open (FLUX, ref sam_front_greytop_s12)
            "side": "sam_side_idle_s11.png",
            "back": "sam_back_idle_s11.png",
            "side_A": "sam_side_contact_s11.png",
            "side_A2": "sam_side_contact_s12.png",
            "side_P": "sam_side_passing_s11.png",
            "side_P2": "sam_side_passing_s12.png",
        },
    },
}


# ------------------------------------------------------------- raw prep --
def figure_bbox(rgb):
    fg = (rgb[..., 3] == 255) if rgb.shape[-1] == 4 else (rgb.min(-1) < 225)
    ys = np.where(fg.sum(1) > 2)[0]
    xs = np.where(fg.sum(0) > 2)[0]
    return ys.min(), ys.max(), xs.min(), xs.max()


def components(mask):
    h, w = mask.shape
    seen = np.zeros_like(mask)
    out = []
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        q = deque([(y, x)])
        seen[y, x] = True
        pts = []
        while q:
            cy, cx = q.popleft()
            pts.append((cy, cx))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = cy + dy, cx + dx
                    if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        q.append((yy, xx))
        out.append(np.array(pts))
    return out


def boost_eyes(rgb, N, iris, max_eyes):
    """Repaint each iris as a 2-row grid-aligned block so it survives the downscale."""
    top, bot, _, _ = figure_bbox(rgb)
    a = rgb[..., :3].astype(int)
    H = bot - top
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    if iris == "green":
        m = (g > r + 25) & (g > b + 5) & (sat > 0.3)
    else:
        m = (b > r + 35) & (b > g + 5) & (sat > 0.3)
    region = np.zeros_like(m)
    region[top + int(0.05 * H): top + int(0.14 * H)] = True
    m &= region
    blobs = sorted((c for c in components(m) if len(c) >= 6), key=len, reverse=True)[:max_eyes]
    out = rgb.copy()
    found = []
    for c in blobs:
        cy, cx = c[:, 0].mean(), c[:, 1].mean()
        col = np.median(a[c[:, 0], c[:, 1]], axis=0).astype(np.uint8)
        c1 = int(np.floor(cx / N))
        r1 = int(np.floor(cy / N))
        cols = (c1,) if max_eyes == 1 else (c1 - 1, c1) if (cx / N - c1) < 0.5 else (c1, c1 + 1)
        for k, (row, colr) in enumerate(((r1 - 1, LASH), (r1, tuple(col)))):
            for cc in cols:
                y0, y1 = int(round(row * N)), int(round((row + 1) * N))
                x0, x1 = int(round(cc * N)), int(round((cc + 1) * N))
                out[y0:y1, x0:x1, :3] = colr
        found.append((round(cx), round(cy)))
    return out, found


# --------------------------------------------------------------- post ----
def post(raw_rgb, N, palette=None, colours=24):
    img = Image.fromarray(raw_rgb)
    if palette is not None and not isinstance(palette, (str, Path)):
        import tempfile
        tf = Path(tempfile.mkstemp(suffix=".hex")[1])
        pp.save_palette_hex(palette, tf)
        palette = str(tf)
    small, rep = pp.run_pipeline(img, grid=str(N), bg="auto", colours=colours, palette=palette,
                                 outline="inner", cell=CELL, feet_row=FEET, shadow=False,
                                 keep_largest=True, keep_dark=0.3)
    return np.array(small.convert("RGBA")), rep


def recentre(cell):
    """Shift horizontally so the head/shoulder mass (top 40 rows of the figure) is centred on 47.5."""
    op = cell[..., 3] == 255
    ys = np.where(op.any(1))[0]
    band = op[ys.min(): ys.min() + 40]
    xs = np.nonzero(band)[1]
    dx = int(round(47.5 - (xs.min() + xs.max()) / 2))
    return np.roll(cell, dx, axis=1), dx


def with_shadow(fig):
    sh = pp.shadow_layer(CELL, feet_row=FEET)
    out = sh.copy()
    a = fig[..., 3] == 255
    out[a] = fig[a]
    return out


# ---------------------------------------------------------------- face ---
def is_iris(rgb, iris):
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    if iris == "green":
        return (g > r + 25) & (g > b + 5)
    return (b > r + 35) & (b > g + 5)


def lum(rgb):
    return rgb[..., :3].astype(int) @ np.array([299, 587, 114]) // 1000


def face_fix(cell, iris, front):
    """Clear the dark band the downscale makes of brows + lids + fringe outlines, then redraw a small face:
    brow row (dark hair), a skin row, lid row (dark) over the surviving iris row; on fronts a 2 px mouth."""
    out = cell.copy()
    op = out[..., 3] == 255
    ys = np.where(op.any(1))[0]
    top = ys.min()
    head = np.zeros(op.shape, bool)
    head[top: top + 26] = True
    irm = is_iris(out, iris) & op & head
    if not irm.any():
        return out, None
    r = int(np.nonzero(irm)[0].min())
    xs = np.unique(np.nonzero(irm[r])[0])
    if len(xs) == 0:
        return out, None
    # eyes = runs of iris columns
    eyes, run = [], [xs[0]]
    for x in xs[1:]:
        if x - run[-1] <= 1:
            run.append(x)
        else:
            eyes.append(run)
            run = [x]
    eyes.append(run)
    # skin colour: most common bright warm colour below the eyes
    below = out[r + 2: r + 6][op[r + 2: r + 6]][:, :3]
    warm = below[(below[:, 0].astype(int) > 180) & (below[:, 0].astype(int) > below[:, 2].astype(int) + 20)]
    if len(warm) == 0:
        return out, None
    cols, cnt = np.unique(warm, axis=0, return_counts=True)
    skin = cols[cnt.argmax()]
    # face span on the eye row
    row_op = np.nonzero(op[r])[0]
    fl, fr = row_op.min(), row_op.max()
    dark = lum(out) < 60
    if front:
        span = range(fl + 2, fr - 1)
    else:  # profile: only around the eye, the temple hair stays
        allx = [x for e in eyes for x in e]
        span = range(min(allx) - 2, max(allx) + 3)
    for y in range(r - 4, r):
        for x in span:
            if dark[y, x] and op[y, x]:
                out[y, x, :3] = skin
    hair = MATS_HAIR_DARK
    for e in eyes:
        x0, x1 = min(e), max(e)
        if len(e) == 1:  # widen single-pixel eyes to 2 (front) towards the face centre
            x1 = x0 + (1 if (x0 < (fl + fr) / 2) else 0)
            x0 = x0 - (0 if (x0 < (fl + fr) / 2) else 1)
        for x in range(x0, x1 + 1):
            out[r - 1, x, :3] = LASH
            out[r, x, :3] = out[r, x, :3] if irm[r, x] else out[r, e[0], :3]
        for x in range(x0 - 1, x1 + 2):
            out[r - 3, x, :3] = hair
        out[r - 2, x0 - 1: x1 + 2, :3] = skin
    if front and len(eyes) == 2:
        cx = (max(eyes[0]) + min(eyes[1])) / 2
        chin = r + 9
        ym = r + 6
        out[ym, int(np.floor(cx)): int(np.floor(cx)) + 2, :3] = MOUTH
    return out, {"eye_row": r, "eyes": [[int(min(e)), int(max(e))] for e in eyes]}


# --------------------------------------------------------------- warps ---
def legs_split(cell):
    """Rows and columns of the legs in a front/back standing frame."""
    op = cell[..., 3] == 255
    ys = np.where(op.any(1))[0]
    top, feet = ys.min(), ys.max()
    H = feet - top
    crotch = top + int(round(0.56 * H))
    # gap between the legs: the most central transparent column run in the lower legs
    lower = op[feet - int(0.25 * H): feet - 4]
    occ = lower.any(0)
    xs = np.where(occ)[0]
    mid = (xs.min() + xs.max()) / 2
    gaps = [x for x in range(xs.min(), xs.max()) if not lower[:, x].any()]
    split = int(round(min(gaps, key=lambda x: abs(x - mid)))) if gaps else int(round(mid))
    return top, feet, crotch, split


def lift_leg(cell, x0, x1, crotch, feet, k):
    """Shorten the leg in columns [x0, x1) by k rows (drop k rows at the shin): the foot rises by k."""
    out = cell.copy()
    seg = cell[crotch:feet + 1, x0:x1].copy()
    n = seg.shape[0]
    if k <= 0:
        return out
    # drop k rows spread over the lower half (the shin), keep the shoe intact
    drop = set(np.linspace(n * 0.45, n * 0.8, k).round().astype(int).tolist())
    keep = [i for i in range(n) if i not in drop]
    new = seg[keep]
    out[crotch:feet + 1, x0:x1] = 0
    out[crotch:crotch + new.shape[0], x0:x1] = new
    return out


def shift_rows(cell, y0, y1, dy):
    """Move rows [y0, y1) by dy (positive = down); rows left uncovered at the seam keep their original
    content, so the figure stretches by |dy| there instead of tearing."""
    out = cell.copy()
    out[y0:y1] = 0
    for y in range(y0, y1):
        t = y + dy
        if 0 <= t < cell.shape[0]:
            out[t] = cell[y]
    covered = set(range(y0 + dy, y1 + dy))
    for y in range(y0, y1):
        if y not in covered:
            out[y] = cell[y]
    return out


def arm_swing(cell, side_cols, top, crotch, dy):
    """Move the hand/forearm block in the given column range by dy rows (negative = up = swinging forward)."""
    x0, x1 = side_cols
    y0 = top + int(round(0.42 * (crotch - top) / 0.56))  # elbow height
    y1 = crotch + int(round(0.12 * (crotch - top) / 0.56))
    out = cell.copy()
    seg = cell[y0:y1, x0:x1].copy()
    out[y0:y1, x0:x1] = 0
    yy0, yy1 = max(0, y0 + dy), y1 + dy
    s0 = yy0 - (y0 + dy)
    out[yy0:yy1, x0:x1] = seg[s0:]
    if dy < 0:  # keep the sleeve connected: repeat the first row into the gap
        out[y1 + dy:y1, x0:x1] = np.where(out[y1 + dy:y1, x0:x1, 3:4] == 255, out[y1 + dy:y1, x0:x1], 0)
    else:
        out[y0:y0 + dy, x0:x1] = np.repeat(seg[:1], dy, axis=0)
    return out


def arm_columns(cell, top, crotch):
    """Outer columns holding the arms at hand height (left, right)."""
    op = cell[..., 3] == 255
    yh = crotch - 2
    xs = np.where(op[yh - 6: yh + 6].any(0))[0]
    # the torso: columns occupied at the chest row
    chest = top + int(round(0.30 * (crotch - top) / 0.56))
    tx = np.where(op[chest])[0]
    w = max(6, int(round((tx.max() - tx.min()) * 0.2)))
    return (xs.min(), xs.min() + w), (xs.max() - w + 1, xs.max() + 1)


def walk_front(cell, kind):
    """kind 'A': contact, the figure's right leg (viewer's left) trailing with the heel up, its
    opposite arm forward; 'P': passing, legs together, the trailing foot just off the ground, body 1 row up."""
    top, feet, crotch, split = legs_split(cell)
    left_cols, right_cols = arm_columns(cell, top, crotch)
    out = cell.copy()
    if kind == "A":
        out = lift_leg(out, 0, split, crotch, feet, WARP["A_lift"])
        out = shift_cols(out, 0, split, crotch + (feet - crotch) // 2, feet + 1, 1)  # trailing foot tucks in
        out = arm_swing(out, right_cols, top, crotch, -WARP["arm_fwd"])  # arm opposite the trailing leg forward
        out = arm_swing(out, left_cols, top, crotch, WARP["arm_back"])
    else:
        out = lift_leg(out, 0, split, crotch, feet, WARP["P_lift"])
        out = shift_rows(out, 0, crotch, -1)               # body up 1 (bob)
    return out


WARP = {"A_lift": 6, "P_lift": 3, "arm_fwd": 3, "arm_back": 1}


def shift_cols(cell, x0, x1, y0, y1, dx):
    out = cell.copy()
    seg = cell[y0:y1, x0:x1].copy()
    out[y0:y1, x0:x1] = 0
    out[y0:y1, x0 + dx:x1 + dx] = np.where(seg[..., 3:4] == 255, seg, out[y0:y1, x0 + dx:x1 + dx])
    return out


def breathing(cell):
    """Head and shoulders 1 row lower."""
    op = cell[..., 3] == 255
    ys = np.where(op.any(1))[0]
    top, feet = ys.min(), ys.max()
    split = top + int(round(0.30 * (feet - top)))
    out = cell.copy()
    out[top + 1:split + 1] = cell[top:split]
    out[top] = 0
    return out


def mirror(cell):
    return cell[:, ::-1].copy()


# --------------------------------------------------------------- build ---
def load_raw(path):
    return np.array(Image.open(path).convert("RGB"))


def process(rec, raw_dir, name, view, palette, work, log):
    raw = load_raw(raw_dir / rec["frames"][name])
    raw, n_sh = clean(raw, rec.get("clean_grey", True))
    eyes = []
    if view in ("front", "side"):
        raw, eyes = boost_eyes(raw, rec["N"][view], rec["iris"], 2 if view == "front" else 1)
    cell, rep = post(raw, rec["N"][view], palette=palette)
    face = None
    if view in ("front", "side"):
        cell, face = face_fix(cell, rec["iris"], view == "front")
    cell, dx = recentre(cell)
    if work:
        Image.fromarray(cell).save(work / f"{name}.png")
    op = cell[..., 3] == 255
    ys = np.where(op.any(1))[0]
    log[name] = {"file": rec["frames"][name], "N": rec["N"][view], "shadow_px_removed": n_sh, "eyes_raw": eyes,
                 "top": int(ys.min()), "feet": int(ys.max()), "height": int(ys.max() - ys.min() + 1),
                 "recentre_dx": dx, "face": face, "clipped": rep.get("cell", {}).get("clipped")}
    return cell


def build(char, raw_dir=None, work=None):
    rec = RECIPES[char]
    raw_dir = Path(raw_dir) if raw_dir else REPO / rec["raw"]
    if work:
        work = Path(work)
        work.mkdir(parents=True, exist_ok=True)
    log = {}
    # pass 1: palette from the three standing frames
    pal_cells = []
    for view in ("front", "side", "back"):
        raw = load_raw(raw_dir / rec["frames"][view])
        raw, _ = clean(raw, rec.get("clean_grey", True))
        if view != "back":
            raw, _ = boost_eyes(raw, rec["N"][view], rec["iris"], 2 if view == "front" else 1)
        c, _ = post(raw, rec["N"][view], palette=None, colours=24)
        pal_cells.append(c[c[..., 3] == 255][:, :3])
    palette = [tuple(int(v) for v in c) for c in np.unique(np.concatenate(pal_cells), axis=0)]
    log["palette_colours"] = len(palette)
    # pass 2: all frames with the shared palette
    F = {}
    for name in rec["frames"]:
        view = "side" if name.startswith("side") else name
        F[name] = process(rec, raw_dir, name, view, palette, work, log)

    S = {"down": F["front"], "up": F["back"], "right": F["side"]}
    walk = {}
    for d, base in (("down", F["front"]), ("up", F["back"])):
        A = walk_front(base, "A")
        P = walk_front(base, "P")
        walk[d] = (A, P, mirror(A), mirror(P))
    walk["right"] = (F["side_A"], F["side_P"], F["side_A2"], F["side_P2"])

    sheet = np.zeros((CH * ROWS, CW * COLS, 4), np.uint8)

    def put(row, col, fig):
        sheet[row * CH:(row + 1) * CH, col * CW:(col + 1) * CW] = with_shadow(fig)

    order = ("down", "left", "right", "up")
    for di, d in enumerate(order):
        src = "right" if d == "left" else d
        flip = d == "left"
        st = S[src]
        br = breathing(st)
        idle = [st] * 4 + [br] * 4
        A, P, A2, P2 = walk[src]
        wk = [A, A, A, P, P, A2, A2, A2, P2, P2]
        rn = [A, A, P, P, A2, A2, P2, P2]
        for c, f in enumerate(idle):
            put(di, c, mirror(f) if flip else f)
        for c, f in enumerate(wk):
            put(4 + di, c, mirror(f) if flip else f)
        for c, f in enumerate(rn):
            put(8 + di, c, mirror(f) if flip else f)
    return sheet, log


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("char", choices=sorted(RECIPES))
    ap.add_argument("out")
    ap.add_argument("--raw", help="raw key-frame directory (default: the recipe's)")
    ap.add_argument("--work", help="write the processed single cells here")
    a = ap.parse_args()
    sheet, log = build(a.char, a.raw, a.work)
    Image.fromarray(sheet).save(a.out)
    if a.work:
        (Path(a.work) / "build.json").write_text(json.dumps(log, indent=1))
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: v[kk] for kk in ('top', 'feet', 'height', 'N')})
                      for k, v in log.items()}, indent=None))
    print("wrote", a.out, sheet.shape[1], "x", sheet.shape[0])


if __name__ == "__main__":
    main()
