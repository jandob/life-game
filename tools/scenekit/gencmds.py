"""Model-backed commands: generate (region), fill (cells), apply (commit a candidate through the import core).

The model runs as a subprocess in the artgen venv; this module only needs Pillow."""
import json
import os
import secrets
import subprocess
import sys
import time

from PIL import Image, ImageDraw

import genkit as G
from common import (HERE, OUT_DIR, TILE, Scene, SceneError, abspath_from_root, load_materials, make_meta, normalize_key,
                    parse_region, parse_shape, png_bytes, rel, sha, atomic_write, json_bytes, tile_hash)
from compose import Resolver, cell_image
from editcore import Opts, apply_cells, finish, new_result, summarize
from viewcmds import clip_region

JOBS_DIR = os.path.join(OUT_DIR, "jobs")
ARTGEN_DIR = os.path.abspath(os.path.join(HERE, "..", "artgen"))
BACKEND = "flux2_klein_pixel_lora"
MODELS = {"base": "black-forest-labs/FLUX.2-klein-4B", "lora": "Limbicnation/pixel-art-lora"}


# --------------------------------------------------------------------------- artgen subprocesses

def artgen_python():
    p = os.environ.get("SCENEKIT_ARTGEN_PYTHON") or os.path.join(ARTGEN_DIR, ".venv", "bin", "python")
    if not os.path.isfile(p):
        raise SceneError(f"artgen python not found: {p} (the model runs in tools/artgen/.venv; "
                         f"see tools/artgen/README.md)", "not_found")
    return p


def artgen_script():
    return os.environ.get("SCENEKIT_ARTGEN") or os.path.join(ARTGEN_DIR, "artgen.py")


