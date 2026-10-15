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
