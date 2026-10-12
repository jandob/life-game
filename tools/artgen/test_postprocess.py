"""Tests for the cell-size scaling in postprocess.py. Run: tools/artgen/.venv/bin/python tools/artgen/test_postprocess.py

The golden hashes were produced by the version of postprocess.py before the cell scaling (git 9dbdfa1), so the
first test proves 64x128 output is byte-identical."""
import hashlib
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import postprocess as pp

GOLDEN_64 = [
    "762358003f2033e99673734c187306c4df4ca3b0f8e147e752199bc013edd318",  # feet 105, no shadow
    "aba507a397a29ec5cd59d063ffb6ec02654b91ecc4b6bc06c330735d2b726dae",  # feet None, no shadow
    "49f3dabc42d5bbb202a70be6e44850cd99b3d4adda6f8061024720e0309425a2",  # feet 105, shadow
    "546bdc04c0e87e4ca303a5e996cb27e2f9d6738e356bd8a1ade9604df993c789",  # feet None, shadow
    "4767f28efb5ca357ff85712899426ea098ecc49f597c3b80494460c6b111102d",  # shadow_layer() default
]


def _sprite() -> Image.Image:
    rng = np.random.default_rng(3)
    a = np.zeros((140, 50, 4), np.uint8)
    a[10:130, 8:42] = np.concatenate([rng.integers(0, 255, (120, 34, 3)), np.full((120, 34, 1), 255)], 2)
    return Image.fromarray(a)


def _h(im) -> str:
    return hashlib.sha256(im.tobytes()).hexdigest()


def test_64x128_byte_identical() -> None:
    im, got = _sprite(), []
    for sh in (False, True):
        got.append(_h(pp.fit_cell(im, (64, 128), 105, sh)[0]))
        got.append(_h(pp.fit_cell(im, (64, 128), None, sh)[0]))
    got.append(_h(Image.fromarray(pp.shadow_layer())))
    assert got == GOLDEN_64, got


def test_96x192_geometry() -> None:
    assert pp.shadow_geometry((96, 192), 157) == ((47.5, 152.5), (33.75, 17.25))
    assert pp.char_top_row((96, 192)) == 26 and pp.char_top_row((64, 128)) == 17
    sh = pp.shadow_layer((96, 192), feet_row=157)
    ys, xs = np.nonzero(sh[..., 3])
    assert abs((xs.min() + xs.max()) / 2 - 47.5) <= 0.5 and abs((ys.min() + ys.max()) / 2 - 152.5) <= 0.5
    assert ys.max() < 192 and xs.min() >= 0 and xs.max() < 96


def test_96x192_fit_cell_feet_and_shadow() -> None:
    out, info = pp.fit_cell(_sprite(), (96, 192), 157, True)
    a = np.asarray(out)
    opaque = a[..., 3] == 255
    assert opaque.any(axis=1).nonzero()[0].max() == 157 and not info["clipped"]
    assert (a[..., 3] == 125).any()  # shadow present


if __name__ == "__main__":
    for t in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        t()
        print("ok", t.__name__)
