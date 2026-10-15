"""Generation recipes for the 48 px world (design D6 of world-texel-scale): plans, not model runs.

`recipe texture|prop` prints the exact artgen/scenekit command lines for one texture or prop and checks the sizes
(nothing is executed, nothing is written). `texture roll|seam` are the two small image helpers the texture recipe uses."""
import os
import shlex

from PIL import Image, ImageChops

from common import TILE, SceneError, abspath_from_root, atomic_write, png_bytes, rel

STYLE_SUFFIX = "anime style pixel art, thick dark outlines, flat cel shading with two tones"
BACKEND_OPTS = ["--backend", "flux2_klein_pixel_lora", "--opt", "lora_scale=1.0"]
PALETTE = "art/palettes/interior.hex"
PY = "tools/artgen/.venv/bin/python"
ARTGEN = "tools/artgen/artgen.py"
SCENE = "tools/scenekit/scene.py"
MAX_RAW = 1024          # model canvas long side that fits the 1024 px generation budget
DEFAULT_GRID = 8        # raw px per art px, the generator's native pseudo-pixel
MIN_GRID = 6
PAD = 2                 # art px of plain background around a prop
TEXTURE_SIZES = (48, 96)
TEXTURES = {"floor": "flat top-down floor texture, seamless, repeating pattern, no objects, no shadows",
            "wall": "flat front view of a wall face, seamless, repeating pattern, no objects, no shadows"}


def _sh(args):
    return " ".join(shlex.quote(str(a)) for a in args)


