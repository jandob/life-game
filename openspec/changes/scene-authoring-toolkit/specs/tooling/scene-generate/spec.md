## ADDED Requirements

### Requirement: Region generation as candidate jobs

`scene.py generate` SHALL take a map, a layer, a region in tiles, a prompt and optionally reference images, a material layout, a context width, strength, seeds, count, palette and alpha mode. It SHALL build a canvas from the current pixels around the region and the layout block-out inside it, run the local FLUX.2 klein backend as masked img2img/inpaint at an integer scale, downscale by that fixed factor so the output lies exactly on the 16-pixel grid, apply palette and cleanup, keep only the region's pixels, and write the candidates with previews and a `job.json` under `tools/scenekit/out/jobs/<job-id>/`. It SHALL NOT change the library or any map.

#### Scenario: Four candidates for a floor
- **WHEN** an agent generates a 10x8-cell region with `--n 4` and a layout of `floor` cells
- **THEN** the job directory SHALL contain four 160x128-pixel candidates, four previews with context and grid, and a `job.json` with the parameters and per-candidate counts of new and deduplicated tiles

#### Scenario: Region too large
- **WHEN** the region doesn't fit the model canvas at scale 2
- **THEN** the command SHALL fail with an error that tells the agent to split the region

### Requirement: Applying a candidate

`scene.py apply JOB --pick K` SHALL write the chosen candidate into the map through the import core (dedup, copy-on-write, provenance with origin `generate` or `fill`) and SHALL give each new tile the material from the layout and that material's default collision shape. Context cells outside the region SHALL NOT change.

#### Scenario: Apply keeps neighbours
- **WHEN** a candidate is applied
- **THEN** a `diff` against the previous map version SHALL list changes only inside the job's region

### Requirement: Inpainting cells with context

`scene.py fill` SHALL regenerate an arbitrary set of cells (a list, a one-pixel-per-cell mask, or all empty cells in a region) using the surrounding cells as model context with the same candidate/apply flow. With `--like TILE` it SHALL pass that tile as a reference image. With `--ring 1` it SHALL also regenerate the first ring of context cells through copy-on-write.

#### Scenario: Filling a hole
- **WHEN** an agent erases a 2x2 block in a generated floor and runs `fill --cells` for it
- **THEN** the candidates SHALL change only those four cells

### Requirement: Model work isolated in the artgen environment

Model inference SHALL run as a subprocess in the artgen venv (`tools/artgen/.venv`), using weights already in the local Hugging Face cache, so that every non-generating scenekit command runs with the mise python and Pillow only.

#### Scenario: Inspecting without torch
- **WHEN** `render`, `cells`, `where`, `diff`, `edit`, `export` or `import` runs on a machine without the artgen venv
- **THEN** the command SHALL work
