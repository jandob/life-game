use bevy::prelude::*;
use bevy_rapier2d::prelude::*;

use crate::animation::{
    SpriteAnimator, ANTONIUS_IDLE, ELEONORE_IDLE, IONAS_IDLE, ISABELLE_IDLE, JOTEM_IDLE,
};
use crate::{
    world::{
        camera::{YSort, YSortChild},
        map::generation::BitMap,
    },
    GameAssets, GameState,
};

use super::{Npc, NpcDialogue};

fn spawn_eleonore(commands: &mut Commands, assets: &Res<GameAssets>, pos: Vec2) {
    let transform = Transform::from_translation(pos.extend(0.0));
    let animator = SpriteAnimator::looping(ELEONORE_IDLE);

    let shadow_animator = SpriteAnimator::looping(ELEONORE_IDLE);

    let shadow = commands
        .spawn((
            YSortChild(-26.0),
            shadow_animator,
            Sprite {
                image: assets.eleonore_shadow_texture.clone(),
                texture_atlas: Some(TextureAtlas {
                    layout: assets.eleonore_shadow_layout.clone(),
                    index: ELEONORE_IDLE.first_frame,
                }),
                ..default()
            },
            Transform::from_translation(Vec3::new(0.0, -25.0, 0.0)),
        ))
        .id();

    let collider = commands
        .spawn((
            Collider::ball(16.0),
            ActiveEvents::COLLISION_EVENTS,
            CollisionGroups::default(),
            Transform::from_translation(Vec3::new(0.0, -20.0, 0.0)),
        ))
        .id();

    commands
        .spawn((
            Npc::new(NpcDialogue::Eleonore),
            YSort(16.0),
            animator,
            Sprite {
                image: assets.eleonore_texture.clone(),
                texture_atlas: Some(TextureAtlas {
                    layout: assets.eleonore_layout.clone(),
                    index: ELEONORE_IDLE.first_frame,
                }),
                ..default()
            },
            transform,
        ))
        .add_children(&[collider, shadow]);
}

fn spawn_jotem(commands: &mut Commands, assets: &Res<GameAssets>, pos: Vec2) {
    let transform = Transform::from_translation(pos.extend(0.0));
    let animator = SpriteAnimator::looping(JOTEM_IDLE);

    let collider = commands
        .spawn((
            Collider::ball(16.0),
            ActiveEvents::COLLISION_EVENTS,
            CollisionGroups::default(),
            Transform::from_translation(Vec3::new(0.0, -16.0, 0.0)),
        ))
        .id();

    commands
        .spawn((
            Npc::new(NpcDialogue::Jotem),
            YSort(0.0),
            animator,
            Sprite {
                image: assets.jotem_texture.clone(),
                texture_atlas: Some(TextureAtlas {
                    layout: assets.jotem_layout.clone(),
                    index: JOTEM_IDLE.first_frame,
                }),
                ..default()
            },
            transform,
        ))
        .add_children(&[collider]);
}

fn spawn_isabelle(commands: &mut Commands, assets: &Res<GameAssets>, pos: Vec2) {
    let transform = Transform::from_translation(pos.extend(0.0));
    let animator = SpriteAnimator::looping(ISABELLE_IDLE);

    let collider = commands
        .spawn((
            Collider::ball(16.0),
            ActiveEvents::COLLISION_EVENTS,
            CollisionGroups::default(),
            Transform::from_translation(Vec3::new(0.0, -16.0, 0.0)),
        ))
        .id();

    commands
        .spawn((
            Npc::new(NpcDialogue::Isabelle),
            YSort(0.0),
            animator,
            Sprite {
                image: assets.isabelle_texture.clone(),
                texture_atlas: Some(TextureAtlas {
                    layout: assets.isabelle_layout.clone(),
                    index: ISABELLE_IDLE.first_frame,
                }),
                ..default()
            },
            transform,
        ))
        .add_children(&[collider]);
}

fn spawn_antonius(commands: &mut Commands, assets: &Res<GameAssets>, pos: Vec2) -> Entity {
    let transform = Transform::from_translation(pos.extend(0.0));
    let animator = SpriteAnimator::looping(ANTONIUS_IDLE);

    let collider = commands
        .spawn((
            Collider::ball(8.0),
            ActiveEvents::COLLISION_EVENTS,
            CollisionGroups::default(),
            Transform::from_translation(Vec3::new(0.0, -16.0, 0.0)),
        ))
        .id();

    commands
        .spawn((
            animator,
            Sprite {
                image: assets.antonius_texture.clone(),
                texture_atlas: Some(TextureAtlas {
                    layout: assets.antonius_layout.clone(),
                    index: ANTONIUS_IDLE.first_frame,
                }),
                ..default()
            },
            transform,
        ))
        .add_children(&[collider])
        .id()
}

fn spawn_ionas(commands: &mut Commands, assets: &Res<GameAssets>, pos: Vec2) -> Entity {
    let transform = Transform::from_translation(pos.extend(0.0));
    let animator = SpriteAnimator::looping(IONAS_IDLE);

    let collider = commands
        .spawn((
            Collider::ball(8.0),
            ActiveEvents::COLLISION_EVENTS,
            CollisionGroups::default(),
            Transform::from_translation(Vec3::new(0.0, -16.0, 0.0)),
        ))
        .id();

    commands
        .spawn((
            animator,
            Sprite {
                image: assets.ionas_texture.clone(),
                texture_atlas: Some(TextureAtlas {
                    layout: assets.ionas_layout.clone(),
                    index: IONAS_IDLE.first_frame,
                }),
                flip_x: true,
                ..default()
            },
            transform,
        ))
        .add_children(&[collider])
        .id()
}

fn spawn_antonius_and_ionas(commands: &mut Commands, assets: &Res<GameAssets>, pos: Vec2) {
    let offset = Vec2::new(-20.0, 0.0);
    let antonius = spawn_antonius(commands, assets, offset);
    let ionas = spawn_ionas(commands, assets, -offset);

    commands
        .spawn((
            YSort(0.0),
            Npc::new(NpcDialogue::IonasAndAntonius),
            Transform::from_translation(pos.extend(0.0)),
        ))
        .add_children(&[antonius, ionas]);
}

fn spawn_npcs(mut commands: Commands, bitmap: Res<BitMap>, assets: Res<GameAssets>) {
    let hotspots = bitmap.get_furthest_hotspots(4);
    let npcs = [
        spawn_eleonore,
        spawn_jotem,
        spawn_isabelle,
        spawn_antonius_and_ionas,
    ];

    for i in 0..hotspots.len() {
        npcs[i](&mut commands, &assets, hotspots[i]);
    }
}

pub struct NpcSpawnPlugin;

impl Plugin for NpcSpawnPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(GameState::Gaming), (spawn_npcs,));
    }
}
