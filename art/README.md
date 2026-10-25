# art/: Life Game art data

Project-specific art data. Three areas are kept apart:

| Area | Holds |
|---|---|
| `tools/artgen/` | the generic image tool (code, backends, generic defaults), no Life Game data |
| `assets/` | finished, shipped game assets only (`push_to_itch.sh` ships all of it) |
| `art/` (here) | the project's art data |

```
art/
  artgen-profile.json     art constants for artgen (found automatically; env ARTGEN_PROFILE overrides)
  palettes/*.hex          palettes (interior, apartment, apartment_kitchen, player_ref)
  bench.yaml              artgen's benchmark subjects (the profile's `bench` key)
  jobs/                   generation job lists + notes (run from tools/artgen, see jobs/README.md)
  characters/player/keys/ chosen key frames (png + generation sidecar json) of the player
  characters/samantha/keys/   same for Samantha
```

Flow: new takes land in the git-ignored `tools/artgen/out/`; a chosen take is copied into `characters/<name>/keys/`;
`tools/sprite_gen/realistic/build_sheets.py` and `portraits.py` read the keys and write finished sheets and portraits into
`assets/library/`. Palettes are read by `tools/scenekit` (`art/palettes/interior.hex`). Sidecar JSONs keep the paths they were
generated with (history); they are not rewritten.

## The artgen tool (git subtree)

`tools/artgen/` is a git subtree of the private repo `github.com/jandob/artgen` (its own history, releases and the
RunPod worker live there). Edit it here like any other folder; sync with:

```sh
git remote add artgen https://github.com/jandob/artgen.git  # once
git subtree pull --prefix=tools/artgen artgen main          # bring in tool changes
git subtree push --prefix=tools/artgen artgen main          # publish changes made here
```

The tool's skill is canonical in `tools/artgen/SKILL.md`; copy it to `.claude/`, `.pi/` and `.github/skills/artgen/`
after changing it. `art/test_art.py` checks the copies and that `art/artgen-profile.json` matches the sprite-format spec:
`tools/artgen/.venv/bin/python art/test_art.py`.
