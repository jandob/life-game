"""Create or update the `gen` layer of the game's .aseprite files from generated PNGs.

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
    name: str | None  # "<clip>_<facing>" as src/look.rs expects; None for an untagged still image
    file: str  # generated PNG, relative to the repo root
    row: int = 0
    frames: int = 1
    ms: int = IDLE_MS


@dataclass
class AseSpec:
    target: str  # the .aseprite file the game loads
    tags: list[TagSpec]
    cell: tuple[int, int] | None = None  # canvas size; None: the size of the (single) source image


def look(character: str, look_id: str) -> AseSpec:
    """A look built from build_looks.py strips: idle.png rows down, left, right, up; walk.png facing right."""
    src = f"art/characters/{character}/looks/{look_id}"
    return AseSpec(
        f"assets/library/characters/looks/{look_id}/{look_id}.aseprite",
        [
            TagSpec("idle_down", f"{src}/idle.png", 0, 1, IDLE_MS),
            TagSpec("idle_right", f"{src}/idle.png", 2, 1, IDLE_MS),
            TagSpec("idle_up", f"{src}/idle.png", 3, 1, IDLE_MS),
            TagSpec("walk_right", f"{src}/walk.png", 0, 4, WALK_MS),
        ],
        CELL,
    )


def still(src: str, target: str) -> AseSpec:
    """A single untagged frame, canvas the size of the source image."""
    return AseSpec(target, [TagSpec(None, src)])


ROOMS = ["landing", "flat3a", "flat3b", "shop"]
DOORS = ["door", "door_landing_3a", "door_landing_3b", "door_3a_inside", "door_3b_inside"]
PORTRAITS = ["player", "samantha"]

LOOKS = {
    "player_main": look("player", "player_main"),
    "sam_casual": look("samantha", "sam_casual"),
    "sam_ponytail": look("samantha", "sam_ponytail"),
    **{f"room_{r}": still(f"art/rooms/{r}/background.png", f"assets/library/rooms/{r}/background.aseprite")
       for r in ROOMS},
    **{d: still(f"art/rooms/doors/{d}.png", f"assets/library/rooms/doors/{d}.aseprite") for d in DOORS},
    **{f"portrait_{p}": still(f"art/portraits/{p}.png", f"assets/library/portraits/{p}.aseprite")
       for p in PORTRAITS},
}


def canvas(spec: AseSpec) -> tuple[int, int]:
    return spec.cell or Image.open(ROOT / spec.tags[0].file).size


def gen_frames(spec: AseSpec) -> list[tuple[int, Image.Image]]:
    """(duration, cell image) per frame, in tag order."""
    cw, ch = canvas(spec)
    out = []
    for t in spec.tags:
        strip = Image.open(ROOT / t.file).convert("RGBA")
        for i in range(t.frames):
            out.append((t.ms, strip.crop((i * cw, t.row * ch, (i + 1) * cw, (t.row + 1) * ch))))
    return out


def tag_ranges(spec: AseSpec) -> list[tuple[str, int, int]]:
    out, start = [], 0
    for t in spec.tags:
        if t.name:
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


def sync(name: str, spec: AseSpec, check: bool) -> bool:
    """Returns True if the file is (now) up to date."""
    target = ROOT / spec.target
    frames = gen_frames(spec)
    if not target.exists():
        if check:
            print(f"{name}: missing {spec.target}")
            return False
        w, h = canvas(spec)
        ase = asefile.build(
            w, h, LAYERS,
            [(ms, {GEN: im}) for ms, im in frames],
            tag_ranges(spec),
            asefile.image_palette([im for _, im in frames]),
            grid=spec.cell,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        ase.save(target)
        print(f"{name}: created {spec.target}")
        return True

    ase = asefile.AseFile.load(target)
    names = ase.layer_names()
    if "gen" not in names:
        print(f"{name}: {spec.target} has no 'gen' layer")
        return False
    gen = names.index("gen")
    if ase.tags() != tag_ranges(spec) or len(ase.frames) != len(frames) or (ase.width, ase.height) != canvas(spec):
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
    ap.add_argument("looks", nargs="*", help="names from LOOKS (default: all)")
    args = ap.parse_args()
    ok = True
    for name in args.looks or LOOKS:
        ok &= sync(name, LOOKS[name], args.check)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
