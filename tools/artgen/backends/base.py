"""Backend interface shared by every generation pipeline.

A backend turns a text prompt (plus optional reference images) into raw RGB or
RGBA PIL images. Everything after that (grid snapping, background removal,
palette, cell fitting) lives in ``postprocess.py`` and is backend-agnostic, so
results from different backends can be compared like for like.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from PIL import Image


@dataclass
class BackendInfo:
    name: str                      # registry key, e.g. "flux2_klein_pixel_lora"
    description: str
    models: list[str]              # model / LoRA / service ids used
    licence: str                   # licence of weights or service terms (outputs)
    local: bool = True             # runs on this machine (False = remote API)
    defaults: dict[str, Any] = field(default_factory=dict)  # default opts
    prompt_template: str = "{prompt}"  # how the bench wraps a subject prompt

    def to_dict(self) -> dict:
        return asdict(self)


class Backend:
    """Subclass this, fill in ``info`` and implement ``load`` and ``generate``."""

    info: BackendInfo
    # Options artgen.py/bench.py pass to load() (the rest go to generate()).
    load_keys: frozenset = frozenset({"offload", "dtype"})
    # String options are normally template fields only; these are also given to generate().
    passthrough_opts: frozenset = frozenset({"ref"})
    # Options artgen.py inpaint passes to inpaint().
    inpaint_keys: tuple = ("steps", "guidance", "lora_scale")

    def load(self) -> None:
        """Load weights / open a client. Called once before generate()."""

    def generate(self, prompt: str, negative: str | None = None,
                 width: int = 512, height: int = 512, seed: int = 0,
                 n: int = 1, **opts) -> list[Image.Image]:
        """Return ``n`` images. Image i must be reproducible from seed + i."""
        raise NotImplementedError

    def stats(self) -> dict[str, Any]:
        """Optional runtime stats (peak memory, load time, ...)."""
        return {}

    def unload(self) -> None:
        """Free memory."""

    def apply_template(self, subject: str, **fields) -> str:
        """Wrap a subject in the backend's trigger template.

        Extra ``{fields}`` in the template are filled from ``fields`` first,
        then from ``info.defaults``.
        """
        vals = {k: v for k, v in self.info.defaults.items() if isinstance(v, str)}
        vals.update({k: v for k, v in fields.items() if v is not None})
        return self.info.prompt_template.format(prompt=subject, **vals)

    def precompute(self, prompts: list[str]) -> None:
        """Optional: prepare for a known prompt list (e.g. cache text embeds)."""
