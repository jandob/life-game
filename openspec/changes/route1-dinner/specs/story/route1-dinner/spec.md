## ADDED Requirements

### Requirement: Thursday evening is played

After the croissant scene, a "Thursday. Eight o'clock." card SHALL be shown and the player SHALL get control on the landing. The dinner SHALL start only when the player knocks on 3A.

#### Scenario: Knocking on her door
- **WHEN** the player interacts with 3A after the croissant scene
- **THEN** `Route1DinnerDoor` SHALL start, and it SHALL end with the player inside her flat and in control

### Requirement: The player moves the evening forward

Inside her flat, each beat SHALL be started by the player: sitting at the table starts `Route1Dinner`, and the sink starts `Route1Dishes` after dinner. Her bookshelf and Samantha SHALL be talk targets. Her door SHALL not let him leave before the dishes are done.

#### Scenario: Sink before dinner
- **WHEN** the player interacts with the sink before dinner
- **THEN** he SHALL be told to sit down, and no scene SHALL start

#### Scenario: Leaving early
- **WHEN** the player interacts with her door from inside before the dishes
- **THEN** Samantha SHALL say he's not done, and no scene SHALL start

#### Scenario: The end of the evening
- **WHEN** `Route1Dishes` has finished
- **THEN** he SHALL be walked out to the landing and the end card SHALL be shown

### Requirement: Dinner choices are recorded

The choices SHALL be stored in `$r1_dinner_notes`, `$r1_dinner_reply`, `$r1_dishes_turn` and `$r1_dinner_shelf` in the shared story variables.
