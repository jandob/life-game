#!/usr/bin/env python3
"""Tests for tools/scenekit. Run: mise exec -- python3 tools/scenekit/test_scenekit.py

Each test runs the real CLI in a subprocess against a throw-away copy of the repo's assets (SCENEKIT_ROOT), so the
repository itself is never touched."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "mapgen"))
from PIL import Image  # noqa: E402

warnings.simplefilter("ignore", ResourceWarning)
SCENE = os.path.join(HERE, "scene.py")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="scenekit-test-")
        self.root = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.root, "assets", "maps"))
        shutil.copytree(os.path.join(REPO, "assets", "library", "tilesets", "forest"),
                        os.path.join(self.root, "assets", "library", "tilesets", "forest"))
        for n in ("sandbox", "forest"):
            shutil.copy(os.path.join(REPO, "assets", "maps", n + ".tmj"), os.path.join(self.root, "assets", "maps", n + ".tmj"))
        self.map = os.path.join(self.root, "assets", "maps", "work.tmj")
        shutil.copy(os.path.join(self.root, "assets", "maps", "sandbox.tmj"), self.map)
        self.env = dict(os.environ, SCENEKIT_ROOT=self.root, SCENEKIT_OUT=os.path.join(self.tmp, "out"))
        self.lib = os.path.join(self.root, "assets", "library", "tilesets", "gen")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args, ok=True):
        r = subprocess.run([sys.executable, SCENE, *map(str, args)], capture_output=True, text=True, env=self.env)
        try:
            out = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            self.fail(f"no JSON from {args}: stdout={r.stdout!r} stderr={r.stderr!r}")
        if ok:
            self.assertEqual(r.returncode, 0, out)
            self.assertTrue(out.get("ok"), out)
        else:
            self.assertNotEqual(r.returncode, 0, out)
            self.assertFalse(out.get("ok"), out)
        return out

    def snapshot(self):
        snap = {}
        for dp, _dn, fn in os.walk(self.root):
            for f in fn:
                p = os.path.join(dp, f)
                snap[p] = sha(p)
        return snap

    def cell_gid(self, x, y, layer=0, path=None):
        with open(path or self.map) as f:
            d = json.load(f)
        return d["layers"][layer]["data"][y * d["width"] + x]

    def px_ops(self, cell, colours, dy=3):
        cx, cy = cell
        return [{"px": [cx * 16 + 3 + i, cy * 16 + dy, c]} for i, c in enumerate(colours)]


class TestCompositor(Base):
    def test_flips_opacity_hidden_match_tmxrasterizer(self):
        sys.path.insert(0, HERE)
        d = json.load(open(self.map))
        w, h = d["width"], d["height"]
        # tile 97 (the flower) is asymmetric; put it in every flip combination on layer 2
        l2 = dict(d["layers"][0], id=10, name="Top", opacity=0.5)
        l2["data"] = [0] * (w * h)
        combos = [0, 0x80000000, 0x40000000, 0x20000000, 0xC0000000, 0xA0000000, 0x60000000, 0xE0000000]
        for i, f in enumerate(combos):
            l2["data"][2 * w + 2 + i] = (98 + 0) | f      # gid 98 = tileset local 97
            l2["data"][4 * w + 2 + i] = 6 | f             # tileset local 5 (house piece, alpha)
        l3 = dict(l2, id=11, name="Hidden", visible=False, opacity=1)
        l3["data"] = [10] * (w * h)
        l4 = dict(l2, id=12, name="Opaque", opacity=1)
        l4["data"] = [0] * (w * h)
        for i, f in enumerate(combos):
            l4["data"][6 * w + 2 + i] = 98 | f
        d["layers"] = d["layers"][:1] + [l2, l3, l4] + d["layers"][1:]
        d["nextlayerid"] = 20
        with open(self.map, "w") as f:
            json.dump(d, f)
        out = self.run_cli("render", self.map, "--check-tmx")
        self.assertEqual(out["check_tmx"]["differing_pixels"], 0, out)

    def test_real_maps(self):
        for n in ("sandbox", "forest"):
            out = self.run_cli("render", os.path.join(self.root, "assets", "maps", n + ".tmj"), "--check-tmx")
            self.assertEqual(out["check_tmx"]["differing_pixels"], 0)

    def test_render_overlays_and_region(self):
        out = os.path.join(self.tmp, "r.png")
        res = self.run_cli("render", self.map, "--region", "4,2,8,6", "--scale", 4, "--grid", "--ids", "--uses",
                           "--collision", "--material", "--out", out)
        self.assertEqual(res["region"], [4, 2, 8, 6])
        self.assertEqual(res["px_origin"], [64, 32])
        img = Image.open(out)
        self.assertEqual(img.size, (8 * 64 + 28, 6 * 64 + 28))
        res = self.run_cli("render", self.map, "--scale", 2, "--ids", "--out", out)
        self.assertIn("ids", res["legend"])


class TestLibrary(Base):
    def paint(self, cells_colours, *extra, ok=True):
        ops = []
        for cell, cols in cells_colours:
            ops += self.px_ops(cell, cols)
        return self.run_cli("edit", self.map, "--layer", "Ground", "--ops", json.dumps(ops), *extra, ok=ok)

    def test_three_pixel_edit_changes_exactly_one_cell(self):
        before = self.snapshot()
        res = self.paint([((1, 1), ["#ff0000", "#00ff00", "#0000ff"])])
        self.assertEqual([(c["x"], c["y"]) for c in res["cells_changed"]], [(1, 1)])
        self.assertEqual(res["tiles_new"], ["gen:0"])
        man = json.load(open(os.path.join(self.lib, "tiles.json")))
        self.assertTrue(man["tiles"]["0"]["parent"].startswith("tileset:"))
        self.assertEqual(man["tiles"]["0"]["origin"], "edit")
        after = self.snapshot()
        changed = {os.path.relpath(p, self.root) for p in after if before.get(p) != after[p]}
        self.assertEqual(changed, {"assets/maps/work.tmj", "assets/library/tilesets/gen/page-000.png",
                                   "assets/library/tilesets/gen/page-000.tsj", "assets/library/tilesets/gen/tiles.json"})
        self.assertEqual(before[os.path.join(self.root, "assets/maps/forest.tmj")], after[os.path.join(self.root, "assets/maps/forest.tmj")])
        d = json.load(open(self.map))
        self.assertEqual([t["firstgid"] for t in d["tilesets"]], [1, 257])
        diff = self.run_cli("diff", os.path.join(self.root, "assets/maps/sandbox.tmj"), self.map)
        self.assertEqual(diff["cells_changed"], 1)
        self.assertEqual(diff["pixels_changed"], 3)
        self.assertEqual(self.run_cli("library", "check")["problems"], [])

    def test_exact_dedup_and_batch_dedup(self):
        cols = ["#ff0000", "#00ff00"]
        # (6,5) and (7,5) are both tileset:16 grass; identical pixel edits make one new tile
        res = self.paint([((6, 5), cols), ((7, 5), cols)])
        self.assertEqual(len(res["tiles_new"]), 1)
        self.assertEqual(self.cell_gid(6, 5), self.cell_gid(7, 5))
        # painting a third cell identically later reuses the tile and appends nothing
        res = self.paint([((8, 5), cols)])
        self.assertEqual(res["tiles_new"], [])
        self.assertEqual(res["tiles_reused"], ["gen:0"])
        self.assertEqual(self.run_cli("library", "stats")["tiles"], 1)

    def test_near_dedup_only_when_requested(self):
        self.paint([((6, 5), ["#ff0000", "#00ff00"])])
        res = self.paint([((7, 5), ["#ff0000", "#00ff00", "#0000ff"])])      # one pixel more
        self.assertEqual(res["tiles_new"], ["gen:1"])
        # without --near that was a new tile; with --near 1 a one-pixel difference matches gen:0 or gen:1
        res = self.paint([((8, 5), ["#ff0000", "#00ff00", "#0000ee"])], "--near", "1")
        self.assertEqual(res["tiles_new"], [])
        self.assertEqual(len(res["near_matches"]), 1)
        self.assertEqual(res["near_matches"][0]["pixel_diff"], 1)

    def test_page_rollover(self):
        ops = []
        n = 257
        for i in range(n):
            ops.append({"px": [(2 + i % 16) * 16 + 4, (1 + i // 16) * 16 + 4, "#%02x%02x%02x" % (i % 256, i // 256 + 1, 9)]})
        # i // 16 goes up to 16 -> rows 1..17 do not fit a 15-row map; use two layers of cells instead
        ops = [{"px": [(i % 20) * 16 + 4, (i // 20) * 16 + 4, "#%02x%02x%02x" % (i % 256, i // 256 + 1, 9)]} for i in range(300)]
        res = self.run_cli("edit", self.map, "--layer", "Ground", "--ops", json.dumps(ops))
        self.assertEqual(len(res["tiles_new"]), 300)
        for f in ("page-000.png", "page-000.tsj", "page-001.png", "page-001.tsj"):
            self.assertTrue(os.path.isfile(os.path.join(self.lib, f)), f)
        for n_ in (0, 1):
            self.assertEqual(Image.open(os.path.join(self.lib, f"page-00{n_}.png")).size, (256, 256))
            tsj = json.load(open(os.path.join(self.lib, f"page-00{n_}.tsj")))
            self.assertEqual((tsj["tilecount"], tsj["columns"]), (256, 16))
        # tile 256 sits in slot 0 of page 1: its pixel (4,4) carries the colour of op 256
        p1 = Image.open(os.path.join(self.lib, "page-001.png")).convert("RGBA")
        self.assertEqual(p1.getpixel((4, 4))[:3], (0, 2, 9))
        d = json.load(open(self.map))
        self.assertEqual([t["firstgid"] for t in d["tilesets"]], [1, 257, 513])
        self.assertEqual(self.run_cli("library", "check")["tiles"], 300)
        self.assertEqual(self.run_cli("render", self.map, "--check-tmx")["check_tmx"]["differing_pixels"], 0)
        v = subprocess.run([sys.executable, os.path.join(HERE, "..", "mapgen", "tmj.py"), "validate", self.map],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(json.loads(v.stdout)["errors"], [], v.stdout)

    def test_existing_gids_never_shift_when_a_page_is_added(self):
        ops = [{"px": [(i % 20) * 16 + 4, (5 + i // 20) * 16 + 4, "#%02x%02x%02x" % (i, 1, 9)]} for i in range(200)]
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", json.dumps(ops))
        before = json.load(open(self.map))
        self.assertEqual([t["firstgid"] for t in before["tilesets"]], [1, 257])
        ops = [{"px": [(i % 20) * 16 + 4, (2 + i // 20) * 16 + 4, "#%02x%02x%02x" % (i, 2, 9)]} for i in range(60)]
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", json.dumps(ops))
        d = json.load(open(self.map))
        self.assertEqual([t["firstgid"] for t in d["tilesets"]], [1, 257, 513])
        self.assertEqual(before["layers"][0]["data"][20 * 5:], d["layers"][0]["data"][20 * 5:])

    def test_flips_kept_for_unchanged_cells(self):
        d = json.load(open(self.map))
        d["layers"][0]["data"][2 * 20 + 2] = 98 | 0x80000000
        json.dump(d, open(self.map, "w"))
        self.paint([((8, 8), ["#ff0000"])])
        self.assertEqual(self.cell_gid(2, 2), 98 | 0x80000000)

    def test_library_check_detects_corruption(self):
        self.paint([((1, 1), ["#ff0000"])])
        p = os.path.join(self.lib, "page-000.png")
        img = Image.open(p).convert("RGBA")
        img.putpixel((0, 0), (1, 2, 3, 255))
        img.save(p)
        res = self.run_cli("library", "check", ok=False)
        self.assertTrue(any("gen:0" in x for x in res["problems"]), res)
        Image.new("RGBA", (128, 128)).save(p)
        res = self.run_cli("library", "check", ok=False)
        self.assertTrue(any("128x128" in x for x in res["problems"]), res)


class TestIndexAndInspect(Base):
    def test_where_and_cells(self):
        res = self.run_cli("where", "tileset:16")
        self.assertGreater(res["count"], 1000)
        self.assertEqual(res["maps"], ["assets/maps/forest.tmj", "assets/maps/sandbox.tmj", "assets/maps/work.tmj"])
        res = self.run_cli("where", "tileset:16", "--maps", "assets/maps/forest.tmj,assets/maps/sandbox.tmj")
        self.assertEqual(res["maps"], ["assets/maps/forest.tmj", "assets/maps/sandbox.tmj"])
        cells = self.run_cli("cells", self.map, "--region", "1,1,1,1")
        c = cells["layers"][0]["cells"][0][0]
        self.assertEqual(c["tile"], "tileset:16")
        self.assertGreaterEqual(c["uses"]["maps"], 2)
        self.assertEqual(self.run_cli("where", "gen:0")["count"], 0)

    def test_index_sees_hand_edits(self):
        d = json.load(open(self.map))
        d["layers"][0]["data"][5 * 20 + 5] = 98
        json.dump(d, open(self.map, "w"))
        uses = self.run_cli("where", "tileset:97", "--maps", "assets/maps/work.tmj")["uses"]
        self.assertIn({"map": "assets/maps/work.tmj", "layer": "Ground", "x": 5, "y": 5, "flip": ""}, uses)

    def test_flip_masked_in_index(self):
        d = json.load(open(self.map))
        d["layers"][0]["data"][5 * 20 + 6] = 98 | 0xC0000000
        json.dump(d, open(self.map, "w"))
        uses = self.run_cli("where", "tileset:97", "--maps", "assets/maps/work.tmj")["uses"]
        self.assertTrue(any(u["x"] == 6 and u["flip"] == "hv" for u in uses), uses)

    def test_diff_git_is_read_only(self):
        before = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True).stdout
        env = dict(self.env, SCENEKIT_ROOT=REPO)
        r = subprocess.run([sys.executable, SCENE, "diff", "git:HEAD:assets/maps/sandbox.tmj", "assets/maps/sandbox.tmj"],
                           capture_output=True, text=True, env=env)
        out = json.loads(r.stdout)
        self.assertEqual(out["cells_changed"], 0, out)
        after = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True).stdout
        self.assertEqual(before, after)


class TestRoundTrip(Base):
    def test_unchanged_roundtrip_is_byte_identical(self):
        png = os.path.join(self.tmp, "x.png")
        self.run_cli("export", self.map, "--region", "2,2,8,5", "--layer", "Ground", "--out", png)
        before = self.snapshot()
        res = self.run_cli("import", png)
        self.assertEqual(res["tiles_new"], [])
        self.assertEqual(before, self.snapshot())

    def test_two_identical_changes_make_one_tile(self):
        png = os.path.join(self.tmp, "x.png")
        self.run_cli("export", self.map, "--region", "6,5,4,2", "--layer", "Ground", "--out", png)
        img = Image.open(png).convert("RGBA")
        for cx in (0, 2):
            for i in range(10):
                img.putpixel((cx * 16 + i, 7), (250, 0, 250, 255))
        img.save(png)
        res = self.run_cli("import", png)
        self.assertEqual(len(res["tiles_new"]), 1)
        self.assertEqual(self.cell_gid(6, 5), self.cell_gid(8, 5))
        self.assertEqual(len(res["cells_changed"]), 2)

    def test_import_conflict(self):
        png = os.path.join(self.tmp, "x.png")
        self.run_cli("export", self.map, "--region", "3,3,2,2", "--layer", "Ground", "--out", png)
        img = Image.open(png).convert("RGBA")
        img.putpixel((1, 1), (250, 0, 250, 255))
        img.save(png)
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[50,50,"#00ff00"]}]')  # cell (3,3)
        before = self.snapshot()
        res = self.run_cli("import", png, ok=False)
        self.assertEqual(res["code"], "conflict")
        self.assertEqual(before, self.snapshot())
        self.run_cli("import", png, "--force")

    def test_composite_needs_flatten(self):
        png = os.path.join(self.tmp, "c.png")
        self.run_cli("export", self.map, "--region", "3,3,2,2", "--composite", "--out", png)
        res = self.run_cli("import", png, ok=False)
        self.assertEqual(res["code"], "bad_input")

    def test_flatten_composite(self):
        d = json.load(open(self.map))
        w, h = d["width"], d["height"]
        top = dict(d["layers"][0], id=10, name="Decor")
        top["data"] = [0] * (w * h)
        top["data"][3 * w + 3] = 98      # flower over grass
        d["layers"].insert(1, top)
        json.dump(d, open(self.map, "w"))
        png = os.path.join(self.tmp, "c.png")
        self.run_cli("export", self.map, "--region", "3,3,2,1", "--composite", "--out", png)
        img = Image.open(png).convert("RGBA")
        img.putpixel((1, 1), (250, 0, 250, 255))
        img.save(png)
        res = self.run_cli("import", png, "--flatten-into", "Ground")
        self.assertEqual(res["cleared"], [{"layer": "Decor", "x": 3, "y": 3, "old": "tileset:97"}])
        self.assertEqual(self.cell_gid(3, 3, 1), 0)


class TestGlobalAndMeta(Base):
    def test_global_edit_needs_expect_uses(self):
        cols = ["#ff0000", "#00ff00"]
        ops = json.dumps([{"px": [6 * 16 + 1, 5 * 16 + 1, cols[0]]}, {"px": [7 * 16 + 1, 5 * 16 + 1, cols[0]]}])
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", ops)     # gen:0 at (6,5) and (7,5)
        # a second map also uses gen:0
        other = os.path.join(self.root, "assets", "maps", "other.tmj")
        shutil.copy(self.map, other)
        before = self.snapshot()
        res = self.run_cli("edit", self.map, "--layer", "Ground", "--global", "--ops",
                           json.dumps([{"px": [6 * 16 + 5, 5 * 16 + 5, "#101010"]}, {"px": [7 * 16 + 5, 5 * 16 + 5, "#101010"]}]),
                           ok=False)
        self.assertEqual(res["code"], "impact")
        self.assertEqual(res["total"], 4)
        self.assertEqual(len(res["uses"]), 4)
        self.assertEqual(before, self.snapshot())
        res = self.run_cli("edit", self.map, "--layer", "Ground", "--global", "--expect-uses", 3, "--ops",
                           json.dumps([{"px": [6 * 16 + 5, 5 * 16 + 5, "#101010"]}, {"px": [7 * 16 + 5, 5 * 16 + 5, "#101010"]}]),
                           ok=False)
        self.assertEqual(res["code"], "impact")
        self.assertEqual(before, self.snapshot())
        res = self.run_cli("edit", self.map, "--layer", "Ground", "--global", "--expect-uses", 4, "--ops",
                           json.dumps([{"px": [6 * 16 + 5, 5 * 16 + 5, "#101010"]}, {"px": [7 * 16 + 5, 5 * 16 + 5, "#101010"]}]))
        self.assertEqual(res["global"][0]["total"], 4)
        man = json.load(open(os.path.join(self.lib, "tiles.json")))
        self.assertEqual(len(man["tiles"]["0"]["revisions"]), 1)
        self.assertEqual(self.run_cli("library", "check")["problems"], [])
        # the other map shares the tile, so it shows the new pixels without its file being touched
        self.assertEqual(before[other], sha(other))

    def test_global_refuses_foreign(self):
        res = self.run_cli("edit", self.map, "--layer", "Ground", "--global", "--expect-uses", 1, "--ops",
                           '[{"px":[20,20,"#ff0000"]}]', ok=False)
        self.assertEqual(res["code"], "refused")

    def test_global_different_pixels_fail(self):
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops",
                     json.dumps([{"px": [6 * 16 + 1, 5 * 16 + 1, "#ff0000"]}, {"px": [7 * 16 + 1, 5 * 16 + 1, "#ff0000"]}]))
        res = self.run_cli("edit", self.map, "--layer", "Ground", "--global", "--expect-uses", 2, "--ops",
                           json.dumps([{"px": [6 * 16 + 5, 5 * 16 + 5, "#101010"]}, {"px": [7 * 16 + 5, 5 * 16 + 5, "#202020"]}]),
                           ok=False)
        self.assertEqual(res["code"], "bad_input")

    def test_tile_edit(self):
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[20,20,"#ff0000"]}]')
        res = self.run_cli("tile", "edit", "gen:0", "--ops", '[{"px":[0,0,"#abcdef"]}]', ok=False)
        self.assertEqual(res["code"], "impact")
        self.run_cli("tile", "edit", "gen:0", "--ops", '[{"px":[0,0,"#abcdef"]}]', "--expect-uses", 1)
        self.assertEqual(self.run_cli("library", "check")["problems"], [])

    def test_collide_region_forks_shared_tile_and_materials(self):
        # rows 0-1 of the sandbox: row 0 is water-ish wall (tileset:10, collision already) and row 1 is grass (16)
        res = self.run_cli("material", "region", self.map, "--layer", "Ground", "--region", "1,1,4,1", "floor")
        self.assertEqual(res["forked"][0]["from"], "tileset:16")
        gid = self.cell_gid(1, 1)
        self.assertEqual(self.cell_gid(2, 1), gid)
        self.assertEqual(self.cell_gid(5, 1), 17)        # untouched grass outside the region
        res = self.run_cli("collide", "region", self.map, "--layer", "Ground", "--region", "1,1,4,1", "--shape", "full")
        self.assertEqual(res["in_place"], ["gen:0"])      # only used inside the region now
        cells = self.run_cli("cells", self.map, "--region", "1,1,2,1")["layers"][0]["cells"][0]
        self.assertTrue(cells[0]["collision"])
        self.assertEqual(cells[0]["material"], "floor")
        tsj = json.load(open(os.path.join(self.lib, "page-000.tsj")))
        self.assertEqual(tsj["tiles"][0]["objectgroup"]["objects"][0]["width"], 16)
        # the hand-made tileset was never touched
        self.assertEqual(sha(os.path.join(self.root, "assets/library/tilesets/forest/tileset.tsj")),
                         sha(os.path.join(REPO, "assets/library/tilesets/forest/tileset.tsj")))
        # same pixels with different metadata is a separate tile (meta_variant), and dedup honours metadata
        res = self.run_cli("material", "region", self.map, "--layer", "Ground", "--region", "6,1,2,1", "wall")
        self.assertEqual(len(res["forked"]), 1)
        self.assertEqual(res["forked"][0]["status"], "meta_variant")      # same pixels as gen:0, other metadata
        self.assertEqual(self.run_cli("library", "check")["problems"], [])

    def test_wall_band_scenario(self):
        res = self.run_cli("material", "region", self.map, "--layer", "Ground", "--region", "0,0,20,1", "wall")
        # tileset:10 is used outside the band (sides and bottom), so it was forked for the band's cells
        self.assertTrue(any(f["from"] == "tileset:10" for f in res["forked"]))
        cells = self.run_cli("cells", self.map, "--region", "0,0,2,1")["layers"][0]["cells"][0]
        self.assertEqual(cells[0]["material"], "wall")
        self.assertTrue(cells[0]["collision"])

    def test_collide_tile_needs_expect_uses(self):
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[20,20,"#ff0000"]}]')
        res = self.run_cli("collide", "tile", "gen:0", "--shape", "bottom", ok=False)
        self.assertEqual(res["code"], "impact")
        self.run_cli("collide", "tile", "gen:0", "--shape", "bottom", "--expect-uses", 1)
        cells = self.run_cli("cells", self.map, "--region", "1,1,1,1")["layers"][0]["cells"][0]
        self.assertTrue(cells[0]["collision"])
        res = self.run_cli("collide", "tile", "tileset:16", "--shape", "full", "--expect-uses", 1, ok=False)
        self.assertEqual(res["code"], "refused")


class TestSafety(Base):
    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        res = self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[20,20,"#ff0000"]}]', "--dry-run")
        self.assertTrue(res["dry_run"])
        self.assertEqual(len(res["changed_files"]), 4)
        self.assertEqual(before, self.snapshot())

    def test_if_hash_stale(self):
        h = self.run_cli("cells", self.map, "--region", "0,0,1,1")["map_hash"]
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[20,20,"#ff0000"]}]', "--if-hash", h)
        before = self.snapshot()
        res = self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[40,40,"#ff0000"]}]', "--if-hash", h, ok=False)
        self.assertEqual(res["code"], "stale")
        self.assertEqual(before, self.snapshot())

    def test_undo_restores_and_refuses_after_hand_edit(self):
        orig = sha(self.map)
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[20,20,"#ff0000"]}]')
        self.assertNotEqual(sha(self.map), orig)
        res = self.run_cli("undo")
        self.assertEqual(sha(self.map), orig)
        self.assertFalse(os.path.exists(os.path.join(self.lib, "page-000.png")))
        self.assertEqual(len(res["restored"]), 4)
        # now a hand edit between the command and the undo
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[20,20,"#ff0000"]}]')
        d = json.load(open(self.map))
        d["layers"][0]["data"][0] = 98
        json.dump(d, open(self.map, "w"))
        before = self.snapshot()
        res = self.run_cli("undo", ok=False)
        self.assertEqual(res["code"], "refused")
        self.assertIn("assets/maps/work.tmj", res["error"])
        self.assertEqual(before, self.snapshot())

    def test_undo_two_steps(self):
        orig = sha(self.map)
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[20,20,"#ff0000"]}]')
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[60,60,"#00ff00"]}]')
        self.run_cli("undo")
        self.assertEqual(self.run_cli("library", "stats")["tiles"], 1)
        self.run_cli("undo")
        self.assertEqual(sha(self.map), orig)

    def test_lock_blocks_concurrent_write(self):
        os.makedirs(self.lib, exist_ok=True)
        with open(os.path.join(self.lib, ".lock"), "w") as f:
            f.write("{}")
        before = self.snapshot()
        res = self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[20,20,"#ff0000"]}]', ok=False)
        self.assertEqual(res["code"], "locked")
        after = self.snapshot()
        self.assertEqual({k: v for k, v in before.items()}, {k: v for k, v in after.items() if k in before})

    def test_bad_ops_write_nothing(self):
        before = self.snapshot()
        res = self.run_cli("edit", self.map, "--layer", "Ground", "--ops",
                           '[{"px":[20,20,"#ff0000"]},{"rect":[0,0,9999,4,"#000000"]}]', ok=False)
        self.assertEqual(res["code"], "bad_input")
        self.assertEqual(before, self.snapshot())


class TestOps(Base):
    def test_all_ops(self):
        sys.path.insert(0, HERE)
        from editcore import apply_pixel_ops
        img = Image.new("RGBA", (32, 32), (10, 20, 30, 255))
        pal = os.path.join(self.tmp, "p.hex")
        open(pal, "w").write("000000\nffffff\n")
        ops = [{"rect": [0, 0, 4, 4, "#ff0000"]}, {"line": [0, 31, 31, 31, "#ffff00"]},
               {"copy": {"from": [0, 0, 4, 4], "to": [8, 8]}},
               {"replace": {"from": "#ff0000", "to": "#0000ff", "region": [0, 0, 16, 16]}},
               {"remap": {"map": {"#0000ff": "#123456"}}},
               {"px": [31, 0, "#00000000"]}]
        out = apply_pixel_ops(img, ops, self.tmp)
        self.assertEqual(out.getpixel((1, 1)), (0x12, 0x34, 0x56, 255))
        self.assertEqual(out.getpixel((9, 9)), (0x12, 0x34, 0x56, 255))
        self.assertEqual(out.getpixel((15, 31)), (255, 255, 0, 255))
        self.assertEqual(out.getpixel((31, 0))[3], 0)
        out = apply_pixel_ops(out, [{"quantize": {"palette": pal}}], self.tmp)
        self.assertEqual(out.getpixel((1, 1))[:3], (0, 0, 0))
        self.assertEqual(out.getpixel((15, 31))[:3], (255, 255, 255))
        src = os.path.join(self.tmp, "s.png")
        Image.new("RGBA", (2, 2), (255, 0, 0, 128)).save(src)
        out = apply_pixel_ops(Image.new("RGBA", (8, 8), (0, 0, 255, 255)), [{"paste": {"at": [1, 1], "image": src, "mode": "over"}}])
        self.assertEqual(out.getpixel((1, 1)), (128, 0, 127, 255))
        out = apply_pixel_ops(Image.new("RGBA", (8, 8), (0, 0, 255, 255)), [{"paste": {"at": [1, 1], "image": src, "mode": "replace"}}])
        self.assertEqual(out.getpixel((1, 1)), (255, 0, 0, 128))

    def test_transparent_cell_becomes_empty(self):
        ops = json.dumps([{"rect": [16, 16, 16, 16, "#00000000"]}])
        res = self.run_cli("edit", self.map, "--layer", "Ground", "--ops", ops)
        self.assertEqual(self.cell_gid(1, 1), 0)
        self.assertEqual(res["tiles_new"], [])


class TestValidate(Base):
    def validate(self):
        v = subprocess.run([sys.executable, os.path.join(HERE, "..", "mapgen", "tmj.py"), "validate", self.map, "--no-tiled"],
                           capture_output=True, text=True, env=self.env)
        return json.loads(v.stdout)

    def test_valid_after_edit(self):
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[20,20,"#ff0000"]}]')
        self.assertEqual(self.validate()["errors"], [])

    def test_missing_manifest_entry_page_size_and_above(self):
        self.run_cli("edit", self.map, "--layer", "Ground", "--ops", '[{"px":[20,20,"#ff0000"]}]')
        man_p = os.path.join(self.lib, "tiles.json")
        man = json.load(open(man_p))
        man["tiles"] = {}
        json.dump(man, open(man_p, "w"))
        errs = self.validate()["errors"]
        self.assertTrue(any("gen:0" in e and "manifest" in e for e in errs), errs)
        Image.new("RGBA", (128, 128)).save(os.path.join(self.lib, "page-000.png"))
        errs = self.validate()["errors"]
        self.assertTrue(any("256x256" in e for e in errs), errs)
        d = json.load(open(self.map))
        d["layers"][0]["properties"] = [{"name": "above", "type": "string", "value": "yes"}]
        json.dump(d, open(self.map, "w"))
        errs = self.validate()["errors"]
        self.assertTrue(any("'above' must be a bool" in e for e in errs), errs)


class TestFeedbackFixes(Base):
    """Section 5: --quiet, --if-hash auto, tiles_updated."""

    def paint(self, cell, colour, *extra, ok=True):
        return self.run_cli("edit", self.map, "--layer", "Ground", "--ops", json.dumps(self.px_ops(cell, [colour])), *extra, ok=ok)

    def test_quiet_keeps_summary_only(self):
        full = self.paint((1, 1), "#ff0000", "--dry-run")
        self.assertIn("cells_changed", full)
        q = self.paint((1, 1), "#ff0000", "--quiet", "--dry-run")
        self.assertTrue(q["quiet"])
        for k in ("cells_changed", "tiles_new", "tiles_reused", "near_matches"):
            self.assertNotIn(k, q)
        self.assertEqual(q["counts"]["cells_changed"], 1)
        self.assertEqual(q["counts"]["tiles_new"], 1)
        for k in ("map_hash", "map_hash_before", "changed_files"):
            self.assertIn(k, q)

    def test_if_hash_auto_follows_own_journal_and_refuses_foreign_edits(self):
        # no write by the tool yet: nothing to trust
        e = self.paint((1, 1), "#ff0000", "--if-hash", "auto", ok=False)
        self.assertEqual(e["code"], "stale")
        r1 = self.paint((1, 1), "#ff0000")
        # chained writes with no hash bookkeeping
        r2 = self.paint((2, 1), "#00ff00", "--if-hash", "auto", "--quiet")
        r3 = self.paint((3, 1), "#0000ff", "--if-hash", "auto", "--quiet")
        self.assertEqual(r2["map_hash_before"], r1["map_hash"])
        self.assertEqual(r3["map_hash_before"], r2["map_hash"])
        # undo is the tool's own write too: the file is back at the hash before r3
        self.run_cli("undo")
        self.paint((3, 1), "#0000ff", "--if-hash", "auto", "--quiet")
        # a hand edit (as Tiled would do) is refused, exactly like a stale explicit hash
        d = json.load(open(self.map))
        d["layers"][0]["data"][0] = d["layers"][0]["data"][1]
        json.dump(d, open(self.map, "w"), indent=1)
        before = sha(self.map)
        e = self.paint((4, 1), "#ffff00", "--if-hash", "auto", ok=False)
        self.assertEqual(e["code"], "stale")
        self.assertEqual(e["map_hash"], "sha256:" + before)
        self.assertEqual(sha(self.map), before)
        e2 = self.paint((4, 1), "#ffff00", "--if-hash", "sha256:" + "0" * 64, ok=False)
        self.assertEqual(e2["code"], "stale")
        # after the human looked, an explicit hash works again and auto follows from that write
        self.paint((4, 1), "#ffff00", "--if-hash", "sha256:" + before, "--quiet")
        self.paint((5, 1), "#ffff00", "--if-hash", "auto", "--quiet")

    def test_tiles_updated_reported_next_to_cells_changed(self):
        self.paint((1, 1), "#ff0000")                  # a gen tile used once
        res = self.run_cli("collide", "region", self.map, "--layer", "Ground", "--region", "1,1,1,1", "--shape", "full")
        self.assertEqual(res["counts"]["cells_changed"], 0)
        self.assertEqual(res["counts"]["tiles_updated"], 1)
        self.assertEqual(len(res["tiles_updated"]), 1)
        self.assertTrue(res["tiles_updated"][0].startswith("gen:"))
        again = self.run_cli("collide", "region", self.map, "--layer", "Ground", "--region", "1,1,1,1", "--shape", "full")
        self.assertEqual(again["counts"]["tiles_updated"], 0)          # already that shape
        # a hand-made tile is forked instead: a cell changes, no tile is updated in place
        res = self.run_cli("material", "region", self.map, "--layer", "Ground", "--region", "6,6,1,1", "wall", "--quiet")
        self.assertEqual(res["counts"]["cells_changed"], 1)
        self.assertEqual(res["counts"]["tiles_updated"], 0)
        self.assertNotIn("cells_changed", res)
        key = self.run_cli("cells", self.map, "--region", "1,1,1,1")["layers"][0]["cells"][0][0]["tile"]
        t = self.run_cli("collide", "tile", key, "--shape", "none", "--expect-uses", 1)
        self.assertEqual(t["tiles_updated"], [key])
        self.assertEqual(t["counts"]["tiles_updated"], 1)


class TestTile48(Base):
    """48 px library `gen48`: tile size from the library manifest, library chosen by the map, validate refuses mixed sizes."""

    def setUp(self):
        super().setUp()
        self.lib48 = os.path.join(self.root, "assets", "library", "tilesets", "gen48")
        shutil.copytree(os.path.join(REPO, "assets", "library", "tilesets", "gen48"), self.lib48)
        self.map48 = os.path.join(self.root, "assets", "maps", "work48.tmj")
        self.tmj("new", self.map48, "--width", 6, "--height", 5, "--tile", 48, "--tileset", os.path.join(self.lib48, "page-000.tsj"))

    def tmj(self, *args, ok=True):
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "mapgen", "tmj.py"), *map(str, args)],
                           capture_output=True, text=True, env=self.env)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(r.returncode == 0, ok, out)
        return out

    def ops(self, cell, colours, dy=5):
        cx, cy = cell
        return [{"px": [cx * 48 + 5 + i, cy * 48 + dy, c]} for i, c in enumerate(colours)]

    def test_shipped_library_is_48(self):
        out = self.run_cli("library", "check", "--lib", "gen48")
        self.assertEqual(out["problems"], [])
        man = json.load(open(os.path.join(REPO, "assets", "library", "tilesets", "gen48", "tiles.json")))
        self.assertEqual(man["tile_size"], 48)
        ts = json.load(open(os.path.join(REPO, "assets", "library", "tilesets", "gen48", "page-000.tsj")))
        self.assertEqual((ts["tilewidth"], ts["tileheight"], ts["imagewidth"], ts["imageheight"]), (48, 48, 768, 768))
        self.assertEqual(Image.open(os.path.join(REPO, "assets", "library", "tilesets", "gen48", "page-000.png")).size, (768, 768))

    def test_edit_collide_render_check_tmx(self):
        # the library is picked from the map's tile size (no --lib)
        ops = self.ops((1, 1), ["#ff0000", "#00ff00"]) + [{"rect": [96, 48, 48, 48, "#3355aa"]}]
        res = self.run_cli("edit", self.map48, "--layer", "Ground", "--ops", json.dumps(ops))
        self.assertEqual(sorted((c["x"], c["y"]) for c in res["cells_changed"]), [(1, 1), (2, 1)])
        man = json.load(open(os.path.join(self.lib48, "tiles.json")))
        self.assertEqual(man["next_id"], 2)
        page = Image.open(os.path.join(self.lib48, "page-000.png"))
        self.assertEqual(page.size, (768, 768))
        self.assertEqual(page.getpixel((5, 5))[:3], (255, 0, 0))
        self.run_cli("collide", "region", self.map48, "--layer", "Ground", "--region", "2,1,1,1", "--shape", "bottom")
        tsj = json.load(open(os.path.join(self.lib48, "page-000.tsj")))
        o = [e for e in tsj["tiles"] if "objectgroup" in e][0]["objectgroup"]["objects"][0]
        self.assertEqual((o["x"], o["y"], o["width"], o["height"]), (0, 24, 48, 24))
        self.run_cli("collide", "region", self.map48, "--layer", "Ground", "--region", "2,1,1,1", "--shape", "full")
        tsj = json.load(open(os.path.join(self.lib48, "page-000.tsj")))
        o = [e for e in tsj["tiles"] if "objectgroup" in e][0]["objectgroup"]["objects"][0]
        self.assertEqual((o["x"], o["y"], o["width"], o["height"]), (0, 0, 48, 48))
        out = os.path.join(self.tmp, "r48.png")
        res = self.run_cli("render", self.map48, "--check-tmx", "--collision", "--out", out)
        self.assertEqual(res["check_tmx"]["differing_pixels"], 0, res)
        res = self.run_cli("render", self.map48, "--scale", 2, "--out", out)
        self.assertEqual(Image.open(out).size, (6 * 48 * 2, 5 * 48 * 2))
        self.run_cli("library", "check", "--lib", "gen48")
        self.tmj("layer", self.map48, "add", "Spawn", "--type", "object")
        self.tmj("object", self.map48, "--layer", "Spawn", "add", "--name", "SpawnPoint", "--tile", 0, 0)
        v = self.tmj("validate", self.map48, "--no-tiled")
        self.assertTrue(v["ok"], v)

    def test_tile_size_mismatch_is_refused(self):
        out = self.run_cli("render", self.map48, "--lib", "gen", "--out", os.path.join(self.tmp, "x.png"), ok=False)
        self.assertEqual(out["code"], "mismatch", out)
        out = self.run_cli("render", self.map, "--lib", "gen48", "--out", os.path.join(self.tmp, "x.png"), ok=False)
        self.assertEqual(out["code"], "mismatch", out)
        self.run_cli("render", self.map, "--out", os.path.join(self.tmp, "x.png"))  # 16 px map still picks the 16 px library

    def test_generate_dry_run_canvas_is_48_per_cell(self):
        lay = os.path.join(self.tmp, "lay.txt")
        with open(lay, "w") as f:
            f.write("..\n.#\n")
        res = self.run_cli("generate", self.map48, "--layer", "Ground", "--region", "1,1,2,2", "--layout", lay,
                           "--prompt", "wood floor", "--dry-run", "--context", 0)
        self.assertEqual(res["scale"], 8)                       # 96 art px x 8 = 768 raw px
        with Image.open(res["canvas"]) as im:
            self.assertEqual(im.size, (96 * 8, 96 * 8))

    def test_export_is_48_px_per_cell(self):
        self.run_cli("edit", self.map48, "--layer", "Ground", "--ops", json.dumps(self.ops((0, 0), ["#ff0000"])))
        png = os.path.join(self.tmp, "e.png")
        self.run_cli("export", self.map48, "--region", "0,0,1,1", "--layer", "Ground", "--out", png)
        self.assertEqual(Image.open(png).size, (48, 48))

    def test_validate_rejects_mixed_tile_sizes(self):
        forest = os.path.join(self.root, "assets", "library", "tilesets", "forest")
        tsj = [f for f in os.listdir(forest) if f.endswith(".tsj")][0]
        d = json.load(open(self.map48))
        d["tilesets"].append({"firstgid": 257, "source": os.path.relpath(os.path.join(forest, tsj), os.path.dirname(self.map48))})
        with open(self.map48, "w") as f:
            json.dump(d, f)
        v = self.tmj("validate", self.map48, "--no-tiled", ok=False)
        self.assertTrue(any("mixes tile sizes" in e for e in v["errors"]), v)


class TestRecipes(Base):
    """`recipe` prints plans (nothing runs); `texture roll|seam|size` are local image helpers."""

    def test_texture_recipe(self):
        for size, raw in ((48, 384), (96, 768)):
            out = self.run_cli("recipe", "texture", "--name", "oak", "--kind", "floor", "--size", size, "--prompt", "oak planks")
            self.assertEqual((out["canvas_px"], out["grid"]), ([raw, raw], 8))
            steps = {st["step"]: st for st in out["steps"]}
            self.assertIn(f"--width {raw} --height {raw}", steps["generate"]["cmd"])
            self.assertIn("anime style pixel art, thick dark outlines, flat cel shading with two tones", steps["generate"]["cmd"])
            self.assertIn("--factor 8", steps["snap"]["cmd"])
            self.assertIn("interior.hex", steps["snap"]["cmd"])
        self.run_cli("recipe", "texture", "--name", "x", "--size", 64, "--prompt", "p", ok=False)

    def test_prop_recipe_sizes_and_grid(self):
        out = self.run_cli("recipe", "prop", "--name", "sofa", "--size", "100,60", "--prompt", "sofa")
        self.assertEqual(out["grid"], 8)
        self.assertEqual(out["canvas_px"], [832, 512])     # (100+4)*8 and (60+4)*8, multiples of 16
        self.assertEqual(out["warnings"], [])
        self.assertIn("--grid 8", [st for st in out["steps"] if st["step"] == "post"][0]["cmd"])
        out = self.run_cli("recipe", "prop", "--name", "bed", "--size", "104,148", "--prompt", "bed")
        self.assertLess(out["grid"], 8)
        self.assertTrue(out["warnings"])
        self.assertLessEqual(max(out["canvas_px"]), 1024)
        out = self.run_cli("recipe", "prop", "--name", "bed", "--size", "104,148", "--grid", 8, "--prompt", "bed", ok=False)
        self.assertEqual(out["code"], "too_large")

    def test_texture_helpers(self):
        img = Image.new("RGB", (48, 48))
        for y in range(48):
            for x in range(48):
                img.putpixel((x, y), (100 + (x % 8) * 10, 80 + (y % 8) * 10, 60))   # period 8 divides 48: repeats cleanly
        a, b, c = (os.path.join(self.tmp, n) for n in ("t.png", "r.png", "bad.png"))
        img.save(a)
        res = self.run_cli("texture", "seam", a)
        self.assertLessEqual(max(res["seam_ratio"].values()), 1.5, res)
        self.run_cli("texture", "roll", a, "--out", b)
        self.assertEqual(Image.open(b).convert("RGB").getpixel((24, 24)), img.getpixel((0, 0)))
        ramp = Image.new("RGB", (48, 48))
        for y in range(48):
            for x in range(48):
                ramp.putpixel((x, y), (x * 5, y * 5, 0))                                  # a ramp does not wrap
        ramp.save(c)
        self.assertEqual(self.run_cli("texture", "seam", c, ok=False)["code"], "check_failed")
        sp = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
        sp.paste((255, 0, 0, 255), (5, 4, 25, 20))
        sp.save(a)
        self.assertEqual(self.run_cli("texture", "size", a)["opaque_wh"], [20, 16])


class TestMapgenPolyline(Base):
    """tmj.py object add --polyline: stored the Tiled way, listed in absolute pixels, bounds-checked by validate."""

    def tmj(self, *args, ok=True):
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "mapgen", "tmj.py"), *map(str, args)],
                           capture_output=True, text=True)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(r.returncode == 0, ok, out)
        self.assertEqual(bool(out.get("ok")), ok, out)
        return out

    def test_add_polyline(self):
        self.tmj("layer", self.map, "add", "Paths", "--type", "object")
        out = self.tmj("object", self.map, "--layer", "Paths", "add", "--name", "Walk",
                       "--polyline", "40,56 40,24 72.5,24")
        self.assertEqual(out["object"]["polyline"], [[40, 56], [40, 24], [72.5, 24]])
        with open(self.map) as f:
            o = [l for l in json.load(f)["layers"] if l["name"] == "Paths"][0]["objects"][0]
        self.assertEqual((o["x"], o["y"], o["width"], o["height"]), (40, 56, 0, 0))
        self.assertEqual(o["polyline"], [{"x": 0, "y": 0}, {"x": 0, "y": -32}, {"x": 32.5, "y": -32}])
        self.assertNotIn("point", o)
        listed = self.tmj("object", self.map, "--layer", "Paths", "list")["objects"][0]
        self.assertEqual(listed["polyline"], [[40, 56], [40, 24], [72.5, 24]])
        self.tmj("validate", self.map, "--no-tiled")

    def test_bad_polyline_writes_nothing(self):
        self.tmj("layer", self.map, "add", "Paths", "--type", "object")
        before = sha(self.map)
        self.tmj("object", self.map, "--layer", "Paths", "add", "--name", "A", "--polyline", "1,2", ok=False)
        self.tmj("object", self.map, "--layer", "Paths", "add", "--name", "A", "--polyline", "1,2 x", ok=False)
        self.tmj("object", self.map, "--layer", "Paths", "add", "--name", "A", "--polyline", "1,2 3,4",
                 "--px", "1", "2", ok=False)
        self.assertEqual(sha(self.map), before)

    def test_validate_flags_vertex_outside_map(self):
        self.tmj("layer", self.map, "add", "Paths", "--type", "object")
        self.tmj("object", self.map, "--layer", "Paths", "add", "--name", "Out", "--polyline", "8,8 99999,8")
        out = self.tmj("validate", self.map, "--no-tiled", ok=False)
        self.assertTrue(any("polyline vertex" in e for e in out["errors"]), out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
