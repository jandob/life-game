## ADDED Requirements

### Requirement: Route 1 is cut into chapters

Route 1 SHALL have these chapters, in order, each with this card:

| Chapter | Card |
|---|---|
| `R1Viewing` | "Saturday. The viewing." |
| `R1MoveIn` | "Saturday. Moving day." |
| `R1Sunday` | "Sunday morning." |
| `R1Thu1` | "Thursday. Eight o'clock." |
| `R1Thu2` | "Thursday. A week later." |

#### Scenario: The whole route
- **WHEN** the walk check runs on route 1
- **THEN** all five chapters SHALL pass

### Requirement: Route 1 opens one place at a time

The landing and 3B SHALL be open from the viewing, the inside of 3A from the first Thursday and the corner shop from the second Thursday. The stairs SHALL say there is nothing to buy before then.

#### Scenario: Stairs on Sunday
- **WHEN** he uses the stairs on the first Thursday
- **THEN** he SHALL say he has nothing to get, and he SHALL stay on the landing

### Requirement: The route ends after the second Thursday for now

The second Thursday's bottleneck SHALL show "Thursdays." and end the demo until the next chapter is written.

#### Scenario: Last bed
- **WHEN** he goes to bed after her night text on the second Thursday
- **THEN** the "Thursdays." card SHALL show and the demo SHALL end

### Requirement: Viewing gates

The viewing SHALL have the gates `r1_view_knock` (knock on 3B; she opens 3A and lets him in), then `r1_view_window`, `r1_view_kitchen` and `r1_view_bath` in any order (she tells him to look around), then the bottleneck `r1_view_end` (tell her he's seen enough).

#### Scenario: Leaving too soon
- **WHEN** he tells her he's seen enough before looking at the bath
- **THEN** she SHALL send him to look, and the chapter SHALL not end

### Requirement: Viewing flags

The first of the three things he looks at SHALL set `$r1_viewing_why`, which the move-in reads. The opening and question menus and their variables SHALL be dropped.

#### Scenario: Looking at the window first
- **WHEN** the window is the first thing he looks at in 3B
- **THEN** `$r1_viewing_why` SHALL be `light`, and her line at the move-in SHALL refer to it

### Requirement: Move-in gates

The move-in SHALL have the gates `r1_move_keys` (knock on 3A; she hands him the keys and the blush socks), `r1_move_box` (carry his box in), `r1_move_socks` (put the socks in the drawers or leave them in the box), `r1_move_rules` (she knocks, he answers, she gives her rules), and the bottleneck `r1_move_bed`.

#### Scenario: Box before socks
- **WHEN** he carries the box in and then goes to bed with the socks still in his hand
- **THEN** the bed SHALL say it is too early

### Requirement: Move-in flags

Where he puts the socks SHALL set `$r1_movein_socks`. The keys and rules menus and their variables SHALL be dropped.

#### Scenario: Leaving the socks in the box
- **WHEN** he leaves the socks in the box
- **THEN** `$r1_movein_socks` SHALL be `refuse`, and the croissant scene SHALL react to it

### Requirement: Sunday gates

Sunday morning SHALL have the gates `r1_sun_text` (read her text), `r1_sun_croissant` (knock on 3A holding the bakery bag; the croissant scene plays), and the bottleneck `r1_sun_bed`. She SHALL always invite him for Thursday.

#### Scenario: Knocking without the bag
- **WHEN** he knocks on 3A without the bakery bag
- **THEN** she SHALL ask where her croissant is, and the scene SHALL not start

### Requirement: Sunday flags

Whether he is wearing the socks, has hung them on the drying rack, or neither when he knocks SHALL set `$r1_croissant_socks` (`yes`, `wash`, `no`). The bag and dinner menus SHALL be dropped.

#### Scenario: Socks on the rack
- **WHEN** he hung the socks on the drying rack before knocking
- **THEN** she SHALL hear that they are in the wash, and `$r1_croissant_socks` SHALL be `wash`

### Requirement: First Thursday gates

The first Thursday SHALL have the gates `r1_thu1_text` (her text: eight o'clock, and the wine she drinks, Red Fox 2021), `r1_thu1_door` (knock on 3A), `r1_thu1_sit` (sit at her table; the dinner plays), `r1_thu1_dishes` (wash up; the dishes scene plays), and the bottleneck `r1_thu1_bed`. He brings nothing yet: the wine she names is the clue for the second Thursday.

#### Scenario: Going home before the dishes
- **WHEN** he tries to leave 3A after dinner before washing up
- **THEN** she SHALL point him at the sink, and the chapter SHALL stay as it was

### Requirement: First Thursday flags

During the dishes the sink SHALL offer "Keep washing" and "Turn around", which set `$r1_dishes_turn`. Looking at her notebook on the table before she shows it SHALL set `$r1_dinner_notes`. The dinner and dishes menus SHALL be dropped.

#### Scenario: Turning around
- **WHEN** he turns around at the sink
- **THEN** she SHALL react, `$r1_dishes_turn` SHALL be `turned`, and the dishes scene SHALL go on

### Requirement: Second Thursday gates

The second Thursday SHALL have the gates `r1_thu2_text` (her riddle), `r1_thu2_wine` (holding the Red Fox 2021), `r1_thu2_door` (knock on 3A), `r1_thu2_shoes` (shoes off at her door), `r1_thu2_cork` (the corkscrew from her sink), `r1_thu2_open` (open the wine at her table), `r1_thu2_dinner` (sit; the dinner plays), `r1_thu2_stand` (stand where she tells him at her door; the kiss plays), `r1_thu2_night` (read her night text in 3B), and the bottleneck `r1_thu2_bed`.

#### Scenario: Gifts in any order
- **WHEN** he buys the tulips after the wine and before knocking
- **THEN** he SHALL be able to give both at her door in either order, and the chapter SHALL go on the same way

### Requirement: Second Thursday flavour

The recycling clue, the socks, the tulips and the chocolates SHALL stay optional and only change her lines. Giving things SHALL be give actions on her, and the "Hi." and "That's everything." options and the question game menus SHALL be dropped. Reaching for her instead of standing still SHALL set `$r1_thu2_kiss` and get her line, and the scene SHALL go on once he stands still.

#### Scenario: Reaching for her
- **WHEN** he reaches for her when she told him to stand still
- **THEN** she SHALL stop him with a line, `$r1_thu2_kiss` SHALL record it, and the kiss SHALL play once he stands still

### Requirement: Phone replies stay flavour

Reply options in her texts SHALL remain. They SHALL only set flags and SHALL not set gates.

#### Scenario: Replying to her riddle
- **WHEN** he answers her riddle with any of the replies
- **THEN** `$gate_r1_thu2_text` SHALL be set the same way
