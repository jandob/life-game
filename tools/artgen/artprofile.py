"""Art profile: the constants that make artgen output fit one game.

Resolution (first hit wins): env ``ARTGEN_PROFILE`` (path to a JSON file), else the first
``art/artgen-profile.json`` found walking up from the current directory and then from this tool's
directory, else the generic bundled ``profiles/default.json``. ``load()`` returns a dict (list values
become tuples) with ``_path`` set to the resolved file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_FILE = HERE / "profiles" / "default.json"


def find_profile(start: Path | None = None) -> Path:
    env = os.environ.get("ARTGEN_PROFILE")
    if env:
        p = Path(env).expanduser()
        if not p.is_file():
            raise SystemExit(f"artgen profile not found: {env!r}")
        return p
    for base in (start or Path.cwd(), HERE):
        for d in (Path(base).resolve(), *Path(base).resolve().parents):
            if (d / "art" / "artgen-profile.json").is_file():
                return d / "art" / "artgen-profile.json"
    return DEFAULT_FILE


def load(path: str | Path | None = None) -> dict:
    p = Path(path) if path else find_profile()
    data = json.loads(p.read_text())
    out = {k: tuple(v) if isinstance(v, list) else v for k, v in data.items() if not k.startswith("_")}
    out["_path"] = str(p)
    return out
