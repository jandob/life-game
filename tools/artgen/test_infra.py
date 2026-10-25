"""Tests for the model-free infrastructure of the artgen-qwen-image change: encoding cache,
paste_back / draw_mark, pose strips, `generate --json`.

    .venv/bin/python test_infra.py
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402

import artgen  # noqa: E402
import maskkit  # noqa: E402
import pose  # noqa: E402
from backends import REGISTRY, get_backend  # noqa: E402
from backends import _enc_cache as enc  # noqa: E402
from backends.base import Backend, BackendInfo  # noqa: E402


class SolidBackend(Backend):
    """Test backend: solid-colour images, colour derived from seed + i; records its calls."""
    info = BackendInfo(name="test_solid", description="test", models=[], licence="n/a")
    load_keys = frozenset({"offload"})
    calls: list = []

    def load(self, **kw) -> None:
        pass

    def generate(self, prompt, negative=None, width=512, height=512, seed=0, n=1, **opts):
        refs = [Image.open(p).convert("RGB").getpixel((0, 0)) for p in opts.get("ref", [])]
        SolidBackend.calls.append({"prompt": prompt, "negative": negative, "seed": seed, "opts": dict(opts),
                                   "ref_pixels": refs})
        return [Image.new("RGB", (width, height), ((seed + i) % 256, 10, 20)) for i in range(n)]

    def stats(self):
        return {"peak": 1}


def register_solid() -> None:
    """Make ``get_backend("test_solid")`` and the CLI's ``--backend test_solid`` work."""
    mod = types.ModuleType("backends._test_solid")
    mod.SolidBackend = SolidBackend
    sys.modules["backends._test_solid"] = mod
    REGISTRY["test_solid"] = "_test_solid:SolidBackend"


register_solid()


@contextlib.contextmanager
def cache_env():
    with tempfile.TemporaryDirectory() as td:
        old = os.environ.get("ARTGEN_ENC_CACHE")
        os.environ["ARTGEN_ENC_CACHE"] = td
        try:
            yield Path(td)
        finally:
            if old is None:
                os.environ.pop("ARTGEN_ENC_CACHE", None)
            else:
                os.environ["ARTGEN_ENC_CACHE"] = old


# ------------------------------------------------------------ 1.1 encoding cache
def test_enc_key_sensitivity() -> None:
    a = Image.new("RGB", (8, 8), (1, 2, 3))
    b = a.copy()
    b.putpixel((3, 3), (1, 2, 4))
    base = enc.key("p", [a], 512, "repo@rev")
    assert base == enc.key("p", [a.copy()], 512, "repo@rev")
    assert len(base) == 64
    assert enc.key("p2", [a], 512, "repo@rev") != base
    assert enc.key("p", [b], 512, "repo@rev") != base          # one pixel
    assert enc.key("p", [a], 1024, "repo@rev") != base
    assert enc.key("p", [a], 512, "repo@rev2") != base
    assert enc.key("p", [], 512, "repo@rev") != base
    assert enc.key("p", [a, b], 512, "r") != enc.key("p", [b, a], 512, "r")   # order matters
    assert enc.key("p", [a.convert("L")], 512, "r") != enc.key("p", [a.convert("RGB")], 512, "r")


def test_enc_roundtrip_none_member() -> None:
    with cache_env() as root:
        k = enc.key("p", [], 512, "e")
        assert enc.get(k) is None
        emb = torch.randn(1, 5, 4)
        pad = torch.tensor([[True, False, True]])
        enc.put(k, (emb, None, pad))
        assert (root / "qwen21" / f"{k}.pt").exists()
        got = enc.get(k)
        assert isinstance(got, tuple) and len(got) == 3 and got[1] is None
        assert torch.equal(got[0], emb) and torch.equal(got[2], pad) and got[2].dtype == torch.bool
        st = enc.stats()
        assert st["count"] == 1 and st["bytes"] > 0
        assert not list((root / "qwen21").glob("*.tmp"))


def test_enc_get_is_weights_only() -> None:
    with cache_env() as root:
        k = "ab" * 32
        (root / "qwen21").mkdir(parents=True)
        import pickle

        class Evil:
            def __reduce__(self):
                return (os.system, ("true",))
        torch.save([Evil()], root / "qwen21" / f"{k}.pt", pickle_protocol=2)
        assert enc.get(k) is None                                # refused, treated as a miss


def test_enc_prune() -> None:
    with cache_env() as root:
        for i in range(3):
            enc.put(f"k{i}", (torch.zeros(1000),))
        assert enc.stats()["count"] == 3
        old = time.time() - 10 * 86400
        os.utime(root / "qwen21" / "k0.pt", (old, old))
        assert enc.prune(older_than_days=5) == 1
        assert enc.stats()["count"] == 2
        one = (root / "qwen21" / "k1.pt").stat().st_size
        os.utime(root / "qwen21" / "k1.pt", (old, old))          # k1 oldest now
        assert enc.prune(max_bytes=one) == 1
        assert [p.name for p in (root / "qwen21").glob("*.pt")] == ["k2.pt"]
        assert enc.prune() == 0


