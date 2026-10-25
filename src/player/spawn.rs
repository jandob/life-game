use bevy::prelude::*;

use crate::animation::{SpriteAnimator, CHARACTER_CLIPS};
use crate::character::{character_transform, PLAYER_Z};
use crate::story::scripted::Actor;
use crate::world::map::tiled_map::TiledMap;
use crate::{GameAssets, GameState};

use super::Player;

fn spawn_player(mut commands: Commands, assets: Res<GameAssets>, tiled_map: Res<TiledMap>) {
    // Read the spawn point from the "Spawn" object layer in TiledMap
    let spawn_objects = tiled_map.object_layer("Spawn");
    let spawn_pos: Vec2 = spawn_objects
        .iter()
        .find(|obj| obj.name == "SpawnPoint")
        .map(|obj| tiled_map.tiled_to_game(obj.x, obj.y))
        .unwrap_or(Vec2::ZERO); // Fallback: origin

    let animator = SpriteAnimator::looping(CHARACTER_CLIPS[0]);

    commands.spawn((
        Player::default(),
        Actor("Player".to_string()),
        animator,
        Sprite {
            image: assets.player_texture.clone(),
            texture_atlas: Some(TextureAtlas {
                layout: assets.player_layout.clone(),
                index: CHARACTER_CLIPS[0].first_frame,
            }),
            ..default()
        },
        character_transform(spawn_pos, PLAYER_Z),
    ));
}

pub struct PlayerSpawnPlugin;

impl Plugin for PlayerSpawnPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(GameState::Gaming), spawn_player);
    }
}
