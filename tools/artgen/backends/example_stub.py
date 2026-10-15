"""Template for a new backend. Copy this file, rename the class, register it
in ``backends/__init__.py`` and fill in ``load``/``generate``.

Sketches for likely candidates:

* Replicate (remote)::

      import replicate                        # pip install replicate
      out = replicate.run("<owner>/<model>:<version>",
                          input={"prompt": prompt, "seed": seed, ...})
      # download out[i] URLs -> PIL images. Token from REPLICATE_API_TOKEN.

* PixelLab (remote, returns true-pixel RGBA already)::

      POST https://api.pixellab.ai/v1/generate-image-pixflux
      {"description": prompt, "image_size": {"width": 64, "height": 64},
       "seed": seed, "no_background": true}
      # base64 PNG in the response. Token from PIXELLAB_API_TOKEN.

Remote backends must read their keys from the environment and never write
them into sidecars.
"""
from __future__ import annotations

from .base import Backend, BackendInfo


class ExampleStub(Backend):
    info = BackendInfo(
        name="example_stub",
        description="Template backend, not functional.",
        models=[],
        licence="n/a",
        local=True,
        defaults={},
        prompt_template="{prompt}",
    )

    def load(self) -> None:
        raise NotImplementedError("example_stub is a template; copy it to make a real backend")

    def generate(self, prompt, negative=None, width=512, height=512, seed=0, n=1, **opts):
        raise NotImplementedError
