#!/usr/bin/env python
"""Run a backend over the fixed benchmark prompt set, post-process, and write
contact sheets plus a markdown results table.

    bench.py --backend flux2_klein_pixel_lora --out OUT \
        [--variant name:k=v,k=v ...] [--items id,id] [--seeds 11,42]

Layout of OUT/<backend>/<variant>/:
    raw/<item>_s<seed>.png (+ .json)       model output
    px/<item>_s<seed>_px.png (+ .json)     post-processed
    rows/<item>.png                        one contact-sheet row per item
    contact.png                            all rows
    results.md                             timings, memory, post reports
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import postprocess as pp  # noqa: E402
from artgen import generate_images, parse_opts, write_sidecar  # noqa: E402
from backends import REGISTRY, get_backend  # noqa: E402

REPO = HERE.parent.parent
PROFILE_FILE = Path(pp.PROFILE["_path"])
# profile paths: bench_ref_sheet is relative to the project root (the parent of art/), bench to the profile file
REF_SHEET = (PROFILE_FILE.parent.parent / pp.PROFILE["bench_ref_sheet"]) if pp.PROFILE.get("bench_ref_sheet") else None
BG = (200, 200, 210, 255)
ROW_H = 512
LABEL_W = 220


def font(size=16):
    for f in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def zoom(img: Image.Image, k: int) -> Image.Image:
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def on_bg(img: Image.Image) -> Image.Image:
    bg = Image.new("RGBA", img.size, BG)
    bg.alpha_composite(img.convert("RGBA"))
    return bg


def view_processed(px: Image.Image, kind: str) -> Image.Image:
    """Processed output at 4x (smaller zoom only if it would not fit)."""
    if kind == "tile":
        tiled = Image.new("RGBA", (px.width * 3, px.height * 3))
        for j in range(3):
            for i in range(3):
                tiled.paste(px, (i * px.width, j * px.height))
        k = max(1, min(4, (ROW_H // 2) // tiled.height))
        single = zoom(px, max(1, (ROW_H // 2 - 8) // px.height))
        out = Image.new("RGBA", (max(single.width, tiled.width * k), ROW_H), BG)
        out.paste(single, (0, 0))
        out.paste(zoom(tiled, k), (0, ROW_H // 2))
        return out
    k = 4
    while k > 1 and (px.height * k > ROW_H or px.width * k > ROW_H):
        k -= 1
    return on_bg(zoom(px, k))


def reference_cell() -> Image.Image | None:
    if REF_SHEET is None or not REF_SHEET.exists():
        return None
    return on_bg(zoom(Image.open(REF_SHEET).convert("RGBA").crop((0, 0, 64, 128)), 4))


def build_row(item: dict, cells: list[tuple[Image.Image, Image.Image, int]], ref) -> Image.Image:
    parts = []
    for raw, px, seed in cells:
        parts.append(("raw s%d" % seed, raw.convert("RGBA").resize((ROW_H, ROW_H), Image.NEAREST)))
        parts.append(("px s%d %dx%d" % (seed, px.width, px.height), view_processed(px, item["kind"])))
    if item["kind"] == "character" and ref is not None:
        parts.append(("reference player.png", ref))
    w = LABEL_W + sum(p.width + 12 for _, p in parts)
    row = Image.new("RGBA", (w, ROW_H + 24), (255, 255, 255, 255))
    d = ImageDraw.Draw(row)
    d.text((8, 8), item["id"], fill=(0, 0, 0), font=font(20))
    d.text((8, 36), item["kind"], fill=(90, 90, 90), font=font(14))
    x = LABEL_W
    for label, im in parts:
        row.paste(im, (x, 24))
        d.text((x, 4), label, fill=(0, 0, 0), font=font(14))
        x += im.width + 12
    return row


def stack(rows: list[Image.Image]) -> Image.Image:
    w = max(r.width for r in rows)
    out = Image.new("RGBA", (w, sum(r.height + 6 for r in rows)), (255, 255, 255, 255))
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height + 6
    return out


def parse_variant(s: str) -> tuple[str, dict]:
    name, _, rest = s.partition(":")
    return name, parse_opts([kv for kv in rest.split(",") if kv])


def bench_size(bench: dict, backend_name: str) -> tuple[int, int]:
    """Generation size: the yaml's ``sizes[<backend>]`` if present, else its ``width``/``height``
    (512 by default). Same for every backend that has no entry, so existing runs are unchanged."""
    if backend_name in (bench.get("sizes") or {}):
        w, h = bench["sizes"][backend_name]
        return int(w), int(h)
    return int(bench.get("width", 512)), int(bench.get("height", 512))


def item_post_kwargs(item: dict) -> dict:
    kw = dict(item.get("post", {}))
    if "cell" in kw and kw["cell"] is not None:
        kw["cell"] = tuple(kw["cell"])
    return kw


def run(args) -> None:
    if not args.bench:
        raise SystemExit("no bench file: pass --bench FILE (the active profile defines none)")
    bench = yaml.safe_load(Path(args.bench).read_text())
    items = bench["items"]
    if args.items:
        keep = set(args.items.split(","))
        items = [i for i in items if i["id"] in keep]
    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else bench["seeds"]
    variants = [parse_variant(v) for v in (args.variant or ["default:"])]
    size = bench_size(bench, args.backend)

    b = get_backend(args.backend)
    base_opts = {k: v for k, v in b.info.defaults.items() if v is not None}
    base_opts.update(parse_opts(args.opt))
    load_keys = b.load_keys
    t0 = time.perf_counter()
    if not args.post_only:
        b.load(**{k: v for k, v in base_opts.items() if k in load_keys})
    load_s = time.perf_counter() - t0

    def full_prompt(item):
        fields = {"background": item["background"]} if item.get("background") else {}
        return b.apply_template(item["subject"].strip(), **fields)

    if args.precompute and not args.post_only:
        t1 = time.perf_counter()
        b.precompute([full_prompt(i) for i in items])
        print(f"precomputed {len(items)} prompts in {time.perf_counter() - t1:.1f}s", flush=True)

    ref = reference_cell()
    root = Path(args.out) / args.backend
    for vname, vopts in variants:
        vdir = root / vname
        for sub in ("raw", "px", "rows"):
            (vdir / sub).mkdir(parents=True, exist_ok=True)
        opts = {k: v for k, v in base_opts.items() if k not in load_keys}
        opts.update(vopts)
        records, rows = [], []
        post_only_stats: dict = {}
        for item in items:
            cells = []
            for seed in seeds:
                gen_opts = dict(opts)
                if item.get("background"):
                    gen_opts["background"] = item["background"]
                if item.get("ref"):
                    gen_opts["ref"] = str(vdir / "raw" / f"{item['ref']}_s{seed}.png")
                t = time.perf_counter()
                existing = vdir / "raw" / f"{item['id']}_s{seed}.png"
                if args.post_only:
                    if not existing.exists():
                        print(f"skip {existing} (missing)")
                        continue
                    raw_p = existing
                    side = json.loads(existing.with_suffix(".json").read_text())
                    gen_s = side["timings"]["image_s"] or side["timings"]["call_total_s"]
                    st = {"last_encode_s": side["timings"].get("encode_s")}
                    post_only_stats.update(side.get("stats") or {})
                else:
                    [raw_p] = generate_images(b, item["subject"].strip(), raw_prompt=False, seed=seed,
                                              n=1, width=size[0],
                                              height=size[1], negative=None,
                                              opts=gen_opts, out_dir=vdir / "raw",
                                              stem=item["id"])
                    gen_s = time.perf_counter() - t
                    st = b.stats()
                raw = Image.open(raw_p)
                kw = item_post_kwargs(item)
                t = time.perf_counter()
                px, rep = pp.run_pipeline(raw, **kw)
                post_s = time.perf_counter() - t
                px_p = vdir / "px" / f"{item['id']}_s{seed}_px.png"
                px.save(px_p)
                write_sidecar(px_p, {"kind": "post", "source": str(raw_p), "params": kw,
                                     "report": rep, "post_s": round(post_s, 2)})
                records.append({"item": item["id"], "kind": item["kind"], "seed": seed,
                                "gen_s": round(gen_s, 1), "encode_s": st.get("last_encode_s"),
                                "post_s": round(post_s, 2), "report": rep,
                                "raw": str(raw_p), "px": str(px_p)})
                print(f"[{vname}] {item['id']} s{seed}: gen {gen_s:.1f}s post {post_s:.2f}s "
                      f"-> {rep.get('final_size')} grid={rep.get('grid')}", flush=True)
                cells.append((raw, px, seed))
            row = build_row(item, cells, ref)
            row.save(vdir / "rows" / f"{item['id']}.png")
            rows.append(row)
        stack(rows).save(vdir / "contact.png")
        stats = post_only_stats if args.post_only else b.stats()
        if args.post_only:
            load_s = stats.get("load_s", 0.0)
        write_table(vdir / "results.md", args.backend, b, vname, opts, load_s, records, stats)
        (vdir / "results.json").write_text(json.dumps(
            {"backend": b.info.to_dict(), "variant": vname, "opts": opts,
             "load_s": round(load_s, 1), "stats": stats, "records": records},
            indent=2, default=str))
        print(f"wrote {vdir / 'contact.png'}", flush=True)


def note_for(r: dict) -> str:
    rep, notes = r["report"], []
    bgi = rep.get("background", {})
    if bgi.get("bg_fraction") is not None:
        f = bgi["bg_fraction"]
        if f < 0.2:
            notes.append(f"bg removal weak ({f:.0%} removed)")
        elif f > 0.95:
            notes.append(f"almost all removed ({f:.0%})")
    if rep.get("cell", {}).get("clipped"):
        notes.append("clipped to cell")
    g = rep.get("grid", {})
    if g.get("mode") == "auto" and g.get("score", 1) < 0.15:
        notes.append("weak grid signal")
    return "; ".join(notes)


def write_table(path: Path, backend: str, b, vname: str, opts: dict, load_s: float,
                records: list[dict], st: dict) -> None:
    lines = [
        f"# Bench: {backend} / {vname}", "",
        f"- Models: {', '.join(b.info.models)}",
        f"- Licence: {b.info.licence}",
        f"- Options: `{json.dumps(opts)}`",
        f"- Load time: {load_s:.1f}s; device {st.get('device')}, dtype {st.get('dtype')}, "
        f"offload {st.get('offload')}",
        f"- Peak MPS driver memory: {st.get('peak_mps_driver_gb')} GB overall "
        f"(includes text encoding), {st.get('peak_mps_gen_gb', 'n/a')} GB during image generation; "
        f"peak process RSS: {st.get('peak_rss_gb')} GB",
        f"- Contact sheet: `{path.parent / 'contact.png'}`", "",
        "| item | kind | seed | gen s | encode s | post s | grid | native | final | colours | notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        rep = r["report"]
        g = rep.get("grid", {})
        gs = g.get("scale", g.get("scale_x"))
        lines.append(
            f"| {r['item']} | {r['kind']} | {r['seed']} | {r['gen_s']} | {r['encode_s']} | "
            f"{r['post_s']} | {g.get('mode')} {gs} | {rep.get('native_size')} | "
            f"{rep.get('final_size')} | {rep.get('colours_used')} | {note_for(r)} |")
    gens = [r["gen_s"] for r in records]
    lines += ["", f"Mean generation time: {sum(gens) / len(gens):.1f}s per image "
              f"(min {min(gens)}, max {max(gens)}), {len(gens)} images.", ""]
    path.write_text("\n".join(lines))


def default_bench() -> str | None:
    b = pp.PROFILE.get("bench")
    return str(Path(pp.PROFILE["_path"]).parent / b) if b else None


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", required=True, choices=list(REGISTRY))
    ap.add_argument("--bench", default=default_bench(),
                    help="bench yaml (default: the active profile's `bench` file; required if the profile has none)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--variant", action="append",
                    help="name:k=v,k=v backend options for one run (repeatable)")
    ap.add_argument("--opt", action="append", help="option k=v applied to all variants")
    ap.add_argument("--items", help="comma-separated item ids (default all)")
    ap.add_argument("--seeds", help="comma-separated seeds (default from yaml)")
    ap.add_argument("--post-only", action="store_true",
                    help="reuse existing raw images, only redo post-processing and sheets")
    ap.add_argument("--precompute", action="store_true",
                    help="let the backend pre-encode all prompts (frees the text encoder)")
    run(ap.parse_args(argv))


if __name__ == "__main__":
    main()
