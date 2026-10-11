//! A non-talkable NPC that wanders randomly around her home.

use std::time::Duration;

use bevy::prelude::*;
use bevy_rapier2d::{dynamics::Velocity, plugin::PhysicsSet, prelude::*};
use rand::{thread_rng, Rng};

use crate::animation::{
    character_clip, play_character_clip, CharacterAnim, SpriteAnimator, CHARACTER_CLIPS,
};
use crate::world::camera::YSort;
use crate::world::map::tiled_map::TiledMap;
use crate::world::MainCamera;
use crate::{GameAssets, GameState};

const SCALE: Vec3 = Vec3::splat(0.5);
/// Collider centre relative to the transform (child at y = -32, parent scale 0.5).
const FEET_OFFSET: Vec2 = Vec2::new(0.0, -16.0);
const WANDER_RADIUS: f32 = 96.0;
const WALK_SPEED: f32 = 60.0;
const ARRIVE_DISTANCE: f32 = 4.0;
const PAUSE_SECONDS: (f32, f32) = (2.0, 5.0);
const TARGET_TRIES: usize = 8;
const PATH_SAMPLES: usize = 4;
const STUCK_SECONDS: f32 = 1.5;
const STUCK_PROGRESS: f32 = 2.0;
/// Water colliders only exist near the camera; stand still beyond this distance.
const MAX_CAMERA_DISTANCE: f32 = 640.0;
const TILE: f32 = 16.0;
/// Extra clearance (roughly her collider radius) checked around a point.
const CLEARANCE: f32 = 8.0;

#[derive(Component)]
pub struct Wanderer {
    home: Vec2,
    target: Option<Vec2>,
    pause: Timer,
    facing: Vec2,
    best_dist: f32,
    stuck: Timer,
}

impl Wanderer {
    fn new(home: Vec2) -> Self {
        Self {
            home,
            target: None,
            pause: random_pause(),
            facing: Vec2::NEG_Y,
            best_dist: f32::MAX,
            stuck: Timer::from_seconds(STUCK_SECONDS, TimerMode::Once),
        }
    }
}

fn random_pause() -> Timer {
    let secs = thread_rng().gen_range(PAUSE_SECONDS.0..PAUSE_SECONDS.1);
    Timer::new(Duration::from_secs_f32(secs), TimerMode::Once)
}

fn spawn_wanderer(mut commands: Commands, assets: Res<GameAssets>, tiled_map: Res<TiledMap>) {
    let find = |layer: &str, name: &str| {
        tiled_map
            .object_layer(layer)
            .iter()
            .find(|obj| obj.name == name)
            .map(|obj| tiled_map.tiled_to_game(obj.x, obj.y))
    };
    let pos = find("NPCs", "Wanderer")
        .or_else(|| find("Spawn", "SpawnPoint").map(|p| p + Vec2::new(48.0, 0.0)))
        .unwrap_or(Vec2::ZERO);

    let collider = commands
        .spawn((
            Collider::ball(16.0),
            CollisionGroups::default(),
            Transform::from_translation(Vec3::new(0.0, -32.0, 0.0)),
        ))
        .id();

    let clip = CHARACTER_CLIPS[0];
    commands
        .spawn((
            Wanderer::new(pos),
            RigidBody::Dynamic,
            LockedAxes::ROTATION_LOCKED,
            Velocity::zero(),
            YSort(0.0),
            SpriteAnimator::looping(clip),
            Sprite {
                image: assets.wanderer_texture.clone(),
                texture_atlas: Some(TextureAtlas {
                    layout: assets.wanderer_layout.clone(),
                    index: clip.first_frame,
                }),
                ..default()
            },
            Transform::from_translation(pos.extend(0.0)).with_scale(SCALE),
        ))
        .add_child(collider);
}

/// Whether the spot where her feet would stand is free of tile colliders and inside the map.
fn is_free(map: &TiledMap, pos: Vec2) -> bool {
    let feet = pos + FEET_OFFSET;
    if !map.world_bounds().contains(feet) {
        return false;
    }
    [
        Vec2::ZERO,
        Vec2::X * CLEARANCE,
        Vec2::NEG_X * CLEARANCE,
        Vec2::Y * CLEARANCE,
        Vec2::NEG_Y * CLEARANCE,
    ]
    .iter()
    .all(|offset| {
        let tile = ((feet + *offset) / TILE).round();
        !map.has_collision(tile.x as i32, tile.y as i32)
    })
}

