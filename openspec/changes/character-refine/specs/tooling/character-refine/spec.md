## ADDED Requirements

### Requirement: Cast recipe
`artgen.py cast RECIPE.json` SHALL apply a list of regions to one image in order, each with its own mask, prompt, LoRAs, strength and seed, repainting at full image resolution, and SHALL write the final image, every intermediate and a JSON log.

#### Scenario: Two characters
- **WHEN** a recipe lists a head region with `lgwoman1` and a second region with another LoRA
- **THEN** both are repainted with their own LoRA in one command and rerunning the recipe reproduces the result
