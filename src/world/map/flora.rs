use rand::{thread_rng, Rng};

use bevy::prelude::*;
use bevy_hanabi::prelude::*;
use bevy_rapier2d::prelude::*;

use crate::{
    world::camera::{YSort, YSortStatic, YSortStaticChild},
    GameAssets, GameState,
};

use super::tiled_map::TiledMap;

const ROCKS_COUNT: usize = 3;

// The petal effect renders on this z to always stay above world sprites (in front of the tree).
// In the 2D camera, near plane is at z=-1000, so negative z = closer to camera = on top.
const PETAL_Z: f32 = -100.0;

#[derive(Component)]
struct SakuraPetal;

/// Links a petal effect entity to its parent Flora for cleanup.
#[derive(Component)]
struct PetalSpawner(Entity);

/// Marker component for flora entities spawned from Tiled object layers.
#[derive(Component)]
struct Flora;

fn spawn_rock(
    commands: &mut Commands,
    assets: &Res<GameAssets>,
    pos: Vec3,
) {
    let collider = commands
        .spawn((
            Collider::cuboid(8.0, 8.0),
            Transform::from_translation(Vec3::new(0.0, 0.0, 0.0)),
        ))
        .id();

    let mut rng = thread_rng();

    commands
        .spawn((
            Flora,
            YSort(-8.0),
            Sprite {
                image: assets.rocks_texture.clone(),
                texture_atlas: Some(TextureAtlas {
                    layout: assets.rocks_layout.clone(),
                    index: rng.gen_range(0..ROCKS_COUNT),
                }),
                ..default()
            },
            Transform::from_translation(pos),
        ))
        .add_children(&[collider]);
}

fn spawn_bush(
    commands: &mut Commands,
    assets: &Res<GameAssets>,
    pos: Vec3,
    index: usize,
) {
    let texture = if index == 0 {
        assets.bush1.clone()
    } else {
        assets.bush2.clone()
    };
    let c = if index == 0 {
        Collider::cuboid(16.0, 8.0)
    } else {
        Collider::cuboid(8.0, 8.0)
    };

    let collider = commands
        .spawn((
            c,
            Transform::from_translation(Vec3::new(0.0, -8.0, 0.0)),
        ))
        .id();

    commands
        .spawn((
            Flora,
            YSort(0.0),
            Sprite {
                image: texture,
                ..default()
            },
            Transform::from_translation(pos),
        ))
        .add_children(&[collider]);
}

/// Builds the looping sakura petal effect, spawning ~4 particles per second at the
/// tree position, drifting outward/downward in random directions with a gentle wobble,
/// fading in and out.
fn build_petal_effect() -> EffectAsset {
    let writer = ExprWriter::new();

    // Age starts at a random [0, 1] fraction so petals don't all spawn in sync.
    let init_age = SetAttributeModifier::new(Attribute::AGE, writer.rand(ScalarType::Float).expr());

    // Lifetime roughly in [0.5, 2.5]s.
    let lifetime = (writer.lit(1.0) + (writer.rand(ScalarType::Float) - writer.lit(0.5)) * writer.lit(2.0)).expr();
    let init_lifetime = SetAttributeModifier::new(Attribute::LIFETIME, lifetime);

    // Random outward direction with gentle downward drift.
    let velocity = (
        writer.rand(VectorType::VEC3F) * writer.lit(Vec3::new(120.0, 40.0, 0.0))
        + writer.lit(Vec3::new(-60.0, -50.0, 0.0))
    ).expr();
    let init_velocity = SetAttributeModifier::new(Attribute::VELOCITY, velocity);

    let init_position = SetAttributeModifier::new(
        Attribute::POSITION,
        (writer.rand(VectorType::VEC3F) * writer.lit(Vec3::splat(32.0))
            - writer.lit(Vec3::splat(16.0)))
            .expr(),
    );

    let texture_slot = writer.lit(0u32).expr();

    let drag = writer.lit(0.5_f32).expr();

    let mut module = writer.finish();
    module.add_texture_slot("petal");

    let mut color_gradient = bevy_hanabi::Gradient::new();
    color_gradient.add_key(0.0, Vec4::new(1.0, 1.0, 1.0, 0.0));
    color_gradient.add_key(0.3, Vec4::ONE);
    color_gradient.add_key(0.8, Vec4::ONE);
    color_gradient.add_key(0.95, Vec4::new(1.0, 1.0, 1.0, 0.0));
    color_gradient.add_key(1.0, Vec4::new(1.0, 1.0, 1.0, 0.0));

    EffectAsset::new(
        32768,
        SpawnerSettings::rate(4.0.into()),
        module,
    )
    .with_name("sakura_petal")
    .init(init_age)
    .init(init_lifetime)
    .init(init_velocity)
    .init(init_position)
    .render(ParticleTextureModifier {
        texture_slot,
        sample_mapping: ImageSampleMapping::Modulate,
    })
    .render(ColorOverLifetimeModifier::new(color_gradient))
    .render(SizeOverLifetimeModifier {
        gradient: bevy_hanabi::Gradient::constant(Vec3::splat(16.0)),
        screen_space_size: true,
    })
    .update(LinearDragModifier { drag })
}

