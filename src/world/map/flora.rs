use std::collections::HashSet;

use rand::{thread_rng, Rng};

use bevy::prelude::*;
use bevy_hanabi::prelude::*;
use bevy_rapier2d::prelude::*;

use crate::{
    npc::Npc,
    ui::keyboard_hint::{KeyboardHint, KEYBOARD_ICON_RADIUS},
    world::camera::{YSort, YSortStatic, YSortStaticChild},
    GameAssets, GameState,
};

use super::{
    chunk_manager::{DespawnedChunk, SpawnedChunk},
    generation::BitMap,
    poisson_sampling::generate_poisson_points_variable_radii,
    CHUNK_SIZE, TILE_SIZE,
};

const ROCKS_COUNT: usize = 3;

const REJECTION_ITER: usize = 20;
const MIN_RADIUS: f32 = 1.0;
const MAX_RADIUS: f32 = 4.0;

const TREE_RADIUS: f32 = 3.0;
const BUSH_1_RADIUS: f32 = 2.25;
const BUSH_2_RADIUS: f32 = 1.25;
const ROCK_RADIUS: f32 = 1.15;

const NPC_FLORA_RADIUS: f32 = 64.0;

// The petal effect renders on this z to always stay above world sprites (in front of the tree).
// In the 2D camera, near plane is at z=-1000, so negative z = closer to camera = on top.
const PETAL_Z: f32 = -100.0;

#[derive(Component)]
struct SakuraPetal;

/// Links a petal effect entity to its parent Flora for cleanup.
#[derive(Component)]
struct PetalSpawner(Entity);

#[derive(Component)]
struct Flora {
    chunk_pos: IVec2,
}

impl Flora {
    fn new(chunk_pos: IVec2) -> Self {
        Self { chunk_pos }
    }
}

