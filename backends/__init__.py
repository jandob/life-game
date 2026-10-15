"""Backend registry.

Add a backend by writing ``backends/<name>.py`` with a ``Backend`` subclass and
registering it below as ``"<name>": "<module>:<Class>"``. Modules are imported
lazily so a broken or heavy backend never slows the others down.
"""
from __future__ import annotations

import importlib

from .base import Backend, BackendInfo

REGISTRY: dict[str, str] = {
    "flux2_klein_pixel_lora": "flux2_klein_pixel_lora:Flux2KleinPixelLora",
    "qwen_image21": "qwen_image21:QwenImage21",
    "z_image_turbo": "z_image_turbo:ZImageTurbo",
    # Template only: raises NotImplementedError until someone fills it in.
    "example_stub": "example_stub:ExampleStub",
}


def get_backend(name: str) -> Backend:
    if name not in REGISTRY:
        raise SystemExit(f"unknown backend {name!r}; known: {', '.join(REGISTRY)}")
    mod_name, cls_name = REGISTRY[name].split(":")
    mod = importlib.import_module(f"{__name__}.{mod_name}")
    return getattr(mod, cls_name)()


__all__ = ["Backend", "BackendInfo", "REGISTRY", "get_backend"]