fn spawn_tree(
    commands: &mut Commands,
    assets: &Res<GameAssets>,
    effects: &mut Assets<EffectAsset>,
    pos: Vec3,
) {
    let pos = pos + Vec3::new(0.0, 48.0, 0.0);

    let mut rng = thread_rng();

    let trunk = commands
        .spawn((
            YSortStaticChild(16.1),
            Sprite {
                image: assets.tree_trunk.clone(),
                ..default()
            },
        ))
        .id();

    let shadow = commands
        .spawn((
            YSortStaticChild(64.0),
            Sprite {
                image: assets.tree_shadow.clone(),
                ..default()
            },
        ))
        .id();

    let collider = commands
        .spawn((
            Collider::cuboid(16.0, 8.0),
            Transform::from_translation(Vec3::new(0.0, -48.0, 0.0)),
        ))
        .id();

    let petal_effect = effects.add(build_petal_effect());
    let petal_pos = Vec3::new(pos.x, pos.y, PETAL_Z);
    let tree_petals = commands
        .spawn((
            SakuraPetal,
            ParticleEffect {
                handle: petal_effect,
                prng_seed: Some(rng.gen()),
            },
            EffectMaterial {
                images: vec![assets.tree_petal.clone()],
            },
            Transform::from_translation(petal_pos),
        ))
        .id();

    commands
        .spawn((
            Flora,
            PetalSpawner(tree_petals),
            YSortStatic(40.0),
            Sprite {
                image: assets.tree.clone(),
                ..default()
            },
            Transform::from_translation(pos),
        ))
        .add_children(&[trunk, shadow, collider]);
}

/// Spawn flora from the "Flora" object layer in the TiledMap.
/// Runs once on `OnEnter(GameState::Gaming)`.
fn spawn_flora_from_tiled(
    mut commands: Commands,
    assets: Res<GameAssets>,
    mut effects: ResMut<Assets<EffectAsset>>,
    tiled_map: Res<TiledMap>,
) {
    let flora_objects = tiled_map.object_layer("Flora");
    for obj in flora_objects {
        let pos = tiled_map.tiled_to_game(obj.x, obj.y).extend(0.0);

        match obj.obj_type.as_str() {
            "tree" => {
                spawn_tree(&mut commands, &assets, &mut effects, pos);
            }
            "bush1" => {
                spawn_bush(&mut commands, &assets, pos, 0);
            }
            "bush2" => {
                spawn_bush(&mut commands, &assets, pos, 1);
            }
            "rock" => {
                spawn_rock(&mut commands, &assets, pos);
            }
            _ => {
                warn!("Unknown flora type: {}", obj.obj_type);
            }
        }
    }
}

// Flora despawn around NPCs: since flora is now authored in Tiled,
// NPC despawn is not needed — the map author places flora intentionally.
// Kept as a stub in case dynamic cleanup is needed later.

pub struct FloraPlugin;

impl Plugin for FloraPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(
            OnEnter(GameState::Gaming),
            (spawn_flora_from_tiled,),
        );
        // Flora despawn/cleanup systems from the original codebase
        // are not needed since flora is now authored in Tiled.
        // The map author intentionally places flora without overlap.
    }
}