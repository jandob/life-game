# Start points

Start the game at a point in the story instead of playing through to it. Meant for
testing and debugging a scene, by people and by agents.

## Use

Native:

```sh
cargo run -- --start list                 # print the start points and exit
cargo run -- --start r1thu2               # skip the menu, start the second Thursday
cargo run -- --start r1thu2 --set gate_r1_thu2_text=true
```

Web build (local server or the direct page URL; the itch.io page doesn't pass query
parameters to the game's iframe):

```
index.html?start=r1thu2
index.html?start=r1thu2&set=gate_r1_thu2_text=true
index.html?start=list                     # logs the list to the browser console
```

An unknown name logs the list as an error and opens the normal menu.

## What a start point does

The main menu is skipped. The story chart's walker (`src/story/chart.rs`) finds the
shortest way to the point, chapter by chapter, from a new game: in each chapter the
fewest player actions (hotspot actions and texts read) that reach the point or the next
chapter. It plays that way without showing it. That sets every Yarn variable, pending
text and phone note as real play would. Then the end state of the world it leaves is
restored: actors where their last walk or `<<place>>` put them, facing, shown or hidden,
doors open or closed, the screen black after a `<<fade_out>>` or clear after a
`<<fade_in>>`. Then the player gets control.

Because the walk is found, not written down, a start point keeps working however the
earlier chapters change.

`--set NAME=VALUE` (repeatable, `$` optional) overrides a variable afterwards, e.g. a
gate inside a chapter (`gate_r1_thu2_text=true`) or a flag (`r1_movein_socks=refuse`).
The value is typed like the variable's declaration (string, number, `true`/`false`); an
unknown name is logged and skipped.

The log says which start point was applied (`Starting at 'r1thu2': ...`), and any error
during the walk.

## Adding a start point

Add an entry to `START_POINTS` in `src/story/start_point.rs`, in story order:

- `name`: short, lowercase, what you'd type after `--start`.
- `begin`: `Begin::Chapter("R1Thu2")` for the start of a chapter (its start node
  played), or `Begin::Gate("r1_thu2_door")` for the first point inside a chapter where
  that gate is done.

Every chapter has one. The tests in `start_point.rs` walk to every start point against
the real dialogue files and map, so a broken chapter fails `cargo test`.

## Limits

- The walk takes the shortest way, so flags come out as the shortest way sets them; use
  `--set` for others.
- Only the world commands listed in `chart.rs` (`WORLD_COMMANDS`) restore world state. A
  new command that changes the world (e.g. switching maps) needs a case in `replay` too.
- Read texts are not in the phone's message history.

## Rooms

Route 1 plays side-on, walked by clicking: the landing, 3B, 3A and the corner shop are
rooms of `maps/side/route1.tmj` (see `openspec/changes/side-view/`). A start point puts
the player at its spawn or path, in whichever room that lies; walks into another room go
through the doors and stairs between them.
