//! World-space footprint shared by every character.

use bevy::prelude::*;
use bevy_rapier2d::prelude::*;

/// Radius of the feet collider in world px.
pub const FEET_RADIUS: f32 = 24.0;
/// The feet collider's centre lies this far below the sprite centre, in world px.
pub const FEET_BELOW_CENTRE: f32 = 48.0;

/// How a character sheet maps to the world: the sprite scale.
#[derive(Clone, Copy)]
pub struct SheetFormat {
    pub scale: f32,
}

/// 64x128 cells drawn at 1.5, which gives 96x192 world px.
pub const LEGACY: SheetFormat = SheetFormat { scale: 1.5 };

/// 96x192 cells drawn at 1.0, which gives 96x192 world px.
pub const REALISTIC: SheetFormat = SheetFormat { scale: 1.0 };

impl SheetFormat {
    /// The feet collider and its local transform, for a child of the (scaled) sprite entity.
    pub fn feet_collider(self) -> (Collider, Transform) {
        (
            Collider::ball(FEET_RADIUS / self.scale),
            Transform::from_xyz(0.0, -FEET_BELOW_CENTRE / self.scale, 0.0),
        )
    }

    /// Transform of the sprite centre at `pos`, scaled for this format.
    pub fn transform(self, pos: Vec2) -> Transform {
        Transform::from_translation(pos.extend(0.0)).with_scale(Vec3::splat(self.scale))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn legacy_collider_matches_the_old_local_numbers() {
        let (collider, transform) = LEGACY.feet_collider();
        assert_eq!(collider.as_ball().unwrap().radius(), 16.0);
        assert_eq!(transform.translation, Vec3::new(0.0, -32.0, 0.0));
        assert_eq!(
            LEGACY.transform(Vec2::new(1.0, 2.0)).scale,
            Vec3::splat(1.5)
        );
    }

    #[test]
    fn realistic_collider_is_in_world_px() {
        let (collider, transform) = REALISTIC.feet_collider();
        assert_eq!(collider.as_ball().unwrap().radius(), 24.0);
        assert_eq!(transform.translation, Vec3::new(0.0, -48.0, 0.0));
    }
}
