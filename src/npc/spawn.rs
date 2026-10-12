use bevy::prelude::*;
use bevy_rapier2d::prelude::*;

use crate::animation::{SpriteAnimator, CHARACTER_CLIPS};
use crate::character::LEGACY;
use crate::story::scripted::Actor;
use crate::utils::COLLISION_GROUPS_NONE;
use crate::world::map::tiled_map::TiledMap;
use crate::{world::camera::YSort, GameAssets, GameState};

use super::{FourWayFacing, Npc, NpcDialogue};

/// Samantha is a kinematic body: only scripted commands move her, she never gets
/// pushed, and she pushes the player aside.
fn spawn_samantha(commands: &mut Commands, assets: &Res<GameAssets>, pos: Vec2, hidden: bool) {
    let mut collider = commands.spawn((
        LEGACY.feet_collider(),
        // Scripted scenes walk her and the player side by side through doorways;
        // a solid kinematic body there would shove him into the walls.
        COLLISION_GROUPS_NONE,
    ));
    if hidden {
        collider.insert(ColliderDisabled);
    }
    let collider = collider.id();

    let clip = CHARACTER_CLIPS[0];
    let mut samantha = commands.spawn((
        Npc {
            id: NpcDialogue::Samantha,
        },
        Actor("Samantha".to_string()),
        FourWayFacing {
            facing: Vec2::NEG_Y,
        },
        RigidBody::KinematicPositionBased,
        YSort(0.0),
        SpriteAnimator::looping(clip),
        Sprite {
            image: assets.samantha_texture.clone(),
            texture_atlas: Some(TextureAtlas {
                layout: assets.samantha_layout.clone(),
                index: clip.first_frame,
            }),
            ..default()
        },
        LEGACY.transform(pos),
    ));
    if hidden {
        samantha.insert(Visibility::Hidden);
    }
    samantha.add_child(collider);
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
            // Spawned by `wander::spawn_wanderer`, which reads this object itself.
            "Wanderer" => {}
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
