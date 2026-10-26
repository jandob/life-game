//! World-space placement shared by every character.

use bevy::prelude::*;

use crate::look::{LOOK_CELL, LOOK_FEET_ROW};

/// The sprite's feet (row 245 of a 256 px look cell) lie this far below its centre, in world px.
/// Legacy 96x192 sheets (feet row 157) would need 61.
pub const SPRITE_FEET_BELOW_CENTRE: f32 = (LOOK_FEET_ROW - LOOK_CELL.y / 2) as f32;

/// Characters stand between the room's background and foreground image layers;
/// the player a little in front of everyone else.
pub const CHARACTER_Z: f32 = 0.0;
pub const PLAYER_Z: f32 = 1.0;

/// Transform of a character's sprite centre at `pos` (look cells drawn at scale 1,
/// one pixel per world pixel).
pub fn character_transform(pos: Vec2, z: f32) -> Transform {
    Transform::from_translation(pos.extend(z))
}
