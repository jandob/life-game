"""Project art profile: the constants that make artgen output fit one game.

One JSON file in ``profiles/`` (default ``life-game``); select another with the env var ``ARTGEN_PROFILE``
(a profile name or a path to a JSON file). ``load()`` returns a dict; list values become tuples.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"
DEFAULT = "life-game"


def load(name_or_path: str | None = None) -> dict:
    ref = name_or_path or os.environ.get("ARTGEN_PROFILE") or DEFAULT
    p = Path(ref)
    if not (p.suffix == ".json" and p.is_file()):
        p = PROFILES_DIR / f"{ref}.json"
    if not p.is_file():
        raise SystemExit(f"artgen profile not found: {ref!r} (looked for {p})")
    data = json.loads(p.read_text())
    return {k: tuple(v) if isinstance(v, list) else v for k, v in data.items() if not k.startswith("_")}
