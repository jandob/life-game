//! World-space placement shared by every character.

use bevy::prelude::*;

/// The sprite's feet (row 157 of a 192 px cell) lie this far below its centre, in world px.
pub const SPRITE_FEET_BELOW_CENTRE: f32 = 61.0;

/// Characters stand between the room's background and foreground image layers;
/// the player a little in front of everyone else.
pub const CHARACTER_Z: f32 = 0.0;
pub const PLAYER_Z: f32 = 1.0;

/// Transform of a character's sprite centre at `pos` (96x192 sheet cells drawn at
/// scale 1, one sheet pixel per world pixel).
pub fn character_transform(pos: Vec2, z: f32) -> Transform {
    Transform::from_translation(pos.extend(z))
}
