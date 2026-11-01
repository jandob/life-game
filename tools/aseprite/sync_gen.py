"""Create or update the `gen` layer of the game's .aseprite files from generated strips.

The game loads .aseprite files directly (bevy_aseprite_ultra). Each file has two layers:
  gen    the generated pixels (locked), written only by this script
  paint  hand edits on top, never touched by this script
Regenerating art therefore never clobbers hand edits. A frame whose gen cel carries the user data
text `frozen` (cel properties in Aseprite) is skipped, for frames where gen itself was hand-edited.

Usage (no Aseprite needed):
  python tools/aseprite/sync_gen.py            create missing files, refresh gen layers
  python tools/aseprite/sync_gen.py --check    exit 1 if any file is missing or its gen layer is stale
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).parent))
import asefile  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CELL = (128, 256)  # src/look.rs LOOK_CELL
GEN, PAINT = 0, 1
LAYERS = [("gen", asefile.LAYER_VISIBLE), ("paint", asefile.LAYER_VISIBLE | asefile.LAYER_EDITABLE)]
IDLE_MS = 1000
WALK_MS = 140


@dataclass
class TagSpec:
    name: str  # "<clip>_<facing>", as src/look.rs expects
    file: str  # strip in the gen folder
    row: int
    frames: int
    ms: int


@dataclass
class LookSpec:
    gen_dir: str  # generated strips (written by tools/sprite_gen/looks/build_looks.py)
    target: str  # the .aseprite file the game loads
    tags: list[TagSpec]


def look_tags() -> list[TagSpec]:
    """Strip layout of build_looks.py: idle.png rows down, left, right, up; walk.png one row facing right."""
    return [
        TagSpec("idle_down", "idle.png", 0, 1, IDLE_MS),
        TagSpec("idle_right", "idle.png", 2, 1, IDLE_MS),
        TagSpec("idle_up", "idle.png", 3, 1, IDLE_MS),
        TagSpec("walk_right", "walk.png", 0, 4, WALK_MS),
    ]


LOOKS = {
    "sam_casual": LookSpec(
        "art/characters/samantha/looks/sam_casual",
        "assets/library/characters/looks/sam_casual/sam_casual.aseprite",
        look_tags(),
    ),
}


def gen_frames(spec: LookSpec) -> list[tuple[int, Image.Image]]:
    """(duration, cell image) per frame, in tag order."""
    out = []
    for t in spec.tags:
        strip = Image.open(ROOT / spec.gen_dir / t.file).convert("RGBA")
        for i in range(t.frames):
            box = (i * CELL[0], t.row * CELL[1], (i + 1) * CELL[0], (t.row + 1) * CELL[1])
            out.append((t.ms, strip.crop(box)))
    return out


def tag_ranges(spec: LookSpec) -> list[tuple[str, int, int]]:
    out, start = [], 0
    for t in spec.tags:
        out.append((t.name, start, start + t.frames - 1))
        start += t.frames
    return out


def _visible(im: Image.Image) -> Image.Image:
    """RGBA with fully transparent pixels zeroed, so hidden colour values do not count."""
    im = im.convert("RGBA")
    clear = Image.new("RGBA", im.size)
    return Image.composite(im, clear, im.getchannel("A").point(lambda a: 255 if a else 0))


def same(a: Image.Image, b: Image.Image) -> bool:
    return ImageChops.difference(_visible(a), _visible(b)).getbbox(alpha_only=False) is None


def sync(name: str, spec: LookSpec, check: bool) -> bool:
    """Returns True if the file is (now) up to date."""
    target = ROOT / spec.target
    frames = gen_frames(spec)
    if not target.exists():
        if check:
            print(f"{name}: missing {spec.target}")
            return False
        ase = asefile.build(
            CELL[0], CELL[1], LAYERS,
            [(ms, {GEN: im}) for ms, im in frames],
            tag_ranges(spec),
            asefile.image_palette([im for _, im in frames]),
            grid=CELL,
        )
        ase.save(target)
        print(f"{name}: created {spec.target}")
        return True

    ase = asefile.AseFile.load(target)
    names = ase.layer_names()
    if "gen" not in names:
        print(f"{name}: {spec.target} has no 'gen' layer")
        return False
    gen = names.index("gen")
    if ase.tags() != tag_ranges(spec) or len(ase.frames) != len(frames):
        print(f"{name}: frame or tag layout of {spec.target} differs from the spec; fix it by hand or rebuild")
        return False

    stale = []
    for i, (_, im) in enumerate(frames):
        if "frozen" in (ase.cel_user_data(i, gen) or ""):
            if not same(ase.render_layer(i, gen), im):
                print(f"{name}: frame {i} is frozen, new gen pixels not applied")
            continue
        if not same(ase.render_layer(i, gen), im):
            stale.append(i)
            if not check:
                ase.replace_cel(i, gen, im)
    if not stale:
        print(f"{name}: up to date")
        return True
    if check:
        print(f"{name}: gen layer stale in frames {stale}")
        return False
    ase.save(target)
    print(f"{name}: updated gen layer in frames {stale}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="only report, exit 1 if anything is missing or stale")
    ap.add_argument("looks", nargs="*", help="look ids (default: all)")
    args = ap.parse_args()
    ok = True
    for name in args.looks or LOOKS:
        ok &= sync(name, LOOKS[name], args.check)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