fn spawn_rock(commands: &mut Commands, assets: &Res<GameAssets>, chunk_pos: IVec2, pos: Vec3) {
    let collider = commands
        .spawn((
            Collider::cuboid(8.0, 8.0),
            Transform::from_translation(Vec3::new(0.0, 0.0, 0.0)),
        ))
        .id();

    let mut rng = thread_rng();

    commands
        .spawn((
            Flora::new(chunk_pos),
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
    chunk_pos: IVec2,
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
            Flora::new(chunk_pos),
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
    // Each particle gets a random velocity:
    //   x: [-60, 60] px/s  — random left/right spread
    //   y: [-50, -10] px/s  — always downward, gentle
    //   z: 0
    // This keeps particles on-screen near the tree crown while producing
    // multi-directional outward spread.
    let velocity = (
        writer.rand(VectorType::VEC3F) * writer.lit(Vec3::new(120.0, 40.0, 0.0))
        + writer.lit(Vec3::new(-60.0, -50.0, 0.0))
    ).expr();
    let init_velocity = SetAttributeModifier::new(Attribute::VELOCITY, velocity);

    // Spawn in a small region around the tree crown. The effect entity is placed at the
    // tree top (z ≈ 100), so this keeps petals near the crown.
    let init_position = SetAttributeModifier::new(
        Attribute::POSITION,
        (writer.rand(VectorType::VEC3F) * writer.lit(Vec3::splat(32.0))
            - writer.lit(Vec3::splat(16.0)))
            .expr(),
    );

    let texture_slot = writer.lit(0u32).expr();

    // Gentle drag so particles decelerate over time, producing a natural
    // lazy-drift feel instead of constant-speed motion.
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
    chunk_pos: IVec2,
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
            Flora::new(chunk_pos),
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

fn spawn_flora(
    commands: &mut Commands,
    assets: &Res<GameAssets>,
    effects: &mut Assets<EffectAsset>,
    bitmap: &mut ResMut<BitMap>,
    chunk_pos: IVec2,
    ipos: IVec2,
    radius: f32,
) {
    let v = IVec2::new(
        ipos.x + chunk_pos.x * CHUNK_SIZE as i32,
        ipos.y + chunk_pos.y * CHUNK_SIZE as i32,
    );
    let pos = TILE_SIZE * Vec3::new(v.x as f32, v.y as f32, 0.0);

    if v.x.unsigned_abs() % CHUNK_SIZE == 0 || v.y.unsigned_abs() % CHUNK_SIZE == 0 {
        return;
    }
    if radius > TREE_RADIUS {
        if !(bitmap.get_flora_flag(v)
            && bitmap.get_flora_flag(v + IVec2::new(1, 0))
            && bitmap.get_flora_flag(v + IVec2::new(0, 1))
            && bitmap.get_flora_flag(v + IVec2::new(1, 1))
            && bitmap.get_flora_flag(v + IVec2::new(2, 0))
            && bitmap.get_flora_flag(v + IVec2::new(-2, 0)))
        {
            return;
        }
        spawn_tree(commands, assets, effects, chunk_pos, pos);
    } else if radius > BUSH_1_RADIUS {
        if !(bitmap.get_flora_flag(v)
            && bitmap.get_flora_flag(v - IVec2::Y)
            && bitmap.get_flora_flag(v + IVec2::X)
            && bitmap.get_flora_flag(v - IVec2::X))
        {
            return;
        }
        spawn_bush(commands, assets, chunk_pos, pos, 0);
    } else if radius > BUSH_2_RADIUS {
        if !(bitmap.get_flora_flag(v) && bitmap.get_flora_flag(v - IVec2::Y)) {
            return;
        }
        spawn_bush(commands, assets, chunk_pos, pos, 1);
    } else if radius > ROCK_RADIUS {
        if !bitmap.get_flora_flag(v) {
            return;
        }
        spawn_rock(commands, assets, chunk_pos, pos);
    }
}

fn spawn_flora_chunks(
    mut commands: Commands,
    assets: Res<GameAssets>,
    mut effects: ResMut<Assets<EffectAsset>>,
    mut bitmap: ResMut<BitMap>,
    mut ev_spawned_chunk: MessageReader<SpawnedChunk>,
) {
    for ev in ev_spawned_chunk.read() {
        let seed =
            bitmap.seed() as u64 + ev.pos.x.unsigned_abs() as u64 + ev.pos.y.unsigned_abs() as u64;

        // Because we discretize our positions here, we have to make sure that no two
        // flora positions map to the same IVec2.
        // We filter out any duplicates with a HashSet.
        let mut unique_points = HashSet::new();
        let points_with_radius: Vec<(IVec2, f32)> = generate_poisson_points_variable_radii(
            MIN_RADIUS,
            MAX_RADIUS,
            CHUNK_SIZE as f32 * Vec2::ONE,
            REJECTION_ITER,
            seed,
        )
        .into_iter()
        .map(|p_r| {
            let v = IVec2::new(p_r.x.floor() as i32, p_r.y.floor() as i32);
            (v, p_r.z)
        })
        .filter(|(p, _)| unique_points.insert(*p))
        .collect();

        for (p, r) in points_with_radius {
            spawn_flora(&mut commands, &assets, &mut effects, &mut bitmap, ev.pos, p, r);
        }
    }
}

fn despawn_flora_chunks(
    mut commands: Commands,
    q_floras: Query<(Entity, &Flora, Option<&PetalSpawner>)>,
    mut ev_despawned_chunk: MessageReader<DespawnedChunk>,
) {
    for ev in ev_despawned_chunk.read() {
        for (entity, flora, petal_spawner) in &q_floras {
            if flora.chunk_pos == ev.chunk_pos {
                if let Some(petal_spawner) = petal_spawner {
                    commands.entity(petal_spawner.0).despawn();
                }
                commands.entity(entity).despawn();
            }
        }
    }
}

fn despawn_flora_around_start_hint(
    mut commands: Commands,
    q_keyboard_icon: Query<&Transform, (With<KeyboardHint>, Without<Flora>)>,
    q_floras: Query<(Entity, &Transform, Option<&PetalSpawner>), Added<Flora>>,
) {
    let start_hint_transform = match q_keyboard_icon.single() {
        Ok(r) => r,
        Err(_) => return,
    };

    for (entity, flora_transform, petal_spawner) in &q_floras {
        if flora_transform
            .translation
            .distance_squared(start_hint_transform.translation)
            <= KEYBOARD_ICON_RADIUS.powi(2)
        {
            if let Some(petal_spawner) = petal_spawner {
                commands.entity(petal_spawner.0).despawn();
            }
            commands.entity(entity).despawn();
        }
    }
}

fn despawn_flora_around_npcs(
    mut commands: Commands,
    q_npcs: Query<&Transform, (With<Npc>, Without<Flora>)>,
    q_floras: Query<(Entity, &Transform, Option<&PetalSpawner>), Added<Flora>>,
) {
    for (entity, flora_transform, petal_spawner) in &q_floras {
        for npc_transform in &q_npcs {
            if flora_transform
                .translation
                .distance_squared(npc_transform.translation)
                <= NPC_FLORA_RADIUS.powi(2)
            {
                if let Some(petal_spawner) = petal_spawner {
                    commands.entity(petal_spawner.0).despawn();
                }
                commands.entity(entity).despawn();
            }
        }
    }
}

pub struct FloraPlugin;

impl Plugin for FloraPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(
            Update,
            (
                spawn_flora_chunks,
                despawn_flora_chunks,
                despawn_flora_around_start_hint,
                despawn_flora_around_npcs,
            )
                .run_if(in_state(GameState::Gaming)),
        );
    }
}
