use bevy::prelude::*;
use bevy_rapier2d::prelude::*;

use crate::animation::{SpriteAnimator, PLAYER_CLIPS};
use crate::world::camera::YSort;
use crate::{GameAssets, GameState};

use super::{Player, PLAYER_COLLISION_GROUPS, PLAYER_SCALE, PLAYER_SPAWN_POS};

fn spawn_player(mut commands: Commands, assets: Res<GameAssets>) {
    let collider = commands
        .spawn((
            Collider::ball(16.0),
            ActiveEvents::COLLISION_EVENTS,
            PLAYER_COLLISION_GROUPS,
            Transform::from_translation(Vec3::new(0.0, -32.0, 0.0)),
        ))
        .id();

    let animator = SpriteAnimator::looping(PLAYER_CLIPS[0]);

    commands
        .spawn((
            Player::default(),
            RigidBody::Dynamic,
            LockedAxes::ROTATION_LOCKED,
            Velocity::zero(),
            Ccd::enabled(),
            YSort(0.0),
            animator,
            Sprite {
                image: assets.player_texture.clone(),
                texture_atlas: Some(TextureAtlas {
                    layout: assets.player_layout.clone(),
                    index: PLAYER_CLIPS[0].first_frame,
                }),
                ..default()
            },
            Transform::from_translation(PLAYER_SPAWN_POS).with_scale(PLAYER_SCALE),
        ))
        .add_child(collider);
}

pub struct PlayerSpawnPlugin;

impl Plugin for PlayerSpawnPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(GameState::Gaming), spawn_player);
    }
}
