#!/usr/bin/env python3
"""Procedural generator for the male player sprite sheet of Life Game.

Usage:
    python male_player.py OUTPUT.png [REFERENCE.png]

The sheet is 640x1536 RGBA: cells of 64x128, 10 columns x 12 rows.
  rows 0-3  idle  (8 frames)  down, left, right, up
  rows 4-7  walk  (10 frames) down, left, right, up
  rows 8-11 run   (8 frames)  down, left, right, up
Unused cells stay fully transparent.

The figure is drawn from simple shapes (ellipses, capsules, polygons) posed by
a tiny rig, then outlined and shaded per part with hard pixels. The drop
shadow is copied from the reference sheet (the female player) when it is
given, so the feet anchor and shadow match exactly; without a reference an
equivalent ellipse is drawn. Left-facing frames are mirrors of right-facing
ones.
"""
import math
import sys

import numpy as np
from PIL import Image, ImageDraw

CW, CH = 64, 128
COLS, ROWS = 10, 12
GROUND = 105  # lowest opaque row of the feet (matches the reference)

YY, XX = np.mgrid[0:CH, 0:CW]

# ---------------------------------------------------------------- palette --
NAVY = (34, 32, 52)
SKIN_OUT = (69, 33, 45)

# material: (light, base, shade, dark, outline)
MATS = {
    "skin": ((255, 236, 200), (255, 224, 177), (249, 191, 153), (245, 164, 137), SKIN_OUT),
    "skin_far": ((249, 191, 153), (245, 164, 137), (226, 140, 128), (203, 113, 115), SKIN_OUT),
    "tunic": ((140, 166, 98), (108, 138, 82), (80, 106, 70), (58, 78, 58), NAVY),
    "tunic_far": ((96, 124, 76), (80, 106, 70), (64, 88, 62), (52, 70, 54), NAVY),
    "pants": ((102, 104, 132), (80, 82, 108), (62, 64, 90), (50, 50, 74), NAVY),
    "pants_far": ((80, 82, 108), (64, 66, 92), (54, 54, 80), (46, 44, 68), NAVY),
    "boot": ((150, 102, 68), (118, 78, 52), (90, 58, 44), (66, 42, 38), NAVY),
    "boot_far": ((118, 78, 52), (96, 62, 46), (78, 50, 40), (62, 40, 36), NAVY),
    "hair": ((170, 116, 72), (132, 86, 56), (100, 62, 46), (72, 44, 40), NAVY),
    "belt": ((112, 74, 52), (86, 56, 42), (70, 44, 38), (58, 36, 34), NAVY),
}
MAT_IDS = {name: i + 1 for i, name in enumerate(MATS)}
MAT_NAMES = {v: k for k, v in MAT_IDS.items()}

EYE_IRIS = (78, 104, 70)
EYE_IRIS_DARK = (52, 70, 56)
EYE_IRIS_LIGHT = (116, 146, 92)
EYE_WHITE = (225, 234, 253)
BUCKLE = (255, 243, 171)
MOUTH = (203, 113, 115)
BROW = (72, 44, 40)


# ----------------------------------------------------------------- shapes --
def ellipse(cx, cy, rx, ry):
    return ((XX - cx) / rx) ** 2 + ((YY - cy) / ry) ** 2 <= 1.0


def capsule(p, q, r):
    px, py = p
    qx, qy = q
    dx, dy = qx - px, qy - py
    ll = dx * dx + dy * dy
    if ll == 0:
        t = np.zeros_like(XX, dtype=float)
    else:
        t = np.clip(((XX - px) * dx + (YY - py) * dy) / ll, 0, 1)
    ex = XX - (px + t * dx)
    ey = YY - (py + t * dy)
    return ex * ex + ey * ey <= r * r


def polygon(pts):
    img = Image.new("L", (CW, CH), 0)
    ImageDraw.Draw(img).polygon([(round(x), round(y)) for x, y in pts], fill=1, outline=1)
    return np.array(img, dtype=bool)