fn pick_target(map: &TiledMap, from: Vec2, home: Vec2) -> Option<Vec2> {
    let mut rng = thread_rng();
    for _ in 0..TARGET_TRIES {
        let angle = rng.gen_range(0.0..std::f32::consts::TAU);
        let dist = WANDER_RADIUS * rng.gen_range(0.0f32..1.0).sqrt();
        let target = home + Vec2::from_angle(angle) * dist;

        let clear = (0..=PATH_SAMPLES).all(|i| {
            let p = from.lerp(target, i as f32 / PATH_SAMPLES as f32);
            is_free(map, p)
        });
        if clear {
            return Some(target);
        }
    }
    None
}

fn wander(
    time: Res<Time>,
    tiled_map: Res<TiledMap>,
    q_camera: Query<&Transform, (With<MainCamera>, Without<Wanderer>)>,
    mut q_wanderer: Query<(&mut Wanderer, &Transform, &mut Velocity)>,
) {
    let camera = match q_camera.single() {
        Ok(c) => c.translation.truncate(),
        Err(_) => return,
    };

    for (mut wanderer, transform, mut velocity) in &mut q_wanderer {
        let pos = transform.translation.truncate();

        if pos.distance(camera) > MAX_CAMERA_DISTANCE {
            velocity.linear = Vec2::ZERO;
            continue;
        }

        let Some(target) = wanderer.target else {
            velocity.linear = Vec2::ZERO;
            wanderer.pause.tick(time.delta());
            if wanderer.pause.is_finished() {
                match pick_target(&tiled_map, pos, wanderer.home) {
                    Some(target) => {
                        wanderer.target = Some(target);
                        wanderer.best_dist = pos.distance(target);
                        wanderer.stuck.reset();
                    }
                    None => wanderer.pause = random_pause(),
                }
            }
            continue;
        };

        let to_target = target - pos;
        let dist = to_target.length();

        if dist <= ARRIVE_DISTANCE {
            wanderer.target = None;
            wanderer.pause = random_pause();
            velocity.linear = Vec2::ZERO;
            continue;
        }

        // Retarget when something (flora, another body) keeps her from getting closer.
        if dist < wanderer.best_dist - STUCK_PROGRESS {
            wanderer.best_dist = dist;
            wanderer.stuck.reset();
        } else if wanderer.stuck.tick(time.delta()).is_finished() {
            wanderer.target = None;
            wanderer.pause = random_pause();
            velocity.linear = Vec2::ZERO;
            continue;
        }

        let dir = to_target / dist;
        wanderer.facing = dir;
        velocity.linear = dir * WALK_SPEED;
    }
}

fn animate_wanderer(
    mut q_wanderer: Query<(&Wanderer, &Velocity, &mut SpriteAnimator, &mut Sprite)>,
) {
    for (wanderer, velocity, mut animator, mut sprite) in &mut q_wanderer {
        let anim = if velocity.linear.length() > 1.0 {
            CharacterAnim::Walk
        } else {
            CharacterAnim::Idle
        };
        let clip = character_clip(wanderer.facing, anim);
        play_character_clip(&mut animator, &mut sprite, clip);
    }
}

/// Without this she would keep drifting during the ending (no gravity, no damping).
fn stop_wanderer(mut q_wanderer: Query<&mut Velocity, With<Wanderer>>) {
    for mut velocity in &mut q_wanderer {
        velocity.linear = Vec2::ZERO;
    }
}

pub struct WanderPlugin;

impl Plugin for WanderPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(GameState::Gaming), spawn_wanderer)
            .add_systems(OnExit(GameState::Gaming), stop_wanderer)
            .add_systems(Update, wander.run_if(in_state(GameState::Gaming)))
            .add_systems(
                PostUpdate,
                animate_wanderer
                    .before(PhysicsSet::Writeback)
                    .run_if(in_state(GameState::Gaming)),
            );
    }
}
