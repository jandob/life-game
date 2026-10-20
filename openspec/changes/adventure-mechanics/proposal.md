## Why

Life Game is story only so far: the player walks, presses E at a door or a person, and watches or picks dialogue options. Janosch wants it to play more like a point-and-click adventure, without timers or mini-games (thread decision, 2026-10-20). Progress in a scene should come from looking at things, carrying and using items, and following her instructions, most of which arrive on his phone. The route 1 outline (`openspec/ideas/drafts/route1-outline.md`) and the mechanics draft (`openspec/ideas/drafts/adventure-mechanics.md`) describe where this is going. This change builds the three systems those need.

Decided by Janosch:
- Keyboard walking stays. There's no click-to-walk and no pathfinding.
- E interacts. If there are several things to do at a target, a small popup lists them.
- He has an inventory.
- He has a phone with her texts and with notes, which work as a quest log.
- Nothing is timed. The pivot's rule of no stats and no grind still holds.

## What Changes

- **Action popup**: a talk target's node may open with options instead of a line (`-> Knock`, `-> Look`). The engine shows these as a compact popup with no dialogue box. If only one option is available, it runs at once with no popup, so a single-action target behaves like today's. Escape on a popup closes it and forgets the runner, so the next E starts the node fresh and re-checks its conditions. Use and give are ordinary options with an item condition (`-> Give her the bag <<if $item_bakery_bag>>`).
- **Inventory**: items are Yarn bool variables `$item_<id>`, declared in `assets/dialogue/items.yarn`. The story takes and removes them with plain `<<set>>`. A Rust item table gives each id a display name and a description. `I` opens the inventory panel. A short toast ("Got: blush socks") shows when an item is added. Because items are variables, conditions, start points, `--set` and fast-forward already work with them.
- **Phone**: `P` opens it. It has two lists:
  - **Messages.** `<<phone NODE>>` delivers a text conversation. The phone shows an unread marker, and opening it plays the node in the dialogue box (her lines, his reply options). Every line of a node tagged `phone` is kept in the message history.
  - **Notes** (the quest log). `<<note ID "text">>` adds or updates an open note, and `<<note_done ID>>` ticks it off. Open notes are listed first.
  - Start points replay `note`, `note_done` and pending `phone` commands.
- **Yarn checks** (`test.rs`): the new commands and their arity. A node may open with options (an action popup) but still not with a `You:` line. Every `$item_` variable has an entry in the item table, and every table entry is declared.
- **Demo content** in the existing route 1 scenes, so the systems can be played and tested:
  - The blush socks become an item at move-in.
  - The bakery bag is an item on Sunday morning, and she takes it in the croissant scene.
  - Both doors on the landing get popups (knock or open, and look).
  - She texts him on Sunday morning, which adds the note "Bring Samantha a plain croissant". The croissant scene ticks it off.
  - The new lines are placeholders for Janosch to rewrite.
- **Hints**: a key hint in the top left lists `I` and `P`, and how many texts are unread.

## Non-Goals

- Click-to-walk, pathfinding, hover highlights or a mouse-driven verb bar.
- Item icons. The inventory is text first, and icons are a later art pass.
- Combining items, item pick-ups that hide map art, and a generic "that doesn't work" fallback for every item at every target.
- Texting her first, photos on the phone, and other contacts.
- Logging phone lines that a start point skips over. Only commands are replayed.
- Save and load.

## Impact

- **Code**: new `src/story/inventory.rs` and `src/story/phone.rs`. `src/ui/dialogue/{updating,option_selection,runner,spawn,test}.rs` handle the popup, and `src/story/start_point.rs` replays the new commands. `src/player/input.rs` blocks walking and talking while a panel is open, the new `src/ui/hud.rs` holds the panels, key hint and notice, and `src/main.rs` registers the new Yarn files.
- **Assets**: new `assets/dialogue/items.yarn` and `assets/dialogue/phone_route1.yarn`. Small additions to `door_3a.yarn`, `door_3b.yarn`, `route1_movein.yarn` and `route1_croissant.yarn`.
- **Web build**: nothing wasm-sensitive. It uses UI nodes and resources only.
- **PR #5 (Thursday dinner)** touches the same door dispatchers. Whichever lands second merges the door nodes.
