use bevy::prelude::*;

use crate::animation::{SpriteAnimator, CHARACTER_CLIPS};
use crate::character::{character_transform, CHARACTER_Z};
use crate::story::scripted::Actor;
use crate::world::map::tiled_map::TiledMap;
use crate::{GameAssets, GameState};

use super::{FourWayFacing, Npc, NpcDialogue};

/// Only scripted commands move Samantha.
fn spawn_samantha(commands: &mut Commands, assets: &Res<GameAssets>, pos: Vec2, hidden: bool) {
    let clip = CHARACTER_CLIPS[0];
    let mut samantha = commands.spawn((
        Npc {
            id: NpcDialogue::Samantha,
        },
        Actor("Samantha".to_string()),
        FourWayFacing {
            facing: Vec2::NEG_Y,
        },
        SpriteAnimator::looping(clip),
        Sprite {
            image: assets.samantha_texture.clone(),
            texture_atlas: Some(TextureAtlas {
                layout: assets.samantha_layout.clone(),
                index: clip.first_frame,
            }),
            ..default()
        },
        character_transform(pos, CHARACTER_Z),
    ));
    if hidden {
        samantha.insert(Visibility::Hidden);
    }
}

/// Spawn NPCs from the "NPCs" object layer in the TiledMap.
/// Runs once on `OnEnter(GameState::Gaming)`.
fn spawn_npcs(mut commands: Commands, assets: Res<GameAssets>, tiled_map: Res<TiledMap>) {
    let npc_objects = tiled_map.object_layer("NPCs");
    if npc_objects.is_empty() {
        warn!("Map has no NPCs layer or it is empty, no NPCs spawn");
    }
    for obj in npc_objects {
        let pos = tiled_map.tiled_to_game(obj.x, obj.y);

        match obj.name.as_str() {
            "Samantha" => spawn_samantha(
                &mut commands,
                &assets,
                pos,
                obj.prop_bool("hidden").unwrap_or(false),
            ),
            _ => {
                warn!("Unknown NPC name: {}", obj.name);
            }
        }
    }
}

pub struct NpcSpawnPlugin;

impl Plugin for NpcSpawnPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(GameState::Gaming), (spawn_npcs,));
    }
}
