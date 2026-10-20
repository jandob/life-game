## ADDED Requirements

### Requirement: A week after the dinner, she sends a riddle

After `Route1Dishes`, a "Thursday. A week later." card SHALL be shown, the player SHALL get control on the landing and her text "Tonight. Bring what I'd want." SHALL arrive on his phone with a note for it. Nothing in the scene SHALL be timed or gated: he MAY knock on 3A at any point.

#### Scenario: Knocking straight away
- **WHEN** the player knocks on 3A before doing anything else
- **THEN** `Route1Thu2Door` SHALL start and she SHALL react to him arriving empty-handed

### Requirement: The clues are in the world

The empty Red Fox bottle on her recycling, her earlier wine text (if he asked in the croissant scene) and the socks in 3B SHALL be findable with Look and Take. The socks SHALL be in the drawers, on the drying rack or in the moving box depending on `$r1_croissant_socks`.

#### Scenario: Socks in the wash
- **WHEN** `$r1_croissant_socks` is `wash`
- **THEN** the socks SHALL be on the drying rack, and the drawers and the box SHALL not offer them

### Requirement: The shop is a place he goes

The stairs on the landing SHALL take him to the corner shop with a fade, and the shop door SHALL bring him back. Taking a bottle, the tulips or the chocolates SHALL add the item. He SHALL carry one bottle at a time.

### Requirement: She checks what he brought

At her door she SHALL wait for him to give her things; each item SHALL get its own reaction. When he takes his shoes off she SHALL react to whether he wears the socks, carries them, or neither.

### Requirement: The evening ends with a kiss

After dinner she SHALL kiss him at her door on every path; his choice there SHALL only change her reaction. If he stands still she SHALL say "Good boy." Her night text SHALL ask him to wear the socks next Thursday, and the scene SHALL end with the end card.

### Requirement: Choices are recorded

The choices SHALL be stored in `$r1_thu2_*` variables in the shared story variables.
