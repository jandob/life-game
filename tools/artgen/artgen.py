#!/usr/bin/env python
"""artgen: generate raw images with a pluggable backend, then post-process
them into game-ready pixel art. Every output gets a JSON sidecar so it can be
reproduced.

    artgen.py backends
    artgen.py generate --backend flux2_klein_pixel_lora --prompt "..." --seed 1 --n 4 --out DIR
    artgen.py inpaint --image canvas.png --mask mask.png --prompt "..." --strength 0.75 --n 4 --out DIR
    artgen.py snap DIR/*.png --factor 4 --palette p.hex --out DIR2
    artgen.py post DIR/*.png --grid fit --cell 64x128 --feet-row 105 --shadow --out DIR2
    artgen.py palette-from IMAGE --out palettes/x.hex

Run with tools/artgen/.venv/bin/python.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import postprocess as pp  # noqa: E402
from backends import REGISTRY, get_backend  # noqa: E402


def slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:n] or "img"


def parse_opts(pairs: list[str]) -> dict:
    """--opt k=v pairs. Values parse as JSON when possible (numbers, lists)."""
    out = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def parse_cell(s: str | None):
    if not s:
        return None
    w, h = s.lower().split("x")
    return int(w), int(h)


def write_sidecar(png: Path, data: dict) -> None:
    png.with_suffix(".json").write_text(json.dumps(data, indent=2, default=str))


# ------------------------------------------------------------- generate
def generate_images(backend, subject: str, *, raw_prompt: bool, seed: int, n: int,
                    width: int, height: int, negative: str | None, opts: dict,
                    out_dir: Path, stem: str | None = None) -> list[Path]:
    """Generate n images for one prompt and write PNG + sidecar each."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl_fields = {k: v for k, v in opts.items() if isinstance(v, str)}
    prompt = subject if raw_prompt else backend.apply_template(subject, **tmpl_fields)
    gen_opts = {k: v for k, v in opts.items() if k not in tmpl_fields or k == "ref"}
    t0 = time.perf_counter()
    imgs = backend.generate(prompt, negative=negative, width=width, height=height,
                            seed=seed, n=n, **gen_opts)
    total = time.perf_counter() - t0
    stats = backend.stats()
    paths = []
    stem = stem or slug(subject)
    for i, img in enumerate(imgs):
        p = out_dir / f"{stem}_s{seed + i}.png"
        img.save(p)
        write_sidecar(p, {
            "kind": "generate",
            "backend": backend.info.to_dict(),
            "subject": subject,
            "prompt": prompt,
            "negative": negative,
            "seed": seed + i,
            "width": width, "height": height,
            "opts": opts,
            "timings": {"call_total_s": round(total, 2),
                        "image_s": (stats.get("last_image_s") or [None] * n)[i],
                        "encode_s": stats.get("last_encode_s")},
            "stats": stats,
            "created": datetime.now(timezone.utc).isoformat(),
        })
        paths.append(p)
    return paths


def cmd_generate(a) -> None:
    b = get_backend(a.backend)
    opts = dict(b.info.defaults)
    opts = {k: v for k, v in opts.items() if v is not None}
    opts.update(parse_opts(a.opt))
    if a.ref:
        opts["ref"] = a.ref
    load_keys = {"offload", "dtype"}
    b.load(**{k: v for k, v in opts.items() if k in load_keys})
    gen = {k: v for k, v in opts.items() if k not in load_keys}
    paths = generate_images(b, a.prompt, raw_prompt=a.raw_prompt, seed=a.seed, n=a.n,
                            width=a.width, height=a.height, negative=a.negative,
                            opts=gen, out_dir=Path(a.out), stem=a.name)
    for p in paths:
        print(p)
    print(json.dumps(b.stats()), file=sys.stderr)


