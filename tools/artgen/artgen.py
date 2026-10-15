#!/usr/bin/env python
"""artgen: generate raw images with a pluggable backend, then post-process
them into game-ready pixel art. Every output gets a JSON sidecar so it can be
reproduced.

    artgen.py backends
    artgen.py generate --backend flux2_klein_pixel_lora --prompt "..." --seed 1 --n 4 --out DIR
    artgen.py inpaint --image canvas.png --mask mask.png --prompt "..." --strength 0.75 --n 4 --out DIR
    artgen.py refine --image scene.png --mask head.png --strength 0.4 --prompt "..." --out DIR
    artgen.py mask --size 1024x768 --heads 0.2,0.1,0.3,0.3 --units frac --out mask.png
    artgen.py pose --preset stand_front --size 832x1216 --out pose.png
    artgen.py snap DIR/*.png --factor 4 --palette p.hex --out DIR2
    artgen.py post DIR/*.png --grid fit --cell 64x128 --feet-row 105 --shadow --out DIR2
    artgen.py palette-from IMAGE --out art/palettes/x.hex
    artgen.py cache --stats | --prune --older-than 30

Run with tools/artgen/.venv/bin/python.
"""
from __future__ import annotations

import argparse
import json
import math
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


# ------------------------------------------------------------- capabilities
CAPS_DOC = {"refs": "generate --ref", "edit": "edit", "sheet": "sheet", "rgba": "--opt rgba=1 (real alpha)",
            "inpaint": "inpaint", "refine": "refine", "remote": "--opt runner=remote:NAME"}


def require_cap(name: str, cap: str, what: str) -> None:
    """Exit with a clear message unless backend ``name`` declares ``cap`` (see BackendInfo.caps)."""
    have = lambda info: cap in getattr(info, "caps", frozenset())  # noqa: E731
    if have(get_backend(name).info):
        return
    ok = []
    for other in REGISTRY:
        try:
            if have(get_backend(other).info):
                ok.append(other)
        except Exception:  # noqa: BLE001
            pass
    raise SystemExit(f"backend {name} does not support {what}; backends that do: {', '.join(ok) or 'none'}")


def open_backend(name: str, opts: dict, kind: str):
    """Backend for generate/edit/sheet honouring ``--opt runner=local|remote:<name>`` (consumed here).

    local: the registered backend, loaded. remote:<name>: a ``runner.RunnerBackend`` proxy that ships each
    call as a JobSpec to ``ARTGEN_REMOTE_<NAME>_CMD`` (nothing is loaded locally).
    """
    import runner as runnermod
    spec = opts.pop("runner", "local")
    if spec != "local":
        require_cap(name, "remote", "--opt runner=remote:NAME")
        return runnermod.RunnerBackend(name, spec, kind=kind, variant=opts.get("variant"))
    b = get_backend(name)
    b.load(**{k: v for k, v in opts.items() if k in b.load_keys})
    return b


