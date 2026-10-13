Generation jobs for the raw key frames used by `../build_sheets.py` (outputs in `tools/artgen/out/sam_art/`, git-ignored).
Run from `tools/artgen` with `.venv/bin/python`; JSON job lists go through `../flux_batch.py` (one FLUX klein load):
`.venv/bin/python ../sprite_gen/realistic/flux_batch.py ../sprite_gen/realistic/jobs/08_player_idles_sam_walk.json`.

- `01_fronts_sdxl.sh`: SDXL WAI v17 + pixel_art_xl fronts; `sam_front_s13` seeds Samantha's look (the player fronts here were rejected as too young).
- `02_views_flux.sh`: FLUX klein side/back views from those fronts; `sam_side_s11` and `sam_back_s11` are Samantha's standing side/back.
- `06_...json`: adult player fronts (FLUX, no ref; seed 32 chosen) and Samantha's grey-top front (`sam_front_greytop_s12`).
- `08_...json`: player front/side/back idles (side s11, back s11) and Samantha's walk key frames.
  Samantha's front idle `keys/sam/sam_front_idle_s11.png` came from an earlier run of the same front-idle job (ref `sam_front_greytop_s12`).
- `09_...json`: player walk key frames.
Seeds and full prompts are in each output's JSON sidecar.
