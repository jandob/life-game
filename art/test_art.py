#!/usr/bin/env python
"""Project checks for Life Game's art setup (the artgen tool's own tests live in tools/artgen/).

    tools/artgen/.venv/bin/python art/test_art.py

- art/artgen-profile.json matches the authoritative sprite-format spec;
- the artgen skill copies in .claude/.pi/.github equal the tool's canonical tools/artgen/SKILL.md;
- the life-game-art skill copies are identical.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools/artgen"))


def test_skill_copies() -> None:
    canonical = {"artgen": REPO / "tools/artgen/SKILL.md", "life-game-art": None}
    for name, limit in (("artgen", 300), ("life-game-art", 150)):
        paths = [REPO / d / "skills" / name / "SKILL.md" for d in (".claude", ".pi", ".github")]
        if canonical[name]:
            paths.insert(0, canonical[name])
        texts = [p.read_bytes() for p in paths]
        assert all(texts), f"skill {name} missing"
        assert len(set(texts)) == 1, f"the {name} SKILL.md copies differ: {[str(p) for p in paths]}"
        head = texts[0].decode().split("---")[1]
        assert f"name: {name}" in head and "description:" in head
        assert len(texts[0].decode().splitlines()) < limit


def test_profile_matches_sprite_format_spec() -> None:
    import re
    import artprofile
    spec = (REPO / "openspec/changes/realistic-character-sprites/specs/characters/sprite-format/spec.md").read_text()
    w, h = (int(v) for v in re.search(r"(\d+)x(\d+)-pixel cells", spec).groups())
    feet = int(re.search(r"feet on row (\d+)", spec).group(1))
    prof = artprofile.load()
    assert prof["_path"].endswith("art/artgen-profile.json") and prof["name"] == "life-game"
    assert tuple(prof["sheet_post_cell"]) == (w, h) == (96, 192) and prof["sheet_feet_row"] == feet == 157
    import postprocess
    assert postprocess.CHAR_CELL == (64, 128) and postprocess.OUTLINE == (34, 32, 52)
    assert postprocess.SHADOW_CENTRE == (31.5, 102) and postprocess.SHADOW_RADII == (22.5, 11.5)
    assert "thick dark outlines" in prof["sheet_style"]
    old = os.environ.get("ARTGEN_PROFILE")
    os.environ["ARTGEN_PROFILE"] = "/no/such/profile.json"
    try:
        artprofile.load()
    except SystemExit as e:
        assert "not found" in str(e)
    else:
        raise AssertionError("missing profile must fail")
    finally:
        if old is None:
            os.environ.pop("ARTGEN_PROFILE")
        else:
            os.environ["ARTGEN_PROFILE"] = old


if __name__ == "__main__":
    os.chdir(REPO)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
