"""Multi-region cast recipes (backend-agnostic): each region is a full-resolution masked refine.

``refine_masked`` wraps ``backend.refine`` / ``backend.inpaint``; ``run_cast`` applies a recipe of regions
to one image in order. Used by ``artgen.py cast``.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

import maskkit

DEFAULT_FEATHER = 6.0
MASK_KEYS = ("mask", "rect", "ellipse", "heads", "keep_rect", "keep_ellipse")
REGION_KEYS = {"name", "prompt", "raw_prompt", "negative", "opts", "strength", "seed", "n", "feather", "head_pad", "head_shape", "units", "base", *MASK_KEYS}
TOP_KEYS = {"image", "backend", "opts", "regions", "negative"}


def mask_bbox(mask: Image.Image, thresh: int = 0):
    """Bounding box of mask pixels > ``thresh``, or None when the mask is empty."""
    return mask.convert("L").point(lambda v: 255 if v > thresh else 0).getbbox()


# ----------------------------------------------------------- refine call
def refine_masked(b, prompt, image, mask, *, seed=0, n=1, strength=0.5, negative=None, gen=None):
    """Refine ``image`` (full resolution, whole image as context) under ``mask`` (white = repaint, None = all).
    Uses ``b.refine`` or, for inpaint-only backends, ``b.inpaint``. Pixels outside the (feathered) mask stay
    unchanged. Returns a list of n images."""
    gen = dict(gen or {})
    if hasattr(b, "refine"):
        return b.refine(prompt, image, mask, seed=seed, n=n, strength=strength, negative=negative, **gen)
    m = mask if mask is not None else Image.new("L", image.size, 255)
    return b.inpaint(prompt, image, m, seed=seed, n=n, strength=strength, **gen)


# --------------------------------------------------------- recipe checks
class RecipeError(Exception):
    pass


def _as_list(v):
    return [] if v is None else (v if isinstance(v, list) else [v])


def region_mask(region: dict, size, base_dir: Path) -> Image.Image:
    """Build the (unfeathered) repaint mask of a region from a file or boxes."""
    if region.get("mask"):
        m = Image.open(base_dir / region["mask"]).convert("L")
        if m.size != tuple(size):
            raise RecipeError(f"region {region['name']!r}: mask {m.size} does not match image {tuple(size)}")
        return m
    return maskkit.build_mask(
        tuple(size), rects=_as_list(region.get("rect")), ellipses=_as_list(region.get("ellipse")),
        keep_rects=_as_list(region.get("keep_rect")), keep_ellipses=_as_list(region.get("keep_ellipse")),
        heads=_as_list(region.get("heads")), head_pad=float(region.get("head_pad", 0.15)),
        head_shape=region.get("head_shape", "ellipse"), units=region.get("units", "px"),
        base=region.get("base"), feather=0.0)


def validate_recipe(recipe, base_dir: Path, backends=None) -> dict:
    """Check a parsed recipe without loading any model. Returns {"size": (w, h), "masks": [Image, ...]}.
    Raises RecipeError with a message naming the offending field."""
    def need(cond, msg):
        if not cond:
            raise RecipeError(msg)

    need(isinstance(recipe, dict), "recipe must be a JSON object")
    unknown = set(recipe) - TOP_KEYS
    need(not unknown, f"unknown top-level keys: {sorted(unknown)}")
    need(isinstance(recipe.get("image"), str), "'image' (path) is required")
    img_path = base_dir / recipe["image"]
    need(img_path.is_file(), f"image not found: {img_path}")
    if "backend" in recipe:
        need(backends is None or recipe["backend"] in backends, f"unknown backend {recipe['backend']!r}")
    need(isinstance(recipe.get("opts", {}), dict), "'opts' must be an object")
    regions = recipe.get("regions")
    need(isinstance(regions, list) and regions, "'regions' must be a non-empty list")
    size = Image.open(img_path).size
    names, masks = set(), []
    for i, r in enumerate(regions):
        need(isinstance(r, dict), f"regions[{i}] must be an object")
        name = r.get("name")
        need(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]+", name or ""),
             f"regions[{i}]: 'name' required, letters/digits/_/- only")
        need(name not in names, f"duplicate region name {name!r}")
        names.add(name)
        where = f"region {name!r}"
        unknown = set(r) - REGION_KEYS
        need(not unknown, f"{where}: unknown keys {sorted(unknown)}")
        need(isinstance(r.get("prompt"), str) and r["prompt"].strip(), f"{where}: 'prompt' is required")
        has_file = bool(r.get("mask"))
        has_boxes = any(r.get(k) for k in MASK_KEYS if k != "mask")
        need(has_file != has_boxes, f"{where}: give either 'mask' (file) or boxes (rect/ellipse/heads), not both/none")
        s = r.get("strength", 0.5)
        need(isinstance(s, (int, float)) and not isinstance(s, bool) and 0 < s <= 1, f"{where}: strength must be in (0, 1]")
        need(isinstance(r.get("seed", 0), int), f"{where}: 'seed' must be an integer")
        need(isinstance(r.get("opts", {}), dict), f"{where}: 'opts' must be an object")
        need(r.get("units", "px") in ("px", "frac"), f"{where}: units must be px or frac")
        fe = r.get("feather", DEFAULT_FEATHER)
        need(isinstance(fe, (int, float)) and fe >= 0, f"{where}: feather must be >= 0")
        if has_file:
            need((base_dir / r["mask"]).is_file(), f"{where}: mask not found: {base_dir / r['mask']}")
        try:
            m = region_mask(r, size, base_dir)
        except ValueError as e:
            raise RecipeError(f"{where}: {e}") from None
        need(mask_bbox(m) is not None, f"{where}: mask is empty")
        masks.append(m)
    return {"size": size, "masks": masks, "image": img_path}


# ------------------------------------------------------------------ cast
def run_cast(recipe: dict, base_dir: Path, out_dir: Path, get_backend, parse_default_opts, save_atomic,
             backends=None) -> dict:
    """Validate, load the backend once, apply each region in order. Returns the log dict (also cast.json)."""
    v = validate_recipe(recipe, base_dir, backends)
    backend_name = recipe.get("backend", "sdxl")
    b = get_backend(backend_name)
    if not hasattr(b, "refine") and not hasattr(b, "inpaint"):
        raise RecipeError(f"backend {backend_name} has neither refine() nor inpaint()")
    gopts = {k: x for k, x in b.info.defaults.items() if x is not None}
    gopts.update(recipe.get("opts", {}))
    t_all = time.perf_counter()
    b.load(**{k: x for k, x in gopts.items() if k in b.load_keys})
    load_s = round(time.perf_counter() - t_all, 2)
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = getattr(b, "refine_keys", None) or b.inpaint_keys
    cur = Image.open(v["image"]).convert("RGB")
    log = {"kind": "cast", "backend": b.info.to_dict(), "image": str(v["image"]), "size": list(cur.size),
           "opts": gopts, "load_s": load_s, "regions": [], "created": datetime.now(timezone.utc).isoformat()}
    for i, (r, m) in enumerate(zip(recipe["regions"], v["masks"]), 1):
        name = r["name"]
        opts = {**gopts, **r.get("opts", {})}
        feather = float(r.get("feather", opts.get("feather", DEFAULT_FEATHER)))
        opts["feather"] = feather
        prompt = r["prompt"] if r.get("raw_prompt") else b.apply_inpaint_template(r["prompt"], **opts)
        gen = {k: opts[k] for k in keys if k in opts}
        t0 = time.perf_counter()
        res = refine_masked(b, prompt, cur, m, seed=r.get("seed", 0), n=1, strength=r.get("strength", 0.5),
                            negative=r.get("negative", recipe.get("negative")), gen=gen)
        dt = round(time.perf_counter() - t0, 2)
        prev, cur = cur, res[0]
        step = out_dir / f"{i:02d}_{name}.png"
        pv = out_dir / f"{i:02d}_{name}_mask.png"
        save_atomic(cur, step)
        save_atomic(maskkit.overlay(prev, m), pv)
        log["regions"].append({"index": i, "name": name, "prompt": prompt, "subject": r["prompt"],
                               "strength": r.get("strength", 0.5), "seed": r.get("seed", 0),
                               "gen_opts": gen, "file": str(step), "mask_preview": str(pv),
                               "mask_stats": maskkit.mask_stats(m), "seconds": dt})
    final = out_dir / "final.png"
    save_atomic(cur, final)
    log["final"] = str(final)
    log["total_s"] = round(time.perf_counter() - t_all, 2)
    log["stats"] = b.stats()
    tmp = out_dir / "cast.json.tmp"
    tmp.write_text(json.dumps(log, indent=2, default=str))
    tmp.replace(out_dir / "cast.json")
    log["log"] = str(out_dir / "cast.json")
    return log
