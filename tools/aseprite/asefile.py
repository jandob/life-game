"""Minimal reader/writer for Aseprite files (RGBA only), enough to build and update look files
without the Aseprite app.

Spec: https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md

Reading keeps every chunk as raw bytes, so a file saved by Aseprite round-trips unchanged except
for the chunks we replace on purpose (the cels of one layer).
"""
from __future__ import annotations

import struct
import zlib
from collections import Counter
from dataclasses import dataclass, field

from PIL import Image

HEADER_MAGIC = 0xA5E0
FRAME_MAGIC = 0xF1FA

CHUNK_LAYER = 0x2004
CHUNK_CEL = 0x2005
CHUNK_TAGS = 0x2018
CHUNK_PALETTE = 0x2019
CHUNK_USER_DATA = 0x2020

LAYER_VISIBLE = 1
LAYER_EDITABLE = 2

CEL_COMPRESSED_IMAGE = 2


def _string(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<H", len(b)) + b


def _read_string(data: bytes, off: int) -> tuple[str, int]:
    (n,) = struct.unpack_from("<H", data, off)
    return data[off + 2 : off + 2 + n].decode("utf-8"), off + 2 + n


@dataclass
class Chunk:
    type: int
    data: bytes

    def encode(self) -> bytes:
        return struct.pack("<IH", len(self.data) + 6, self.type) + self.data


@dataclass
class Frame:
    duration_ms: int
    chunks: list[Chunk] = field(default_factory=list)

    def encode(self) -> bytes:
        body = b"".join(c.encode() for c in self.chunks)
        n = len(self.chunks)
        head = struct.pack("<IHHH2xI", 16 + len(body), FRAME_MAGIC, min(n, 0xFFFF), self.duration_ms, n)
        return head + body


@dataclass
class AseFile:
    width: int
    height: int
    header: bytes  # the 128-byte header as read (rewritten on save for size and frame count)
    frames: list[Frame]

    # ------------------------------------------------------------------ reading
    @classmethod
    def load(cls, path) -> "AseFile":
        data = open(path, "rb").read()
        _size, magic, nframes, w, h, depth = struct.unpack_from("<IHHHHH", data, 0)
        if magic != HEADER_MAGIC:
            raise ValueError(f"{path}: not an Aseprite file")
        if depth != 32:
            raise ValueError(f"{path}: only RGBA sprites are supported (colour depth {depth})")
        off = 128
        frames = []
        for _ in range(nframes):
            fsize, fmagic, old_n, dur, new_n = struct.unpack_from("<IHHH2xI", data, off)
            if fmagic != FRAME_MAGIC:
                raise ValueError(f"{path}: bad frame magic at {off}")
            n = new_n if new_n else old_n
            coff = off + 16
            chunks = []
            for _ in range(n):
                csize, ctype = struct.unpack_from("<IH", data, coff)
                chunks.append(Chunk(ctype, data[coff + 6 : coff + csize]))
                coff += csize
            frames.append(Frame(dur, chunks))
            off += fsize
        return cls(w, h, data[:128], frames)

    def layer_names(self) -> list[str]:
        names = []
        for c in self.frames[0].chunks:
            if c.type == CHUNK_LAYER:
                name, _ = _read_string(c.data, 16)
                names.append(name)
        return names

    def tags(self) -> list[tuple[str, int, int]]:
        for c in self.frames[0].chunks:
            if c.type == CHUNK_TAGS:
                (n,) = struct.unpack_from("<H", c.data, 0)
                off, out = 10, []
                for _ in range(n):
                    frm, to = struct.unpack_from("<HH", c.data, off)
                    name, off = _read_string(c.data, off + 17)
                    out.append((name, frm, to))
                return out
        return []

    def cel_user_data(self, frame: int, layer: int) -> str | None:
        """Text of the user data attached to a cel, if any."""
        chunks = self.frames[frame].chunks
        for i, c in enumerate(chunks):
            if c.type == CHUNK_CEL and struct.unpack_from("<H", c.data, 0)[0] == layer:
                if i + 1 < len(chunks) and chunks[i + 1].type == CHUNK_USER_DATA:
                    ud = chunks[i + 1].data
                    (flags,) = struct.unpack_from("<I", ud, 0)
                    if flags & 1:
                        return _read_string(ud, 4)[0]
                return None
        return None

    def render_layer(self, frame: int, layer: int) -> Image.Image:
        """The cel of one layer as a full-canvas RGBA image (only compressed image cels)."""
        out = Image.new("RGBA", (self.width, self.height))
        for c in self.frames[frame].chunks:
            if c.type != CHUNK_CEL:
                continue
            li, x, y, _op, ctype = struct.unpack_from("<HhhBH", c.data, 0)
            if li != layer:
                continue
            if ctype != CEL_COMPRESSED_IMAGE:
                raise ValueError(f"frame {frame} layer {layer}: unsupported cel type {ctype}")
            w, h = struct.unpack_from("<HH", c.data, 16)
            px = zlib.decompress(c.data[20:])
            out.paste(Image.frombytes("RGBA", (w, h), px), (x, y))
        return out

    def render(self, frame: int) -> Image.Image:
        """Visible layers composited with normal blending and full opacity (enough for checks)."""
        out = Image.new("RGBA", (self.width, self.height))
        layers = [c for c in self.frames[0].chunks if c.type == CHUNK_LAYER]
        for li, c in enumerate(layers):
            (flags,) = struct.unpack_from("<H", c.data, 0)
            if flags & LAYER_VISIBLE:
                out = Image.alpha_composite(out, self.render_layer(frame, li))
        return out

    # ------------------------------------------------------------------ editing
    def replace_cel(self, frame: int, layer: int, image: Image.Image) -> None:
        """Replaces (or adds) the cel of `layer` in `frame`; other chunks stay as they are."""
        chunks = self.frames[frame].chunks
        new = cel_chunk(layer, image)
        for i, c in enumerate(chunks):
            if c.type == CHUNK_CEL and struct.unpack_from("<H", c.data, 0)[0] == layer:
                if new is None:
                    del chunks[i]
                    if i < len(chunks) and chunks[i].type == CHUNK_USER_DATA:
                        del chunks[i]
                else:
                    chunks[i] = new
                return
        if new is not None:
            chunks.append(new)

    # ------------------------------------------------------------------ writing
    def save(self, path) -> None:
        body = b"".join(f.encode() for f in self.frames)
        header = bytearray(self.header)
        struct.pack_into("<IHH", header, 0, 128 + len(body), HEADER_MAGIC, len(self.frames))
        with open(path, "wb") as fh:
            fh.write(bytes(header) + body)


def new_header(width: int, height: int, grid: tuple[int, int] | None = None) -> bytes:
    gw, gh = grid or (16, 16)
    return struct.pack(
        "<IHHHHHIHIIB3xHBBhhHH84x",
        0, HEADER_MAGIC, 0, width, height, 32,
        1,  # flags: layer opacity is valid
        100, 0, 0, 0,  # speed (deprecated), reserved, reserved, transparent index
        0, 1, 1, 0, 0, gw, gh,  # colours (unused for RGBA), pixel ratio 1:1, grid origin and size
    )


def layer_chunk(name: str, flags: int) -> Chunk:
    data = struct.pack("<HHHHHHB3x", flags, 0, 0, 0, 0, 0, 255) + _string(name)
    return Chunk(CHUNK_LAYER, data)


def cel_chunk(layer: int, image: Image.Image) -> Chunk | None:
    """A compressed-image cel trimmed to the opaque bounding box (None if fully transparent)."""
    image = image.convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        return None
    crop = image.crop(bbox)
    head = struct.pack("<HhhBHh5xHH", layer, bbox[0], bbox[1], 255, CEL_COMPRESSED_IMAGE, 0, *crop.size)
    return Chunk(CHUNK_CEL, head + zlib.compress(crop.tobytes(), 9))


def tags_chunk(tags: list[tuple[str, int, int]]) -> Chunk:
    data = struct.pack("<H8x", len(tags))
    for name, frm, to in tags:
        # from, to, direction (forward), repeat (0 = loop), reserved, rgb (deprecated), extra
        data += struct.pack("<HHBH6x3Bx", frm, to, 0, 0, 0, 0, 0) + _string(name)
    return Chunk(CHUNK_TAGS, data)


def palette_chunk(colours: list[tuple[int, int, int, int]]) -> Chunk:
    data = struct.pack("<III8x", len(colours), 0, max(len(colours) - 1, 0))
    for r, g, b, a in colours:
        data += struct.pack("<HBBBB", 0, r, g, b, a)
    return Chunk(CHUNK_PALETTE, data)


def image_palette(images: list[Image.Image], limit: int = 256) -> list[tuple[int, int, int, int]]:
    """The opaque colours of the images, most used first (a convenience palette for editing)."""
    count: Counter = Counter()
    for im in images:
        for n, (r, g, b, a) in im.convert("RGBA").getcolors(1 << 24) or []:
            if a:
                count[(r, g, b, 255)] += n
    return [(0, 0, 0, 0)] + [c for c, _ in count.most_common(limit - 1)]


def build(width: int, height: int, layers: list[tuple[str, int]], frames: list[tuple[int, dict[int, Image.Image]]],
          tags: list[tuple[str, int, int]], palette: list[tuple[int, int, int, int]], grid=None) -> AseFile:
    """A new file. `layers` are (name, flags) bottom to top; `frames` are (duration_ms, {layer: image})."""
    out = []
    for i, (dur, cels) in enumerate(frames):
        chunks = []
        if i == 0:
            chunks.append(palette_chunk(palette))
            chunks += [layer_chunk(n, f) for n, f in layers]
            chunks.append(tags_chunk(tags))
        for li, im in sorted(cels.items()):
            c = cel_chunk(li, im)
            if c is not None:
                chunks.append(c)
        out.append(Frame(dur, chunks))
    return AseFile(width, height, new_header(width, height, grid), out)
