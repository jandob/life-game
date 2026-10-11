#!/usr/bin/env python3
"""Tests for the phase 2 (generate / fill / apply) parts of tools/scenekit that need no model.

Run: mise exec -- python3 tools/scenekit/test_generate.py

The model is replaced by a stub `artgen.py` (SCENEKIT_ARTGEN) that paints a periodic pattern with a little off-grid
noise into the masked area; `snap` still runs the real artgen code in tools/artgen/.venv, so those tests are skipped when
the venv is missing."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "mapgen"))
from PIL import Image  # noqa: E402

import genkit as G  # noqa: E402
from common import SceneError, load_materials  # noqa: E402
from test_scenekit import Base, sha  # noqa: E402

ARTGEN = os.path.abspath(os.path.join(HERE, "..", "artgen"))
VENV_PY = os.path.join(ARTGEN, ".venv", "bin", "python")
HAVE_VENV = os.path.isfile(VENV_PY)

STUB = textwrap.dedent('''
    import json, os, random, runpy, sys
    from PIL import Image
    args = sys.argv[1:]
    if args[0] != "inpaint":
        sys.argv = [os.environ["REAL_ARTGEN"]] + args
        runpy.run_path(os.environ["REAL_ARTGEN"], run_name="__main__")
        sys.exit(0)
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    canvas = Image.open(opt("--image")).convert("RGB")
    mask = Image.open(opt("--mask")).convert("L")
    out, n, seed = opt("--out"), int(opt("--n", 1)), int(opt("--seed", 0))
    B = int(os.environ.get("STUB_BLOCK", 4))
    pal = [(150, 110, 70), (140, 100, 62), (160, 120, 80), (120, 85, 55), (96, 100, 125), (80, 84, 105)]
    files = []
    for i in range(n):
        rng = random.Random(seed + i)
        im = canvas.copy()
        px, mk = im.load(), mask.load()
        for gy in range(im.height // B):
            for gx in range(im.width // B):
                if mk[gx * B, gy * B] < 128:
                    continue
                base = pal[(gx % 16 + 2 * (gy % 16) + i) % len(pal)]
                for dy in range(B):
                    for dx in range(B):
                        c = base
                        if rng.random() < 0.06:           # off-grid noise inside a block
                            c = (min(255, base[0] + 40), base[1], base[2])
                        px[gx * B + dx, gy * B + dy] = tuple(min(255, v + rng.randint(-2, 2)) for v in c)
        p = os.path.join(out, "raw-%d.png" % i)
        im.save(p); files.append(p)
    print(json.dumps({"ok": True, "files": files, "prompt": "STUB " + opt("--prompt", ""), "gen_opts": {"steps": 4}, "stats": {}}))
''')

LAYOUT = "##########\n##########\n" + "..........\n" * 6


class Gen(Base):
    def setUp(self):
        super().setUp()
        self.stub = os.path.join(self.tmp, "stub_artgen.py")
        with open(self.stub, "w") as f:
            f.write(STUB)
        self.env.update(SCENEKIT_ARTGEN=self.stub, REAL_ARTGEN=os.path.join(ARTGEN, "artgen.py"),
                        SCENEKIT_ARTGEN_PYTHON=VENV_PY if HAVE_VENV else sys.executable)
        self.layout = os.path.join(self.tmp, "room.txt")
        with open(self.layout, "w") as f:
            f.write(LAYOUT)
        self.hex = os.path.join(self.tmp, "p.hex")
        with open(self.hex, "w") as f:
            f.write("\n".join(f"{r:02x}{g:02x}{b:02x}" for r, g, b in
                              [(150, 110, 70), (140, 100, 62), (160, 120, 80), (120, 85, 55), (96, 100, 125), (80, 84, 105)]))
        self.clear = '[{"rect":[0,0,320,240,"#00000000"]}]'

    def gen(self, *extra, ok=True):
        return self.run_cli("generate", self.map, "--layer", "Ground", "--region", "5,3,10,8", "--layout", self.layout,
                            "--prompt", "room", "--scale", "4", *extra, ok=ok)

    def job_dir(self, out):
        return os.path.join(self.tmp, "out", "jobs", out["job"])


class TestLayoutAndGeometry(unittest.TestCase):
    def setUp(self):
        self.mats = load_materials()

    def test_text_layout_legend_and_keep(self):
        g = G.parse_layout_text("# #\n. _\n", 3, 2, self.mats)
        self.assertEqual(g, [["wall", None, "wall"], ["floor", None, None]])
        g = G.parse_layout_text("@ X = water\nXX\n..\n", 2, 2, self.mats)
        self.assertEqual(g[0], ["water", "water"])

    def test_layout_errors(self):
        for text, w, h in (("##\n", 2, 2), ("###\n##\n", 2, 2), ("?#\n", 2, 1)):
            with self.assertRaises(SceneError):
                G.parse_layout_text(text, w, h, self.mats)

    def test_png_layout(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "l.png")
        im = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
        im.putpixel((0, 0), (0x8a, 0x6d, 0x4b, 255))
        im.save(p)
        self.assertEqual(G.parse_layout_png(p, 2, 1, self.mats), [["floor", None]])
        im.putpixel((1, 0), (1, 2, 3, 255))
        im.save(p)
        with self.assertRaises(SceneError):
            G.parse_layout_png(p, 2, 1, self.mats)

    def test_scale_and_box(self):
        self.assertEqual(G.pick_scale(224, 192), 4)          # 14 x 12 cells
        self.assertEqual(G.pick_scale(512, 100), 2)
        self.assertIsNone(G.pick_scale(528, 100))
        box, ring, s = G.fit_box(20, 15, (5, 3, 10, 8), 2)
        self.assertEqual((box, ring, s), ((3, 1, 14, 12), 2, 4))
        box, ring, s = G.fit_box(100, 100, (10, 10, 30, 20), 5)     # ring shrinks until scale 2 fits
        self.assertGreaterEqual(s, 2)
        self.assertLessEqual(ring, 1)
        with self.assertRaises(SceneError) as e:
            G.fit_box(100, 100, (0, 0, 33, 4), 0)
        self.assertEqual(e.exception.code, "too_large")
        self.assertIn("split", str(e.exception))

    def test_blockout_texture_is_continuous_and_keeps_none(self):
        layout = [["wall", None], ["floor", "floor"]]
        a = G.blockout_region(layout, (0, 0, 2, 2), self.mats)
        b = G.blockout_region([["floor", "floor"]], (0, 1, 2, 1), self.mats)   # same cells seen from another region
        self.assertEqual(a.crop((0, 16, 32, 32)).tobytes(), b.tobytes())
        self.assertEqual(a.getpixel((20, 5))[3], 0)


class TestCanvas(Gen):
    def test_canvas_mask_and_context(self):
        out = self.gen("--dry-run")
        jd = self.job_dir(out)
        canvas = Image.open(os.path.join(jd, "canvas.png"))
        mask = Image.open(os.path.join(jd, "mask.png"))
        self.assertEqual(out["box"], [3, 1, 14, 12])
        self.assertEqual(canvas.size, (14 * 16 * 4, 12 * 16 * 4))
        self.assertEqual(mask.size, canvas.size)
        self.assertEqual(canvas.size[0] % 16 + canvas.size[1] % 16, 0)
        # white exactly over the region (cells 5..14 x 3..10 -> box offset 2,2)
        for (x, y), want in (((2 * 64, 2 * 64), 255), ((12 * 64 - 1, 10 * 64 - 1), 255), ((2 * 64 - 1, 2 * 64), 0),
                             ((12 * 64, 5 * 64), 0), ((5 * 64, 2 * 64 - 1), 0), ((5 * 64, 10 * 64), 0)):
            self.assertEqual(mask.getpixel((x, y)), want, (x, y))
        # context = the map's pixels, nearest-neighbour upscaled; inside = block-out wall colour on top rows
        base = Image.open(os.path.join(jd, "base.png")).convert("RGB")
        up = base.resize((base.width * 4, base.height * 4), Image.NEAREST)
        ctx = [(5, 5), (40, 20), (canvas.width - 6, canvas.height - 6)]
        for p in ctx:
            self.assertEqual(canvas.convert("RGB").getpixel(p), up.getpixel(p))
        wall = G.parse_colour(load_materials()["wall"]["colour"])[:3]
        self.assertEqual(canvas.convert("RGB").getpixel((7 * 64, 3 * 64)), wall)
        # dry run wrote nothing but the job directory
        self.assertEqual(sha(self.map), sha(os.path.join(self.root, "assets", "maps", "sandbox.tmj")))

    def test_too_large_region(self):
        d = json.load(open(self.map))
        d["width"], d["height"] = 40, 40
        d["layers"][0]["width"], d["layers"][0]["height"] = 40, 40
        d["layers"][0]["data"] = [0] * 1600
        big = os.path.join(self.root, "assets", "maps", "big.tmj")
        json.dump(d, open(big, "w"))
        out = self.run_cli("generate", big, "--layer", "Ground", "--region", "0,0,33,10", "--prompt", "x", "--dry-run", ok=False)
        self.assertEqual(out["code"], "too_large")
        self.assertIn("split", out["error"])

    def test_layout_size_mismatch(self):
        out = self.run_cli("generate", self.map, "--layer", "Ground", "--region", "5,3,9,8", "--layout", self.layout, "--dry-run", ok=False)
        self.assertEqual(out["code"], "bad_input")


@unittest.skipUnless(HAVE_VENV, "needs tools/artgen/.venv for the snap step")
class TestPipeline(Gen):
    def test_generate_apply_dedup_provenance(self):
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", self.clear)   # an empty map to build in
        before = self.snapshot()
        out = self.gen("--n", "3", "--palette", self.hex, "--seed", "5")
        # generate writes nothing but the job directory (which lives outside the repo copy here)
        self.assertEqual(before, self.snapshot())
        jd = self.job_dir(out)
        self.assertEqual([c["k"] for c in out["candidates"]], [0, 1, 2])
        pal = set(G.read_hex(self.hex))
        for k in range(3):
            cand = Image.open(os.path.join(jd, f"cand-{k}.png"))
            self.assertEqual(cand.size, (160, 128))
            self.assertTrue(G.image_colours(cand) <= pal, k)
            self.assertTrue(os.path.isfile(os.path.join(jd, f"preview-{k}.png")))
            with Image.open(os.path.join(jd, f"preview-{k}.png")) as pv:
                self.assertGreater(pv.width, 14 * 64 * 2)
        with open(os.path.join(jd, "job.json")) as fh:
            job = json.load(fh)
        self.assertEqual(job["region"], [5, 3, 10, 8])
        self.assertEqual(job["candidates"][1]["seed"], 6)
        # the raw model output has noise; the snapped candidate lies on the grid: re-snapping the 4x upscale is identical
        c0 = Image.open(os.path.join(jd, "cand-0.png")).convert("RGB")
        up = c0.resize((c0.width * 4, c0.height * 4), Image.NEAREST)
        self.assertEqual(up.resize(c0.size, Image.NEAREST).tobytes(), c0.tobytes())

        # apply: only the region changes
        before_map = os.path.join(self.root, "assets", "maps", "before.tmj")
        with open(self.map, "rb") as f, open(before_map, "wb") as g:
            g.write(f.read())
        res = self.run_cli("apply", job["id"], "--pick", 1, "--if-hash", self.run_cli("cells", self.map, "--region", "0,0,1,1")["map_hash"])
        self.assertEqual(res["counts"]["cells_changed"], 80)
        d = self.run_cli("diff", before_map, self.map)
        changed = [(c["x"], c["y"]) for l in d["layers"].values() for c in l["changed"]]
        self.assertEqual(len(changed), 80)
        self.assertTrue(all(5 <= x < 15 and 3 <= y < 11 for x, y in changed))
        # provenance and materials/collision from the layout
        man = json.load(open(os.path.join(self.lib, "tiles.json")))
        self.assertEqual(len(man["tiles"]), len(res["tiles_new"]))
        for k, t in man["tiles"].items():
            self.assertEqual(t["origin"], "generate")
            self.assertEqual(t["job"], job["id"])
            self.assertEqual(t["gen"]["seed"], 6)
            for f in ("backend", "models", "lora_scale", "prompt", "strength", "steps", "scale", "refs", "layout", "palette"):
                self.assertIn(f, t["gen"], f)
            self.assertEqual(t["source"]["map"].endswith("work.tmj"), True)
            self.assertIn(t["material"], ("floor", "wall"))
        tsj = json.load(open(os.path.join(self.lib, "page-000.tsj")))
        walls = [int(k) for k, t in man["tiles"].items() if t["material"] == "wall"]
        with_coll = {e["id"] for e in tsj["tiles"] if e.get("objectgroup")}
        self.assertTrue(set(walls) <= with_coll)
        floors = [int(k) for k, t in man["tiles"].items() if t["material"] == "floor"]
        self.assertFalse(set(floors) & with_coll)
        self.assertTrue(self.run_cli("library", "check")["ok"])
        # re-applying the same candidate: nothing changes, no new tiles
        again = self.run_cli("apply", job["id"], "--pick", 1)
        self.assertEqual(again["counts"], {"cells_changed": 0, "tiles_new": 0})
        self.assertEqual(again["changed_files"], [])
        # a different candidate over the changed cells is refused (map changed since the job) unless forced
        stale = self.run_cli("apply", job["id"], "--pick", 0, ok=False)
        self.assertEqual(stale["code"], "conflict")
        self.run_cli("apply", job["id"], "--pick", 0, "--force")

    def test_fill_hole_changes_only_those_cells(self):
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", self.clear)
        out = self.gen("--n", "1", "--palette", self.hex)
        self.run_cli("apply", out["job"], "--pick", 0)
        ref = os.path.join(self.root, "assets", "maps", "ref.tmj")
        with open(self.map, "rb") as f, open(ref, "wb") as g:
            g.write(f.read())
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"rect":[160,96,32,32,"#00000000"]}]')   # hole at 10,6 2x2
        holed = os.path.join(self.root, "assets", "maps", "holed.tmj")
        with open(self.map, "rb") as f, open(holed, "wb") as g:
            g.write(f.read())
        f = self.run_cli("fill", self.map, "--layer", "Ground", "--cells", "10,6;11,6;10,7;11,7", "--scale", "4", "--n", "2",
                         "--palette", self.hex, "--context", "3")
        self.assertEqual(f["region"], [10, 6, 2, 2])
        self.assertEqual(f["box"], [7, 3, 8, 8])
        mask = Image.open(os.path.join(self.tmp, "out", "jobs", f["job"], "mask.png"))
        self.assertEqual(mask.getpixel((3 * 64 * 1 + 1, 3 * 64 + 1)), 255)
        self.assertEqual(mask.getpixel((1, 1)), 0)
        res = self.run_cli("apply", f["job"], "--pick", 0)
        d = self.run_cli("diff", holed, self.map)
        changed = sorted((c["x"], c["y"]) for l in d["layers"].values() for c in l["changed"])
        self.assertEqual(changed, [(10, 6), (10, 7), (11, 6), (11, 7)])
        # the hole's four cells took the floor material only if inherited; there was no old tile, so none
        self.assertEqual(res["counts"]["cells_changed"], 4)

    def test_fill_ring_expands_mask_and_empty_mode(self):
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"rect":[0,0,320,240,"#00000000"]},{"rect":[48,48,16,16,"#ff0000"]}]')
        f = self.run_cli("fill", self.map, "--layer", "Ground", "--empty", "--region", "2,2,3,3", "--ring", "1", "--dry-run", "--scale", "4")
        self.assertEqual(f["box"][2] > 0, True)
        with open(os.path.join(self.tmp, "out", "jobs", f["job"], "job.json")) as fh:
            job = json.load(fh)
        # 8 empty cells of the 3x3 (the red one is at 3,3) plus the ring: every cell of 1..5 x 1..5 within one step
        cells = {tuple(c) for c in job["cells"]}
        self.assertIn((1, 1), cells)
        self.assertIn((5, 5), cells)
        self.assertNotIn((0, 0), cells)

    def test_grid_detect_fallback_and_alpha_key(self):
        # snap directly with the real artgen code: noise-free 4x blocks, detect fallback must give the target size
        im = Image.new("RGB", (64, 48))
        for y in range(48):
            for x in range(64):
                im.putpixel((x, y), (200, 0, 0) if (x // 4 + y // 4) % 2 else (0, 0, 200))
        d = tempfile.mkdtemp()
        src = os.path.join(d, "a.png")
        im.save(src)
        r = subprocess.run([VENV_PY, os.path.join(ARTGEN, "artgen.py"), "snap", src, "--factor", "4", "--grid", "detect",
                            "--target", "16x12", "--out", d], capture_output=True, text=True)
        res = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(Image.open(res["results"][0]["out"]).size, (16, 12))
        # key colour -> transparent
        im2 = Image.new("RGB", (16, 16), (255, 0, 255))
        for y in range(8, 16):
            for x in range(16):
                im2.putpixel((x, y), (10, 200, 10))
        src2 = os.path.join(d, "b.png")
        im2.save(src2)
        r = subprocess.run([VENV_PY, os.path.join(ARTGEN, "artgen.py"), "snap", src2, "--factor", "1", "--key", "#ff00ff",
                            "--cleanup", "0", "--out", d], capture_output=True, text=True)
        out = Image.open(json.loads(r.stdout.strip().splitlines()[-1])["results"][0]["out"])
        self.assertEqual(out.getpixel((3, 3))[3], 0)
        self.assertEqual(out.getpixel((3, 12)), (10, 200, 10, 255))


@unittest.skipUnless(HAVE_VENV, "needs tools/artgen/.venv (numpy)")
class TestDownscaleFixed(unittest.TestCase):
    def run_py(self, code):
        r = subprocess.run([VENV_PY, "-c", "import sys; sys.path.insert(0, %r)\n%s" % (ARTGEN, code)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_mode_per_block_and_phase(self):
        out = self.run_py(textwrap.dedent('''
            import random
            from PIL import Image
            import postprocess as pp
            random.seed(1)
            small = Image.new("RGBA", (7, 5))
            for y in range(5):
                for x in range(7):
                    small.putpixel((x, y), (random.randrange(0, 256, 16), random.randrange(0, 256, 16), 99, 255))
            S = 5
            big = small.resize((7 * S, 5 * S), Image.NEAREST)
            for _ in range(60):                       # 2 noisy pixels per block at most (< half of 25)
                x, y = random.randrange(35), random.randrange(25)
                big.putpixel((x, y), (255, 255, 255, 255))
            res = pp.downscale_fixed(big, S)
            print(res.size == small.size, res.tobytes() == small.tobytes())
            shifted = Image.new("RGBA", (7 * S + 3, 5 * S + 2), (1, 2, 3, 255)); shifted.paste(big, (3, 2))
            res2 = pp.downscale_fixed(shifted, S, phase=(3, 2))
            print(res2.tobytes() == small.tobytes())
            try:
                pp.downscale_fixed(big, 0)
            except ValueError:
                print("err")
        '''))
        self.assertEqual(out.splitlines(), ["True True", "True", "err"])


class TestToolkitFeedback(Gen):
    """Section 5 of the change: --compose, legend overrides, --init, --quiet, --rerun, layer-scoped staleness."""

    def add_decor(self):
        d = json.load(open(self.map))
        base = d["layers"][0]
        dec = dict(base, id=d.get("nextlayerid", 10), name="Decor", data=[0] * len(base["data"]))
        dec.pop("properties", None)
        d["layers"].insert(1, dec)
        d["nextlayerid"] = dec["id"] + 1
        json.dump(d, open(self.map, "w"))

    def decor_gen(self, *extra, ok=True):
        return self.run_cli("generate", self.map, "--layer", "Decor", "--region", "5,3,4,3", "--layout", self.layout4,
                            "--prompt", "chair", "--scale", "4", "--n", "1", "--palette", self.hex, *extra, ok=ok)

    def setUp(self):
        super().setUp()
        self.layout4 = os.path.join(self.tmp, "decor.txt")
        open(self.layout4, "w").write("@ F = furniture\nFF_F\n____\n_FF_\n")
        self.add_decor()

    def canvas_px(self, out, cell, off=(2, 2)):
        im = Image.open(os.path.join(self.job_dir(out), "canvas.png")).convert("RGB")
        bx, by = out["box"][0], out["box"][1]
        return im.getpixel(((cell[0] - bx) * 64 + off[0], (cell[1] - by) * 64 + off[1]))

    # 5.1
    def test_compose_modes(self):
        ground = self.run_cli("render", self.map, "--layers", "Ground", "--region", "3,3,1,1", "--scale", 1, "--out",
                              os.path.join(self.tmp, "g.png"))
        gpx = Image.open(os.path.join(self.tmp, "g.png")).convert("RGB").getpixel((2, 2))
        key = (255, 0, 255)
        cases = {}
        for mode in ("below", "none", "all"):
            out = self.decor_gen("--alpha", "--compose", mode, "--dry-run")
            self.assertEqual(out["compose"], mode)
            cases[mode] = self.canvas_px(out, (3, 3))          # a context cell left of the region
        self.assertEqual(cases["below"], gpx)                  # default behaviour: the floor is composited in
        self.assertEqual(cases["all"], gpx)
        self.assertEqual(cases["none"], key)                   # only the target layer: floor not baked in
        default = self.decor_gen("--alpha", "--dry-run")
        self.assertEqual(default["compose"], "below")
        self.assertEqual(self.canvas_px(default, (3, 3)), gpx)

    # 5.2
    def test_legend_override_colour_and_texture(self):
        mats_before = sha(os.path.join(self.root, "assets", "library", "tilesets", "gen", "materials.json")) \
            if os.path.isfile(os.path.join(self.lib, "materials.json")) else None
        g = G.parse_layout_text("@ O = wall #ddd5c4 texture=none\n@ P = wall #101010\nO#P\n", 3, 1, dict(load_materials()))
        self.assertEqual(len(set(g[0])), 3)
        m = dict(load_materials())
        g = G.parse_layout_text("@ O = wall #ddd5c4 texture=none\n@ P = wall #101010\nO#P\n", 3, 1, m)
        self.assertEqual(G.base_material(g[0][0], m), "wall")
        self.assertEqual(m[g[0][0]]["colour"], "#ddd5c4")
        self.assertEqual(m[g[0][2]]["colour"], "#101010")
        self.assertEqual(m[g[0][1]]["colour"], load_materials()["wall"]["colour"])
        for bad in ("@ O = wall #zzzzzz\nO\n", "@ O = wall texture=lava\nO\n", "@ O = nothing #ffffff\nO\n"):
            with self.assertRaises(SceneError):
                G.parse_layout_text(bad, 1, 1, dict(load_materials()))
        # through the CLI: the block-out has the override colour; nothing shared changed
        open(self.layout4, "w").write("@ F = furniture #ddd5c4 texture=none\nFF_F\n____\n_FF_\n")
        out = self.decor_gen("--dry-run")
        self.assertEqual(self.canvas_px(out, (5, 3), (30, 30)), (0xdd, 0xd5, 0xc4))
        job = json.load(open(os.path.join(self.job_dir(out), "job.json")))
        self.assertEqual(set(job["materials"].values()), {"furniture"})
        self.assertEqual(list(job["layout_variants"].values())[0]["colour"], "#ddd5c4")
        if mats_before:
            self.assertEqual(mats_before, sha(os.path.join(self.lib, "materials.json")))

    # 5.3
    def test_init_png_is_canvas_only(self):
        init = Image.new("RGBA", (4 * 16, 3 * 16), (0, 0, 0, 0))
        for y in range(16):
            for x in range(16):
                init.putpixel((x, y), (200, 30, 30, 255))
        ip = os.path.join(self.tmp, "init.png")
        init.save(ip)
        before = self.snapshot()
        out = self.run_cli("generate", self.map, "--layer", "Decor", "--region", "5,3,4,3", "--init", ip, "--compose", "none",
                           "--alpha", "--scale", "4", "--dry-run")
        self.assertEqual(self.canvas_px(out, (5, 3), (30, 30)), (200, 30, 30))
        self.assertEqual(self.canvas_px(out, (6, 3), (30, 30)), (255, 0, 255))
        self.assertEqual(before, self.snapshot())            # neither map nor library written
        job = json.load(open(os.path.join(self.job_dir(out), "job.json")))
        self.assertEqual(job["init"], "sha256:" + sha(ip))
        bad = os.path.join(self.tmp, "bad.png")
        Image.new("RGBA", (10, 10)).save(bad)
        e = self.run_cli("generate", self.map, "--layer", "Decor", "--region", "5,3,4,3", "--init", bad, "--dry-run", ok=False)
        self.assertEqual(e["code"], "bad_input")

    # 5.4 (apply --quiet) and 5.6
    def test_scoped_staleness_and_rerun(self):
        # a Ground edit first, so the gen page is already in the map and later edits don't change the tileset list
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", json.dumps(self.px_ops((1, 1), ["#ff0000"])))
        job_none = self.decor_gen("--compose", "none", "--alpha", "--seed", "3")
        job_below = self.decor_gen("--seed", "3")
        jn, jb = job_none["job"], job_below["job"]
        self.assertEqual(sorted(json.load(open(os.path.join(self.job_dir(job_none), "job.json")))["scope"]["layers"]), ["Decor"])
        self.assertEqual(sorted(json.load(open(os.path.join(self.job_dir(job_below), "job.json")))["scope"]["layers"]),
                         ["Decor", "Ground"])
        # an unrelated write (Ground) leaves the none-job valid and makes the below-job stale
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", json.dumps(self.px_ops((2, 1), ["#00ff00"])))
        stale = self.run_cli("apply", jb, "--pick", 0, "--if-hash", "job", ok=False)
        self.assertEqual(stale["code"], "stale")
        self.assertIn("layer 'Ground' changed", stale["reasons"])
        # the same job applied without --if-hash job keeps today's behaviour
        self.run_cli("apply", jb, "--pick", 0, "--dry-run")
        # a write to a layer it writes (Decor, outside the region's cells) makes the none-job stale too
        ok = self.run_cli("apply", jn, "--pick", 0, "--if-hash", "job", "--quiet", "--dry-run")
        self.assertTrue(ok["quiet"])
        self.assertNotIn("cells_changed", ok)
        self.assertEqual(ok["counts"]["cells_changed"], 12)
        self.run_cli("edit", self.map, "--layer", "Decor", "--ops", json.dumps(self.px_ops((12, 8), ["#0000ff"])))
        s2 = self.run_cli("apply", jn, "--pick", 0, "--if-hash", "job", ok=False)
        self.assertEqual(s2["code"], "stale")
        self.assertIn("layer 'Decor' changed", s2["reasons"])
        # rerun: new seed, same inputs; works from the map as it is now
        re1 = self.run_cli("generate", "--rerun", jn, "--seed", "40")
        self.assertEqual([c["seed"] for c in re1["candidates"]], [40])
        self.assertEqual(re1["rerun_of"], jn)
        j1 = json.load(open(os.path.join(self.job_dir(re1), "job.json")))
        j0 = json.load(open(os.path.join(self.job_dir(job_none), "job.json")))
        for k in ("layer", "region", "prompt_subject", "layout", "alpha", "compose", "strength", "palette"):
            self.assertEqual(j1[k], j0[k], k)
        self.run_cli("apply", re1["job"], "--pick", 0, "--if-hash", "job", "--quiet")      # fresh scope: valid
        # default seed = previous seed + n; the layout file is not needed any more (the job kept a copy)
        os.remove(self.layout4)
        re2 = self.run_cli("generate", "--rerun", re1["job"], "--dry-run")
        self.assertEqual(json.load(open(os.path.join(self.job_dir(re2), "job.json")))["seed"], 41)
        # other inputs cannot be combined with --rerun
        e = self.run_cli("generate", "--rerun", jn, "--layer", "Ground", ok=False)
        self.assertEqual(e["code"], "bad_input")
        # structure: a new layer makes a job stale
        d = json.load(open(self.map))
        d["layers"].append(dict(d["layers"][0], id=99, name="Extra"))
        json.dump(d, open(self.map, "w"))
        st = self.run_cli("apply", re1["job"], "--pick", 0, "--if-hash", "job", ok=False)
        self.assertEqual(st["code"], "stale")
        self.assertTrue(any("structure" in r for r in st["reasons"]))

    def test_rerun_fill_and_variant_apply(self):
        open(self.layout4, "w").write("@ F = furniture #ddd5c4\nFF_F\n____\n_FF_\n")
        out = self.decor_gen("--seed", "2")
        res = self.run_cli("apply", out["job"], "--pick", 0, "--quiet")
        self.assertGreater(res["counts"]["cells_changed"], 0)
        self.assertNotIn("cells_changed", res)
        man = json.load(open(os.path.join(self.lib, "tiles.json")))
        self.assertIn("furniture", {t.get("material") for t in man["tiles"].values()})   # variant -> base material
        f = self.run_cli("fill", self.map, "--layer", "Ground", "--cells", "2,2;3,2", "--n", "1", "--palette", self.hex)
        f2 = self.run_cli("fill", "--rerun", f["job"], "--seed", "9")
        self.assertEqual(f2["candidates"][0]["seed"], 9)
        self.assertEqual(f2["rerun_of"], f["job"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