# ------------------------------------------------------------ 1.2 maskkit
def _noise(size, seed):
    return Image.fromarray(np.random.default_rng(seed).integers(0, 256, (size[1], size[0], 3), dtype=np.uint8))


def test_paste_back_exact_outside_mask() -> None:
    orig, edit = _noise((64, 48), 1), _noise((64, 48), 2)
    mask = Image.new("L", (64, 48), 0)
    mask.paste(255, (20, 10, 40, 30))
    hard = maskkit.paste_back(orig, edit, mask)
    o, e, h = (np.asarray(x) for x in (orig, edit, hard))
    assert (h[:, :20] == o[:, :20]).all() and (h[10:30, 20:40] == e[10:30, 20:40]).all()
    assert maskkit.drift_outside(orig, hard, mask) == 0.0
    soft = np.asarray(maskkit.paste_back(orig, edit, mask, feather=2.0))
    # beyond the blur reach (4 sigma ~ 8 px) pixels equal the original
    far = np.ones((48, 64), bool)
    far[10 - 9:30 + 9, 20 - 9:40 + 9] = False
    assert (soft[far] == o[far]).all()
    assert (soft != o).any()
    assert 0 < maskkit.drift_outside(orig, edit, mask)


def test_paste_back_resizes_edit() -> None:
    orig, edit = _noise((64, 48), 1), _noise((128, 96), 2)
    mask = Image.new("L", (64, 48), 255)
    out = maskkit.paste_back(orig, edit, mask)
    assert out.size == orig.size and out.mode == "RGB"
    assert np.abs(np.asarray(out, int) - np.asarray(edit.resize(orig.size, Image.LANCZOS), int)).max() == 0
    assert maskkit.drift_outside(orig, edit, Image.new("L", orig.size, 255)) == 0.0   # nothing outside


def test_draw_mark() -> None:
    img = Image.new("RGB", (100, 100), (0, 0, 255))
    out = maskkit.draw_mark(img, 50, 50, 20)
    assert img.getpixel((70, 50)) == (0, 0, 255)                 # original untouched
    assert out.getpixel((70, 50)) == (255, 0, 0) and out.getpixel((50, 50)) == (0, 0, 255)


# ------------------------------------------------------------ 1.3 pose strip
def test_pose_strip() -> None:
    cell = (384, 768)
    frames = pose.walk_side_frames(5)
    assert len(frames) == 5 and all(len(f) == 18 for f in frames)
    k = (832 / 1216) / (cell[0] / cell[1])
    assert abs(frames[0][1][0] - (0.5 + (pose.walk_side(0)[1][0] - 0.5) * k)) < 1e-9
    assert frames[0] != frames[2]
    im = pose.strip(frames, cell)
    assert im.size == (5 * 384, 768)
    a = np.asarray(im)
    for i in range(5):
        assert a[:, i * 384:(i + 1) * 384].max() > 0, f"cell {i} is black"
    small = pose.strip(pose.walk_side_frames(3, (100, 200)), (100, 200))
    assert small.size == (300, 200)


# ------------------------------------------------------------ 1.5 generate --json
def _run_cli(argv) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        artgen.main(argv)
    return buf.getvalue()


def test_generate_json_flag() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = ["generate", "--backend", "test_solid", "--prompt", "a b", "--raw-prompt", "--seed", "3", "--n", "2",
                "--width", "8", "--height", "8", "--out", td]
        plain = _run_cli(base).strip().splitlines()
        assert len(plain) == 2 and all(l.endswith(".png") for l in plain)       # default unchanged
        out = _run_cli(base + ["--json"]).strip().splitlines()
        obj = json.loads(out[-1])
        assert obj["ok"] is True and obj["seeds"] == [3, 4] and obj["stats"] == {"peak": 1}
        assert obj["files"] == plain and all(Path(f).exists() for f in obj["files"])


def test_default_profile_without_project_profile() -> None:
    import artprofile
    old = os.environ.pop("ARTGEN_PROFILE", None)
    saved = artprofile.HERE
    try:
        with tempfile.TemporaryDirectory() as td:
            artprofile.HERE = Path(td)                      # neither cwd nor the tool dir is under an art/ folder
            assert artprofile.find_profile(Path(td)) == artprofile.DEFAULT_FILE
            (Path(td) / "art").mkdir()
            (Path(td) / "art" / "artgen-profile.json").write_text('{"name": "p", "char_cell": [1, 2]}')
            found = artprofile.find_profile(Path(td) / "a" if (Path(td) / "a").exists() else Path(td))
            assert found == Path(td).resolve() / "art" / "artgen-profile.json"
            assert artprofile.load(found)["char_cell"] == (1, 2)
    finally:
        artprofile.HERE = saved
        if old is not None:
            os.environ["ARTGEN_PROFILE"] = old
    d = artprofile.load(artprofile.DEFAULT_FILE)
    assert d["name"] == "default" and d["bench_ref_sheet"] is None and d["bench"] is None
    assert "assets/" not in json.dumps(d) and "Life" not in json.dumps(d)
    assert d["char_cell"] == (64, 128) and d["sheet_post_cell"] == (96, 192)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