# -------------------------------------------------------------- inpaint
def cmd_inpaint(a) -> None:
    """Masked img2img on a canvas: n candidates, one PNG + sidecar each. Prints one JSON object on stdout."""
    from PIL import Image
    b = get_backend(a.backend)
    if not hasattr(b, "inpaint"):
        raise SystemExit(f"backend {a.backend} has no inpaint()")
    opts = {k: v for k, v in b.info.defaults.items() if v is not None}
    opts.update(parse_opts(a.opt))
    b.load(**{k: v for k, v in opts.items() if k in {"offload", "dtype"}})
    img, mask = Image.open(a.image).convert("RGB"), Image.open(a.mask).convert("L")
    prompt = a.prompt if a.raw_prompt else b.apply_inpaint_template(a.prompt)
    gen = {k: opts[k] for k in ("steps", "guidance", "lora_scale") if k in opts}
    t0 = time.perf_counter()
    imgs = b.inpaint(prompt, img, mask, seed=a.seed, n=a.n, strength=a.strength, ref=a.ref, **gen)
    total = time.perf_counter() - t0
    stats = b.stats()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for i, im in enumerate(imgs):
        p = out / f"{a.name}-{i}.png"
        im.save(p)
        write_sidecar(p, {"kind": "inpaint", "backend": b.info.to_dict(), "subject": a.prompt, "prompt": prompt,
                          "seed": a.seed + i, "strength": a.strength, "image": str(a.image), "mask": str(a.mask),
                          "size": list(im.size), "refs": a.ref or [], "opts": gen,
                          "timings": {"call_total_s": round(total, 2),
                                      "image_s": (stats.get("last_image_s") or [None] * a.n)[i],
                                      "encode_s": stats.get("last_encode_s"), "load_s": stats.get("load_s")},
                          "stats": stats, "created": datetime.now(timezone.utc).isoformat()})
        files.append(str(p))
    print(json.dumps({"ok": True, "files": files, "prompt": prompt, "seeds": [a.seed + i for i in range(a.n)],
                      "gen_opts": gen, "stats": stats, "total_s": round(total, 2)}))


