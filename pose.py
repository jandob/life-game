"""Draw OpenPose-style skeleton images (the pose strip that the `sheet` command feeds to qwen_image21 as a reference).

No annotator model is needed: poses are defined as 18 COCO/OpenPose keypoints in
unit coordinates (x, y in 0..1 of the canvas, y down) and drawn the way the
OpenPose renderer does (coloured limbs as ellipses, coloured joint dots, black
background). Missing joints are ``null`` and their limbs are skipped.

    artgen.py pose --preset stand_front --size 832x1216 --out pose.png
    artgen.py pose --keypoints my_pose.json --size 832x1216 --out pose.png   # JSON: list of 18 [x, y] or null

Keypoint order: 0 nose, 1 neck, 2 r.shoulder, 3 r.elbow, 4 r.wrist, 5 l.shoulder,
6 l.elbow, 7 l.wrist, 8 r.hip, 9 r.knee, 10 r.ankle, 11 l.hip, 12 l.knee, 13 l.ankle,
14 r.eye, 15 l.eye, 16 r.ear, 17 l.ear. "r" is the person's right (left side of the
image when they face the viewer).
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

LIMBS = [(1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10), (1, 11),
         (11, 12), (12, 13), (1, 0), (0, 14), (14, 16), (0, 15), (15, 17)]
COLORS = [(255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0),
          (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
          (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85)]

# Full-body presets, canvas-relative. The figure spans about 80 % of the height.
PRESETS: dict[str, list] = {
    "stand_front": [
        (0.50, 0.14), (0.50, 0.22), (0.41, 0.23), (0.37, 0.37), (0.35, 0.50), (0.59, 0.23), (0.63, 0.37),
        (0.65, 0.50), (0.45, 0.52), (0.45, 0.72), (0.45, 0.91), (0.55, 0.52), (0.55, 0.72), (0.55, 0.91),
        (0.48, 0.125), (0.52, 0.125), (0.45, 0.135), (0.55, 0.135)],
    "stand_front_arms_out": [
        (0.50, 0.14), (0.50, 0.22), (0.41, 0.23), (0.30, 0.33), (0.20, 0.42), (0.59, 0.23), (0.70, 0.33),
        (0.80, 0.42), (0.45, 0.52), (0.44, 0.72), (0.43, 0.91), (0.55, 0.52), (0.56, 0.72), (0.57, 0.91),
        (0.48, 0.125), (0.52, 0.125), (0.45, 0.135), (0.55, 0.135)],
    "stand_side": [   # facing the image's right; right limbs omitted from view
        (0.56, 0.14), (0.50, 0.22), (0.50, 0.23), (0.51, 0.37), (0.56, 0.49), (0.50, 0.23), (0.50, 0.37),
        (0.54, 0.49), (0.49, 0.52), (0.50, 0.72), (0.49, 0.91), (0.49, 0.52), (0.51, 0.72), (0.52, 0.91),
        (0.58, 0.125), None, (0.51, 0.135), None],
    "sit_front": [    # seated, thighs foreshortened towards the viewer, knees out
        (0.50, 0.20), (0.50, 0.29), (0.41, 0.30), (0.37, 0.43), (0.40, 0.55), (0.59, 0.30), (0.63, 0.43),
        (0.60, 0.55), (0.45, 0.58), (0.40, 0.64), (0.42, 0.86), (0.55, 0.58), (0.60, 0.64), (0.58, 0.86),
        (0.48, 0.185), (0.52, 0.185), (0.45, 0.195), (0.55, 0.195)],
}


def walk_side(phase: int) -> list:
    """Side-view walk cycle frame 0..3 (facing right): contact, passing, contact (legs swapped), passing."""
    ph = phase * math.pi / 2
    a = math.radians(30) * math.cos(ph)           # thigh angle of leg A from vertical (+ = forward)
    lift = max(0.0, math.sin(ph))                  # leg A lifts on the way forward
    liftb = max(0.0, -math.sin(ph))

    def leg(hip, ang, lf):
        k = (hip[0] + 0.20 * math.sin(ang), hip[1] + 0.20 * math.cos(ang))
        sa = ang - math.radians(10) - lf * math.radians(55)
        return k, (k[0] + 0.19 * math.sin(sa), k[1] + 0.19 * math.cos(sa))

    def arm(sh, ang):
        e = (sh[0] + 0.13 * math.sin(ang), sh[1] + 0.13 * math.cos(ang))
        fa = ang + math.radians(25)
        return e, (e[0] + 0.12 * math.sin(fa), e[1] + 0.12 * math.cos(fa))

    hip, sh = (0.49, 0.52), (0.50, 0.23)
    ka, aa = leg(hip, a, lift)
    kb, ab = leg(hip, -a, liftb)
    ea, wa = arm(sh, -a * 0.9)
    eb, wb = arm(sh, a * 0.9)
    return [(0.56, 0.14), (0.50, 0.22), sh, ea, wa, sh, eb, wb, hip, ka, aa, hip, kb, ab,
            (0.58, 0.125), None, (0.51, 0.135), None]


PRESETS.update({f"walk_side_{i}": walk_side(i) for i in range(4)})


def place(kps: list, ox: float, k: float = 0.85, canvas: tuple[int, int] = (1024, 768)) -> list:
    """Scale a portrait-canvas (832x1216) skeleton by ``k`` and centre it at x = ``ox`` on ``canvas``."""
    w, h = canvas
    ax = (832 / 1216) * (h / w) * k
    return [None if p is None else (ox + (p[0] - 0.5) * ax, 0.5 + (p[1] - 0.5) * k) for p in kps]


# Several people: list of skeletons (landscape 1024x768 canvas).
MULTI: dict[str, list] = {
    "sit_pair": [place(PRESETS["sit_front"], 0.38), place(PRESETS["sit_front"], 0.62)],
}


def draw_poses(people: list, size=(1024, 768)) -> Image.Image:
    """Several skeletons on one black canvas."""
    from PIL import ImageChops
    img = None
    for kps in people:
        one = draw_pose(kps, size)
        img = one if img is None else ImageChops.lighter(img, one)
    return img


def draw_pose(keypoints: list, size: tuple[int, int] = (832, 1216), stickwidth: int | None = None) -> Image.Image:
    """Render 18 keypoints (unit coordinates or None) as an OpenPose skeleton on black."""
    if len(keypoints) != 18:
        raise ValueError(f"need 18 keypoints, got {len(keypoints)}")
    w, h = size
    sw = stickwidth or max(2, round(min(w, h) / 100))
    img = Image.new("RGB", size, (0, 0, 0))
    pts = [None if k is None else (k[0] * w, k[1] * h) for k in keypoints]
    # limbs: draw each as a rotated ellipse on its own layer, dimmed like OpenPose (0.6)
    for (a, b), col in zip(LIMBS, COLORS):
        if pts[a] is None or pts[b] is None:
            continue
        (x1, y1), (x2, y2) = pts[a], pts[b]
        length = math.hypot(x2 - x1, y2 - y1)
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        layer = Image.new("RGB", size, (0, 0, 0))
        e = Image.new("L", (int(length) + 2 * sw + 2, 2 * sw + 2), 0)
        ImageDraw.Draw(e).ellipse((0, 0, e.width - 1, e.height - 1), fill=255)
        e = e.rotate(-angle, expand=True, resample=Image.BICUBIC)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        pos = (round(cx - e.width / 2), round(cy - e.height / 2))
        layer.paste(tuple(int(c * 0.6) for c in col), pos, e)
        img = Image.composite(layer, img, Image.eval(layer.convert("L"), lambda v: 255 if v else 0))
    d = ImageDraw.Draw(img)
    for p, col in zip(pts, COLORS):
        if p is not None:
            d.ellipse((p[0] - sw, p[1] - sw, p[0] + sw, p[1] + sw), fill=col)
    return img


def walk_side_frames(n: int, cell: tuple[int, int] = (384, 768)) -> list:
    """``n`` evenly spaced ``walk_side`` phases over one cycle, x corrected for the cell aspect.

    ``walk_side`` is drawn for an 832x1216 canvas; on another cell shape x is rescaled about the
    centre by ``k = (832/1216)/(cw/ch)`` so the figure keeps its proportions.
    """
    cw, ch = cell
    k = (832 / 1216) / (cw / ch)
    frames = []
    for i in range(n):
        kps = walk_side(4 * i / n)
        frames.append([None if p is None else (0.5 + (p[0] - 0.5) * k, p[1]) for p in kps])
    return frames


def strip(poses: list[list], cell: tuple[int, int] = (384, 768)) -> Image.Image:
    """N skeletons side by side (each in its own ``cell``) on black: an image of size (N*cw, ch)."""
    cw, ch = cell
    out = Image.new("RGB", (cw * len(poses), ch), (0, 0, 0))
    for i, kps in enumerate(poses):
        out.paste(draw_pose(kps, (cw, ch)), (i * cw, 0))
    return out