def rect(x0, y0, x1, y1):
    return (XX >= x0) & (XX <= x1) & (YY >= y0) & (YY <= y1)


def shift(m, dx, dy):
    """out[y, x] = m[y - dy, x - dx] (False outside)."""
    out = np.zeros_like(m)
    h, w = m.shape
    ys = slice(max(dy, 0), h + min(dy, 0))
    xs = slice(max(dx, 0), w + min(dx, 0))
    ys2 = slice(max(-dy, 0), h + min(-dy, 0))
    xs2 = slice(max(-dx, 0), w + min(-dx, 0))
    out[ys, xs] = m[ys2, xs2]
    return out


def at(m, dx, dy):
    """Boolean map: is m set at (x+dx, y+dy)?"""
    return shift(m, -dx, -dy)


def boundary(m):
    inner = m & at(m, 1, 0) & at(m, -1, 0) & at(m, 0, 1) & at(m, 0, -1)
    return m & ~inner


def clean_mask(m):
    """Remove 1-pixel spurs that make ugly outlines."""
    for _ in range(2):
        n = (at(m, 1, 0).astype(int) + at(m, -1, 0) + at(m, 0, 1) + at(m, 0, -1))
        m = m & (n >= 2)
    return m


def angle_vec(deg, length):
    """Angle from straight down, positive = towards +x."""
    a = math.radians(deg)
    return (math.sin(a) * length, math.cos(a) * length)


def add(p, v):
    return (p[0] + v[0], p[1] + v[1])


# ----------------------------------------------------------------- canvas --
class Canvas:
    def __init__(self):
        self.rgba = np.zeros((CH, CW, 4), dtype=np.uint8)
        self.owner = np.zeros((CH, CW), dtype=np.int32)  # part id per pixel
        self.next_id = 1
        self.part_masks = {}

    def put(self, mask, color):
        c = color if len(color) == 4 else (*color, 255)
        self.rgba[mask] = c

    def part(self, mask, mat, merge_with=None, seams=True, light=True):
        """Draw a shaded, outlined part.

        mat: material name, or an int array of material ids (per pixel).
        merge_with: mask of already drawn pixels that should not get an
            outline between them and this part (e.g. shoulder joint).
        """
        mask = clean_mask(mask)
        if isinstance(mat, str):
            matmap = np.where(mask, MAT_IDS[mat], 0)
        else:
            matmap = np.where(mask, mat, 0)
        solid = mask | merge_with if merge_with is not None else mask
        outline = mask & boundary(solid)
        # sides of the merge region that touch the outside still get outline
        interior = mask & ~outline
        tone = np.ones(mask.shape, dtype=np.int32)  # 1 = base
        r1 = ~at(interior, 1, 0)
        r2 = ~at(interior, 2, 0)
        l1 = ~at(interior, -1, 0)
        l2 = ~at(interior, -2, 0)
        b1 = ~at(interior, 0, 1)
        tone[interior & r2] = 2
        tone[interior & b1] = 2
        tone[interior & r1 & (b1 | ~at(interior, 0, 2))] = 3
        if light:
            tone[interior & l2 & ~l1 & ~r2] = 0
        for mid, name in MAT_NAMES.items():
            sel = matmap == mid
            if not sel.any():
                continue
            pal = MATS[name]
            for t in range(4):
                self.put(interior & sel & (tone == t), pal[t])
            self.put(outline & sel, pal[4])
        if seams:
            # dark seam where cloth meets another material inside the part
            for mid, name in MAT_NAMES.items():
                if name.startswith("skin"):
                    continue
                sel = (matmap == mid) & interior
                other = mask & (matmap != mid) & (matmap != 0)
                touch = sel & (at(other, 0, 1) | at(other, 0, -1))
                self.put(touch, MATS[name][4])
        pid = self.next_id
        self.next_id += 1
        self.owner[mask] = pid
        self.part_masks[pid] = mask
        return mask

    def px(self, x, y, color):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < CW and 0 <= y < CH:
            self.rgba[y, x] = (*color, 255)

    def hline(self, x0, x1, y, color):
        for x in range(int(round(x0)), int(round(x1)) + 1):
            self.px(x, y, color)