def _up(v, m):
    return -(-v // m) * m


def _outdir(a, kind, name):
    return (a.out_dir or f"tools/scenekit/out/recipes/{kind}-{name}").rstrip("/")


def plan_texture(a):
    size, g = a.size, a.grid
    if size not in TEXTURE_SIZES:
        raise SceneError(f"--size must be one of {TEXTURE_SIZES} art px, got {size}", "bad_input")
    raw = size * g
    if raw % 16 or raw > MAX_RAW:
        raise SceneError(f"{size} px at grid {g} is a {raw}px canvas; it must be a multiple of 16 and at most {MAX_RAW}", "bad_input")
    d = _outdir(a, "texture", a.name)
    subject = f"{a.prompt}, {TEXTURES[a.kind]}, {STYLE_SUFFIX}"
    band = 2 * g * 3 // 1          # cross band: 6 art px wide, centred on the rolled seams
    c = raw // 2
    steps = [
        {"step": "generate", "note": f"{a.n} candidates at {raw}x{raw} raw px (= {size}x{size} art px at grid {g})",
         "cmd": f"{PY} {ARTGEN} generate " + _sh(BACKEND_OPTS + ["--opt", "background=plain flat background", "--prompt", subject,
                "--width", raw, "--height", raw, "--seed", a.seed, "--n", a.n, "--out", d, "--name", "raw"]),
         "outputs": [f"{d}/raw_s{a.seed + i}.png" for i in range(a.n)]},
        {"step": "roll", "note": "shift by half in x and y so the wrap-around seams meet in the middle cross (PICK.png = the candidate you chose, e.g. raw_s2.png)",
         "cmd": f"mise exec -- python3 {SCENE} texture roll PICK.png --out {d}/rolled.png"},
        {"step": "mask", "cmd": f"{PY} {ARTGEN} mask --size {raw}x{raw} --rect {c - band // 2},0,{c + band // 2},{raw} "
                                f"--rect 0,{c - band // 2},{raw},{c + band // 2} --out {d}/seam_mask.png"},
        {"step": "inpaint", "note": "repaint the cross; the result repeats seamlessly",
         "cmd": f"{PY} {ARTGEN} inpaint --image {d}/rolled.png --mask {d}/seam_mask.png --strength 0.9 --seed {a.seed} --n 2 "
                f"--name fixed --prompt {shlex.quote(subject)} --out {d}",
         "outputs": [f"{d}/fixed-0.png", f"{d}/fixed-1.png"]},
        {"step": "snap", "note": f"exact {g}x{g} block downscale and the shared palette",
         "cmd": f"{PY} {ARTGEN} snap {d}/fixed-0.png --factor {g} --palette {a.palette} --cleanup 1 --out {d}/snap",
         "outputs": [f"{d}/snap/fixed-0-snap.png"]},
        {"step": "check", "note": "seam ratio must be <= 1.5 (wrap edge vs the 95th percentile of the interior edges)",
         "cmd": f"mise exec -- python3 {SCENE} texture seam {d}/snap/fixed-0-snap.png"},
        {"step": "stamp", "note": f"paste at cell (0,0) and copy across the area; the {size} px texture covers {size // TILE if TILE else 1} cell(s) per side "
                                 f"at the {TILE} px tile size. ops file: one paste, then copy ops",
         "cmd": f"mise exec -- python3 {SCENE} edit MAP --layer LAYER --if-hash auto --quiet --ops OPS.json   "
                f"# OPS.json: [{{\"paste\":{{\"at\":[X,Y],\"image\":\"{d}/snap/fixed-0-snap.png\",\"mode\":\"replace\"}}}}, {{\"copy\":{{\"from\":[X,Y,{size},{size}],\"to\":[X2,Y2]}}}}, ...]"},
    ]
    return {"ok": True, "kind": f"texture/{a.kind}", "name": a.name, "art_px": [size, size], "canvas_px": [raw, raw], "grid": g,
            "palette": a.palette, "style_suffix": STYLE_SUFFIX, "dir": d, "steps": steps}


def plan_prop(a):
    w, h = a.size
    if min(w, h) < 1:
        raise SceneError("--size must be W,H art px", "bad_input")
    long_side = max(w, h) + 2 * PAD
    g = a.grid
    warnings = []
    if g is None:
        g = DEFAULT_GRID
        while g > MIN_GRID and long_side * g > MAX_RAW:
            g -= 1
        if g < DEFAULT_GRID:
            warnings.append(f"{w}x{h} art px does not fit 1024 raw px at grid {DEFAULT_GRID}; grid {g} is used. The model's own "
                            f"pixels are about {DEFAULT_GRID} raw px, so detail is lost; split the prop in two parts if it matters")
    cw, ch = _up((w + 2 * PAD) * g, 16), _up((h + 2 * PAD) * g, 16)
    if max(cw, ch) > MAX_RAW:
        raise SceneError(f"{w}x{h} art px needs a {cw}x{ch} canvas at grid {g} (max {MAX_RAW}); split the prop (at most about "
                         f"{MAX_RAW // g - 2 * PAD} art px per side at grid {g})", "too_large")
    d = _outdir(a, "prop", a.name)
    subject = f"{a.prompt}, isolated on a plain flat background, full object visible, {STYLE_SUFFIX}"
    steps = [
        {"step": "generate", "note": f"canvas {cw}x{ch} raw px; the prop is {w}x{h} art px = {w * g}x{h * g} raw px, so ask for the "
                                     f"proportions in the prompt (front view, 3/4 top-down)",
         "cmd": f"{PY} {ARTGEN} generate " + _sh(BACKEND_OPTS + ["--opt", "background=plain flat white background", "--prompt", subject,
                "--width", cw, "--height", ch, "--seed", a.seed, "--n", a.n, "--out", d, "--name", "raw"]),
         "outputs": [f"{d}/raw_s{a.seed + i}.png" for i in range(a.n)]},
        {"step": "post", "note": f"outputs raw_s<seed>_px.png; fixed --grid {g} (never auto/fit: every prop of the scene keeps one pixel size), shared palette, "
                                 f"background removed, outline inner",
         "cmd": f"{PY} {ARTGEN} post {d}/raw_s*.png --grid {g} --palette {a.palette} --outline inner --keep-largest --out {d}/px"},
        {"step": "check", "note": f"the opaque box should be about {w}x{h}; crop/pad to exactly that before stamping",
         "cmd": f"mise exec -- python3 {SCENE} texture size {d}/px/raw_sN_px.png"},
        {"step": "stamp", "note": f"{-(-w // TILE)}x{-(-h // TILE)} cells of {TILE} px. paste with the feet/bottom edge on a cell boundary, "
                                 f"mode over, on the Decor layer (alpha), then `collide region`/`material` for the footprint",
         "cmd": f"mise exec -- python3 {SCENE} edit MAP --layer Decor --if-hash auto --quiet --ops "
                f"'[{{\"paste\":{{\"at\":[X,Y],\"image\":\"{d}/px/raw_sN_px.png\",\"mode\":\"over\"}}}}]'"},
    ]
    return {"ok": True, "kind": "prop", "name": a.name, "art_px": [w, h], "canvas_px": [cw, ch], "grid": g, "palette": a.palette,
            "style_suffix": STYLE_SUFFIX, "dir": d, "warnings": warnings, "steps": steps}


def cmd_recipe(a):
    if a.what == "texture":
        return plan_texture(a)
    return plan_prop(a)


def _load(path):
    p = abspath_from_root(path)
    if not os.path.isfile(p):
        raise SceneError(f"image not found: {path}", "not_found")
    return Image.open(p).convert("RGBA"), p


def cmd_texture(a):
    img, _p = _load(a.image)
    w, h = img.size
    if a.action == "roll":
        if not a.out:
            raise SceneError("texture roll needs --out PNG", "bad_input")
        out = ImageChops.offset(img, w // 2, h // 2)
        outp = abspath_from_root(a.out)
        atomic_write(outp, png_bytes(out))
        return {"ok": True, "image": outp, "size": [w, h], "shift": [w // 2, h // 2]}
    if a.action == "size":
        bb = img.getchannel("A").getbbox()
        return {"ok": True, "size": [w, h], "opaque_box": list(bb) if bb else None,
                "opaque_wh": [bb[2] - bb[0], bb[3] - bb[1]] if bb else None}
    # seam: colour step across the wrap-around edge vs the interior edges
    px = img.convert("RGB").load()

    def step(p, q):
        return sum(abs(p[i] - q[i]) for i in range(3))

    def mean(vals):
        return sum(vals) / max(1, len(vals))

    # per-boundary mean colour step (column k | k+1, row k | k+1); the wrap boundary is judged against the 95th percentile of
    # the interior boundaries, so periodic textures with hard edges (plank joints) pass and ramps / cut-off patterns fail
    prof_x = [mean([step(px[x, y], px[x + 1, y]) for y in range(h)]) for x in range(w - 1)]
    prof_y = [mean([step(px[x, y], px[x, y + 1]) for x in range(w)]) for y in range(h - 1)]
    wrap_x = mean([step(px[w - 1, y], px[0, y]) for y in range(h)])
    wrap_y = mean([step(px[x, h - 1], px[x, 0]) for x in range(w)])

    def p95(v):
        return sorted(v)[int(0.95 * (len(v) - 1))] if v else 0.0

    rx, ry = wrap_x / max(p95(prof_x), 1e-6), wrap_y / max(p95(prof_y), 1e-6)
    ok = max(rx, ry) <= a.max_ratio
    res = {"ok": ok, "size": [w, h], "seam_ratio": {"x": round(rx, 3), "y": round(ry, 3)}, "max_ratio": a.max_ratio}
    if not ok:
        res.update(error=f"the texture does not repeat cleanly (ratio {max(rx, ry):.2f} > {a.max_ratio})", code="check_failed")
    return res
