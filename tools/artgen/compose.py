#!/usr/bin/env python
"""Two-stage character-consistent scenes: FLUX klein composes with --ref, SDXL refines.

    compose.py scene  --ref MAN.png WOMAN.png --scene "<who, clothes, pose, place>" --out DIR [--style s3]
    compose.py refine --image DIR/scene_s11.png --heads x0,y0,x1,y1 --heads ... --prompt "<tags>" --out DIR
    compose.py sheet  --row "label=path" ... --out sheet.png   (rows of labelled images, see --help)

Each stage runs ``artgen.py`` in a subprocess (FLUX and SDXL never share memory). Stage 2 needs the head
boxes of the stage 1 image, so look at the image first (``artgen.py mask --preview`` shows them).
Every command prints one JSON object on stdout and exits non-zero on error.
Run with tools/artgen/.venv/bin/python.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Per style: FLUX prefix + lora scale, and SDXL suffix tags + LoRA. Same wording as STYLES.md.
STYLES = {
    "s2": {"flux_prefix": "detailed hi-res pixel art, realistic anatomy, sculpted form shading, crisp specular highlights, "
                          "limited palette.",
           "flux_lora": 0.5, "sdxl_suffix": "detailed hi-res pixel art, sculpted form shading, crisp specular highlights, "
                                            "limited palette", "sdxl_loras": "pixel_art_xl:0.5"},
    "s3": {"flux_prefix": "anime style pixel art, thick dark outlines, flat cel shading with two tones.",
           "flux_lora": 1.0, "sdxl_suffix": "anime style pixel art, thick dark outlines, flat cel shading with two tones",
           "sdxl_loras": "pixel_art_xl:0.8"},
    "s4": {"flux_prefix": "flat vector illustration, clean dark line art, two-tone cel shading, flat colours.",
           "flux_lora": 0.0, "sdxl_suffix": "flat vector illustration, clean dark line art, two-tone cel shading, flat colours",
           "sdxl_loras": None},
}


def run_artgen(args: list[str]) -> dict:
    """Run artgen.py; return the last stdout line parsed as JSON when it is JSON, else {"stdout": ...}."""
    r = subprocess.run([sys.executable, str(HERE / "artgen.py"), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"artgen.py {args[0]} failed ({r.returncode}):\n{r.stderr[-1500:]}")
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    try:
        return json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        return {"stdout": lines}


def cmd_scene(a) -> dict:
    st = STYLES[a.style]
    prompt = (f"{st['flux_prefix']} {a.scene}" if st["flux_prefix"] else a.scene)
    cmd = ["generate", "--backend", "flux2_klein_pixel_lora", "--raw-prompt", "--prompt", prompt,
           "--opt", f"lora_scale={st['flux_lora']}", "--width", str(a.width), "--height", str(a.height),
           "--seed", str(a.seed), "--n", str(a.n), "--out", a.out, "--name", a.name]
    if a.ref:
        cmd += ["--ref", *a.ref]
    for o in a.opt or []:
        cmd += ["--opt", o]
    res = run_artgen(cmd)
    files = [ln for ln in res.get("stdout", []) if ln.endswith(".png")]
    return {"ok": True, "stage": 1, "prompt": prompt, "files": files}


def cmd_refine(a) -> dict:
    st = STYLES[a.style]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    mask = a.mask
    mres = None
    if a.heads:
        mask = str(out / f"{a.name}_mask.png")
        m = ["mask", "--image", a.image, "--out", mask, "--feather", str(a.feather), "--head-pad", str(a.head_pad),
             "--preview", str(out / f"{a.name}_mask_preview.png")]
        for h in a.heads:
            m += ["--heads", h]
        mres = run_artgen(m)
    prompt = f"{a.prompt}, {st['sdxl_suffix']}" if st["sdxl_suffix"] else a.prompt
    cmd = ["refine", "--backend", "sdxl", "--image", a.image, "--prompt", prompt, "--seed", str(a.seed),
           "--n", str(a.n), "--out", a.out, "--name", a.name, "--strength", *[str(s) for s in a.strength],
           "--opt", f"model={a.model}"]
    loras = a.loras if a.loras is not None else st["sdxl_loras"]
    if loras:
        cmd += ["--opt", f"loras={loras}"]
    if mask:
        cmd += ["--mask", mask]
    if a.pose:
        cmd += ["--pose", a.pose]
    for o in a.opt or []:
        cmd += ["--opt", o]
    res = run_artgen(cmd)
    return {"ok": True, "stage": 2, "mask": mres, "files": res.get("files"), "prompt": prompt}


def build_sheet(rows: list[tuple[str, list[tuple[str, str]]]], cell_h: int = 384, pad: int = 6):
    """rows: [(row label, [(column label, image path), ...]), ...] -> PIL image. Cells are scaled to ``cell_h`` high."""
    from PIL import Image, ImageDraw
    lab_w, lab_h = 110, 18
    scaled = [[(c, Image.open(p).convert("RGB")) for c, p in cols] for _, cols in rows]
    scaled = [[(c, im.resize((max(1, round(im.width * cell_h / im.height)), cell_h), Image.LANCZOS)) for c, im in r]
              for r in scaled]
    width = lab_w + max(sum(im.width + pad for _, im in r) for r in scaled)
    sheet = Image.new("RGB", (width, len(rows) * (cell_h + lab_h + pad)), "white")
    d = ImageDraw.Draw(sheet)
    y = 0
    for (rl, _), r in zip(rows, scaled):
        d.text((4, y + lab_h + cell_h // 2), rl, fill="black")
        x = lab_w
        for c, im in r:
            d.text((x + 2, y + 3), c, fill="black")
            sheet.paste(im, (x, y + lab_h))
            x += im.width + pad
        y += cell_h + lab_h + pad
    return sheet


def cmd_sheet(a) -> dict:
    rows = []
    for spec in a.row:
        label, _, rest = spec.partition("=")
        cols = []
        for item in rest.split(","):
            c, sep, p = item.partition("@")
            if not sep:
                c, p = Path(item).stem, item
            if not Path(p).is_file():
                raise SystemExit(f"image not found: {p}")
            cols.append((c, p))
        rows.append((label, cols))
    sheet = build_sheet(rows, a.height)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp.png")
    sheet.save(tmp)
    tmp.replace(out)
    return {"ok": True, "file": str(out), "size": list(sheet.size)}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("scene", help="stage 1: FLUX klein composes the scene from 1-2 character refs")
    s1.add_argument("--ref", nargs="+", help="character image(s), e.g. a clothed front view per character")
    s1.add_argument("--scene", required=True, help='e.g. "The man and the woman from the reference images, both adults, '
                                                   'fully clothed in the same clothes, sitting side by side on a sofa"')
    s1.add_argument("--style", default="s3", choices=list(STYLES))
    s1.add_argument("--width", type=int, default=1024)
    s1.add_argument("--height", type=int, default=768)
    s1.add_argument("--seed", type=int, default=11)
    s1.add_argument("--n", type=int, default=1)
    s1.add_argument("--opt", action="append", help="extra FLUX option k=v")
    s1.add_argument("--name", default="scene")
    s1.add_argument("--out", required=True)

    s2 = sub.add_parser("refine", help="stage 2: SDXL img2img at one or more strengths, optionally protecting heads")
    s2.add_argument("--image", required=True, help="stage 1 image")
    s2.add_argument("--prompt", required=True, help="SDXL tags: people, clothes and hair colours, place")
    s2.add_argument("--heads", action="append", help="head box incl. hair, x0,y0,x1,y1 in px (repeatable)")
    s2.add_argument("--mask", help="ready mask PNG (white = repaint); alternative to --heads")
    s2.add_argument("--head-pad", type=float, default=0.06)
    s2.add_argument("--feather", type=float, default=3.0)
    s2.add_argument("--strength", type=float, nargs="+", default=[0.45])
    s2.add_argument("--style", default="s3", choices=list(STYLES))
    s2.add_argument("--model", default="wai_v17", help="sdxl key from models.json")
    s2.add_argument("--loras", help="override the style's LoRA, e.g. pixel_art_xl:0.5")
    s2.add_argument("--pose", help="OpenPose skeleton PNG")
    s2.add_argument("--seed", type=int, default=11)
    s2.add_argument("--n", type=int, default=1)
    s2.add_argument("--opt", action="append", help="extra sdxl option k=v")
    s2.add_argument("--name", default="refined")
    s2.add_argument("--out", required=True)

    sh = sub.add_parser("sheet", help="contact sheet: --row 'label=col@path,col@path' per row")
    sh.add_argument("--row", action="append", required=True)
    sh.add_argument("--height", type=int, default=384, help="cell height in px")
    sh.add_argument("--out", required=True)

    a = ap.parse_args(argv)
    if a.cmd == "refine" and bool(a.heads) == bool(a.mask) and (a.heads or a.mask):
        raise SystemExit("give either --heads or --mask, not both")
    res = {"scene": cmd_scene, "refine": cmd_refine, "sheet": cmd_sheet}[a.cmd](a)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
