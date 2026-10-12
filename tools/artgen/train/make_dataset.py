#!/usr/bin/env python
"""Generate the lgwoman1 character dataset with FLUX klein + --ref, then pad to squares + write captions.

  .venv/bin/python train/make_dataset.py gen  --ref REF.png --raw ~/.cache/artgen/datasets/lgwoman1_raw
  .venv/bin/python train/make_dataset.py pack --raw RAW --out ~/.cache/artgen/datasets/lgwoman1 [--drop id id ...]
  .venv/bin/python train/make_dataset.py sheet --out DATASET --png sheet.png

``gen`` writes RAW/<id>.png (+ .json). ``pack`` pads every kept image onto a square canvas in its
own corner colour (the trainer centre-crops to a square, which would cut a standing full-body figure),
writes OUT/<id>.png and OUT/metadata.jsonl ({"file_name", "text"}). Adults, clothed only.
"""
import argparse, json, os, sys, time
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TRIGGER = "lgwoman1"
STYLE = "anime style pixel art, thick dark outlines, flat cel shading with two tones"
HAIR = "same face, same auburn hair in a ponytail"
OUTFITS = {
    "A": ("her white cropped t-shirt, light blue jeans and white sneakers", "white crop top, blue jeans, white sneakers"),
    "B": ("a knee-length green summer dress with short sleeves and brown sandals", "green dress, short sleeves, knee-length dress, sandals"),
    "C": ("a grey hoodie, black leggings and red sneakers", "grey hoodie, black leggings, red sneakers"),
    "D": ("a white collared shirt, black blazer, black knee-length pencil skirt and black flats", "white collared shirt, black blazer, black skirt, pencil skirt, black flats"),
}
BGS = {
    "w": ("plain flat white background", "simple background, white background"),
    "b": ("plain flat light blue background", "simple background, blue background"),
    "g": ("plain flat light grey background", "simple background, grey background"),
    "p": ("plain flat pale pink background", "simple background, pink background"),
}
FULL, HALF, PORT = (576, 1024), (768, 1024), (768, 768)
FRAMING = {"full": (FULL, "full body"), "half": (HALF, "upper body"), "port": (PORT, "portrait, close-up")}
# id, outfit, framing, bg, plain-English pose, caption pose tags
SPECS = [
    ("01", "A", "full", "w", "standing, front view, arms at her sides", "standing, facing viewer"),
    ("02", "A", "full", "g", "walking, side view, profile", "walking, from side, profile"),
    ("03", "A", "full", "w", "standing, seen from behind, back view", "standing, from behind"),
    ("04", "A", "full", "b", "standing, three-quarter view, one hand on hip", "standing, three-quarter view, hand on hip"),
    ("05", "A", "full", "w", "sitting on a wooden chair, front view", "sitting, chair"),
    ("06", "A", "port", "p", "front view, smiling, looking at the viewer", "smile, looking at viewer"),
    ("07", "A", "port", "w", "three-quarter view, looking at the viewer", "three-quarter view, looking at viewer"),
    ("08", "B", "full", "w", "standing, front view, hands clasped in front", "standing, facing viewer"),
    ("09", "B", "full", "b", "walking, three-quarter view", "walking, three-quarter view"),
    ("10", "B", "half", "w", "sitting, front view, smiling", "sitting, smile"),
    ("11", "B", "port", "g", "front view, smiling", "smile, looking at viewer"),
    ("12", "B", "full", "p", "standing, seen from behind, back view", "standing, from behind"),
    ("13", "C", "full", "w", "standing, front view, hands in the hoodie pocket", "standing, hands in pockets, facing viewer"),
    ("14", "C", "full", "g", "walking, side view, profile", "walking, from side, profile"),
    ("15", "C", "full", "w", "sitting on a stool, front view", "sitting, stool"),
    ("16", "C", "half", "b", "three-quarter view, hands in the hoodie pocket", "three-quarter view, hands in pockets"),
    ("17", "C", "port", "w", "side view, profile", "from side, profile"),
    ("18", "C", "half", "p", "seen from behind, back view", "from behind"),
    ("19", "D", "full", "w", "standing, front view, arms at her sides", "standing, facing viewer"),
    ("20", "D", "full", "g", "walking, three-quarter view", "walking, three-quarter view"),
    ("21", "D", "half", "w", "sitting at a desk, front view", "sitting, desk"),
    ("22", "D", "port", "b", "front view, neutral expression", "looking at viewer"),
    ("23", "D", "full", "w", "standing, side view, profile", "standing, from side, profile"),
    ("24", "D", "half", "p", "standing, arms crossed, three-quarter view", "standing, crossed arms, three-quarter view"),
    ("25", "A", "full", "g", "sitting cross-legged on the floor, front view", "sitting, cross-legged"),
    ("26", "A", "half", "b", "front view, waving with one hand, smiling", "waving, smile"),
    ("27", "B", "port", "w", "side view, profile", "from side, profile"),
    ("28", "D", "half", "b", "seen from behind, back view", "from behind"),
]


# FLUX ignores "portrait"/"upper body" with a full-body ref: nearly every raw image is full body. Captions
# use the framing that is really in the image; close-ups are made by cropping (CROPS).
DROP = {"05", "06", "07", "15", "20", "23", "09", "16"}   # standing behind the chair/stool, duplicates
ACTUAL_FRAMING = {"10": "cowboy shot"}
TOPS = {"A": "white crop top", "B": "green dress, short sleeves", "C": "grey hoodie", "D": "white collared shirt, black blazer"}
# source id, kind (port | half), caption pose override (None = spec's)
CROPS = [("11", "port"), ("22", "port"), ("17", "port"), ("03", "port"), ("04", "half"), ("24", "half")]
SPEC = {s[0]: s for s in SPECS}


