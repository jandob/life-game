# Start points

Start the game at a point in the story instead of playing through to it. Meant for
testing and debugging a scene, by people and by agents.

## Use

Native:

```sh
cargo run -- --start list                 # print the start points and exit
cargo run -- --start croissant            # skip the menu, start the croissant scene
cargo run -- --start sunday --set r1_movein_rules=fair
```

Web build (local server or the direct page URL; the itch.io page doesn't pass query
parameters to the game's iframe):

```
index.html?start=croissant
index.html?start=sunday&set=r1_movein_rules=fair
index.html?start=list                     # logs the list to the browser console
```

An unknown name logs the list as an error and opens the normal menu.

## What a start point does

The main menu is skipped. The scenes before the point are fast-forwarded without being
shown: the **first available option at every choice**, lines skipped. That sets every
Yarn variable and visit count (`visited()`) as real play would. Then the end state of the
world those scenes leave is restored: actors where their last walk or `<<place>>` put
them, facing, shown or hidden, doors open or closed, the screen black after a
`<<fade_out>>` or clear after a `<<fade_in>>`. Finally the point's scene starts, or the
player gets control.

`--set NAME=VALUE` (repeatable, `$` optional) overrides a variable after the
fast-forward, for testing another branch. The value is typed like the variable's
declaration (string, number, `true`/`false`); an unknown name is logged and skipped.

The log says which start point was applied (`Starting at 'croissant': ...`), and any
error during the fast-forward.

## Adding a start point

Add an entry to `START_POINTS` in `src/story/start_point.rs`, in story order:

- `name`: short, lowercase, what you'd type after `--start`.
- `played`: the scenes played before it, in order. List only nodes the game starts
  itself (`<<next_scene>>` targets and the first scene), not nodes reached by `<<jump>>`,
  since a jump is followed during the fast-forward.
- `begin`: `Begin::Scene("Node")` to start a scene at once, or `Begin::Roam` to hand the
  player control, as at the end of a scene that leaves the player free to walk.

The tests in `start_point.rs` fast-forward every start point against the real dialogue
files, so a renamed node or a broken scene fails `cargo test`.

## Limits

- Only the first option is taken at every choice; use `--set` for other branches.
- Only the commands listed in `REPLAYED` restore world state. A new command that changes
  the world (e.g. switching maps) needs a case in `replay` too.

## Side view (spike)

`--view side` (web: `?view=side`) plays Route 1 side-on, walked by clicking, instead of
the top-down map: the landing, 3B, 3A and the corner shop as rooms of
`maps/side/route1.tmj`. See `openspec/changes/side-view/`. Start points combine with it,
e.g. `--view side --start viewing`: the spawns and paths have the same names as on the
top-down map, and walks into another room go through the doors and stairs between them.