def mat_by(mask, cond_true, name_true, name_false):
    return np.where(mask & cond_true, MAT_IDS[name_true],
                    np.where(mask, MAT_IDS[name_false], 0))


# ---------------------------------------------------------- shared pieces --
def front_leg(cv, x, hip_y, foot_y, far=False, back=False):
    """Vertical leg seen from the front/back, ending in a boot at foot_y."""
    leg = capsule((x, hip_y), (x, foot_y - 6), 5.2)
    boot = ellipse(x, foot_y - 3, 5.6, 3.6) | rect(x - 5, foot_y - 10, x + 5, foot_y - 3)
    m = leg | boot
    mat = mat_by(m, boot, "boot", "pants")
    cv.part(m, mat)
    if back:
        # heel line
        cv.hline(x - 3, x + 3, foot_y - 3, MATS["boot"][3])
    else:
        # toe cap highlight
        cv.hline(x - 2, x + 1, foot_y - 2, MATS["boot"][0])
    # boot cuff fold
    cv.hline(x - 4, x + 4, foot_y - 9, MATS["boot"][0])


def front_torso(cx, top, hem, back=False):
    pts = [
        (cx - 6, top), (cx + 6, top),
        (cx + 13, top + 2), (cx + 15, top + 5),
        (cx + 13, top + 19), (cx + 12, top + 21),
        (cx + 13, hem), (cx - 13, hem),
        (cx - 12, top + 21), (cx - 13, top + 19),
        (cx - 15, top + 5), (cx - 13, top + 2),
    ]
    m = polygon(pts)
    if not back:
        m &= ~polygon([(cx - 3, top - 1), (cx + 3, top - 1), (cx, top + 5)])
    return m


def front_arm(cx, side, shoulder_y, pose, bend=False):
    """side=-1 for viewer-left arm. pose: (hand_dx, hand_dy)."""
    hdx, hdy = pose
    sx = cx + side * 14
    sh = (sx, shoulder_y + 2)
    if bend:
        el = (cx + side * 16, shoulder_y + 10)
        hand = (cx + side * (10 - hdx), shoulder_y + 15 + hdy)
    else:
        el = (cx + side * 16, shoulder_y + 11)
        hand = (cx + side * (18 - hdx), shoulder_y + 23 + hdy)
    upper = capsule(sh, el, 4.3)
    fore = capsule(el, hand, 3.6)
    fist = ellipse(hand[0], hand[1] + 1, 3.4, 3.2)
    m = upper | fore | fist
    sleeve = (YY <= shoulder_y + 8) & capsule(sh, el, 5)
    mat = mat_by(m, sleeve, "tunic", "skin")
    return m, mat


# ------------------------------------------------------------- head (front)
def head_front(cv, cx, cy, back=False):
    # ears
    for s in (-1, 1):
        ear = ellipse(cx + s * 12.5, cy + 4, 2.3, 3.3)
        cv.part(ear, "skin", light=False)
    head = ellipse(cx, cy, 12.4, 14.2) & (YY <= cy + 13)
    # slightly squarer jaw
    head |= ellipse(cx, cy + 6, 11.0, 8.0)
    cv.part(head, "skin")
    if not back:
        # eyes
        for s in (-1, 1):
            ex = cx + s * 5
            ey = cy + 4
            inner = ex - s * 1  # towards nose
            outer = ex + s * 1
            # upper lid line with a small outer wing
            for x in (inner, ex, outer, outer + s):
                cv.px(x, ey - 1, NAVY)
            cv.px(outer, ey, EYE_IRIS_DARK)
            cv.px(ex, ey, NAVY)
            cv.px(inner, ey, EYE_WHITE)
            cv.px(outer, ey + 1, EYE_IRIS)
            cv.px(ex, ey + 1, NAVY)
            cv.px(inner, ey + 1, EYE_IRIS)
            cv.px(ex, ey + 2, EYE_IRIS)
            cv.px(inner, ey + 2, EYE_IRIS_LIGHT)
            # brows: thick, straight
            for x in range(-2, 3):
                cv.px(ex + s * x, ey - 4, BROW)
            for x in (-2, -1, 0):
                cv.px(ex + s * x, ey - 3, BROW)
        # nose and mouth
        cv.px(cx, cy + 8, MATS["skin"][3])
        cv.px(cx + 1, cy + 8, MATS["skin"][2])
        cv.hline(cx - 1, cx, cy + 11, MOUTH)
        # cheek shade under the jaw line is handled by part shading


