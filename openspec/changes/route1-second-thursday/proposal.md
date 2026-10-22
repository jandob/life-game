## Why

The Thursday dinner ends with "Next Thursday. Same time. I'll text you what to bring." This change plays that next Thursday, the first scene of route 1 outline beat 1 ("Thursdays"), and the first scene built on the adventure mechanics: her text is a riddle ("Tonight. Bring what I'd want."), and the player solves it by looking around, taking things and giving them to her. The real answer is the blush socks on his feet; the wine is the decoy she set up herself. It ends with their first real kiss at her door and her first "good boy".

Story draft: `/mnt/project-files/scene-drafts/route1-second-thursday.md` (project files). Decided by Janosch (2026-10-20): the kiss happens this Thursday, the shop is a real new location, and "good boy" is introduced here.

## What Changes

- **Time skip**: `Route1Dishes` no longer ends with `<<end_demo>>`. It fades to the landing a week later ("Thursday. A week later."), puts the socks away in 3B (`$item_blush_socks` false) and delivers her text `PhoneThursday2`.
- **Wine text**: if he asked what to bring in the croissant scene, the time skip after it delivers the text she promised (`PhoneWineChoice`: "Red Fox. The 2021. Not the one with the gold label."), so it is in his phone history a week later.
- **Map** (`route1_flat.tmj`, still one map, design D7):
  - Landing: her recycling bag by 3A with the empty bottle on top; the stairs become a talk target.
  - 3B: a chest of drawers, a moving box and a drying rack. The socks are in one of them depending on `$r1_croissant_socks`. The bed is a talk target (put the socks on).
  - A new corner shop area, not connected on foot: wine shelf (three reds), tulips, chocolates, a till and a door. The stairs and the shop door move him with a fade.
  - Her notebook on her table.
- **Items**: `wine_fox`, `wine_reserve`, `wine_house`, `tulips`, `chocolates`, `corkscrew`.
- **Dialogue**: new `route1_thursday2.yarn` with `Route1Thu2Start` (the time skip and her text), `Route1Thu2Door` (knock: give her things in a loop, `Route1Thu2Give`; shoes off and the socks check, `Route1Thu2Shoes`), `Route1Thu2Dinner` (sit down: the question game, then the kiss at her door and home) and `Route1Thu2End` (going to bed after her night text: end card). One dispatcher file per new talk target: `stairs_landing`, `recycling_3a`, `drawers_3b`, `rack_3b`, `box_3b`, `bed_3b`, `door_3b_inside`, `shop_door`, `shop_wine`, `shop_flowers`, `shop_chocolates`, `shop_till`. `Door3A`, `Door3B`, `Table3A` (her notebook, the wine), `Sink3A` (the corkscrew), `Samantha3A` and `Door3AInside` get Thursday 2 branches. Phone texts `PhoneWineChoice`, `PhoneThursday2` and `PhoneThursday2Night` in `phone_route1.yarn`; notes for the riddle and its clues.
- **Options after a jump** (`src/ui/dialogue/updating.rs`): options that arrive after their line was already finished and continued (after a `<<jump>>`, a command or an `<<if>>` block) are shown at once. Before, they only appeared on the next typewriter finish, so the giving loop and the night text would have stalled (architect review).
- **Graph check**: `dialogue_graph` counts `<<phone NODE>>` targets as entry nodes, like `<<next_scene>>` targets.
- **Start points**: `dinner`, `thursday2`, `shop`, `thursday2door`, `thursday2dinner`, `thursday2night`. Earlier points after Sunday morning list `PhoneSundayMorning` as played so the old text isn't unread.

## Non-Goals

- Item icons, a shopkeeper, money.
- Consequences of the new flags beyond flavour in this scene (they are recorded for later beats).
- The third Thursday.

## Impact

- **Assets**: `route1_flat.tmj` grows (shop area, props), new gen48 tiles; new Yarn files registered in `src/main.rs`; new rows in the item table (`src/story/inventory.rs`) and `items.yarn`; start points in `src/story/start_point.rs`.
- **Depends on PR #5** (Thursday dinner, still open). This branch merges it with main; it should land after #5, or together with it.
