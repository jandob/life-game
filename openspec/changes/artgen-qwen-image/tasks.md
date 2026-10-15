## 1. Model-free infrastructure

- [x] 1.1 `backends/_enc_cache.py` (key, save/load, stats, prune) + tests: key changes with prompt, resized ref pixels, `ref_res` and encoder id; `weights_only` load
- [x] 1.2 `maskkit.paste_back` + `--mark` circle drawing + tests: pixels outside the mask equal the source; edit resized to source size
- [x] 1.3 `pose.strip` (row of N skeletons from a preset cycle, cell size) + test of the output size and skeleton count
- [x] 1.4 `runner.py`: `JobSpec`, `Runner` protocol, `LocalRunner`, fake remote runner (subprocess round-trip of a `JobSpec`) tested with the stub backend
- [x] 1.5 `generate --json` (opt-in) + test; existing `test_backends.py` and `tools/scenekit/test_generate.py` still pass

## 2. Qwen backend: text to image

- [x] 2.1 `backends/_gguf.py` (idempotent non-Linear dequant fix) and `backends/qwen_encode.py` (encode worker, stdout to stderr)
- [x] 2.2 `backends/qwen_image21.py` turbo profile: light `load`, `precompute`, `generate` with encode-before-transformer sequencing, tiled VAE, load-time `encode_prompt` signature check; registry + `models.json` entry
- [x] 2.3 Smoke run: bench `man_front` seed 11 at 1024 px is near-identical to `out/eval_2026-10/turbo/steps8/raw/man_front_s11.png`; peak MPS < 14 GB in stats; a second run does no encode; `artgen.py backends` lists it
- [x] 2.4 `--opt rgba=1` wording; smoke: the sofa has real alpha (> 50 % of pixels below alpha 10 raw, fully transparent after `post`; the model writes alpha 1-9 rather than exactly 0)

## 3. References and composition

- [x] 3.1 `generate --ref` for `qwen_image21` (condition-image resize identical for encode and generate, bf16 VAE with refs)
- [x] 3.2 Smoke: reproduce the sofa scene (room + player + Samantha, scene prompt v2) near-identically

## 4. `edit`

- [x] 4.1 `edit` command (source + extra refs, output size = source, `--mark`, `--mask`/`--feather` paste-back, drift-outside-mask in the sidecar, JSON stdout)
- [x] 4.2 Smoke: front -> back turnaround of the player; hand fix with `--mark` + `--mask` has 0 drift outside the mask

## 5. `sheet`

- [x] 5.1 `sheet` command (skeleton strip from `pose.strip`, one generation, optional `--slice` into cells and post with a fixed grid N, feet row 157)
- [x] 5.2 Smoke: 5-frame player walk sheet, sliced and post-processed to 96x192 cells, plus a preview GIF

## 6. Remote seam

- [x] 6.1 `--opt runner=local|remote:<name>` selects the runner; base profile defaults (40 steps, cfg, negative prompt) defined; remote runs fail with a clear "no host configured" error

## 7. Removals

- [x] 7.1 Delete `backends/sdxl.py`, `cast.py`, `compose.py`, `train/`, `examples/cast_recipe.json`, the `cast` CLI and the SDXL path of `refine`; `refine` default backend -> `flux2_klein_pixel_lora`; drop the SDXL sections of `models.json`; update `test_backends.py`
- [x] 7.2 Note in `openspec/changes/character-refine/` that cast is removed by this change; header note in `tools/sprite_gen/realistic/jobs/01_fronts_sdxl.sh` that it no longer runs

## 8. Docs and integration

- [x] 8.1 `bench.py`/`compare.py` accept `qwen_image21` (incl. refs) 
- [x] 8.2 README: setup with the pinned diffusers commit and `gguf`, memory notes, command reference; STYLES.md rewritten as the stage-by-stage pipeline (initial generation / composition / edit / sheet / post)
- [x] 8.3 `cache --stats` / `--prune` command
- [x] 8.4 Agent skill `.claude/skills/artgen/SKILL.md` (D6), copied byte-identical to `.pi/skills/artgen/` and `.github/skills/artgen/`; test that the copies match
- [x] 8.5 Skill dry run (no model runs; user: no tests over 2 min in this change): a fresh agent given only the skills writes the commands for a transparent prop, a 2-character scene and a walk sheet; every command and flag is checked against `artgen.py <cmd> --help` and the capability guards

- [x] 8.6 Capability flags (`BackendInfo.caps`): `backends` prints them; edit/sheet/--ref/rgba/refine/inpaint/remote fail clearly on backends that lack them; model-free guard tests

## 9. Generic tool and project layer (D7)

- [x] 9.1 `profiles/life-game.json` + loader (`ARTGEN_PROFILE`); `postprocess.py`, `sheet` defaults and `bench.py` read it; outputs unchanged (existing post tests still pass bit-for-bit)
- [x] 9.2 `artgen` skill made project-neutral (profile-based sizes, pointer to `life-game-art`); README/STYLES mention the profile
- [x] 9.3 `life-game-art` skill (+ `.pi`/`.github` copies): sprite format with spec link, character registry, style suffix, adults-only, output flow, agent roles
- [x] 9.4 `.claude/agents/pixel-artist.md` updated to use artgen + both skills
- [x] 9.5 Tests: profile matches the sprite-format spec (96x192, feet row 157); copies of both skills identical; all suites green (model-free only)
