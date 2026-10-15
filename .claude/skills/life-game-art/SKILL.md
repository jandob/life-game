---
name: life-game-art
description: Life Game art conventions and registry. Use when making or changing art for the Life Game project - characters (the player, Samantha), sprites and sprite sheets, portraits, props and room scenes - or when an agent asks what size, style, references or output flow the game's art needs. Pairs with the artgen skill (how to run the tool).
---

# Life Game art

How to run the tool is in the **artgen** skill (`tools/artgen/README.md`, `STYLES.md`). This skill holds the project's
numbers, references and rules. The active artgen profile is `art/artgen-profile.json`.

## Where things live (three areas)

- `tools/artgen/`: the generic tool (code, backends, generic defaults). No Life Game data.
- `assets/`: finished, shipped game assets only (`push_to_itch.sh` ships all of it). Nothing else goes there.
- `art/`: Life Game art data: `artgen-profile.json`, `palettes/`, `bench.yaml`, `jobs/` (generation job lists), `characters/{player,samantha}/keys/` (chosen key frames). Scripts in `tools/sprite_gen/` read from `art/`. See `art/README.md`.

## Rules

- **Every character is an adult** (the prompts say so explicitly: "clearly an adult in his mid twenties").
- Art is **good enough**, not polished: no polish or regeneration rounds; art gets reworked later.
- Never overwrite or delete anything in `assets/` unless asked. Generated images are not committed; only finished assets are.
- Outputs go to `tools/artgen/out/` (git-ignored). One model process at a time (24 GB Mac).
- Style words for sprite prompts: **anime style pixel art, thick dark outlines, flat cel shading with two tones**.

## Sprite format (realistic characters)

Authoritative spec: `openspec/changes/realistic-character-sprites/specs/characters/sprite-format/spec.md`
(also `.../characters/player/` and `.../characters/samantha/`). Summary:

- Sheet **960x2304** RGBA, cells **96x192**, 10 columns x 12 rows, rows in `CHARACTER_CLIPS` order: idle 0-3, walk 4-7,
  run 8-11, each in the order down, left, right, up. Drawn at scale 1.0 (one sheet pixel = one world pixel = a tile pixel).
- Figure centred horizontally; lowest opaque row of the feet on **row 157**. Standing adult man **132 rows** tall (+-2),
  adult woman about **126** rows. Drop shadow from artgen's post (`--shadow`).
- Post command, with ONE fixed pixel size N per character (measured from the standing front view, never re-fit per frame):
  `artgen.py post RAW --grid N --cell 96x192 --feet-row 157 --shadow --outline inner --colours 24 --keep-largest --out OUT`.
  N in use **for the 576x1024 key frames** (FLUX klein raws, see the registry): player 7.36 (all views); Samantha 7.48 front,
  7.29 side, 7.33 back. N scales with the raw image size: for `artgen.py sheet` output (cells 384x768) let `--slice` fit N on
  frame 0 (about 5.1 for the player); don't reuse the key-frame N there.
- Older legacy characters use 64x128 cells (feet row 105); do not mix.

## Character registry (reference images)

The keys are tracked in git under `art/characters/<name>/keys/` (not in `assets/`). Paths are from the repo root; from `tools/artgen` (where artgen runs) prefix them with `../../`. The keys are raw
model output (576x1024 RGB, plain white background, FLUX klein + pixel LoRA), not pixel-art cells; use them as `--ref`/`--image`.

| Character | Canonical references | Finished assets |
|---|---|---|
| Player | `art/characters/player/keys/player_{front,side,back}_idle_s11.png` | `assets/library/characters/player/player.png`, `assets/library/portraits/player.png` |
| Samantha | `art/characters/samantha/keys/sam_{front,side,back}_idle_s11.png` | `assets/library/characters/samantha/samantha.png`, `assets/library/portraits/samantha.png` |

Walk key frames sit next to them (`*_contact_*`, `*_passing_*`, `*_contactL/R_*`). Discarded takes stay untracked in `tools/artgen/out/sam_art/keys/rejected/`. New generations land in
`tools/artgen/out/` (the job files' `out`); copy a take into `art/characters/<name>/keys/` only once it is chosen, then rebuild the sheet.
Other portraits: `assets/library/portraits/` (antonius, eleonore, ionas, isabelle, jotem, pai).

Subject descriptions (use in prompts, plus the style words; templated `generate` already adds "pixel art sprite", verbatim
prompts and `sheet --subject` need the style words added). They start with "the same ..." because they follow a reference
("the same slender young adult man from the reference image, ..."); without a reference drop "the same":

- **Player**: the same slender young adult man, clearly an adult in his mid twenties, short messy brown hair, green eyes,
  olive green hoodie, dark blue jeans, brown sneakers.
- **Samantha**: the same young woman, clearly an adult woman of 25, long blonde hair, blue eyes, teal zip-up track jacket with
  white stripes, fitted light grey top, black leggings, white sneakers.

More wording and seeds: the job files `art/jobs/*.json` and the sidecar JSON of each key image.

## Producing a new view or pose

1. Reference = the canonical front idle. `artgen.py edit --image <front> --prompt "Picture 1 shows ... Draw the same ... from
   behind ..."` (see artgen recipe 4.3), or `sheet --ref FRONT SIDE ... --slice` for a walk (the profile supplies 96x192, row 157).
2. Look at the result; reroll the seed if identity or outfit drifted; do not polish.
3. Post with the fixed N of that character (above).

## Known gaps (don't guess, ask)

- `artgen.py sheet` makes one direction (side view, facing right) with N frames; the game sheet needs 10 columns per clip and
  down/left/right/up rows. `build_sheets.py` assembles sheets from the key frames, not from `sheet` output. Mapping sheet frames
  into the game format is not defined yet.
- Props: no fixed size yet. For map props the scene-designer rule applies (at most about 128 art px per side, one fixed grid,
  the style words, generated alone, stamped via scenekit). Props made with artgen alone stay in `tools/artgen/out/`.
- Scene images with characters (e.g. two characters on a sofa) are full-resolution images; there is no in-game target format
  or post step for them yet.

## Output flow

`tools/artgen/out/...` (raw, px) -> `tools/artgen/.venv/bin/python tools/sprite_gen/realistic/build_sheets.py {player|samantha} OUT.png
[--raw DIR] [--work DIR]` (builds the 960x2304 sheet from the key frames; portraits via `portraits.py {player|samantha} OUT.png`)
-> `assets/library/characters/<name>/<name>.png`. Copy into `assets/` only when asked. Rooms and maps go through
`tools/scenekit` (the scene-designer agent), not through artgen alone.

## Who does what

- **pixel-artist** agent: characters, sprites, sheets, portraits, props, using artgen with both skills; Pillow scripts only for
  touch-ups, recolours and sheet assembly.
- **scene-designer** agent: Tiled maps and room scenes via scenekit.
- **architect** agent: pipeline or tool changes (artgen internals, sprite format).