def caption(spec, framing=None, outfit=None):
    _id, o, f, b, _pe, tags = spec
    framing = framing or ACTUAL_FRAMING.get(_id, "full body")
    return ", ".join([TRIGGER, "1girl", "adult", "solo", outfit or OUTFITS[o][1], tags, framing, BGS[b][1], "pixel art"])


def crop_figure(im, kind):
    """Square crop of the head (port) or upper body (half) of a single standing figure on a flat background."""
    import numpy as np
    a = np.asarray(im.convert("RGB")).astype(int)
    bg = a[2, 2]
    mask = (abs(a - bg).sum(2) > 60)
    ys = np.where(mask.any(1))[0]
    top, H = ys.min(), ys.max() - ys.min()
    frac = 0.27 if kind == "port" else 0.58
    side = int(H * frac)
    rows = mask[top:top + side]
    xs = np.where(rows.any(0))[0]
    cx = (xs.min() + xs.max()) // 2
    x0 = max(0, min(im.width - side, cx - side // 2)); y0 = max(0, top - side // 12)
    return im.crop((x0, y0, x0 + side, y0 + side))


def gen(a):
    from artgen import get_backend
    raw = Path(a.raw).expanduser(); raw.mkdir(parents=True, exist_ok=True)
    b = get_backend("flux2_klein_pixel_lora")
    b.load(offload="none")
    times = []
    for s in SPECS:
        _id, o, f, bg, pe, _tags = s
        if (raw / f"{_id}.png").exists():
            continue
        (w, h), _ = FRAMING[f]
        prompt = (f"{STYLE}. The same adult woman from the reference image ({HAIR}), wearing {OUTFITS[o][0]}, "
                  f"{pe}, {FRAMING[f][1]}, {BGS[bg][0]}")
        prompt = b.apply_template(prompt, background=BGS[bg][0]) if False else f"pixel art sprite, {prompt}"
        t0 = time.perf_counter()
        im = b.generate(prompt, width=w, height=h, seed=100 + int(_id), n=1, ref=[a.ref], lora_scale=1.0)[0]
        dt = time.perf_counter() - t0
        times.append(dt)
        im.save(raw / f"{_id}.png")
        (raw / f"{_id}.json").write_text(json.dumps({"prompt": prompt, "seed": 100 + int(_id), "secs": round(dt, 1), "size": [w, h]}))
        print(_id, f"{dt:.0f}s", flush=True)
    print(json.dumps({"n": len(times), "mean_s": sum(times) / max(1, len(times))}))


def pack(a):
    raw, out = Path(a.raw).expanduser(), Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    drop = set(a.drop or [])
    lines = []
    for s in SPECS:
        if s[0] in drop or s[0] in DROP or not (raw / f"{s[0]}.png").exists():
            continue
        im = Image.open(raw / f"{s[0]}.png").convert("RGB")
        side = max(im.size)
        bgc = im.getpixel((2, 2))
        canvas = Image.new("RGB", (side, side), bgc)
        canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
        canvas = canvas.resize((1024, 1024), Image.LANCZOS)
        canvas.save(out / f"{s[0]}.png")
        lines.append(json.dumps({"file_name": f"{s[0]}.png", "text": caption(s)}))
    for sid, kind in CROPS:
        s = SPEC[sid]
        if sid in drop or not (raw / f"{sid}.png").exists():
            continue
        c = crop_figure(Image.open(raw / f"{sid}.png"), kind).resize((1024, 1024), Image.NEAREST)
        name = f"{sid}_{kind}.png"
        c.save(out / name)
        fr, top = ("portrait, close-up", TOPS[s[1]]) if kind == "port" else ("upper body", TOPS[s[1]])
        lines.append(json.dumps({"file_name": name, "text": caption(s, framing=fr, outfit=top)}))
    tmp = out / "metadata.jsonl.tmp"
    tmp.write_text("\n".join(lines) + "\n"); os.replace(tmp, out / "metadata.jsonl")
    print(json.dumps({"kept": len(lines), "out": str(out)}))


def sheet(a):
    d = Path(a.out).expanduser()
    meta = [json.loads(l) for l in (d / "metadata.jsonl").read_text().splitlines()]
    t = 256; cols = 6; rows = (len(meta) + cols - 1) // cols
    sh = Image.new("RGB", (cols * t, rows * (t + 14)), "white")
    dr = ImageDraw.Draw(sh)
    for i, m in enumerate(meta):
        im = Image.open(d / m["file_name"]).resize((t, t), Image.LANCZOS)
        x, y = (i % cols) * t, (i // cols) * (t + 14)
        sh.paste(im, (x, y + 14)); dr.text((x + 3, y + 1), m["file_name"][:-4], fill="black")
    sh.save(a.png); print(a.png)


if __name__ == "__main__":
    p = argparse.ArgumentParser(); sp = p.add_subparsers(dest="cmd", required=True)
    g = sp.add_parser("gen"); g.add_argument("--ref", required=True); g.add_argument("--raw", required=True); g.set_defaults(f=gen)
    k = sp.add_parser("pack"); k.add_argument("--raw", required=True); k.add_argument("--out", required=True); k.add_argument("--drop", nargs="*"); k.set_defaults(f=pack)
    s = sp.add_parser("sheet"); s.add_argument("--out", required=True); s.add_argument("--png", required=True); s.set_defaults(f=sheet)
    a = p.parse_args(); a.f(a)
