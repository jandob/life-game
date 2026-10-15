## ADDED Requirements

### Requirement: Qwen-Image 2.1 backend
`artgen.py` SHALL provide a `qwen_image21` backend that generates with Qwen-Image 2.1 Turbo from a GGUF transformer on MPS. The text encoder SHALL run in a separate process and SHALL never be resident together with the transformer. The peak MPS memory SHALL stay below 14 GB at 1024x1024.

#### Scenario: Text to image
- **WHEN** `artgen.py generate --backend qwen_image21 --prompt P --seed 11` runs twice
- **THEN** both runs write an image and a sidecar with GGUF sha, diffusers commit, sigmas and peak memory, and the second run performs no text encoding

#### Scenario: Transparent output
- **WHEN** `--opt rgba=1` is given
- **THEN** the PNG has a real alpha channel with the background fully transparent

### Requirement: Encoding cache
Encodings SHALL be cached on disk keyed by the prompt, the resized reference pixels, the reference resolution and the encoder identity. `artgen.py cache` SHALL report the cache size and prune it.

#### Scenario: Extra seeds
- **WHEN** the same prompt and references are generated with a new seed
- **THEN** no text encoding runs

### Requirement: Reference composition
`generate --backend qwen_image21 --ref A B C` SHALL condition the image on the references in order (Picture 1, 2, 3).

#### Scenario: Characters placed in a room
- **WHEN** a room image and two character images are passed with a placement prompt
- **THEN** the output shows both characters in the room with the room's layout preserved

### Requirement: Edit with paste-back
`artgen.py edit --image SRC --prompt P` SHALL edit SRC by instruction at SRC's size. With `--mark x,y,r` a circle SHALL be drawn on the input to show the model the region. With `--mask M` only the masked region SHALL be taken from the edit, through a feathered composite, and the sidecar SHALL record the drift outside the mask.

#### Scenario: Local fix
- **WHEN** a hand is fixed with `--mark` and `--mask`
- **THEN** pixels outside the mask equal the source image

### Requirement: Sprite sheet
`artgen.py sheet` SHALL generate a whole animation as one image from character references plus a strip of pose skeletons. With `--slice` it SHALL cut the sheet into frame cells and post-process them with one fixed grid size.

#### Scenario: Walk cycle
- **WHEN** `sheet --ref FRONT SIDE --poses walk_side --frames 5 --slice` runs
- **THEN** five frame PNGs with feet on the configured row and a sheet PNG are written

### Requirement: Runner interface
Generation jobs SHALL be expressible as a serialisable job spec executed by a runner. The local runner SHALL be the default. Selecting a remote runner without a configured host SHALL fail with a clear error.

#### Scenario: Remote not configured
- **WHEN** `--opt runner=remote:cloud` is passed and no host is configured
- **THEN** the command exits with an error naming the missing configuration

### Requirement: Stable consumer contracts
`artgen.py inpaint` and `artgen.py snap` SHALL keep their arguments, file naming and JSON output so that `tools/scenekit` works unchanged. `generate` SHALL keep printing paths unless `--json` is given.

#### Scenario: Scenekit regression
- **WHEN** `tools/scenekit/test_generate.py` runs after this change
- **THEN** it passes unchanged

### Requirement: Agent skill
The repository SHALL provide an `artgen` agent skill at `.claude/skills/artgen/SKILL.md`, with byte-identical copies in `.pi/skills/artgen/` and `.github/skills/artgen/`. It SHALL document which backend to use per stage, one copy-paste recipe per task (character, transparent prop, scene composition, turnaround, local fix, sprite sheet) with its post-processing settings, the prompt patterns that worked, and the operating rules for the 24 GB Mac.

#### Scenario: Agent uses the tool from the skill alone
- **WHEN** an agent with only the skill is asked for a transparent prop and a two-character scene
- **THEN** it produces both with the documented commands without reading artgen's source

#### Scenario: Copies stay in sync
- **WHEN** one copy of the skill is edited without the others
- **THEN** the artgen test suite fails

### Requirement: Project profile and project skill
Life Game's art constants SHALL live in one profile file (`tools/artgen/profiles/life-game.json`) that the post-processor, `sheet` and the bench read, not in code. Life-Game-specific art conventions SHALL be documented in a `life-game-art` skill, separate from the project-neutral `artgen` skill.

#### Scenario: Profile matches the sprite format
- **WHEN** the artgen tests run
- **THEN** they fail if the profile's realistic cell size or feet row differs from the sprite-format spec

#### Scenario: Default behaviour unchanged
- **WHEN** `artgen.py post` runs without `ARTGEN_PROFILE`
- **THEN** it produces the same output as before the profile existed

## REMOVED Requirements

### Requirement: SDXL backend
**Reason**: Superseded by `qwen_image21` (user decision 2026-10-15). Character identity now comes from reference images instead of LoRAs, and pose from skeleton strips instead of ControlNet.
**Migration**: Use `generate --backend qwen_image21 --ref ...` for identity, `edit` for repaints and `sheet` for poses.
