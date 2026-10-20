## 1. Map

- [x] 1.1 Landing: recycling bag prop by 3A, `Recycling3A` and `StairsLanding` talk targets
- [x] 1.2 3B: chest of drawers, moving box, drying rack (with collision); `Drawers3B`, `Box3B`, `Rack3B`, `Bed3B` talk targets
- [x] 1.3 Corner shop area (floor, walls, door, wine shelf, tulips, chocolates, till, collision) and its talk targets
- [x] 1.4 Notebook on her table; paths `ShopIn`, `PlayerFromShop`, `PlayerKiss3A`, `SamanthaKiss3A`, `PlayerOutOf3AKiss`, `PlayerOutOf3B`; `Door3BInside`

## 2. Scene

- [x] 2.1 Items and item table rows
- [x] 2.2 Dishes end with the time skip; croissant delivers the wine text
- [x] 2.3 `route1_thursday2.yarn`: door, dinner, kiss, night text
- [x] 2.4 Dispatchers: stairs, recycling, 3B socks spots, shop, Thursday 2 branches at the doors and in 3A
- [x] 2.5 Register files; start points

## 3. Checks

- [x] 3.1 `cargo test --workspace`, clippy, fmt, `cargo check --target wasm32-unknown-unknown`
- [x] 3.2 Play `thursday2` to the end card natively (shop, socks, door, dinner, kiss, text); screenshots in `screenshots/` (Xvfb, lavapipe; full path with the clue, socks on, Red Fox and tulips, then `thursday2door` with `--set`)

## 4. Review (user)

- [ ] 4.1 Play it and decide on wording
