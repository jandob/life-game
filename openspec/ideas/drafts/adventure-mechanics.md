# DRAFT: Point-and-click adventure mechanics

Status: direction agreed 2026-10-20 (see Decided); details still open. It replaces the earlier timers and mini-games draft (Janosch: "point-and-click adventure style, no timers, no minigames").

The idea: progress in a scene comes from looking at things, picking them up, using and giving them, and saying the right thing, as in classic adventure games. It keeps the pivot's rule of no stats and no grind, and nothing is ever timed. The player can always take their time.

## Decided (Janosch, 2026-10-20)

- **Keyboard and inventory.** Walking stays on the keyboard. No click-to-walk and no pathfinding.
- **E to interact.** If the object has one action, E does it straight away. If it has several (look, take, use an item, give, talk), a small popup lists them, and the player picks one with up/down and E, the same as dialogue options today.
- **A phone.** It holds her texts, and it's where most of her instructions arrive. It has notes as a quest log.
- **Build all three**: inventory, E popup and phone.

## Actions in the popup

| Action | What it does | Exists today? |
|---|---|---|
| **Look** | A short line from him about an object or person | Partly (his remarks at objects, e.g. the shelf in 3A) |
| **Talk** | Start a conversation | Yes (NPCs and `Interact` objects) |
| **Take** | Put an item in the inventory | No |
| **Use (item)** | Use an item on an object: key on a door, socks on himself. One entry per item that fits. | No |
| **Give (item)** | Hand an item to a person | No |

Only the actions that make sense at that object are listed. With one entry there's no popup, so today's doors and NPCs behave as they do now.

## Phone

- It opens with its own key (for example Tab or P). It's also a story device: it buzzes, and a small icon shows that a new text has arrived.
- **Messages.** Her texts are written in Yarn like any other scene, so she can send one at a story point ("Thursday. Bring what I'd want."). Some texts give him reply options, which set flags like a dialogue choice. Later, other people text him too (her friends, the landlord, side stories).
- **Notes** (decided). A list of what she has asked for that's still open. It works as the quest log and hint system, written in her voice.
- **Photos** (later, optional). She sends one, or asks for one. It fits the clothing and domination threads, and it's a natural way to show scene stills.
- Nothing about it is timed. A text waits until he reads it.

## Inventory

- A small bar or pouch with a handful of items at a time. No weight, no money.
- Items can be combined (wine + her note = the right bottle).
- Story flags record what he carries and what he handed over, so her lines react ("You brought the blush ones. Good.").

## Puzzle types that fit route 1

Each one is her control expressed as a puzzle: she sets the task, and the player works out how to meet it.

1. **Her instructions, decoded.** She texts something vague ("Bring what I'd want."). Clues are around her flat and his: the empty bottle by her sink, her notebook, a shop receipt. Bringing the right thing earns praise; the wrong thing gets a dry callback.
2. **Getting ready.** Before a Thursday he has to put together what she asked for from his wardrobe and the shop: the socks, later more. The wardrobe is an inventory puzzle, and it's also the route's clothing escalation, step by step.
3. **The spare key.** She has it, he doesn't. Getting into places (her flat when she's out, a locked drawer, his own flat after she's changed something) becomes a key and item chain.
4. **Conversation puzzles.** With the landlord (beat 5) or her friends (beat 4), he has to say the right thing, using what he's picked up and what he knows from her notes. Failing never kills the run; it changes how the scene goes.
5. **Her games in the bedroom.** The domination thread as puzzles, not reflexes: she hides something and gives him rules to find it; she sets a task and he chooses how to fulfil it. Non-timed, so the tension comes from the writing, not a clock.

## Size

- **Inventory plus take, use and give**: M. New Yarn commands (`<<give_item>>`, `<<take_item>>`, an item check in dispatchers), an inventory UI, item icons. Builds on the `Interact` layer and the `visited()` dispatchers.
- **Action popup on E**: S. It reuses the dialogue option UI.
- **Phone with messages**: M. A UI screen, Yarn commands to send a text and wait for a reply, and an unread indicator. Notes and photos come later.
- **Puzzles per scene**: S each once the system exists. The next scene (the second Thursday, with "I'll text you what to bring") is a natural first puzzle: decode her text, find the item, bring it.

## Open questions for Janosch

- Can he text her first, or only reply?
