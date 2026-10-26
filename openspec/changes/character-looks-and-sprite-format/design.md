## Context

Decided with Janosch (2026-10-26): 128x256 cells; walk drawn once facing right and mirrored; no vertical walks; not every look supports every clip; looks are data (manifest files). Architect review (same day) recommended per-look clip tables with a fallback chain, and flagged mirroring, animation state reset and the collider offset.

## Decisions

**D1 One strip per clip.** A look folder holds `idle.png`, `walk.png` and later `sit.png` and so on. Each strip has its own frame count, so no shared grid. All strips use 128x256 cells with the same feet row, so clips from different strips line up. Strips stay under 2048 px per side (WebGL2).

**D2 Manifest** (`look.ron`, loaded through the asset server so it works on wasm):
```
Look(id: "sam_casual", character: "samantha", clips: {
  Idle: (file: "idle.png", frames: 1, rows: [Down, Left, Right, Up], mirror_left: false),
  Walk: (file: "walk.png", frames: 4, rows: [Right], mirror_left: true, frame_ms: 140),
})
```
`mirror_left` is per clip, so a look with an asymmetric detail (side braid, shoulder bag) can ship a drawn left row instead.

**D3 Resolution.** `character_clip(look, anim, facing)` returns the look's own clip, else the default look's clip, else `Idle` of the same facing. Run is not part of the new looks and resolves to Walk. Vertical movement resolves to Walk facing the last horizontal direction.

**D4 Animation state.** Switching look swaps the image, atlas layout and clip together and resets the frame index. `flip_x` is set from the clip's mirror flag and reset on every clip change. The feet anchor is horizontally centred, so mirroring does not shift the figure.

**D5 Collider.** The feet collider stays 24 world px in radius, but its offset below the sprite centre is recomputed from the new cell height and feet row (it assumed 192 px).

**D6 Production.** Key frames are raw model output (about 640x1024, plain white background). One pixel size N per character, measured on the standing front view and reused for every frame of every look of that character. `artgen.py post --grid N --cell 128x256 --feet-row 245 --shadow --outline inner --colours 24 --keep-largest`. Left idle is the mirrored right idle (unless the look says otherwise). Hair-only looks redo only the head with a masked edit.

**Pixelorama.** Import a strip with "spritesheet" and N frames across and 1 or 4 rows; export by animation tag with the same rows and columns. Frame durations live in the manifest, not in the PNG.

## Open Questions

- Exact feet row for 128x256 (proposed 245) and figure height (about 230 rows) are set from the first processed strips.
- Walk frame count (proposed 4: contact, passing, contact, passing) and idle frames (1 for now, breathing later).
