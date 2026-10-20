## Why

Testing a scene meant playing the whole story up to it, every time. That is slow for
people and the main cost for agents that check a scene in the real game (user request
2026-10-19: "start the game at any point in time ... instead of needing to do a full
playthrough each time").

## What Changes

- **Start points** (`src/story/start_point.rs`): a table of named points in story order
  (`viewing`, `movein`, `sunday`, `croissant`), each with the scenes played before it and
  whether it starts a scene or hands the player control.
- **Launch option**: `--start NAME` natively, `?start=NAME` on the web; `--start list`
  prints the table. `--set NAME=VALUE` / `&set=NAME=VALUE` overrides a Yarn variable.
- **Fast-forward**: the earlier scenes run on a bare Yarn `Dialogue` over the shared
  story variables, taking the first available option at every choice. Their world
  commands are replayed for their end state (positions, facing, visibility, doors, fade).
- The main menu is skipped when a valid start point is given.
- `ScreenFade::black()` to start a scene that opens with `<<fade_in>>`.
- Docs for agents and people: `docs/start-points.md`.

## Non-Goals

- Save/load, or choosing options per choice on the command line.
- An in-game menu for start points.
