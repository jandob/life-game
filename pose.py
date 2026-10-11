"""Draw OpenPose-style skeleton images (the control input of the OpenPose ControlNet).

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
        (0.60, 0.55), (0.45, 0.58), (0.40, 0.67), (0.43, 0.88), (0.55, 0.58), (0.60, 0.67), (0.57, 0.88),
        (0.48, 0.185), (0.52, 0.185), (0.45, 0.195), (0.55, 0.195)],
}


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
