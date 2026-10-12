"""Repaint masks from boxes (no segmentation model): white = repaint, black = keep.

Boxes are ``x0,y0,x1,y1``. ``units="px"`` takes pixels, ``units="frac"`` takes 0..1 of the canvas.
Used by ``artgen.py mask`` and ``compose.py``.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter


def parse_box(text: str, size: tuple[int, int], units: str = "px") -> tuple[int, int, int, int]:
    """``"x0,y0,x1,y1"`` -> pixel box, clamped to the canvas; raises ValueError on bad or empty boxes."""
    try:
        v = [float(t) for t in str(text).replace(" ", "").split(",")]
    except ValueError:
        raise ValueError(f"bad box {text!r}; expected x0,y0,x1,y1") from None
    if len(v) != 4:
        raise ValueError(f"bad box {text!r}; expected 4 numbers x0,y0,x1,y1")
    if units == "frac":
        v = [v[0] * size[0], v[1] * size[1], v[2] * size[0], v[3] * size[1]]
    elif units != "px":
        raise ValueError(f"units must be px or frac, got {units!r}")
    x0, y0, x1, y1 = v
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    box = (max(0, round(x0)), max(0, round(y0)), min(size[0], round(x1)), min(size[1], round(y1)))
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError(f"box {text!r} is empty after clamping to {size[0]}x{size[1]}")
    return box


def pad_box(box, size, pad: float):
    """Grow a box by ``pad`` x its own width/height on every side (clamped)."""
    w, h = box[2] - box[0], box[3] - box[1]
    return (max(0, round(box[0] - pad * w)), max(0, round(box[1] - pad * h)),
            min(size[0], round(box[2] + pad * w)), min(size[1], round(box[3] + pad * h)))


def build_mask(size: tuple[int, int], *, rects=(), ellipses=(), keep_rects=(), keep_ellipses=(),
               heads=(), head_pad: float = 0.15, head_shape: str = "ellipse", units: str = "px",
               base: str | None = None, feather: float = 0.0) -> Image.Image:
    """Return an "L" mask.

    * ``rects`` / ``ellipses``: boxes painted white (repaint).
    * ``keep_rects`` / ``keep_ellipses``: boxes painted black (keep), applied after the white ones.
    * ``heads``: "everything except heads": the base is white and each head box (grown by ``head_pad``)
      is painted black. Give boxes that include the hair.
    * ``base``: ``white`` or ``black``. Default: black when any white box is given, else white.
    * ``feather``: Gaussian blur radius in px, for soft edges.
    """
    if base is None:
        base = "black" if (rects or ellipses) and not heads else "white"
    if base not in ("white", "black"):
        raise ValueError("base must be white or black")
    m = Image.new("L", size, 255 if base == "white" else 0)
    d = ImageDraw.Draw(m)

    def draw(boxes, shape, fill, grow=0.0):
        for t in boxes:
            b = parse_box(t, size, units)
            if grow:
                b = pad_box(b, size, grow)
            (d.ellipse if shape == "ellipse" else d.rectangle)(b, fill=fill)

    draw(rects, "rect", 255)
    draw(ellipses, "ellipse", 255)
    draw(keep_rects, "rect", 0)
    draw(keep_ellipses, "ellipse", 0)
    draw(heads, head_shape, 0, head_pad)
    if feather > 0:
        m = m.filter(ImageFilter.GaussianBlur(feather))
    return m


def overlay(image: Image.Image, mask: Image.Image, colour=(255, 0, 0), alpha: float = 0.45) -> Image.Image:
    """Tint the repaint area red on a copy of ``image`` (for checking a mask by eye)."""
    img = image.convert("RGB")
    m = mask.convert("L").resize(img.size).point(lambda v: int(v * alpha))
    return Image.composite(Image.new("RGB", img.size, colour), img, m)


def mask_stats(mask: Image.Image) -> dict:
    hist = mask.convert("L").histogram()
    total = sum(hist)
    return {"white_frac": round(sum(hist[128:]) / total, 4), "size": list(mask.size)}
