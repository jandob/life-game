## ADDED Requirements

### Requirement: One world unit is one art pixel

Tiles, props and character sheets SHALL be drawn so that one pixel of their art covers one world unit, except legacy 64x128 character sheets, which SHALL be drawn at scale 1.5 until they are replaced. Map tiles for the new story SHALL be 48x48 px, drawn at the same pixel density as the realistic characters (about 74 art pixels per metre).

#### Scenario: Consistent pixel size
- **WHEN** a realistic character stands in a room of a 48 px tile map
- **THEN** a tile pixel and a character pixel SHALL cover the same number of screen pixels

### Requirement: Tile size per map

The map loader SHALL read the tile size from the map file, and every tileset used by the map SHALL have that tile size. A map whose tilesets disagree with its tile size SHALL fail to load with an error message, without a panic. Maps with 16 px tiles SHALL still load.

#### Scenario: 48 px map
- **WHEN** `route1_flat.tmj` with 48 px tiles loads
- **THEN** tiles, tile colliders, map objects and paths SHALL line up with a 48 px grid

#### Scenario: Mismatched tileset
- **WHEN** a map with 48 px tiles references a 16 px tileset
- **THEN** loading SHALL fail with an error naming the tileset

### Requirement: Integer pixel scaling

The camera SHALL draw every art pixel as a whole number `t` of physical screen pixels, with `t = max(1, round(physical window height / 540))`, and SHALL recompute `t` when the window size or scale factor changes. The F3 debug zoom MAY scale the view on top of this.

#### Scenario: 1080p fullscreen
- **WHEN** the window is 1080 physical pixels tall
- **THEN** every art pixel SHALL be 2x2 screen pixels and 540 world px SHALL be visible vertically

#### Scenario: HiDPI default window
- **WHEN** the 1280x720 window is shown at a scale factor of 2
- **THEN** every art pixel SHALL be 3x3 physical pixels
