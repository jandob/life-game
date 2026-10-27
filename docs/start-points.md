# Start points

Start the game at a point in the story instead of playing through to it. Meant for
testing and debugging a scene, by people and by agents.

## Use

Native:

```sh
cargo run -- --start list                 # print the start points and exit
cargo run -- --start r1dinner2            # skip the menu, start the second Thursday
cargo run -- --start r1dinner2night       # inside that box, after the kiss
cargo run -- --start r1dinner1 --set r1_dishes_turn=stay
cargo run -- --start r1retry              # the evening after she sent him home
cargo run -- --start r1knock              # late at night in 3B: the knock
cargo run -- --start r1notebook           # evening in 3B: her notebook on the counter
```

Web build (local server or the direct page URL; the itch.io page doesn't pass query
parameters to the game's iframe):

```
index.html?start=r1dinner2
index.html?start=r1dinner1&set=r1_dishes_turn=stay
index.html?start=list                     # logs the list to the browser console
```

An unknown name logs the list as an error and opens the normal menu.

## What a start point does

A start point is a box of the story graph (`assets/dialogue/graph_route1.yarn`, see
`src/story/graph.rs`). The main menu is skipped. The game sets what the earlier boxes leave
behind (Samantha's name, `base_vars` in `src/story/start_point.rs`) and plays the box's
entry node: the title card, the fade, the player placed, the text delivered. The entry node
runs `<<enter_box>>`, so the box starts the same way as in a real game. Then the player gets
control.

A point inside a box (`r1dinner2night`) also lists steps of the box. The walker
(`src/story/walker.rs`) finds the shortest way from the entry to a state where they are
done: in the box, the fewest player actions (hotspot actions and texts read). It plays that
way without showing it. That sets every Yarn variable, pending text and phone note as real
play would. Then the end state of the world it leaves is restored: actors where their last
walk or `<<place>>` put them, facing, shown or hidden, doors open or closed, the screen
black after a `<<fade_out>>` or clear after a `<<fade_in>>`.

Because the walk is found, not written down, a point keeps working however the box changes.

`--set NAME=VALUE` (repeatable, `$` optional) overrides a variable afterwards, e.g. a flavour
variable of a box (`r1_dishes_turn=stay`). The value is typed like the variable's
declaration (string, number, `true`/`false`); an unknown name is logged and skipped. The
story graph's own variables (`$box`, `$step_*`) are not declared, so they can't be set this
way: use a point inside the box.

The log says which start point was applied (`Starting at 'r1dinner2': ...`), and any error
during the walk.

## Adding a start point

Add an entry to `START_POINTS` in `src/story/start_point.rs`, in story order:

- `name`: short, lowercase, what you'd type after `--start`.
- `box_id`: the box of the graph; it needs an entry node (`entry=NODE` on its `<<box>>`).
- `steps`: empty for the start of the box, or the steps of the box that are done first
  (`&["door"]`).

Every box with a scene has a point at its start. The tests in `start_point.rs` walk to every
start point against the real dialogue files and map, so a broken box fails `cargo test`.

## Limits

- A point inside a box takes the shortest way, so flags come out as the shortest way sets
  them; use `--set` for others.
- Only the world commands listed in `walker.rs` (`WORLD_COMMANDS`) restore world state for a
  point inside a box (a point at the start of a box plays the entry node for real). A
  new command that changes the world (e.g. switching maps) needs a case in `replay` too.
- Read texts are not in the phone's message history.

## Rooms

Route 1 plays side-on, walked by clicking: the landing, 3B, 3A and the corner shop are
rooms of `maps/side/route1.tmj` (see `openspec/changes/side-view/`). A start point puts
the player at its spawn or path, in whichever room that lies; walks into another room go
through the doors and stairs between them.
