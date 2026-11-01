"""Tests for asefile.py and sync_gen.py: python tools/aseprite/test_sync_gen.py"""
from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import asefile  # noqa: E402
import sync_gen  # noqa: E402


def _cell(colour, box=(10, 20, 50, 200)) -> Image.Image:
    im = Image.new("RGBA", sync_gen.CELL)
    im.paste(colour, box)
    return im


def _strips(d: Path, colour) -> None:
    idle = Image.new("RGBA", (128, 256 * 4))
    for row in range(4):
        idle.paste(_cell(colour), (0, row * 256))
    idle.save(d / "idle.png")
    walk = Image.new("RGBA", (128 * 4, 256))
    for i in range(4):
        walk.paste(_cell(colour, (10 + i, 20, 50, 200)), (i * 128, 0))
    walk.save(d / "walk.png")


def _user_data(text: str) -> asefile.Chunk:
    return asefile.Chunk(asefile.CHUNK_USER_DATA, struct.pack("<I", 1) + asefile._string(text))


def test_regen_keeps_paint_and_frozen_frames() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sync_gen.ROOT = tmp
        spec = sync_gen.look("c", "l")
        gen = tmp / "art/characters/c/looks/l"
        gen.mkdir(parents=True)
        _strips(gen, (255, 0, 0, 255))
        assert sync_gen.sync("t", spec, check=False)
        assert sync_gen.sync("t", spec, check=True)

        # Hand edits: a paint stroke on frame 3, and frame 0's gen cel frozen.
        ase = asefile.AseFile.load(tmp / spec.target)
        assert ase.layer_names() == ["gen", "paint"]
        assert [t[0] for t in ase.tags()] == ["idle_down", "idle_right", "idle_up", "walk_right"]
        stroke = _cell((0, 0, 255, 255), (60, 60, 64, 64))
        ase.replace_cel(3, sync_gen.PAINT, stroke)
        chunks = ase.frames[0].chunks
        i = next(i for i, c in enumerate(chunks) if c.type == asefile.CHUNK_CEL)
        chunks.insert(i + 1, _user_data("frozen"))
        ase.save(tmp / spec.target)

        # Regenerate with a new colour.
        _strips(gen, (0, 255, 0, 255))
        assert not sync_gen.sync("t", spec, check=True)
        assert sync_gen.sync("t", spec, check=False)

        ase = asefile.AseFile.load(tmp / spec.target)
        assert ase.render_layer(0, sync_gen.GEN).getpixel((20, 30)) == (255, 0, 0, 255)  # frozen
        assert ase.render_layer(1, sync_gen.GEN).getpixel((20, 30)) == (0, 255, 0, 255)  # refreshed
        assert sync_gen.same(ase.render_layer(3, sync_gen.PAINT), stroke)  # paint kept
        assert ase.render(3).getpixel((61, 61)) == (0, 0, 255, 255)
        assert [f.duration_ms for f in ase.frames] == [1000] * 3 + [140] * 4


def test_still_image() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sync_gen.ROOT = tmp
        (tmp / "art").mkdir()
        src = Image.new("RGB", (300, 120), (10, 20, 30))
        src.save(tmp / "art/bg.png")
        spec = sync_gen.still("art/bg.png", "assets/bg.aseprite")
        assert sync_gen.sync("bg", spec, check=False)
        ase = asefile.AseFile.load(tmp / spec.target)
        assert (ase.width, ase.height, len(ase.frames), ase.tags()) == (300, 120, 1, [])
        assert ase.render(0).getpixel((5, 5)) == (10, 20, 30, 255)
        assert sync_gen.sync("bg", spec, check=True)


if __name__ == "__main__":
    test_still_image()
    test_regen_keeps_paint_and_frozen_frames()
    print("ok")
