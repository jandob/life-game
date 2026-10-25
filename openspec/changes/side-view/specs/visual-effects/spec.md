## REMOVED Requirements

### Requirement: UI hint animations
**Reason**: The dialogue start hint (the bubble over the nearest talk target) and the keyboard key icons belonged to walking with the keyboard and talking with E. The side view walks and talks by clicking (stage 5 of `side-view`, user decision 2026-10-25).
**Migration**: Hovering a hotspot shows its label and a pointer cursor (`src/world/side_view/mod.rs`). The hint and key art stays in `assets/library/ui/`.

### Requirement: Flora particle effects
**Reason**: Flora (trees, bushes, rocks and the sakura petals) only existed on the top-down forest map, which the game no longer loads (stage 5 of `side-view`; the forest art stays in the library, user decision 2026-10-25).
**Migration**: None. The forest art stays in `assets/library/props/forest/` and `tilesets/forest/`.
