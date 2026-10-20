## 1. Action popup

- [x] 1.1 Present options before any line as a popup (no dialogue box), auto-pick a lone available option, end on none
- [x] 1.2 Escape on a popup despawns its runner
- [x] 1.3 Yarn check: a node may open with options

## 2. Inventory

- [x] 2.1 `items.yarn` declarations, item table, item check test
- [x] 2.2 Inventory panel on `I`, walking paused while open
- [x] 2.3 "Got:" toast from diffing the item variables

## 3. Phone

- [x] 3.1 `<<phone>>`, `<<note>>`, `<<note_done>>` commands and `Phone` resource
- [x] 3.2 Phone panel on `P`: notes and message history; opening with an unread text plays it
- [x] 3.3 Message history from `phone`-tagged nodes
- [x] 3.4 Start points replay the phone commands

## 4. Content and hints

- [x] 4.1 Socks and bakery bag items, door popups, Sunday text and croissant note (placeholder lines)
- [x] 4.2 Key hint (top left) lists `I` and `P` and unread texts

## 5. Checks

- [x] 5.1 `cargo test --workspace`, clippy, fmt, `cargo check --target wasm32-unknown-unknown`
- [x] 5.2 Play `sunday` and `movein` natively (Xvfb, lavapipe): popups at both doors, Escape, the text and reply, phone and inventory panels, the croissant scene to the end card, the socks notice; screenshots in `screenshots/`

## 6. Review (user)

- [ ] 6.1 Rewrite the placeholder lines and decide on the popup look