def run_artgen(args, log_path, timeout):
    """Run `artgen.py ARGS`, keep stderr in log_path, return the JSON object printed last on stdout."""
    cmd = [artgen_python(), artgen_script()] + [str(a) for a in args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SceneError(f"artgen {args[0]} timed out after {timeout}s", "error")
    with open(log_path, "a") as f:
        f.write(f"$ {' '.join(cmd)}\n{r.stderr}\n")
    if r.returncode != 0:
        tail = "\n".join(r.stderr.strip().splitlines()[-6:])
        raise SceneError(f"artgen {args[0]} failed (exit {r.returncode}); see {rel(log_path)}\n{tail}", "error")
    for line in reversed(r.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise SceneError(f"artgen {args[0]} printed no JSON; see {rel(log_path)}", "error")


# --------------------------------------------------------------------------- shared helpers

def new_job_id():
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + secrets.token_hex(2)


def parse_cells_arg(text, m):
    cells = set()
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        try:
            x, y = [int(v) for v in part.split(",")]
        except ValueError:
            raise SceneError(f"--cells entries must be 'x,y' separated by ';', got '{part}'", "bad_input")
        if not (0 <= x < m.width and 0 <= y < m.height):
            raise SceneError(f"cell ({x},{y}) is outside the {m.width}x{m.height} map", "bad_input")
        cells.add((x, y))
    if not cells:
        raise SceneError("--cells is empty", "bad_input")
    return cells


def cell_metas(layout, region, materials):
    """{(x, y): meta} for cells the layout names; the others inherit from the tile they replace."""
    out = {}
    if layout is None:
        return out
    rx, ry = region[0], region[1]
    for j, row in enumerate(layout):
        for i, mat in enumerate(row):
            if mat:
                out[(rx + i, ry + j)] = (mat, make_meta(parse_shape(materials[mat].get("shape", "none")), "", mat))
    return out


def simulate(map_path, layer_name, new_cells, meta_override, near, no_inherit=False):
    """What apply would do, in a throw-away Scene (nothing is written): counts of new / deduplicated tiles."""
    sc = Scene("generate-stats", dry_run=True)
    m = sc.load_map(map_path)
    layer = m.layer(layer_name, "tilelayer")
    o = Opts(None, origin="generate", near=near, inherit=not no_inherit)
    res = apply_cells(sc, m, layer, new_cells, o, meta_override=meta_override or None)
    placed = [r for r in res["cells_changed"] if r["new"]]
    new = len(res["tiles_new"])
    near_n = len(res["near_matches"])
    return {"cells_changed": len(res["cells_changed"]), "tiles_new": new, "deduped": max(0, len(placed) - new - near_n),
            "near_matches": near_n, "cells_unchanged": len(new_cells) - len(res["cells_changed"])}


def palette_args(sc, m, spec, cells, job_dir, colours):
    """-> (snap args, description). spec: 'scene' | 'none' | path to a .hex/.gpl/.png palette."""
    if spec in (None, "scene"):
        pal = G.scene_palette(sc, m, cells)
        if pal:
            p = os.path.join(job_dir, "palette.hex")
            G.write_hex(p, pal)
            return ["--palette", p], f"scene ({len(pal)} colours of the map outside the region)"
        return ["--colours", str(colours)], f"adaptive {colours} (the map has too few colours for 'scene')"
    if spec == "none":
        return [], "none"
    p = abspath_from_root(spec)
    if not os.path.isfile(p):
        raise SceneError(f"palette file not found: {spec}", "not_found")
    return ["--palette", p], f"file {rel(p)}"


def contact_sheet(job_dir, region, cands, cols=2, zoom=3):
    rx, ry, rw, rh = region
    w, h = rw * TILE * zoom, rh * TILE * zoom + 14
    rows = (len(cands) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * (w + 8) + 8, rows * (h + 8) + 8), (20, 20, 20, 255))
    d = ImageDraw.Draw(sheet)
    for i, c in enumerate(cands):
        im = Image.open(os.path.join(job_dir, c["file"])).convert("RGBA")
        bg = Image.new("RGBA", im.size, (60, 60, 60, 255))
        im = Image.alpha_composite(bg, im).resize((w, h - 14), Image.NEAREST)
        im = G.draw_grid(im, TILE * zoom)
        x, y = 8 + (i % cols) * (w + 8), 8 + (i // cols) * (h + 8)
        d.text((x, y), f"cand-{c['k']}  seed {c['seed']}", fill=(255, 255, 255, 255))
        sheet.paste(im, (x, y + 14))
    out = os.path.join(job_dir, "contact.png")
    sheet.save(out)
    return out


def write_png(path, img):
    atomic_write(path, png_bytes(img))


# --------------------------------------------------------------------------- the pipeline

def run_pipeline(a, kind, m, sc, layer, cells, region, layout, layout_hash, layout_materials):
    t_all = time.perf_counter()
    materials = load_materials()
    alpha = bool(a.alpha)
    canvas = G.build_canvas(sc, m, layer, cells, region, layout, a.context, a.scale, alpha)
    job = new_job_id()
    job_dir = os.path.join(JOBS_DIR, job)
    os.makedirs(job_dir)
    log = os.path.join(job_dir, "model.log")
    write_png(os.path.join(job_dir, "canvas.png"), canvas.image)
    write_png(os.path.join(job_dir, "mask.png"), canvas.mask)
    write_png(os.path.join(job_dir, "base.png"), canvas.base)

    hints = G.layout_hints(layout, materials) if layout is not None else []
    subject = ", ".join([t for t in [a.prompt.strip() if a.prompt else ""] + hints if t]) or "matching the surrounding scene"
    refs = [abspath_from_root(r) for r in (a.ref or [])]
    for r in refs:
        if not os.path.isfile(r):
            raise SceneError(f"reference image not found: {r}", "not_found")
    like = getattr(a, "like", None)
    if like:
        key, _ = normalize_key(like, m)
        ts, local = sc.resolve_key(key, m)
        lp = os.path.join(job_dir, "ref-like.png")
        t = sc.tile_image(ts, local).convert("RGB")
        write_png(lp, t.resize((t.width * canvas.scale * 4, t.height * canvas.scale * 4), Image.NEAREST))
        refs.append(lp)
    pal_args, pal_desc = palette_args(sc, m, a.palette, cells, job_dir, a.colours)

    info = {
        "id": job, "kind": kind, "map": rel(m.path), "map_hash": sc.map_hash(m), "layer": layer["name"],
        "region": list(region), "cells": sorted([x, y] for x, y in cells), "box": list(canvas.box), "context": canvas.ring,
        "context_requested": a.context, "scale": canvas.scale, "canvas_px": list(canvas.image.size), "prompt_subject": subject,
        "strength": a.strength, "steps": a.steps, "lora_scale": a.lora_scale, "seed": a.seed, "n": a.n,
        "palette": pal_desc, "alpha": alpha, "grid": a.grid, "near": a.near, "ring_fill": getattr(a, "ring", 0),
        "refs": [sha(open(r, "rb").read()) for r in refs], "layout": layout_hash,
        "materials": {f"{x},{y}": mat for (x, y), (mat, _meta) in layout_materials.items()},
        "layer_gids": {f"{x},{y}": layer["data"][y * m.width + x] for (x, y) in sorted(cells)},
        "backend": BACKEND, "models": MODELS, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    mismatch = sorted({mt for (mt, _m) in layout_materials.values()
                       if materials[mt].get("layer") and materials[mt]["layer"] != layer["name"]})
    if mismatch:
        info["warnings"] = [f"materials {mismatch} have a different layer hint than '{layer['name']}'; "
                            f"they are written to '{layer['name']}' anyway"]
    if a.dry_run:
        info["dry_run"] = True
        atomic_write(os.path.join(job_dir, "job.json"), json_bytes(info, indent=1))
        return {"ok": True, "job": job, "dir": rel(job_dir), "dry_run": True, "canvas": rel(os.path.join(job_dir, "canvas.png")),
                "mask": rel(os.path.join(job_dir, "mask.png")), "scale": canvas.scale, "box": list(canvas.box),
                "context": canvas.ring, "canvas_px": info["canvas_px"], "prompt_subject": subject, "palette": pal_desc,
                "warnings": info.get("warnings", [])}

    # 1. model
    t0 = time.perf_counter()
    args = ["inpaint", "--image", os.path.join(job_dir, "canvas.png"), "--mask", os.path.join(job_dir, "mask.png"),
            "--prompt", subject, "--strength", a.strength, "--seed", a.seed, "--n", a.n, "--name", "raw",
            "--opt", f"steps={a.steps}", "--opt", f"lora_scale={a.lora_scale}", "--out", job_dir]
    if refs:
        args += ["--ref"] + refs
    mres = run_artgen(args, log, a.timeout)
    t_model = time.perf_counter() - t0
    info["prompt"] = mres["prompt"]
    info["model"] = {"seconds": round(t_model, 1), "stats": mres.get("stats"), "gen_opts": mres.get("gen_opts")}

    # 2. snap to the grid, palette, cleanup
    t0 = time.perf_counter()
    raws = [os.path.join(job_dir, f"raw-{i}.png") for i in range(a.n)]
    sargs = ["snap"] + raws + ["--factor", canvas.scale, "--grid", a.grid, "--cleanup", a.cleanup, "--out", job_dir,
                               "--target", f"{canvas.box[2] * TILE}x{canvas.box[3] * TILE}"] + pal_args
    if alpha:
        sargs += ["--key", "#%02x%02x%02x" % G.KEY]
    sres = run_artgen(sargs, log, a.timeout)
    t_snap = time.perf_counter() - t0

    # 3. candidates, stats, previews
    cands = []
    for i, r in enumerate(sres["results"]):
        snapped = Image.open(r["out"]).convert("RGBA")
        cells_img = G.cut_cells(snapped, canvas.box, cells)
        cand = G.region_image(cells_img, region, cells)
        write_png(os.path.join(job_dir, f"cand-{i}.png"), cand)
        prev = G.preview_image(canvas.base, canvas.box, cells_img, cells, 4, f"cand-{i} seed {a.seed + i}")
        write_png(os.path.join(job_dir, f"preview-{i}.png"), prev)
        meta_over = {c: mt for c, (_n, mt) in layout_materials.items()}
        stats = simulate(m.path, layer["name"], cells_img, meta_over, __import__("editcore").parse_near(a.near))
        cands.append({"k": i, "seed": a.seed + i, "file": f"cand-{i}.png", "preview": f"preview-{i}.png",
                      "raw": f"raw-{i}.png", "snap_report": r["report"], **stats})
    contact = contact_sheet(job_dir, region, cands)
    info.update(candidates=cands, contact=os.path.basename(contact),
                timings={"model_s": round(t_model, 1), "snap_s": round(t_snap, 1),
                         "total_s": round(time.perf_counter() - t_all, 1)})
    atomic_write(os.path.join(job_dir, "job.json"), json_bytes(info, indent=1))
    return {"ok": True, "job": job, "dir": rel(job_dir), "kind": kind, "map": info["map"], "map_hash": info["map_hash"],
            "layer": info["layer"], "region": info["region"], "box": info["box"], "scale": canvas.scale, "context": canvas.ring,
            "prompt": info["prompt"], "palette": pal_desc, "contact": rel(contact), "timings": info["timings"],
            "candidates": [{k: c[k] for k in ("k", "seed", "file", "preview", "tiles_new", "deduped", "near_matches",
                                              "cells_changed")} | {"colours": c["snap_report"]["colours_used"]} for c in cands],
            "warnings": info.get("warnings", []), "next": f"scene.py apply {job} --pick K"}


def check_common(a):
    if a.n < 1 or a.n > 16:
        raise SceneError("--n must be 1..16", "bad_input")
    if not 0.05 <= a.strength <= 1.0:
        raise SceneError("--strength must be between 0.05 and 1.0", "bad_input")
    if a.context < 0:
        raise SceneError("--context must be >= 0", "bad_input")


def cmd_generate(a):
    check_common(a)
    sc = Scene("generate", True)
    m = sc.load_map(abspath_from_root(a.map), a.if_hash)
    layer = m.layer(a.layer, "tilelayer")
    region = clip_region(m, parse_region(a.region))
    if region != tuple(parse_region(a.region)):
        raise SceneError(f"region {a.region} reaches outside the {m.width}x{m.height} map", "bad_input")
    rx, ry, rw, rh = region
    cells = {(x, y) for y in range(ry, ry + rh) for x in range(rx, rx + rw)}
    layout = layout_hash = None
    if a.layout:
        layout, layout_hash = G.load_layout(abspath_from_root(a.layout), rw, rh, load_materials())
    return run_pipeline(a, "generate", m, sc, layer, cells, region, layout, layout_hash,
                        cell_metas(layout, region, load_materials()))


def cmd_fill(a):
    check_common(a)
    if a.ring not in (0, 1):
        raise SceneError("--ring must be 0 or 1", "bad_input")
    modes = [bool(a.cells), bool(a.mask), bool(a.empty)]
    if sum(modes) != 1:
        raise SceneError("fill needs exactly one of --cells, --mask, --empty", "bad_input")
    sc = Scene("fill", True)
    m = sc.load_map(abspath_from_root(a.map), a.if_hash)
    layer = m.layer(a.layer, "tilelayer")
    reg = None
    if a.region:
        reg = parse_region(a.region)
        if clip_region(m, reg) != tuple(reg):
            raise SceneError(f"region {a.region} reaches outside the {m.width}x{m.height} map", "bad_input")
    if a.cells:
        cells = parse_cells_arg(a.cells, m)
    elif a.mask:
        mp = abspath_from_root(a.mask)
        if not os.path.isfile(mp):
            raise SceneError(f"mask not found: {a.mask}", "not_found")
        im = Image.open(mp).convert("L")
        ox, oy, mw, mh = reg if reg else (0, 0, m.width, m.height)
        if im.size != (mw, mh):
            raise SceneError(f"mask is {im.size[0]}x{im.size[1]}, expected one pixel per cell: {mw}x{mh}"
                             f"{'' if reg else ' (the whole map; pass --region for a smaller mask)'}", "bad_input")
        cells = {(ox + x, oy + y) for y in range(mh) for x in range(mw) if im.getpixel((x, y)) >= 128}
    else:
        if not reg:
            raise SceneError("--empty needs --region", "bad_input")
        rx, ry, rw, rh = reg
        cells = {(x, y) for y in range(ry, ry + rh) for x in range(rx, rx + rw) if not layer["data"][y * m.width + x]}
    if not cells:
        raise SceneError("no cells to fill (the mask is empty)", "bad_input")
    if a.ring:
        cells |= {(x + dx, y + dy) for (x, y) in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                  if 0 <= x + dx < m.width and 0 <= y + dy < m.height}
    return run_pipeline(a, "fill", m, sc, layer, cells, G.bbox_of(cells), None, None, {})


# --------------------------------------------------------------------------- apply

def load_job(spec):
    p = abspath_from_root(spec)
    if not os.path.isdir(p):
        p = os.path.join(JOBS_DIR, spec)
    jp = os.path.join(p, "job.json")
    if not os.path.isfile(jp):
        raise SceneError(f"job not found: {spec} (looked for {jp})", "not_found")
    with open(jp) as f:
        job = json.load(f)
    if job.get("dry_run"):
        raise SceneError(f"job {job['id']} is a dry run (no candidates)", "bad_input")
    return p, job


def cmd_apply(a):
    jdir, job = load_job(a.job)
    cands = {c["k"]: c for c in job["candidates"]}
    if a.pick not in cands:
        raise SceneError(f"job {job['id']} has candidates {sorted(cands)}, not {a.pick}", "bad_input")
    c = cands[a.pick]
    sc = Scene("apply", a.dry_run)
    m = sc.load_map(abspath_from_root(job["map"]), a.if_hash)
    layer = m.layer(job["layer"], "tilelayer")
    cells = [tuple(x) for x in job["cells"]]
    cand = Image.open(os.path.join(jdir, c["file"])).convert("RGBA")
    rx, ry = job["region"][0], job["region"][1]
    new_cells = {(x, y): cand.crop(((x - rx) * TILE, (y - ry) * TILE, (x - rx + 1) * TILE, (y - ry + 1) * TILE)) for (x, y) in cells}
    # a cell is stale if its tile changed since the job was made, unless it already shows the candidate (re-apply)
    resolver = Resolver(m)
    stale = [[x, y] for (x, y) in cells
             if layer["data"][y * m.width + x] != job["layer_gids"][f"{x},{y}"]
             and tile_hash(cell_image(sc, m, layer, x, y, resolver)) != tile_hash(new_cells[(x, y)])]
    if stale and not a.force:
        raise SceneError(f"{len(stale)} cell(s) of the job's region changed on layer '{layer['name']}' since the job was "
                         f"made (first: {stale[:8]}); regenerate, or pass --force to overwrite", "conflict", cells=stale)
    materials = load_materials()
    meta_over = {}
    for key, mat in job["materials"].items():
        x, y = [int(v) for v in key.split(",")]
        if mat not in materials:
            raise SceneError(f"material '{mat}' from the job is no longer in materials.json", "bad_input")
        meta_over[(x, y)] = make_meta(parse_shape(materials[mat].get("shape", "none")), "", mat)
    gen = {"backend": job["backend"], "models": job["models"], "lora_scale": job["lora_scale"], "prompt": job["prompt"],
           "seed": c["seed"], "strength": job["strength"], "steps": job["steps"], "scale": job["scale"], "refs": job["refs"],
           "layout": job["layout"], "palette": job["palette"], "alpha": job["alpha"]}
    near = a.near if a.near is not None else job.get("near")
    o = Opts(a, origin=job["kind"], job=job["id"], gen=gen)
    o.near = __import__("editcore").parse_near(near)
    res = apply_cells(sc, m, layer, new_cells, o, meta_override=meta_over or None)
    res = summarize(finish(sc, m, res, bool(res["cells_changed"])))
    res.update(job=job["id"], pick=a.pick, seed=c["seed"], region=job["region"], layer=job["layer"])
    return res
