use bevy::prelude::*;
use bevy_rapier2d::prelude::*;

use crate::character::LEGACY;
use crate::animation::{SpriteAnimator, CHARACTER_CLIPS};
use crate::story::scripted::Actor;
use crate::world::camera::YSort;
use crate::world::map::tiled_map::TiledMap;
use crate::{GameAssets, GameState};

use super::{Player, PLAYER_COLLISION_GROUPS};

fn spawn_player(mut commands: Commands, assets: Res<GameAssets>, tiled_map: Res<TiledMap>) {
    // Read the spawn point from the "Spawn" object layer in TiledMap
    let spawn_objects = tiled_map.object_layer("Spawn");
    let spawn_pos: Vec2 = spawn_objects
        .iter()
        .find(|obj| obj.name == "SpawnPoint")
        .map(|obj| {
            tiled_map.tiled_to_game(obj.x, obj.y)
        })
        .unwrap_or(Vec2::ZERO); // Fallback: origin

    let collider = commands
        .spawn((
            LEGACY.feet_collider(),
            ActiveEvents::COLLISION_EVENTS,
            PLAYER_COLLISION_GROUPS,
        ))
        .id();

    let animator = SpriteAnimator::looping(CHARACTER_CLIPS[0]);

    commands
        .spawn((
            Player::default(),
            Actor("Player".to_string()),
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
                    index: CHARACTER_CLIPS[0].first_frame,
                }),
                ..default()
            },
            LEGACY.transform(spawn_pos),
        ))
        .add_child(collider);
}

pub struct PlayerSpawnPlugin;

impl Plugin for PlayerSpawnPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(GameState::Gaming), spawn_player);
    }
}