def hair_front(cv, cx, cy, back=False):
    shell = ellipse(cx, cy - 1, 13.6, 15.2)
    if back:
        # back of the head: hair down to the nape, jagged ends
        bottom = {}
        for x in range(cx - 14, cx + 15):
            d = abs(x - cx)
            base = cy + 11 - (d // 4)
            jag = [0, 1, 2, 1][(x - cx + 40) % 4]
            bottom[x] = base + jag - (3 if d >= 11 else 0)
        m = shell & np.array([[y <= bottom.get(x, -1) for x in range(CW)] for y in range(CH)])
    else:
        # fringe: messy spikes over the forehead, sideburns to the ears
        bottom = {}
        spikes = [0, 2, 3, 1, 0, 2, 4, 2, 0, 1, 3, 2, 0]
        for x in range(cx - 14, cx + 15):
            d = abs(x - cx)
            if d >= 11:
                base = cy + 4  # sideburns
            elif d >= 9:
                base = cy - 2
            else:
                base = cy - 6 + spikes[(x - cx + 6) % len(spikes)] // 1
            bottom[x] = base
        m = shell & np.array([[y <= bottom.get(x, -1) for x in range(CW)] for y in range(CH)])
    # messy top tufts
    for tx, ty, w in ((cx - 7, cy - 15, 2), (cx - 1, cy - 16, 2), (cx + 6, cy - 15, 2),
                      (cx + 11, cy - 11, 1), (cx - 12, cy - 10, 1)):
        m |= polygon([(tx - w, ty + 3), (tx, ty), (tx + w + 1, ty + 3)])
    cv.part(m, "hair")
    hb = MATS["hair"]
    # highlight arcs and strand lines
    hl = ellipse(cx - 2, cy - 5, 9.5, 8.5) & ~ellipse(cx - 2, cy - 4, 8.5, 8.0) & (YY < cy - 6)
    hl &= m & ~boundary(m) & (XX < cx + 6)
    cv.put(hl & ((XX + YY) % 5 != 0), hb[0])
    for sx0, sy0, sx1, sy1 in ((cx - 4, cy - 12, cx - 7, cy - 6), (cx + 3, cy - 13, cx + 5, cy - 7),
                               (cx - 9, cy - 8, cx - 11, cy - 2)):
        cv.put(capsule((sx0, sy0), (sx1, sy1), 0.5) & m & ~boundary(m), hb[3])
    if back:
        for sx0, sy0, sx1, sy1 in ((cx - 5, cy - 2, cx - 6, cy + 8), (cx + 1, cy - 4, cx + 1, cy + 9),
                                   (cx + 6, cy - 2, cx + 7, cy + 7)):
            cv.put(capsule((sx0, sy0), (sx1, sy1), 0.5) & m & ~boundary(m), hb[2])


# ----------------------------------------------------------- front / back --
def draw_front(pose, back=False):
    cv = Canvas()
    cx = 32
    ub = pose.get("ub", 0)
    lifts = pose.get("lift", (0, 0))
    fdy = pose.get("fdy", (0, 0))
    hip = 72 + ub
    legs = [(-1, cx - 6), (1, cx + 6)]
    # draw the lifted (further back in depth) leg first
    order = sorted(legs, key=lambda l: -lifts[0 if l[0] < 0 else 1])
    for side, x in order:
        i = 0 if side < 0 else 1
        front_leg(cv, x, hip, GROUND - lifts[i] + fdy[i], back=back)
    top = 49 + ub
    hem = 80 + ub
    torso = front_torso(cx, top, hem, back=back)
    neck = rect(cx - 4, 42 + ub, cx + 4, top + 4)
    cv.part(neck, "skin", light=False)
    if not back:
        # shade the neck under the chin
        cv.put(neck & ~boundary(neck) & (YY <= 46 + ub), MATS["skin"][2])
    cv.part(torso, "tunic")
    # belt
    belt = torso & (YY >= hip - 3) & (YY <= hip - 1)
    cv.put(belt & ~boundary(torso), MATS["belt"][1])
    cv.put(belt & boundary(torso), NAVY)
    cv.hline(cx - 12, cx + 12, hip - 4, NAVY)
    cv.hline(cx - 12, cx + 12, hip, NAVY)
    if not back:
        cv.put(rect(cx - 1, hip - 3, cx + 1, hip - 1), BUCKLE)
        cv.px(cx, hip - 2, MATS["belt"][2])
        # collar laces / placket
        for y in range(top + 5, top + 10):
            cv.px(cx, y, MATS["tunic"][3])
        cv.px(cx - 1, top + 6, MATS["tunic"][0])
        cv.px(cx + 1, top + 8, MATS["tunic"][0])
    else:
        cv.hline(cx - 5, cx + 5, top + 1, MATS["tunic"][3])
        for y in range(top + 6, hip - 5):
            cv.px(cx, y, MATS["tunic"][2])
    # hem fold lines
    for x in (cx - 7, cx + 6):
        cv.px(x, hem - 2, MATS["tunic"][3])
        cv.px(x, hem - 1, MATS["tunic"][3])
    arms = pose.get("arms", ((0, 0), (0, 0)))
    bend = pose.get("bend", False)
    for i, side in enumerate((-1, 1)):
        am, amat = front_arm(cx, side, 53 + ub, arms[i], bend=bend)
        cv.part(am, amat, merge_with=torso & (YY <= 57 + ub))
    head_front(cv, cx, 33 + ub, back=back)
    hair_front(cv, cx, 33 + ub, back=back)
    return cv.rgba


# ------------------------------------------------------------------ side --
def leg_geom(hip, thigh_a, knee_a, grounded):
    knee = add(hip, angle_vec(thigh_a, 13))
    shin_a = thigh_a - knee_a
    ankle = add(knee, angle_vec(shin_a, 12))
    if grounded:
        fdir = (1.0, 0.0)
        base = (ankle[0], ankle[1] + 3.0)
    else:
        a = math.radians(shin_a)
        fdir = (math.cos(a), -math.sin(a))
        base = add(ankle, (math.sin(a) * 3.0, math.cos(a) * 3.0))
    heel = (base[0] - fdir[0] * 2.5, base[1] - fdir[1] * 2.5)
    toe = (base[0] + fdir[0] * 5.0, base[1] + fdir[1] * 5.0)
    return knee, shin_a, ankle, heel, toe


FOOT_R = 2.6


def side_leg(cv, hip, thigh_a, knee_a, far=False, grounded=True):
    """Leg seen from the side (facing +x)."""
    knee, shin_a, ankle, heel, toe = leg_geom(hip, thigh_a, knee_a, grounded)
    thigh = capsule(hip, knee, 4.9)
    shin = capsule(knee, ankle, 4.4)
    foot = capsule(heel, toe, FOOT_R)
    boot = foot | capsule(add(ankle, angle_vec(shin_a, -4)), ankle, 4.5)
    m = thigh | shin | boot
    sfx = "_far" if far else ""
    mat = mat_by(m, boot, "boot" + sfx, "pants" + sfx)
    cv.part(m, mat)
    return m


def side_leg_extent(thigh_a, knee_a, grounded=True):
    _, _, ankle, heel, toe = leg_geom((0, 0), thigh_a, knee_a, grounded)
    return max(ankle[1] + 4.4, heel[1] + FOOT_R, toe[1] + FOOT_R)


def side_arm(cv, shoulder, a, bend, far=False, merge=None):
    el = add(shoulder, angle_vec(a, 11))
    hand = add(el, angle_vec(a + bend, 9))
    upper = capsule(shoulder, el, 4.0)
    fore = capsule(el, hand, 3.4)
    fist = ellipse(hand[0], hand[1], 3.2, 3.2)
    m = upper | fore | fist
    sleeve = capsule(shoulder, add(shoulder, angle_vec(a, 7)), 4.6)
    sfx = "_far" if far else ""
    mat = mat_by(m, sleeve, "tunic" + sfx, "skin" + sfx)
    cv.part(m, mat, merge_with=merge)
    return m


def head_side(cv, cx, cy):
    head = ellipse(cx, cy, 12.0, 14.2) & (YY <= cy + 13)
    head |= ellipse(cx + 2, cy + 6, 10.0, 8.0)
    # nose
    head |= polygon([(cx + 11, cy + 3), (cx + 14, cy + 7), (cx + 11, cy + 8)])
    cv.part(head, "skin")
    # eye (facing right)
    ex, ey = cx + 8, cy + 4
    for x in (ex - 1, ex, ex + 1, ex + 2):
        cv.px(x, ey - 1, NAVY)
    cv.px(ex, ey, NAVY)
    cv.px(ex + 1, ey, EYE_WHITE)
    cv.px(ex, ey + 1, NAVY)
    cv.px(ex + 1, ey + 1, EYE_IRIS)
    cv.px(ex, ey + 2, EYE_IRIS)
    cv.px(ex + 1, ey + 2, EYE_IRIS_LIGHT)
    for x in range(-1, 4):
        cv.px(ex + x, ey - 4, BROW)
    for x in range(0, 3):
        cv.px(ex + x, ey - 3, BROW)
    cv.hline(cx + 9, cx + 10, cy + 11, MOUTH)
    # ear
    ear = ellipse(cx - 1, cy + 4, 2.6, 3.6)
    cv.part(ear, "skin", light=False)
    cv.px(cx - 1, cy + 4, MATS["skin"][3])
    cv.px(cx - 1, cy + 5, MATS["skin"][3])


def hair_side(cv, cx, cy):
    shell = ellipse(cx - 0.5, cy - 1, 13.0, 15.2)
    bottom = {}
    for x in range(cx - 15, cx + 15):
        rel = x - cx
        if rel >= 9:
            b = cy - 6 + [0, 2, 1, 3, 0, 1][(rel) % 6]  # fringe over forehead
        elif rel >= 4:
            b = cy - 4 + [0, 2, 1][rel % 3]
        elif rel >= 2:
            b = cy - 1  # hair line just above the ear
        elif rel >= -3:
            b = cy - 0  # above the ear
        else:
            b = cy + 6 + [0, 1, 2, 1][(rel + 40) % 4] - (2 if rel < -10 else 0)  # nape
        bottom[x] = b
    m = shell & np.array([[y <= bottom.get(x, -1) for x in range(CW)] for y in range(CH)])
    for tx, ty, w in ((cx - 6, cy - 15, 2), (cx + 1, cy - 16, 2), (cx + 7, cy - 14, 2),
                      (cx - 12, cy - 9, 1)):
        m |= polygon([(tx - w, ty + 3), (tx, ty), (tx + w + 1, ty + 3)])
    # a tuft sticking out at the back
    m |= polygon([(cx - 12, cy - 2), (cx - 15, cy), (cx - 12, cy + 3)])
    cv.part(m, "hair")
    hb = MATS["hair"]
    hl = ellipse(cx, cy - 5, 9.5, 8.5) & ~ellipse(cx, cy - 4, 8.5, 8.0) & (YY < cy - 6)
    hl &= m & ~boundary(m) & (XX > cx - 7)
    cv.put(hl & ((XX + YY) % 5 != 0), hb[0])
    for sx0, sy0, sx1, sy1 in ((cx - 3, cy - 12, cx - 8, cy - 3), (cx + 3, cy - 13, cx + 7, cy - 7),
                               (cx - 8, cy - 7, cx - 10, cy + 4)):
        cv.put(capsule((sx0, sy0), (sx1, sy1), 0.5) & m & ~boundary(m), hb[3])


def draw_side(pose):
    """Facing right (+x)."""
    cv = Canvas()
    cx = 33
    lean = pose.get("lean", 0)
    legs = pose["legs"]  # ((thigh_a, knee_a) near, (thigh_a, knee_a) far)
    def ankle_depth(l):
        return leg_geom((0, 0), l[0], l[1], True)[2][1]
    g0 = ankle_depth(legs[0]) >= ankle_depth(legs[1])
    grounded = (g0, not g0)
    ext = max(side_leg_extent(*legs[0], grounded[0]), side_leg_extent(*legs[1], grounded[1]))
    hip_y = GROUND + 0.5 - ext - pose.get("air", 0)
    hip_y = round(hip_y)
    ub = hip_y - 73 + pose.get("ub", 0)
    hip = (cx, hip_y)
    arms = pose["arms"]  # ((a, bend) near, (a, bend) far)
    shoulder = (cx + lean, 54 + ub)
    side_arm(cv, (shoulder[0] + 1, shoulder[1]), *arms[1], far=True)
    side_leg(cv, (hip[0] + 1, hip[1]), *legs[1], far=True, grounded=grounded[1])
    side_leg(cv, hip, *legs[0], grounded=grounded[0])
    top = 49 + ub
    l = lean
    neck = rect(cx - 3 + l, 42 + ub, cx + 3 + l, top + 3)
    cv.part(neck, "skin", light=False)
    torso = polygon([
        (cx - 6 + l, top), (cx + 4 + l, top), (cx + 8 + l, top + 3),
        (cx + 8 + l, top + 12), (cx + 7, top + 21), (cx + 8, hip_y + 7),
        (cx - 7, hip_y + 7), (cx - 7, top + 21), (cx - 8 + l, top + 10), (cx - 8 + l, top + 3),
    ])
    cv.part(torso, "tunic")
    belt = torso & (YY >= hip_y - 3) & (YY <= hip_y - 1)
    cv.put(belt & ~boundary(torso), MATS["belt"][1])
    cv.put(torso & ((YY == hip_y - 4) | (YY == hip_y)), NAVY)
    cv.px(cx + 7, hip_y - 2, BUCKLE)
    cv.px(cx + 7, hip_y - 3, BUCKLE)
    # collar
    cv.px(cx + 4 + l, top + 1, MATS["tunic"][3])
    cv.px(cx + 5 + l, top + 2, MATS["tunic"][3])
    cv.px(cx - 2, hip_y + 4, MATS["tunic"][3])
    cv.px(cx - 2, hip_y + 5, MATS["tunic"][3])
    head_side(cv, cx + 1 + l + (1 if l >= 2 else 0), 33 + ub)
    hair_side(cv, cx + 1 + l + (1 if l >= 2 else 0), 33 + ub)
    side_arm(cv, shoulder, *arms[0], merge=torso & (YY <= shoulder[1] + 2))
    return cv.rgba


# ------------------------------------------------------------------ poses --
def idle_bob(i):
    return [0, 0, 0, 1, 1, 1, 1, 0][i]


def front_pose(kind, i):
    if kind == "idle":
        b = idle_bob(i)
        return {"ub": b, "arms": ((0, 0), (0, 0))}
    n = 10 if kind == "walk" else 8
    ph = 2 * math.pi * i / n
    s = math.sin(ph)
    if kind == "walk":
        lift = (round(4 * max(0, s)), round(4 * max(0, -s)))
        fdy = (1 if s < -0.6 else 0, 1 if s > 0.6 else 0)
        ub = -1 if abs(s) > 0.5 else 0
        sw = round(2 * s)
        return {"ub": ub, "lift": lift, "fdy": fdy,
                "arms": ((1 if sw < 0 else 0, -sw), (1 if sw > 0 else 0, sw))}
    lift = (round(7 * max(0, s)), round(7 * max(0, -s)))
    fdy = (1 if s < -0.6 else 0, 1 if s > 0.6 else 0)
    ub = -2 if abs(s) > 0.6 else 0
    sw = round(4 * s)
    return {"ub": ub, "lift": lift, "fdy": fdy, "bend": True,
            "arms": ((0, -sw), (0, sw))}


def side_pose(kind, i):
    if kind == "idle":
        b = idle_bob(i)
        return {"legs": ((0, 0), (2, 0)), "arms": ((-2, 6), (3, 6)), "ub": b}
    n = 10 if kind == "walk" else 8
    ph = 2 * math.pi * i / n
    s, c = math.sin(ph), math.cos(ph)
    if kind == "walk":
        A, K = 24, 40
        near = (A * s, K * max(0, c) ** 1.5)
        far = (-A * s, K * max(0, -c) ** 1.5)
        return {"legs": (near, far), "arms": ((-22 * s, 14), (22 * s, 14))}
    A, K = 34, 85
    near = (A * s + 6, K * max(0, c) ** 1.2 + 10)
    far = (-A * s + 6, K * max(0, -c) ** 1.2 + 10)
    air = 2 if abs(c) > 0.7 else 0
    return {"legs": (near, far), "arms": ((-40 * s, 85), (40 * s, 85)),
            "lean": 2, "air": air}


# ---------------------------------------------------------------- shadow --
def shadow_from_reference(ref, row, col):
    cell = ref[row * CH:(row + 1) * CH, col * CW:(col + 1) * CW]
    sh = np.zeros((CH, CW, 4), dtype=np.uint8)
    semi = (cell[:, :, 3] > 0) & (cell[:, :, 3] < 255)
    fill = (63, 63, 116, 125)
    for y in range(CH):
        xs = np.where(semi[y])[0]
        if len(xs) == 0:
            continue
        sh[y, xs.min():xs.max() + 1] = fill
        sh[y, semi[y]] = cell[y, semi[y]]
    # interior holes (under the body) also get the fill colour
    return sh


def default_shadow(cx):
    sh = np.zeros((CH, CW, 4), dtype=np.uint8)
    m = ellipse(cx, 102, 22.5, 11.5)
    sh[m] = (63, 63, 116, 125)
    sh[boundary(m) & (YY < 102)] = (92, 92, 169, 125)
    return sh


def composite(shadow, fig):
    out = shadow.copy()
    a = fig[:, :, 3] == 255
    out[a] = fig[a]
    return out


# ------------------------------------------------------------------ main --
def build(ref=None):
    sheet = np.zeros((CH * ROWS, CW * COLS, 4), dtype=np.uint8)
    kinds = [("idle", 8), ("walk", 10), ("run", 8)]
    for k, (kind, n) in enumerate(kinds):
        for d in range(4):  # down, left, right, up
            row = k * 4 + d
            for i in range(n):
                if d == 0:
                    fig = draw_front(front_pose(kind, i))
                elif d == 3:
                    fig = draw_front(front_pose(kind, i), back=True)
                else:
                    fig = draw_side(side_pose(kind, i))
                    if d == 1:
                        fig = fig[:, ::-1]
                if ref is not None:
                    sh = shadow_from_reference(ref, row, i)
                else:
                    sh = default_shadow({0: 31.5, 1: 29.5, 2: 33.5, 3: 31.5}[d])
                cell = composite(sh, fig)
                sheet[row * CH:(row + 1) * CH, i * CW:(i + 1) * CW] = cell
    return sheet


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ref = None
    if len(sys.argv) > 2:
        ref = np.array(Image.open(sys.argv[2]).convert("RGBA"))
        assert ref.shape == (CH * ROWS, CW * COLS, 4), ref.shape
    sheet = build(ref)
    Image.fromarray(sheet).save(sys.argv[1])
    print("wrote", sys.argv[1], sheet.shape[1], "x", sheet.shape[0])


if __name__ == "__main__":
    main()