# ----------------------------------------------------------------- snap
def cmd_snap(a) -> None:
    """Fixed-grid downscale + palette + cleanup of model output (no model needed). One JSON object on stdout."""
    from PIL import Image
    pal = pp.load_palette(a.palette) if a.palette else None
    key = tuple(int(a.key.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) if a.key else None
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res = []
    for s in a.inputs:
        src = Path(s)
        im = Image.open(src)
        tgt = tuple(int(v) for v in a.target.split("x")) if a.target else None
        small, rep = pp.snap_fixed(im, a.factor, palette=pal, colours=a.colours, cleanup_level=a.cleanup,
                                   key=key, grid=a.grid, target=tgt)
        dst = out / f"{src.stem}-snap.png"
        small.save(dst)
        res.append({"source": str(src), "out": str(dst), "report": rep})
    print(json.dumps({"ok": True, "results": res}))


# ----------------------------------------------------------------- post
def post_kwargs(a) -> dict:
    return dict(grid=a.grid, bg=a.bg, colours=a.colours, palette=a.palette,
                outline=None if a.outline == "none" else a.outline,
                cell=parse_cell(a.cell), feet_row=a.feet_row, shadow=a.shadow,
                keep_largest=a.keep_largest, cleanup_level=a.cleanup, tile=a.tile,
                tile_mode=a.tile_mode, keep_dark=a.keep_dark or None)


def post_one(src: Path, out_dir: Path, kw: dict) -> Path:
    from PIL import Image
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    img, rep = pp.run_pipeline(Image.open(src), **kw)
    dst = out_dir / f"{src.stem}_px.png"
    img.save(dst)
    side = {"kind": "post", "source": str(src), "params": kw, "report": rep,
            "post_s": round(time.perf_counter() - t0, 2)}
    gen_side = src.with_suffix(".json")
    if gen_side.exists():
        side["generate"] = json.loads(gen_side.read_text())
    write_sidecar(dst, side)
    return dst


def cmd_post(a) -> None:
    kw = post_kwargs(a)
    for s in a.inputs:
        print(post_one(Path(s), Path(a.out), kw))


def add_post_args(p) -> None:
    p.add_argument("--grid", default="auto", help="auto | fit | <pixel size>")
    p.add_argument("--bg", default="auto", choices=["auto", "none"])
    p.add_argument("--colours", type=int, default=16, help="adaptive palette size")
    p.add_argument("--palette", help="fixed palette (.hex, .gpl or .png)")
    p.add_argument("--outline", default="outer", choices=["outer", "inner", "none"])
    p.add_argument("--cell", help="target cell WxH, e.g. 64x128")
    p.add_argument("--feet-row", type=int, default=None,
                   help="anchor row for the lowest opaque pixel (105 for characters)")
    p.add_argument("--shadow", action="store_true", help="add the project drop shadow")
    p.add_argument("--keep-largest", action="store_true", help="keep only the largest blob")
    p.add_argument("--cleanup", type=int, default=1, choices=[0, 1, 2])
    p.add_argument("--tile", action="store_true", help="make one tile of --cell size")
    p.add_argument("--tile-mode", default="crop", choices=["crop", "resample"],
                   help="crop: native grid then centre crop; resample: whole image -> cell")
    p.add_argument("--keep-dark", type=float, default=0.3,
                   help="keep thin dark lines if this share of a cell is dark (0 = off)")


# -------------------------------------------------------------- palette
def cmd_palette_from(a) -> None:
    cols = pp.load_palette(a.image)
    pp.save_palette_hex(cols, a.out)
    print(f"{len(cols)} colours -> {a.out}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("backends", help="list registered backends")

    g = sub.add_parser("generate", help="generate raw images")
    g.add_argument("--backend", required=True, choices=list(REGISTRY))
    g.add_argument("--prompt", required=True, help="subject; wrapped in the backend template")
    g.add_argument("--raw-prompt", action="store_true", help="send --prompt verbatim")
    g.add_argument("--negative")
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("--n", type=int, default=1)
    g.add_argument("--width", type=int, default=512)
    g.add_argument("--height", type=int, default=512)
    g.add_argument("--ref", nargs="*", help="reference image(s), if the backend supports them")
    g.add_argument("--opt", action="append", help="backend option k=v (repeatable)")
    g.add_argument("--name", help="output file stem")
    g.add_argument("--out", required=True)

    ip = sub.add_parser("inpaint", help="masked img2img on a canvas (white mask = repaint)")
    ip.add_argument("--backend", default="flux2_klein_pixel_lora", choices=list(REGISTRY))
    ip.add_argument("--image", required=True, help="canvas PNG (multiple of 16 px)")
    ip.add_argument("--mask", required=True, help="mask PNG, white = repaint, same size as the canvas")
    ip.add_argument("--prompt", required=True)
    ip.add_argument("--raw-prompt", action="store_true", help="send --prompt without the inpaint template")
    ip.add_argument("--strength", type=float, default=0.75)
    ip.add_argument("--seed", type=int, default=0)
    ip.add_argument("--n", type=int, default=1)
    ip.add_argument("--ref", nargs="*", help="reference image(s) for the masked area")
    ip.add_argument("--opt", action="append", help="backend option k=v (steps, lora_scale, offload, ...)")
    ip.add_argument("--name", default="inpaint")
    ip.add_argument("--out", required=True)

    sn = sub.add_parser("snap", help="downscale model output by a fixed integer factor, palette, cleanup")
    sn.add_argument("inputs", nargs="+")
    sn.add_argument("--factor", type=int, required=True)
    sn.add_argument("--grid", default="fixed", choices=["fixed", "detect"])
    sn.add_argument("--target", help="WxH in output pixels (used by --grid detect)")
    sn.add_argument("--palette", help="fixed palette (.hex, .gpl or .png)")
    sn.add_argument("--colours", type=int, help="adaptive palette size when no --palette")
    sn.add_argument("--cleanup", type=int, default=1, choices=[0, 1, 2])
    sn.add_argument("--key", help="flat key colour #rrggbb to make transparent (alpha layers)")
    sn.add_argument("--out", required=True)

    p = sub.add_parser("post", help="post-process images into pixel art")
    p.add_argument("inputs", nargs="+")
    add_post_args(p)
    p.add_argument("--out", required=True)

    pf = sub.add_parser("palette-from", help="extract a .hex palette from an image")
    pf.add_argument("image")
    pf.add_argument("--out", required=True)

    a = ap.parse_args(argv)
    if a.cmd == "backends":
        for name in REGISTRY:
            try:
                info = get_backend(name).info
                print(f"{name}: {info.description} | models={info.models} | licence={info.licence}")
            except Exception as e:  # noqa: BLE001
                print(f"{name}: (failed to import: {e})")
    elif a.cmd == "generate":
        cmd_generate(a)
    elif a.cmd == "inpaint":
        cmd_inpaint(a)
    elif a.cmd == "snap":
        cmd_snap(a)
    elif a.cmd == "post":
        cmd_post(a)
    elif a.cmd == "palette-from":
        cmd_palette_from(a)


if __name__ == "__main__":
    main()
