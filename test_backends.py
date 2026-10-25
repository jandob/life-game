"""Tests for the backend registry, models.json, pose.py, maskkit and the refine command.

    .venv/bin/python test_backends.py            # fast, no model weights
    ARTGEN_TEST_MODELS=1 .venv/bin/python test_backends.py   # also loads WAI v17 and Z-Image (about 3 min)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PIL import Image  # noqa: E402
from backends import REGISTRY, get_backend  # noqa: E402
from backends._common import load_registry  # noqa: E402
import pose  # noqa: E402

PY = sys.executable
CLI = str(HERE / "artgen.py")


def test_registry_and_models_json() -> None:
    reg = load_registry()
    assert set(k for k in reg if not k.startswith("_")) == {"z_image_turbo", "qwen_image21", "runpod_qwen_image21"}
    assert set(REGISTRY) == {"flux2_klein_pixel_lora", "qwen_image21", "runpod_qwen_image21", "z_image_turbo", "example_stub"}


def test_pose() -> None:
    from PIL import Image
    for name, kps in pose.PRESETS.items():
        img = pose.draw_pose(kps, (256, 384))
        assert img.size == (256, 384) and img.getbbox() is not None, name
    assert pose.draw_poses(pose.MULTI["sit_pair"], (256, 192)).size == (256, 192)
    assert len({tuple(map(tuple, [k for k in pose.PRESETS[f"walk_side_{i}"] if k])) for i in range(4)}) == 4
    try:
        pose.draw_pose([(0, 0)] * 5)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "p.png"
        r = subprocess.run([PY, CLI, "pose", "--preset", "stand_front", "--size", "128x192", "--out", str(out)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["ok"] and Image.open(out).size == (128, 192)
        assert not list(Path(td).glob("*.tmp*"))
        r = subprocess.run([PY, CLI, "pose", "--preset", "sit_pair", "--size", "128x96", "--out", str(out)],
                           capture_output=True, text=True)
        assert r.returncode == 0 and Image.open(out).size == (128, 96), r.stderr
        r = subprocess.run([PY, CLI, "pose", "--preset", "nope", "--out", str(out)], capture_output=True, text=True)
        assert r.returncode != 0


def test_cli_lists_backends() -> None:
    r = subprocess.run([PY, CLI, "backends"], capture_output=True, text=True)
    assert r.returncode == 0 and "qwen_image21:" in r.stdout and "z_image_turbo:" in r.stdout and "sdxl" not in r.stdout, r.stdout + r.stderr


def test_maskkit_and_mask_cli() -> None:
    from PIL import Image
    import maskkit
    m = maskkit.build_mask((100, 80), heads=["10,5,30,25"], head_pad=0.0, head_shape="rect")
    assert m.getpixel((20, 15)) == 0 and m.getpixel((60, 60)) == 255
    m = maskkit.build_mask((100, 80), rects=["0,0,50,40"], keep_ellipses=["10,10,20,20"])
    assert m.getpixel((5, 5)) == 255 and m.getpixel((15, 15)) == 0 and m.getpixel((90, 70)) == 0
    m = maskkit.build_mask((100, 80), ellipses=["0.5,0,1,1"], units="frac")
    assert m.getpixel((75, 40)) == 255 and m.getpixel((10, 40)) == 0
    for bad in ("1,2,3", "a,b,c,d", "200,200,300,300"):
        try:
            maskkit.parse_box(bad, (100, 80))
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    with tempfile.TemporaryDirectory() as td:
        img, out, pv = Path(td) / "i.png", Path(td) / "m.png", Path(td) / "pv.png"
        Image.new("RGB", (64, 48), "blue").save(img)
        r = subprocess.run([PY, CLI, "mask", "--image", str(img), "--heads", "10,5,30,25", "--preview", str(pv),
                            "--out", str(out)], capture_output=True, text=True)
        res = json.loads(r.stdout)
        assert r.returncode == 0 and res["ok"] and Image.open(out).size == (64, 48) and pv.exists()
        assert 0.8 < res["white_frac"] < 1.0 and not list(Path(td).glob("*.tmp*"))
        r = subprocess.run([PY, CLI, "mask", "--out", str(out)], capture_output=True, text=True)
        assert r.returncode != 0


def test_refine_cli_stubbed() -> None:
    """cmd_refine with a fake backend: files, sidecar hash, strength validation, mask size check."""
    import argparse
    import hashlib
    from PIL import Image
    import artgen

    calls = []

    class Fake:
        info = type("I", (), {"defaults": {"model": "x"}, "to_dict": lambda self: {"name": "fake"},
                              "caps": frozenset({"refine", "inpaint"})})()
        load_keys = frozenset({"model"})
        inpaint_keys = ("model", "loras")

        def load(self, **kw): pass
        def apply_inpaint_template(self, s, **_): return "Q, " + s
        def stats(self): return {"last_image_s": [0.1] * 2}

        def inpaint(self, prompt, image, mask, seed=0, n=1, strength=0.5, **kw):
            calls.append((prompt, mask is not None, strength, seed, kw))
            return [image.copy() for _ in range(n)]

    orig = artgen.get_backend
    artgen.get_backend = lambda name: Fake()
    try:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            Image.new("RGB", (64, 48), "red").save(td / "a.png")
            Image.new("L", (64, 48), 255).save(td / "m.png")
            ns = dict(backend="flux2_klein_pixel_lora", image=str(td / "a.png"), mask=str(td / "m.png"), prompt="p", raw_prompt=False,
                      negative=None, strength=[0.3, 0.6], seed=5, n=2, opt=["model=wai_v17"],
                      name=None, out=str(td / "o"))
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                artgen.cmd_refine(argparse.Namespace(**ns))
            res = json.loads(buf.getvalue())
            assert len(res["files"]) == 4 and res["masked"] and len(calls) == 2
            assert calls[0][0] == "Q, p" and calls[1][2] == 0.6 and calls[0][4]["model"] == "wai_v17"
            sc = json.loads(Path(res["files"][0]).with_suffix(".json").read_text())
            assert sc["kind"] == "refine" and sc["source"]["sha256"] == hashlib.sha256((td / "a.png").read_bytes()).hexdigest()
            assert sc["mask"]["sha256"] and Path(res["files"][0]).name == "a_refined_st30_s5.png"
            assert not list((td / "o").glob("*.tmp*"))
            for bad in ({"strength": [0.0]}, {"strength": [1.5]}, {"image": str(td / "none.png")}):
                try:
                    artgen.cmd_refine(argparse.Namespace(**{**ns, **bad}))
                except SystemExit:
                    pass
                else:
                    raise AssertionError(bad)
            # no mask: the backend's inpaint() gets a full white mask
            seen = []
            Fake.inpaint = lambda self, prompt, image, mask, **kw: (seen.append(set(mask.getdata())),
                                                                   [image.copy()])[1]
            with contextlib.redirect_stdout(io.StringIO()):
                artgen.cmd_refine(argparse.Namespace(**{**ns, "mask": None, "n": 1, "strength": [0.5]}))
            assert seen == [{255}]
            Image.new("L", (32, 32), 255).save(td / "m2.png")
            try:
                artgen.cmd_refine(argparse.Namespace(**{**ns, "mask": str(td / "m2.png")}))
            except SystemExit:
                pass
            else:
                raise AssertionError("mask size")
    finally:
        artgen.get_backend = orig


def test_models_smoke() -> None:
    """Needs the weights (Comfy files in ~/ComfyUI-Shared)."""
    import numpy as np
    z = get_backend("z_image_turbo")
    z.load()
    zi = z.generate("a red apple on a wooden table", width=512, height=512, seed=1, n=1, steps=4)[0]
    assert zi.size == (512, 512) and np.asarray(zi).std() > 10


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    if not os.environ.get("ARTGEN_TEST_MODELS"):
        tests = [t for t in tests if t.__name__ != "test_models_smoke"]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
