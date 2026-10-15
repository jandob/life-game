"""Model-free tests for the qwen_image21 backend (template, rgba wording, guard, gguf fix, registry).

    .venv/bin/python test_qwen.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import torch  # noqa: E402

import artgen  # noqa: E402
from backends import REGISTRY, get_backend  # noqa: E402
from backends import qwen_image21 as q  # noqa: E402


def test_registered_and_models_json() -> None:
    assert "qwen_image21" in REGISTRY
    from backends._common import load_registry
    cfg = load_registry()["qwen_image21"]
    assert {"gguf_repo", "gguf_file", "config_repo"} <= set(cfg)


def test_template_and_rgba_wording() -> None:
    b = get_backend("qwen_image21")
    p = b.apply_template("a red sofa")
    assert p == ("Pixel art sprite of a red sofa, 16-bit video game asset, crisp hard-edged pixels, "
                 "flat colours, plain flat white background.")
    r = b.apply_template("a red sofa", rgba=1)
    assert r.startswith("This is an RGBA image with transparency.") and "a red sofa" in r
    assert r.endswith("The image has alpha channel and the background is transparent.")
    assert "white background" not in r
    assert b.apply_template("x", rgba=0) == b.apply_template("x")


def test_rgba_reaches_template_through_artgen() -> None:
    seen = {}

    class Fake(type(get_backend("qwen_image21"))):
        def generate(self, prompt, **kw):
            seen["prompt"], seen["kw"] = prompt, kw
            return []

    with tempfile.TemporaryDirectory() as td:
        artgen.generate_images(Fake(), "a sofa", raw_prompt=False, seed=1, n=1, width=16, height=16,
                               negative=None, opts={"rgba": 1, "background": "plain flat white background"},
                               out_dir=Path(td))
    assert "alpha channel" in seen["prompt"] and seen["kw"].get("rgba") == 1


def test_base_variant_is_remote_only() -> None:
    try:
        get_backend("qwen_image21").load(variant="base")
    except RuntimeError as e:
        assert "remote only" in str(e)
    else:
        raise AssertionError("base variant must not load locally")
    assert q.PROFILES["base"]["steps"] == 40 and q.PROFILES["base"]["true_cfg"] == 4.0
    assert q.PROFILES["base"]["negative"]


def test_api_guard() -> None:
    class Good:
        def __init__(self, sample_sigmas=None): ...
        def encode_prompt(self, prompt, image=None, device=None, num_images_per_prompt=1, prompt_embeds=None,
                          prompt_embeds_mask=None, image_pad_mask=None): ...
        def __call__(self, prompt=None, output_resolution=1024): ...

    q.check_pipeline_api(Good)

    class Bad(Good):
        def encode_prompt(self, prompt, device=None): ...
        def __call__(self, prompt=None): ...

    try:
        q.check_pipeline_api(Bad)
    except RuntimeError as e:
        m = str(e)
        assert q.PINNED_DIFFUSERS in m and "image_pad_mask" in m and "output_resolution" in m
    else:
        raise AssertionError("guard must fail on a changed API")
    q.check_pipeline_api(__import__("diffusers").QwenImage21Pipeline)   # the installed one passes


def test_lfs_sha_from_blob_name() -> None:
    with tempfile.TemporaryDirectory() as td:
        sha = "ab" * 32
        blob = Path(td) / sha
        blob.write_bytes(b"x")
        link = Path(td) / "model.gguf"
        link.symlink_to(blob)
        assert q.lfs_sha256(str(link)) == sha
        assert q.lfs_sha256(str(Path(td) / "other")) is None


def test_gguf_fix_on_fake_module() -> None:
    from diffusers.quantizers.gguf.utils import GGUFLinear, GGUFParameter
    from backends._gguf import fix_non_linear
    # Q-type 30 = BF16 in gguf: raw uint8 payload of 2 bytes per element.
    from gguf import GGMLQuantizationType as T

    vals = torch.tensor([1.0, -2.0, 0.5, 3.0], dtype=torch.bfloat16)
    raw = vals.view(torch.uint8).clone()

    class Norm(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = GGUFParameter(raw.clone(), quant_type=T.BF16, requires_grad=False)

    class M(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.norm = Norm()

    m = M()
    assert m.norm.weight.dtype == torch.uint8
    fixed = fix_non_linear(m)
    assert fixed == ["norm.weight"]
    w = m.norm.weight
    assert not isinstance(w, GGUFParameter) and w.dtype == torch.bfloat16 and torch.equal(w.data, vals)
    assert fix_non_linear(m) == []          # idempotent
    assert isinstance(GGUFLinear, type)


def test_refs_verbatim_prompt_and_vae_dtype() -> None:
    b = get_backend("qwen_image21")
    assert b.apply_template("Picture 1 is a room", ref=["a.png"]) == "Picture 1 is a room"
    assert b.apply_template("x", ref=None).startswith("Pixel art sprite of x")

    class V:
        dt = None
        def to(self, d): self.dt = d
    v = V()
    assert q.set_vae_dtype(v, torch, True) == "bf16" and v.dt == torch.bfloat16
    assert q.set_vae_dtype(v, torch, False) == "fp32" and v.dt == torch.float32


def test_ref_cache_key_and_generate_with_fake_pipeline() -> None:
    import os, types
    from PIL import Image
    from backends import _enc_cache as ec
    with tempfile.TemporaryDirectory() as td:
        os.environ["ARTGEN_ENC_CACHE"] = td
        try:
            red = Path(td) / "red.png"
            Image.new("RGBA", (64, 128), (255, 0, 0, 255)).save(red)
            blue = Path(td) / "blue.png"
            Image.new("RGBA", (64, 128), (0, 0, 255, 255)).save(blue)
            c = lambda p, r: [q.condition_image(Image.open(p), r)]
            k = lambda p, r: ec.key("P", c(p, r), r, "enc")
            assert k(red, 64) != k(blue, 64) and k(red, 64) != k(red, 96) and k(red, 64) == k(red, 64)

            seen = {}

            class Pipe:
                vae = type("V", (), {"to": lambda self, d: seen.__setitem__("dt", d)})()
                def __call__(self, **kw):
                    seen["kw"] = kw
                    seen["enc"] = self.encode_prompt()
                    return types.SimpleNamespace(images=[Image.new("RGB", (32, 16))])

            b = get_backend("qwen_image21")
            b.torch, b.device, b.sched = torch, "cpu", object()
            b.encoder_id, b.sample_sigmas = "enc", [1.0, 0.5]
            b.profile = dict(q.PROFILES["turbo"], name="turbo")
            b.mem = lambda: None
            b._load_pipe = lambda with_refs=False: Pipe()
            conds = c(red, 64)
            enc = (torch.zeros(1, 2, 3), torch.ones(1, 2), torch.ones(1, 2))
            ec.put(ec.key("P", conds, 64, "enc"), enc, q.NAMESPACE)
            out = b.generate("P", width=32, height=16, seed=5, ref=[str(red)], ref_res=64)
            st = b.stats()
            kw = seen["kw"]
            assert out[0].mode == "RGBA" and seen["dt"] == torch.bfloat16
            assert kw["output_resolution"] == 64 and len(kw["image"]) == 1 and kw["width"] == 32
            assert len(seen["enc"]) == 3
            assert st["ref_res"] == 64 and st["enc_cache_hit"] and st["prompt_mode"].startswith("verbatim")
            assert st["refs"][0]["sha256"] == q.file_sha256(red) and st["vae"]["dtype"] == "bf16"
            ec.put(ec.key("P", [], 512, "enc"), enc, q.NAMESPACE)
            b.generate("P", width=32, height=16, seed=5)       # text-only path: fp32 again, no image kwarg
            assert seen["dt"] == torch.float32 and "image" not in seen["kw"]
        finally:
            os.environ.pop("ARTGEN_ENC_CACHE", None)


class FakeEditBackend:
    """Records generate() calls; returns noise images at the requested size."""
    from backends.base import BackendInfo
    info = BackendInfo(name="fake_edit", description="t", models=[], licence="n/a",
                       caps=frozenset({"refs", "edit", "sheet"}))
    load_keys = frozenset()

    def __init__(self):
        self.calls = []

    def load(self, **kw): ...

    def generate(self, prompt, width=0, height=0, seed=0, n=1, **kw):
        import numpy as np
        from PIL import Image
        self.calls.append(dict(prompt=prompt, width=width, height=height, seed=seed, n=n, **kw))
        rng = np.random.default_rng(seed)
        return [Image.fromarray(rng.integers(0, 255, (height, width, 3), dtype="uint8")).convert("RGBA")
                for _ in range(n)]

    def stats(self):
        return {"last_image_s": [0.1]}


def test_edit_mark_size_rounding_and_paste_back() -> None:
    import json
    import numpy as np
    from PIL import Image
    import maskkit
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        src = Image.fromarray(np.random.default_rng(1).integers(0, 255, (100, 70, 3), dtype="uint8"))
        sp = td / "src.png"
        src.save(sp)
        m = Image.new("L", (70, 100), 0)
        m.paste(255, (20, 30, 50, 60))
        mp = td / "mask.png"
        m.save(mp)
        assert artgen.round32(70) == 64 and artgen.round32(100) == 96 and artgen.round32(10) == 32
        b = FakeEditBackend()
        r = artgen.edit_images(b, sp, "Picture 1: fix", extras=[sp], mark=(35, 45, 10), mask_path=mp, feather=2,
                               ref_res=640, seed=7, n=1, out_dir=td / "o", stem="e")
        c = b.calls[0]
        assert (c["width"], c["height"]) == (64, 96) and c["ref_res"] == 640 and c["prompt"] == "Picture 1: fix"
        assert c["ref"][0].endswith("e_marked.png") and c["ref"][1] == str(sp)
        marked = Image.open(c["ref"][0])
        assert marked.size == (70, 100) and np.abs(np.asarray(marked, int) - np.asarray(src, int)).sum() > 0
        out = Image.open(r["files"][0])
        assert out.size == (70, 100)                                         # resized back to the source size
        d = r["stats"]["drift"]
        assert d["drift_outside_reach"] == 0.0 and d["drift_outside_mask"] < 5
        a, o = np.asarray(src, int), np.asarray(out.convert("RGB"), int)
        assert (a[:20] == o[:20]).all() and (a[:, :10] == o[:, :10]).all()     # far from the mask: identical
        assert o[45, 35].tolist() != a[45, 35].tolist()                       # inside the mask: edited
        assert Path(r["raw_files"][0]).name == "e_s7_raw.png" and r["seeds"] == [7]
        sc = json.loads((td / "o" / "e_s7.json").read_text())
        assert sc["mask_sha256"] == artgen.file_sha256(mp) and sc["feather"] == 2 and sc["mark"] == [35, 45, 10]
        assert sc["generated_size"] == [64, 96] and sc["output_size"] == [70, 100]
        # without mark/mask: source is the ref as is, result is the plain edit
        b2 = FakeEditBackend()
        r2 = artgen.edit_images(b2, sp, "p", out_dir=td / "o2")
        assert b2.calls[0]["ref"] == [str(sp)] and b2.calls[0]["ref_res"] == 1024 and "drift" not in r2["stats"]


def test_edit_cli_json_last_line_and_marked_key() -> None:
    import contextlib, io, json
    from PIL import Image
    from backends import _enc_cache as ec
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        Image.new("RGB", (64, 64), (10, 20, 30)).save(td / "s.png")
        fake = FakeEditBackend()
        orig = artgen.get_backend
        artgen.get_backend = lambda name: fake
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                artgen.main(["edit", "--image", str(td / "s.png"), "--prompt", "x", "--mark", "32,32,10",
                             "--seed", "3", "--out", str(td / "o")])
        finally:
            artgen.get_backend = orig
        obj = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert obj["ok"] and obj["seeds"] == [3] and len(obj["files"]) == 1 and "raw_files" not in obj
        # the key of the marked source differs from the key of the plain source
        plain = q.condition_image(Image.open(td / "s.png"), 64)
        marked = q.condition_image(Image.open(fake.calls[0]["ref"][0]), 64)
        assert ec.key("x", [plain], 64, "e") != ec.key("x", [marked], 64, "e")


def test_generate_default_size_from_backend() -> None:
    assert get_backend("qwen_image21").info.default_size == (1024, 1024)
    assert get_backend("z_image_turbo").info.default_size == (512, 512)
    assert get_backend("flux2_klein_pixel_lora").info.default_size == (512, 512)


class FakeSheetBackend(FakeEditBackend):
    """Returns a white sheet with one dark 'figure' per cell, a different width in every frame."""
    def generate(self, prompt, width=0, height=0, seed=0, n=1, **kw):
        from PIL import Image, ImageDraw
        self.calls.append(dict(prompt=prompt, width=width, height=height, seed=seed, n=n, **kw))
        im = Image.new("RGB", (width, height), (255, 255, 255))
        d = ImageDraw.Draw(im)
        cw = width // 5
        for i in range(5):
            half = 10 + 3 * i
            cx = i * cw + cw // 2
            d.rectangle((cx - half, height // 6, cx + half, height - 20), fill=(30, 60 + 20 * i, 120))
        return [im]


def test_sheet_prompt_numbering() -> None:
    p1 = artgen.sheet_prompt(1, 5)
    assert p1.startswith("Picture 1 shows the same character") and "Picture 2 is a row of five" in p1
    assert "Picture 2 (the first frame" in p1 and "Frame 5:" in p1
    p2 = artgen.sheet_prompt(2, 5, subject="a young man")
    assert "Picture 1 shows a young man from the front and Picture 2" in p2 and "Picture 3 is a row" in p2
    p3 = artgen.sheet_prompt(3, 4)
    assert "Pictures 1 to 3 show" in p3 and "Picture 4 is a row of four" in p3 and "Frame 4:" in p3
    assert "Frame 5" not in p3
    # the 5-frame text is the eval's wording
    ev = Path(HERE / "out/eval_2026-10/walk/prompt_sheet_A.txt")
    assert artgen.walk_words(5)[0] in (ev.read_text() if ev.exists() else artgen.walk_words(5)[0])


def test_sheet_strip_slice_fixed_grid_and_json() -> None:
    import json
    from PIL import Image
    import pose
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for n in ("a.png", "b.png"):
            Image.new("RGB", (64, 64), (9, 9, 9)).save(td / n)
        b = FakeSheetBackend()
        r = artgen.sheet_images(b, [td / "a.png", td / "b.png"], frames=5, cell=(64, 128), ref_res=64, seed=4,
                                slice_=True, post_cell=(24, 48), feet_row=40, out_dir=td / "o", stem="w")
        c = b.calls[0]
        assert (c["width"], c["height"]) == (320, 128) and c["ref_res"] == 64
        assert c["ref"][:2] == [str(td / "a.png"), str(td / "b.png")] and c["ref"][2].endswith("w_poses.png")
        strip = Image.open(td / "o" / "w_poses.png")
        assert strip.size == (320, 128)
        assert strip.tobytes() == pose.strip(pose.walk_side_frames(5, (64, 128)), (64, 128)).tobytes()
        names = {Path(f).name for f in r["files"]}
        assert {"w.png", "w.gif", "w_px_row.png"} <= names
        assert {f"w_f{i}.png" for i in range(5)} <= names and {f"w_f{i}_px.png" for i in range(5)} <= names
        for i in range(5):
            assert Image.open(td / "o" / f"w_f{i}_px.png").size == (24, 48)
        sc = json.loads((td / "o" / "w.json").read_text())
        assert sc["grid"] == r["stats"]["grid"] and sc["strip_sha256"] and sc["prompt_mode"] == "generated"
        assert len(sc["refs"]) == 2 and sc["poses"] == "walk_side" and sc["frames"] == 5
        g = Image.open(td / "o" / "w.gif")
        assert g.n_frames == 5 and g.info["duration"] == 140
        # an explicit --grid is used as is, a given prompt verbatim
        b2 = FakeSheetBackend()
        r2 = artgen.sheet_images(b2, [td / "a.png"], frames=5, cell=(64, 128), prompt="P!", grid=2.5,
                                 slice_=True, post_cell=(24, 48), feet_row=40, out_dir=td / "o2")
        assert r2["stats"]["grid"] == 2.5 and b2.calls[0]["prompt"] == "P!"
    try:
        artgen.sheet_images(FakeSheetBackend(), [], frames=5, cell=(100, 128), out_dir=Path(tempfile.mkdtemp()))
    except SystemExit as e:
        assert "multiples of 32" in str(e)
    else:
        raise AssertionError("bad size must be rejected")


def test_sheet_cli_json_last_line() -> None:
    import contextlib, io, json
    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        Image.new("RGB", (64, 64)).save(td / "a.png")
        fake = FakeSheetBackend()
        orig = artgen.get_backend
        artgen.get_backend = lambda name: fake
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                artgen.main(["sheet", "--ref", str(td / "a.png"), "--cell", "64x128", "--ref-res", "64",
                             "--seed", "2", "--out", str(td / "o"), "--name", "s"])
        finally:
            artgen.get_backend = orig
        obj = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert obj["ok"] and obj["seeds"] == [2] and obj["files"] == [str(td / "o" / "s.png")]


def test_runner_opt_remote_roundtrip_and_errors() -> None:
    import contextlib, io, json, os, sys
    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        Image.new("RGB", (64, 64), (1, 2, 3)).save(td / "a.png")
        (td / "fake.py").write_text(
            "import sys, json, base64, io\n"
            "from PIL import Image\n"
            "s = json.load(sys.stdin)\n"
            "json.dump(s, open(sys.argv[1], 'w'))\n"
            "out = []\n"
            "for i in range(s['n']):\n"
            "    b = io.BytesIO(); Image.new('RGB', (s['width'], s['height']), (s['seed'] + i, 5, 5)).save(b, 'PNG')\n"
            "    out.append({'png_base64': base64.b64encode(b.getvalue()).decode(), 'meta': {'stats': {'remote_gpu': 'fake', 'last_image_s': [1.5] * s['n']}}})\n"
            "print(json.dumps(out))\n")
        seen = td / "spec.json"
        os.environ["ARTGEN_REMOTE_FAKE_CMD"] = f"{sys.executable} {td / 'fake.py'} {seen}"

        def run(argv):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                artgen.main(argv)
            return buf.getvalue().strip().splitlines()[-1]
        try:
            obj = json.loads(run(["generate", "--backend", "qwen_image21", "--prompt", "a sofa", "--seed", "3", "--n", "2",
                                  "--width", "64", "--height", "32", "--opt", "runner=remote:fake", "--opt", "variant=base",
                                  "--ref", str(td / "a.png"), "--json", "--out", str(td / "o")]))
            assert obj["ok"] and obj["seeds"] == [3, 4] and obj["stats"]["runner"] == "remote:fake"
            assert Image.open(obj["files"][1]).getpixel((0, 0))[:3] == (4, 5, 5)
            spec = json.loads(seen.read_text())
            assert spec["variant"] == "base" and spec["kind"] == "generate" and spec["backend"] == "qwen_image21"
            assert spec["prompt"] == "a sofa" or spec["prompt"].startswith("a sofa")   # refs given: verbatim
            assert len(spec["refs"]) == 1 and spec["width"] == 64 and "runner" not in spec["opts"]
            assert (td / "o" / "sheet.json").exists() is False and Path(obj["files"][0]).with_suffix(".json").exists()
            # edit and sheet go through the same seam
            e = json.loads(run(["edit", "--image", str(td / "a.png"), "--prompt", "x", "--opt", "runner=remote:fake",
                                "--out", str(td / "e")]))
            assert e["ok"] and json.loads(seen.read_text())["kind"] == "edit"
            sh = json.loads(run(["sheet", "--ref", str(td / "a.png"), "--cell", "64x128", "--opt", "runner=remote:fake",
                                 "--out", str(td / "s")]))
            sp = json.loads(seen.read_text())
            assert sh["ok"] and sp["kind"] == "sheet" and sp["width"] == 320 and len(sp["refs"]) == 2
        finally:
            os.environ.pop("ARTGEN_REMOTE_FAKE_CMD")
        # no host configured
        try:
            run(["generate", "--backend", "qwen_image21", "--prompt", "x", "--opt", "runner=remote:nohost", "--out", str(td / "x")])
        except RuntimeError as err:
            assert "no remote host configured" in str(err) and "ARTGEN_REMOTE_NOHOST_CMD" in str(err)
        else:
            raise AssertionError("expected an error")
        # base + local runner
        try:
            run(["generate", "--backend", "qwen_image21", "--prompt", "x", "--opt", "variant=base", "--out", str(td / "y")])
        except RuntimeError as err:
            assert "base variant runs remote only (use --opt runner=remote:<name>)" in str(err)
        else:
            raise AssertionError("expected an error")


def test_cache_cli_and_bench_size() -> None:
    import contextlib, io, json, os, time
    import bench
    from backends import _enc_cache as ec
    assert bench.bench_size({"width": 512, "height": 512, "sizes": {"qwen_image21": [1024, 1024]}}, "qwen_image21") == (1024, 1024)
    assert bench.bench_size({"width": 512, "height": 512, "sizes": {"qwen_image21": [1024, 1024]}}, "z_image_turbo") == (512, 512)
    assert bench.bench_size({}, "x") == (512, 512)
    assert "qwen_image21" in bench.REGISTRY and "Qwen Research" in get_backend("qwen_image21").info.licence
    with tempfile.TemporaryDirectory() as td:
        os.environ["ARTGEN_ENC_CACHE"] = td
        try:
            def run(*argv):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    artgen.main(["cache", *argv])
                return json.loads(buf.getvalue())
            assert run("--stats")["count"] == 0
            old = ec.put("a" * 64, (torch.zeros(10), None), "qwen21")
            ec.put("b" * 64, (torch.zeros(10), None), "qwen21")
            os.utime(old, (time.time() - 40 * 86400,) * 2)
            r = run("--stats")
            assert r["count"] == 2 and r["bytes"] > 0
            r = run("--prune", "--older-than", "30")
            assert r["removed"] == 1 and r["count"] == 1
            r = run("--prune", "--max-gb", "0")
            assert r["removed"] == 1 and r["count"] == 0
            try:
                run("--prune")
            except SystemExit:
                pass
            else:
                raise AssertionError("prune without a criterion must fail")
        finally:
            os.environ.pop("ARTGEN_ENC_CACHE", None)


def test_capability_guards() -> None:
    import contextlib, io
    caps = {n: get_backend(n).info.caps for n in REGISTRY}
    assert caps["qwen_image21"] == {"refs", "edit", "sheet", "rgba", "remote"}
    assert caps["flux2_klein_pixel_lora"] == {"refs", "inpaint", "refine"}
    assert not caps["z_image_turbo"] and not caps["example_stub"]
    assert get_backend("qwen_image21").info.to_dict()["caps"] == ["edit", "refs", "remote", "rgba", "sheet"]
    cases = [
        (["edit", "--backend", "z_image_turbo", "--image", "x.png", "--prompt", "p", "--out", "o"], "edit", "qwen_image21"),
        (["edit", "--backend", "flux2_klein_pixel_lora", "--image", "x.png", "--prompt", "p", "--out", "o"], "edit", "qwen_image21"),
        (["sheet", "--backend", "flux2_klein_pixel_lora", "--ref", "x.png", "--out", "o"], "sheet", "qwen_image21"),
        (["generate", "--backend", "z_image_turbo", "--prompt", "p", "--ref", "x.png", "--out", "o"], "--ref", "flux2_klein_pixel_lora, qwen_image21"),
        (["generate", "--backend", "flux2_klein_pixel_lora", "--prompt", "p", "--opt", "rgba=1", "--out", "o"], "rgba", "qwen_image21"),
        (["generate", "--backend", "flux2_klein_pixel_lora", "--prompt", "p", "--opt", "runner=remote:x", "--out", "o"], "runner", "qwen_image21"),
        (["refine", "--backend", "qwen_image21", "--image", "x.png", "--prompt", "p", "--out", "o"], "refine", "flux2_klein_pixel_lora"),
        (["inpaint", "--backend", "z_image_turbo", "--image", "x.png", "--mask", "m.png", "--prompt", "p", "--out", "o"], "inpaint", "flux2_klein_pixel_lora"),
    ]
    for argv, what, supporters in cases:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                artgen.main(argv)
        except SystemExit as e:
            m = str(e)
            assert "does not support" in m and what in m and supporters in m, (argv, m)
        else:
            raise AssertionError(argv)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        artgen.main(["backends"])
    assert "caps=edit,refs,remote,rgba,sheet" in buf.getvalue() and "caps=inpaint,refine,refs" in buf.getvalue()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