def generate_images(backend, subject: str, *, raw_prompt: bool, seed: int, n: int,
                    width: int, height: int, negative: str | None, opts: dict,
                    out_dir: Path, stem: str | None = None) -> list[Path]:
    """Generate n images for one prompt and write PNG + sidecar each."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl_fields = {k: v for k, v in opts.items()
                   if isinstance(v, str) or k in getattr(backend, "template_flags", ())}
    prompt = subject if raw_prompt else backend.apply_template(subject, **tmpl_fields)
    gen_opts = {k: v for k, v in opts.items()
                if k not in tmpl_fields or k in backend.passthrough_opts}
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
            "stats": stats, "profile": pp.PROFILE["_path"],
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
        require_cap(a.backend, "refs", "--ref")
    if opts.get("rgba"):
        require_cap(a.backend, "rgba", "--opt rgba=1")
    b = open_backend(a.backend, opts, "generate")
    gen = {k: v for k, v in opts.items() if k not in b.load_keys}
    dw, dh = b.info.default_size
    paths = generate_images(b, a.prompt, raw_prompt=a.raw_prompt, seed=a.seed, n=a.n,
                            width=a.width or dw, height=a.height or dh, negative=a.negative,
                            opts=gen, out_dir=Path(a.out), stem=a.name)
    stats = b.stats()
    if a.json:
        # opt-in: path-per-line stays the default because shell jobs parse it
        print(json.dumps({"ok": True, "files": [str(p) for p in paths],
                          "seeds": [a.seed + i for i in range(len(paths))], "stats": stats}))
        return
    for p in paths:
        print(p)
    print(json.dumps(stats), file=sys.stderr)


# -------------------------------------------------------------- inpaint
def cmd_inpaint(a) -> None:
    """Masked img2img on a canvas: n candidates, one PNG + sidecar each. Prints one JSON object on stdout."""
    from PIL import Image
    require_cap(a.backend, "inpaint", "inpaint")
    b = get_backend(a.backend)
    if not hasattr(b, "inpaint"):
        raise SystemExit(f"backend {a.backend} has no inpaint()")
    opts = {k: v for k, v in b.info.defaults.items() if v is not None}
    opts.update(parse_opts(a.opt))
    b.load(**{k: v for k, v in opts.items() if k in b.load_keys})
    img, mask = Image.open(a.image).convert("RGB"), Image.open(a.mask).convert("L")
    prompt = a.prompt if a.raw_prompt else b.apply_inpaint_template(a.prompt, **opts)
    gen = {k: opts[k] for k in b.inpaint_keys if k in opts}
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


# --------------------------------------------------------------- refine
def file_sha256(path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_atomic(im, dst: Path) -> None:
    tmp = dst.with_name(dst.name + ".tmp.png")
    im.save(tmp)
    tmp.replace(dst)


def write_sidecar_atomic(png: Path, data: dict) -> None:
    sc = png.with_suffix(".json")
    tmp = sc.with_name(sc.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(sc)


def cmd_refine(a) -> None:
    """img2img of an existing image with the chosen backend (FLUX klein inpaint), optional mask.
    One PNG + sidecar (with the source image hash) per strength x n. One JSON object on stdout."""
    from PIL import Image
    require_cap(a.backend, "refine", "refine")
    b = get_backend(a.backend)
    if not hasattr(b, "inpaint"):
        raise SystemExit(f"backend {a.backend} has no inpaint()")
    if not Path(a.image).is_file():
        raise SystemExit(f"image not found: {a.image}")
    if a.mask and not Path(a.mask).is_file():
        raise SystemExit(f"mask not found: {a.mask}")
    for s_ in a.strength:
        if not 0.0 < s_ <= 1.0:
            raise SystemExit(f"--strength must be in (0, 1], got {s_}")
    opts = {k: v for k, v in b.info.defaults.items() if v is not None}
    opts.update(parse_opts(a.opt))
    b.load(**{k: v for k, v in opts.items() if k in b.load_keys})
    img = Image.open(a.image).convert("RGB")
    mask = Image.open(a.mask).convert("L") if a.mask else None
    if mask is not None and mask.size != img.size:
        raise SystemExit(f"mask {mask.size} does not match image {img.size}")
    prompt = a.prompt if a.raw_prompt else b.apply_inpaint_template(a.prompt, **opts)
    gen = {k: opts[k] for k in b.inpaint_keys if k in opts}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    name = a.name or f"{Path(a.image).stem}_refined"
    src_hash = file_sha256(a.image)
    files = []
    t_all = time.perf_counter()
    for st in a.strength:
        t0 = time.perf_counter()
        m = mask if mask is not None else Image.new("L", img.size, 255)
        imgs = b.inpaint(prompt, img, m, seed=a.seed, n=a.n, strength=st, **gen)
        total = time.perf_counter() - t0
        stats = b.stats()
        for i, im in enumerate(imgs):
            p = out / f"{name}_st{round(st * 100):02d}_s{a.seed + i}.png"
            save_atomic(im, p)
            write_sidecar_atomic(p, {
                "kind": "refine", "backend": b.info.to_dict(), "subject": a.prompt, "prompt": prompt,
                "negative": a.negative, "seed": a.seed + i, "strength": st,
                "source": {"path": str(Path(a.image).resolve()), "sha256": src_hash, "size": list(img.size)},
                "mask": ({"path": str(Path(a.mask).resolve()), "sha256": file_sha256(a.mask)} if a.mask else None),
                "size": list(im.size), "opts": gen,
                "timings": {"call_total_s": round(total, 2),
                            "image_s": (stats.get("last_image_s") or [None] * a.n)[i],
                            "load_s": stats.get("load_s")},
                "stats": stats, "created": datetime.now(timezone.utc).isoformat()})
            files.append(str(p))
    print(json.dumps({"ok": True, "files": files, "prompt": prompt, "strengths": a.strength,
                      "seeds": [a.seed + i for i in range(a.n)], "source_sha256": src_hash,
                      "masked": bool(a.mask), "gen_opts": gen, "stats": b.stats(),
                      "total_s": round(time.perf_counter() - t_all, 2)}))


# ----------------------------------------------------------------- edit
def round32(v: int) -> int:
    """Nearest multiple of 32 (min 32): the size the pipeline can generate."""
    return max(32, int(round(v / 32)) * 32)


def _dilate(mask, radius: int):
    from PIL import ImageFilter
    if radius <= 0:
        return mask
    return mask.filter(ImageFilter.MaxFilter(2 * radius + 1))


def edit_images(backend, src_path, prompt: str, *, extras=(), mark=None, mask_path=None, feather: float = 0.0,
                ref_res: int = 1024, seed: int = 0, n: int = 1, out_dir: Path, stem: str | None = None,
                opts: dict | None = None) -> dict:
    """Edit ``src_path`` by instruction (Picture 1 = source, then ``extras``). Returns the JSON result.

    ``mark`` = (x, y, r): a red circle is drawn on the source and the MARKED image is the reference.
    ``mask_path``: only the masked area is taken from the edit (feathered paste-back onto the unmarked
    source); the unpasted edit is saved next to it as ``<stem>_s<seed>_raw.png``.
    """
    from PIL import Image
    import maskkit
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = Image.open(src_path).convert("RGB")
    W, H = src.size
    stem = stem or f"{Path(src_path).stem}_edit"
    ref0 = src_path
    if mark:
        ref0 = out_dir / f"{stem}_marked.png"
        save_atomic(maskkit.draw_mark(src, *mark, width=5), ref0)
    mask = Image.open(mask_path).convert("L") if mask_path else None
    gw, gh = round32(W), round32(H)
    t0 = time.perf_counter()
    imgs = backend.generate(prompt, width=gw, height=gh, seed=seed, n=n,
                            ref=[str(ref0), *map(str, extras)], ref_res=ref_res, **(opts or {}))
    total = time.perf_counter() - t0
    stats = backend.stats()
    reach = int(math.ceil(3 * feather)) if feather > 0 else 0
    files, raws, drifts = [], [], []
    for i, img in enumerate(imgs):
        s = seed + i
        edited = img if img.size == (W, H) else img.resize((W, H), Image.LANCZOS)
        extra = {}
        if mask is not None:
            raw_p = out_dir / f"{stem}_s{s}_raw.png"
            save_atomic(edited, raw_p)
            raws.append(str(raw_p))
            result = maskkit.paste_back(src, edited, mask, feather)
            m = mask if mask.size == (W, H) else mask.resize((W, H), Image.LANCZOS)
            d = {"drift_outside_mask": round(maskkit.drift_outside(src, result, m), 4),
                 "drift_outside_reach": round(maskkit.drift_outside(src, result, _dilate(m, reach)), 4),
                 "raw_edit_drift_outside_mask": round(maskkit.drift_outside(src, edited, m), 4)}
            drifts.append(d)
            extra = {"mask": str(mask_path), "mask_sha256": file_sha256(mask_path), "feather": feather,
                     "raw_file": str(raw_p), **d}
        else:
            result = edited
        p = out_dir / f"{stem}_s{s}.png"
        save_atomic(result, p)
        write_sidecar_atomic(p, {
            "kind": "edit", "backend": backend.info.to_dict(), "prompt": prompt, "seed": s,
            "source": str(src_path), "source_sha256": file_sha256(src_path),
            "extra_refs": [{"path": str(e), "sha256": file_sha256(e)} for e in extras],
            "mark": list(mark) if mark else None, "marked_file": str(ref0) if mark else None,
            "ref_res": ref_res, "generated_size": [gw, gh], "output_size": [W, H], "opts": opts or {},
            "timings": {"call_total_s": round(total, 2), "image_s": (stats.get("last_image_s") or [None] * n)[i],
                        "encode_s": stats.get("last_encode_s")},
            "stats": stats, "profile": pp.PROFILE["_path"],
            "created": datetime.now(timezone.utc).isoformat(), **extra})
        files.append(str(p))
    st = dict(stats)
    if drifts:
        st["drift"] = drifts[0] if len(drifts) == 1 else drifts
    out = {"ok": True, "files": files, "seeds": [seed + i for i in range(len(files))], "stats": st}
    if raws:
        out["raw_files"] = raws
    return out


def cmd_edit(a) -> None:
    b = get_backend(a.backend)
    opts = {k: v for k, v in b.info.defaults.items() if v is not None}
    opts.update(parse_opts(a.opt))
    require_cap(a.backend, "edit", "edit")
    b = open_backend(a.backend, opts, "edit")
    gen = {k: v for k, v in opts.items() if k not in b.load_keys and k not in ("ref", "ref_res")}
    mark = None
    if a.mark:
        try:
            x, y, r = (float(v) for v in a.mark.split(","))
        except ValueError:
            raise SystemExit("--mark must be x,y,r (pixels in the source image)")
        mark = (x, y, r)
    out = edit_images(b, a.image, a.prompt, extras=a.ref or [], mark=mark, mask_path=a.mask, feather=a.feather,
                      ref_res=a.ref_res, seed=a.seed, n=a.n, out_dir=Path(a.out), stem=a.name, opts=gen)
    print(json.dumps(out))


# ----------------------------------------------------------------- sheet
def _pose_cycles() -> dict:
    """name -> function(frames, cell) returning that many keypoint sets. Add new cycles here."""
    import pose as posemod
    return {"walk_side": posemod.walk_side_frames}


NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
                9: "nine", 10: "ten"}
# Per-frame pose words of the 5-frame walk that worked in the eval (walk_side phases 0, .8, 1.6, 2.4, 3.2).
WALK5 = [
    "contact pose, his right leg stepped forward with the heel down, the left leg stretched back, left arm swinging forward",
    "passing pose, legs close together under the body, the left foot lifted off the ground passing forward, arms close to the body",
    "contact pose mirrored, the left leg stepped forward with the heel down, the right leg stretched back, right arm swinging forward",
    "passing pose, legs together, the right foot lifted passing forward",
    "on the way to the next contact, the right leg reaching forward, the left leg behind",
]
WALK_PHASES = [WALK5[0], WALK5[1], WALK5[2], WALK5[3]]   # walk_side phase 0, 1, 2, 3 (cycle of 4)


def walk_words(frames: int) -> list[str]:
    if frames == 5:
        return list(WALK5)
    return [WALK_PHASES[int(round(4 * i / frames)) % 4] for i in range(frames)]


def sheet_prompt(n_refs: int, frames: int, poses: str = "walk_side", subject: str | None = None) -> str:
    """Default sheet prompt (the wording that worked in the eval). Picture numbers follow ``n_refs``
    character references; the skeleton strip is Picture ``n_refs + 1``."""
    if poses != "walk_side":
        raise ValueError(f"no prompt template for poses {poses!r}")
    nf = NUMBER_WORDS.get(frames, str(frames))
    who = subject or "the same character from the references"
    strip_n = n_refs + 1
    if n_refs == 1:
        intro = f"Picture 1 shows {who}."
        pics = "Picture 1"
    elif n_refs == 2:
        intro = f"Picture 1 shows {who} from the front and Picture 2 shows the same character from the side."
        pics = "Pictures 1 and 2"
    else:
        intro = f"Pictures 1 to {n_refs} show {who} from different views."
        pics = f"Pictures 1 to {n_refs}"
    frame_lines = " ".join(f"Frame {i + 1}: {w}." for i, w in enumerate(walk_words(frames)))
    return (f"{intro} Picture {strip_n} is a row of {nf} stick-figure pose skeletons (OpenPose style: coloured "
            f"limbs on black), the {nf} frames of a walk cycle from left to right. Draw a sprite sheet of a walk "
            f"cycle: one horizontal row of {nf} frames of the same character from {pics}, full body, strict side "
            f"view, facing right. Each frame takes the pose of the skeleton at the same position in Picture "
            f"{strip_n} (the first frame follows the first skeleton, and so on), with the same leg positions, knee "
            f"bends and arm swing, but no skeleton lines visible. {frame_lines} Same face, same hair and same "
            f"clothes in every frame, {pp.PROFILE['sheet_style']} as {pics}. "
            f"All {nf} frames have the same size, the same head height and the feet on the same ground line, "
            f"evenly spaced with empty space between them. Plain flat white background, no floor shadow, no grid "
            f"lines, no numbers, no text.")


def sheet_images(backend, refs, *, poses: str = "walk_side", frames: int = 5, cell=(384, 768),
                 prompt: str | None = None, subject: str | None = None, ref_res: int = 768, seed: int = 0,
                 slice_: bool = False, post_cell=None, grid=None, feet_row: int | None = None,
                 out_dir: Path, stem: str = "sheet", opts: dict | None = None) -> dict:
    """One generation of a whole animation sheet from character refs + a skeleton strip (last ref)."""
    from PIL import Image
    import pose as posemod
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cycles = _pose_cycles()
    if poses not in cycles:
        raise SystemExit(f"unknown --poses {poses!r}; known: {', '.join(cycles)}")
    post_cell = post_cell or pp.PROFILE["sheet_post_cell"]
    feet_row = pp.PROFILE["sheet_feet_row"] if feet_row is None else feet_row
    cw, ch = cell
    W, H = cw * frames, ch
    if W % 32 or H % 32:
        raise SystemExit(f"sheet size {W}x{H} (frames x cell) must be multiples of 32")
    strip_p = out_dir / f"{stem}_poses.png"
    save_atomic(posemod.strip(cycles[poses](frames, cell), cell), strip_p)
    prompt_mode = "given"
    if not prompt:
        prompt, prompt_mode = sheet_prompt(len(refs), frames, poses, subject), "generated"
    t0 = time.perf_counter()
    [sheet] = backend.generate(prompt, width=W, height=H, seed=seed, n=1,
                               ref=[*map(str, refs), str(strip_p)], ref_res=ref_res, **(opts or {}))
    total = time.perf_counter() - t0
    stats = backend.stats()
    sheet_p = out_dir / f"{stem}.png"
    save_atomic(sheet, sheet_p)
    files = [str(sheet_p)]
    extra: dict = {}
    if slice_:
        extra = _slice_and_post(sheet, frames, cw, post_cell, grid, feet_row, out_dir, stem)
        files += extra.pop("files")
    write_sidecar_atomic(sheet_p, {
        "kind": "sheet", "backend": backend.info.to_dict(), "prompt": prompt, "prompt_mode": prompt_mode,
        "seed": seed, "refs": [{"path": str(r), "sha256": file_sha256(r)} for r in refs],
        "strip": str(strip_p), "strip_sha256": file_sha256(strip_p), "poses": poses, "frames": frames,
        "cell": list(cell), "size": [W, H], "ref_res": ref_res, "opts": opts or {},
        "timings": {"call_total_s": round(total, 2), "image_s": (stats.get("last_image_s") or [None])[0],
                    "encode_s": stats.get("last_encode_s")},
        "stats": stats, "profile": pp.PROFILE["_path"],
        "created": datetime.now(timezone.utc).isoformat(), **extra})
    st = dict(stats)
    if "grid" in extra:
        st["grid"] = extra["grid"]
    return {"ok": True, "files": files, "seeds": [seed], "stats": st}


def _slice_and_post(sheet, frames, cw, post_cell, grid, feet_row, out_dir: Path, stem: str) -> dict:
    """Cut the sheet into cells, post-process each with ONE fixed pixel grid (detected on frame 0 unless given)."""
    from PIL import Image
    files, pxs, n_used = [], [], grid
    kw = dict(bg="auto", colours=24, outline="inner", cell=tuple(post_cell), feet_row=feet_row, shadow=True,
              keep_largest=True)
    for i in range(frames):
        cell_img = sheet.crop((i * cw, 0, (i + 1) * cw, sheet.height))
        fp = out_dir / f"{stem}_f{i}.png"
        save_atomic(cell_img, fp)
        if n_used is None:      # one pixel size per character: fit on frame 0 only, reuse for all frames
            _, rep0 = pp.run_pipeline(cell_img, grid="fit", **kw)
            n_used = rep0["grid"]["scale"]
        px, _ = pp.run_pipeline(cell_img, grid=n_used, **kw)
        pp_path = out_dir / f"{stem}_f{i}_px.png"
        save_atomic(px, pp_path)
        files += [str(fp), str(pp_path)]
        pxs.append(px.convert("RGBA"))
    pw, ph = pxs[0].size
    row = Image.new("RGBA", (pw * frames, ph), (0, 0, 0, 0))
    for i, px in enumerate(pxs):
        row.paste(px, (i * pw, 0))
    row_p = out_dir / f"{stem}_px_row.png"
    save_atomic(row, row_p)
    gif_frames = []
    for px in pxs:
        bg = Image.new("RGBA", (pw, ph), (200, 200, 210, 255))
        bg.alpha_composite(px)
        gif_frames.append(bg.resize((pw * 3, ph * 3), Image.NEAREST).convert("P", palette=Image.ADAPTIVE))
    gif_p = out_dir / f"{stem}.gif"
    tmp = gif_p.with_name(gif_p.name + ".tmp.gif")
    gif_frames[0].save(tmp, save_all=True, append_images=gif_frames[1:], duration=140, loop=0)
    tmp.replace(gif_p)
    files += [str(row_p), str(gif_p)]
    return {"files": files, "grid": n_used, "post_cell": list(post_cell), "feet_row": feet_row}


def cmd_sheet(a) -> None:
    b = get_backend(a.backend)
    opts = {k: v for k, v in b.info.defaults.items() if v is not None}
    opts.update(parse_opts(a.opt))
    require_cap(a.backend, "sheet", "sheet")
    b = open_backend(a.backend, opts, "sheet")
    gen = {k: v for k, v in opts.items() if k not in b.load_keys and k not in ("ref", "ref_res")}
    prompt = Path(a.prompt_file).read_text().strip() if a.prompt_file else a.prompt
    out = sheet_images(b, a.ref, poses=a.poses, frames=a.frames, cell=parse_cell(a.cell), prompt=prompt,
                       subject=a.subject, ref_res=a.ref_res, seed=a.seed, slice_=a.slice,
                       post_cell=parse_cell(a.post_cell), grid=a.grid, feet_row=a.feet_row,
                       out_dir=Path(a.out), stem=a.name, opts=gen)
    print(json.dumps(out))


# ----------------------------------------------------------------- mask
def cmd_mask(a) -> None:
    """Build a repaint mask (white = repaint) from boxes. One JSON object on stdout."""
    from PIL import Image
    import maskkit
    if a.image:
        src = Image.open(a.image)
        size = src.size
    elif a.size:
        size = tuple(int(v) for v in a.size.lower().split("x"))
    else:
        raise SystemExit("give --size WxH or --image")
    try:
        m = maskkit.build_mask(size, rects=a.rect or [], ellipses=a.ellipse or [], keep_rects=a.keep_rect or [],
                               keep_ellipses=a.keep_ellipse or [], heads=a.heads or [], head_pad=a.head_pad,
                               head_shape=a.head_shape, units=a.units, base=a.base, feather=a.feather)
    except ValueError as e:
        raise SystemExit(str(e))
    if a.invert:
        from PIL import ImageOps
        m = ImageOps.invert(m)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_atomic(m, out)
    res = {"ok": True, "file": str(out), **maskkit.mask_stats(m)}
    if a.preview:
        if not a.image:
            raise SystemExit("--preview needs --image")
        pv = Path(a.preview)
        pv.parent.mkdir(parents=True, exist_ok=True)
        save_atomic(maskkit.overlay(src, m), pv)
        res["preview"] = str(pv)
    print(json.dumps(res))


# ----------------------------------------------------------------- pose
def cmd_pose(a) -> None:
    """Draw an OpenPose-style skeleton PNG (the `sheet` command builds its pose strip from the same drawing code)."""
    import pose as posemod
    if a.keypoints:
        kps = json.loads(Path(a.keypoints).read_text())
    elif a.preset in posemod.MULTI:
        kps = posemod.MULTI[a.preset]
    else:
        if a.preset not in posemod.PRESETS:
            raise SystemExit(f"unknown preset {a.preset!r}; known: {', '.join([*posemod.PRESETS, *posemod.MULTI])}")
        kps = posemod.PRESETS[a.preset]
    size = tuple(int(v) for v in a.size.lower().split("x"))
    multi = kps[0] is not None and len(kps[0]) == 18   # list of skeletons, not a single 18-point list
    img = posemod.draw_poses(kps, size) if multi else posemod.draw_pose(kps, size)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp.png")
    img.save(tmp)
    tmp.replace(out)
    print(json.dumps({"ok": True, "file": str(out), "size": list(size)}))


# ----------------------------------------------------------------- cache
def cmd_cache(a) -> None:
    """Encoding cache (qwen_image21): size report and pruning. One JSON object on stdout."""
    from backends import _enc_cache
    out = {"ok": True}
    if a.prune:
        if a.older_than is None and a.max_gb is None:
            raise SystemExit("--prune needs --older-than DAYS and/or --max-gb G")
        out["removed"] = _enc_cache.prune(older_than_days=a.older_than,
                                          max_bytes=None if a.max_gb is None else int(a.max_gb * 2**30))
    st = _enc_cache.stats()
    out.update(count=st["count"], bytes=st["bytes"], gb=round(st["bytes"] / 2**30, 3), dir=st["dir"])
    print(json.dumps(out))


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
    g.add_argument("--width", type=int, help="default: the backend's default_size (512; qwen_image21 1024)")
    g.add_argument("--height", type=int, help="default: the backend's default_size (512; qwen_image21 1024)")
    g.add_argument("--ref", nargs="*", help="reference image(s), if the backend supports them (qwen_image21: Picture 1, 2, ...; the prompt is then sent verbatim, no template; --opt ref_res=512)")
    g.add_argument("--opt", action="append", help="backend option k=v (repeatable)")
    g.add_argument("--name", help="output file stem")
    g.add_argument("--json", action="store_true",
                   help='print one JSON object {"ok","files","seeds","stats"} as the last stdout line instead of paths')
    g.add_argument("--out", required=True)

    ed = sub.add_parser("edit", help="edit an image by instruction (source = Picture 1, then extra refs); "
                                     "optional --mark circle and --mask paste-back; prints one JSON object")
    ed.add_argument("--backend", default="qwen_image21", choices=list(REGISTRY))
    ed.add_argument("--image", required=True, help="source PNG; the output has the same size")
    ed.add_argument("--prompt", required=True, help="sent verbatim (refer to 'Picture 1', 'Picture 2', ...)")
    ed.add_argument("--ref", nargs="*", help="extra reference images (Picture 2, 3, ...)")
    ed.add_argument("--mark", help="x,y,r: draw a red circle on the source (the marked image is what the model sees)")
    ed.add_argument("--mask", help="mask PNG (white = take the edit): paste the edit back onto the unmarked source")
    ed.add_argument("--feather", type=float, default=0.0, help="Gaussian radius in px for the paste-back mask")
    ed.add_argument("--ref-res", type=int, default=1024,
                    help="side the source and refs are resized to (one value for all; 512 loses source detail)")
    ed.add_argument("--seed", type=int, default=0)
    ed.add_argument("--n", type=int, default=1)
    ed.add_argument("--opt", action="append", help="backend option k=v (repeatable)")
    ed.add_argument("--name", help="output file stem (default <image stem>_edit)")
    ed.add_argument("--out", required=True)

    sh = sub.add_parser("sheet", help="one-shot animation sheet from character refs + a pose-skeleton strip; "
                                      "--slice cuts and post-processes the frames; prints one JSON object")
    sh.add_argument("--backend", default="qwen_image21", choices=list(REGISTRY))
    sh.add_argument("--ref", nargs="+", required=True, help="character reference(s) (Picture 1, 2, ...); the strip is added last")
    sh.add_argument("--poses", default="walk_side", help="pose cycle (walk_side)")
    sh.add_argument("--frames", type=int, default=5)
    sh.add_argument("--cell", default="384x768", help="WxH of one frame; sheet = (frames*W)xH, multiples of 32")
    sh.add_argument("--prompt", help="full prompt, sent verbatim (default: generated from refs/frames/--subject)")
    sh.add_argument("--prompt-file", help="read the full prompt from a file")
    sh.add_argument("--subject", help="identity text for the generated prompt, e.g. 'a young adult man in an olive hoodie'")
    sh.add_argument("--seed", type=int, default=0)
    sh.add_argument("--ref-res", type=int, default=768, help="side all refs are resized to (encode is slow: ~8 min at 768)")
    sh.add_argument("--slice", action="store_true", help="cut into frames and post-process with one fixed grid")
    sh.add_argument("--post-cell", help="WxH of the post-processed cell (default: the active profile, 96x192)")
    sh.add_argument("--grid", type=float, help="fixed pixel size for all frames (default: fit on frame 0, reuse)")
    sh.add_argument("--feet-row", type=int, help="feet row in the post cell (default: the active profile, 157)")
    sh.add_argument("--opt", action="append", help="backend option k=v (repeatable)")
    sh.add_argument("--name", default="sheet", help="output file stem")
    sh.add_argument("--out", required=True)

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

    rf = sub.add_parser("refine", help="img2img an existing image with a chosen backend (optional mask)")
    rf.add_argument("--backend", default="flux2_klein_pixel_lora", choices=list(REGISTRY))
    rf.add_argument("--image", required=True, help="source PNG (multiple of 16 px)")
    rf.add_argument("--mask", help="mask PNG, white = repaint, black = keep (same size as the image)")
    rf.add_argument("--prompt", required=True, help="subject; wrapped in the backend's inpaint template unless --raw-prompt")
    rf.add_argument("--raw-prompt", action="store_true", help="send --prompt verbatim")
    rf.add_argument("--negative")
    rf.add_argument("--strength", type=float, nargs="+", default=[0.5],
                    help="one or more values in (0, 1]; 0.3 keeps most of the source, 0.75 repaints most of it")
    rf.add_argument("--seed", type=int, default=0)
    rf.add_argument("--n", type=int, default=1)
    rf.add_argument("--opt", action="append", help="backend option k=v (steps, lora_scale, feather, ...)")
    rf.add_argument("--name", help="output file stem (default <image stem>_refined)")
    rf.add_argument("--out", required=True)

    mk = sub.add_parser("mask", help="build a repaint mask from boxes (white = repaint); no segmentation model")
    mk.add_argument("--size", help="WxH (or use --image)")
    mk.add_argument("--image", help="take the size from this image; needed for --preview")
    mk.add_argument("--rect", action="append", help="x0,y0,x1,y1 painted white (repeatable)")
    mk.add_argument("--ellipse", action="append", help="x0,y0,x1,y1 ellipse painted white (repeatable)")
    mk.add_argument("--keep-rect", action="append", help="x0,y0,x1,y1 painted black (repeatable)")
    mk.add_argument("--keep-ellipse", action="append", help="x0,y0,x1,y1 ellipse painted black (repeatable)")
    mk.add_argument("--heads", action="append",
                    help="head box incl. hair, x0,y0,x1,y1 (repeatable): everything EXCEPT the heads is repainted")
    mk.add_argument("--head-pad", type=float, default=0.15, help="grow each head box by this share of its size")
    mk.add_argument("--head-shape", default="ellipse", choices=["ellipse", "rect"])
    mk.add_argument("--units", default="px", choices=["px", "frac"], help="box units: pixels or 0..1 fractions")
    mk.add_argument("--base", choices=["white", "black"], help="start colour (default: black if --rect/--ellipse, else white)")
    mk.add_argument("--feather", type=float, default=0.0, help="Gaussian blur radius in px")
    mk.add_argument("--invert", action="store_true")
    mk.add_argument("--preview", help="write the image with the repaint area tinted red (needs --image)")
    mk.add_argument("--out", required=True)

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

    po = sub.add_parser("pose", help="draw an OpenPose-style skeleton PNG (preview of what `sheet` feeds the model)")
    po.add_argument("--preset", default="stand_front")
    po.add_argument("--keypoints", help="JSON file: 18 [x, y] pairs in 0..1 (or null)")
    po.add_argument("--size", default="832x1216")
    po.add_argument("--out", required=True)

    ca = sub.add_parser("cache", help="encoding cache of qwen_image21: --stats (default) or --prune")
    ca.add_argument("--stats", action="store_true", help="report count and size (default)")
    ca.add_argument("--prune", action="store_true", help="delete old / excess entries")
    ca.add_argument("--older-than", type=float, metavar="DAYS", help="with --prune: delete entries unused for DAYS")
    ca.add_argument("--max-gb", type=float, metavar="G", help="with --prune: then delete oldest until <= G GB")

    pf = sub.add_parser("palette-from", help="extract a .hex palette from an image")
    pf.add_argument("image")
    pf.add_argument("--out", required=True)

    a = ap.parse_args(argv)
    if a.cmd == "backends":
        for name in REGISTRY:
            try:
                info = get_backend(name).info
                print(f"{name}: {info.description} | models={info.models} | licence={info.licence} | caps={','.join(sorted(info.caps)) or '-'}")
            except Exception as e:  # noqa: BLE001
                print(f"{name}: (failed to import: {e})")
    elif a.cmd == "generate":
        cmd_generate(a)
    elif a.cmd == "sheet":
        cmd_sheet(a)
    elif a.cmd == "edit":
        cmd_edit(a)
    elif a.cmd == "inpaint":
        cmd_inpaint(a)
    elif a.cmd == "refine":
        cmd_refine(a)
    elif a.cmd == "mask":
        cmd_mask(a)
    elif a.cmd == "pose":
        cmd_pose(a)
    elif a.cmd == "snap":
        cmd_snap(a)
    elif a.cmd == "post":
        cmd_post(a)
    elif a.cmd == "cache":
        cmd_cache(a)
    elif a.cmd == "palette-from":
        cmd_palette_from(a)


if __name__ == "__main__":
    main()
