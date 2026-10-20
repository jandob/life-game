## Context

Talk targets (NPCs and `Interact` objects) start a Yarn node on E. Door nodes are already dispatchers that pick a branch from `visited()`. Story state is one shared `MemoryVariableStorage` (`StoryVars`), and start points fast-forward scenes on a bare `Dialogue` and replay world commands. The option list is already a separate panel (`OptionsBackground`) from the dialogue box. Options are only created after the typewriter finishes a line, which is why a node can't open with options today.

## Decisions

**D1. The popup is Yarn options, not map data.** An action menu could come from Tiled properties (`look=`, `use_socks=`) or from node-name conventions (`Door3A_Look`). Both split one object's behaviour across files and need their own condition system. Yarn options already have conditions (`<<if>>`), visit counts and variables, and the dispatchers are already where a target decides what happens. So a target's node simply opens with options. The engine only has to present "options before any line" as a popup, and auto-pick a lone available option.

**D2. Items are Yarn variables.** `has_item()` as a Yarn function would need the function in every `Dialogue`, including the bare one start points fast-forward on, and an inventory that changes *during* fast-forward. As `$item_<id>` bools, items are read and set with plain Yarn, persist in `StoryVars`, and work with start points and `--set` for free. The engine reads them for the panel and diffs them for the "Got:" toast. The item table in Rust holds what Yarn can't: the name and description.

**D3. Phone texts are Yarn nodes.** A text conversation is a node tagged `phone`, delivered with `<<phone NODE>>` and played in the normal dialogue box when the player opens the phone. Its lines are also appended to the phone history. This reuses portraits, the typewriter, options and flags. A separate chat-bubble renderer would duplicate all of it. Notes are display-only, so they are commands (`<<note>>`, `<<note_done>>`) kept in a `Phone` resource and added to the start point replay list.

**D4. Panels pause walking.** While the inventory or phone panel is open, the player doesn't move or start a chat. E, Escape or the panel's own key closes it. Opening the phone with an unread text closes the panel and starts that node.

**D5. Escaping a popup forgets it.** A runner that never presented a line is despawned on Escape instead of cached. Otherwise the next E would resume with stale option availability.

## Risks

- Yarn commands run on the runner's command system. `<<phone>>` and `<<note>>` are `In<String>` systems like the existing ones.
- Popup detection relies on `RunnerFlags.line` being `None`. `stop_chat_command` sets a `...` line, so the "first line" check uses a separate flag that is set on `PresentLine`.
- A node whose options are all unavailable would hang. In popup mode that ends the conversation with a warning.
