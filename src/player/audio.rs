use std::time::Duration;

use bevy::audio::{AudioPlayer, AudioSink, PlaybackMode, PlaybackSettings, Volume};
use bevy::prelude::*;
use noisy_bevy::simplex_noise_2d_seeded;

use crate::{
    audio::PlaySound,
    GameAssets, GameState,
};

use super::{Player, PlayerState};

const RAND_SPEED_INTENSITY: f64 = 0.2;
const TIME_BETWEEN_STEPS_WALKING: f32 = 0.5;
const TIME_BETWEEN_STEPS_RUNNING: f32 = 0.4;
const WALK_VOLUME: f64 = 1.5;
const RUN_VOLUME: f64 = 2.0;

const BIRD_MAX_VOLUME: f64 = 1.0;
const BIRD_MIN_VOLUME: f32 = 0.1;
const NOISE_ZOOM: f32 = 0.02;
const SEED: f32 = 64.0;

#[derive(Resource, Deref, DerefMut)]
struct StepsTimer(Timer);

#[derive(Component)]
struct BirdSound;

impl Default for StepsTimer {
    fn default() -> Self {
        Self(Timer::from_seconds(
            TIME_BETWEEN_STEPS_WALKING,
            TimerMode::Repeating,
        ))
    }
}

fn spawn_bird_sound(mut commands: Commands, assets: Res<GameAssets>) {
    commands.spawn((
        AudioPlayer(assets.bird_sounds.clone()),
        PlaybackSettings {
            mode: PlaybackMode::Loop,
            volume: Volume::Linear(0.0),
            ..default()
        },
        BirdSound,
    ));
}

fn spawn_cricket_sound(assets: Res<GameAssets>, mut ev_play_sound: MessageWriter<PlaySound>) {
    ev_play_sound.write(PlaySound {
        clip: assets.cricket_sounds.clone(),
        volume: 0.35,
        repeat: true,
        ..default()
    });
}

fn update_bird_sound(time: Res<Time>, mut q_bird: Query<&mut AudioSink, With<BirdSound>>) {
    let noise = simplex_noise_2d_seeded(Vec2::ONE * time.elapsed_secs() * NOISE_ZOOM, SEED)
        .max(BIRD_MIN_VOLUME);
    let volume = noise as f64 * BIRD_MAX_VOLUME;
    for mut sink in q_bird.iter_mut() {
        sink.set_volume(Volume::Linear(volume as f32));
    }
}

fn tick_steps_timers(time: Res<Time>, mut steps_timer: ResMut<StepsTimer>) {
    steps_timer.tick(time.delta());
}

fn play_step_sounds(
    assets: Res<GameAssets>,
    mut steps_timer: ResMut<StepsTimer>,
    q_player: Query<&Player>,
    mut ev_play_sound: MessageWriter<PlaySound>,
) {
    let player_state = match q_player.single() {
        Ok(p) => p.state,
        Err(_) => return,
    };

    if !steps_timer.just_finished() {
        return;
    }

    let sound = match player_state {
        PlayerState::Walking => {
            steps_timer.set_duration(Duration::from_secs_f32(TIME_BETWEEN_STEPS_WALKING));
            Some(PlaySound {
                clip: assets.player_footstep.clone(),
                volume: WALK_VOLUME,
                rand_speed_intensity: RAND_SPEED_INTENSITY,
                ..default()
            })
        }
        PlayerState::Running => {
            steps_timer.set_duration(Duration::from_secs_f32(TIME_BETWEEN_STEPS_RUNNING));
            Some(PlaySound {
                clip: assets.player_footstep.clone(),
                volume: RUN_VOLUME,
                rand_speed_intensity: RAND_SPEED_INTENSITY,
                ..default()
            })
        }
        _ => None,
    };

    if let Some(s) = sound {
        ev_play_sound.write(s);
    }
}

pub struct PlayerAudioPlugin;

impl Plugin for PlayerAudioPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(
            Update,
            (
                update_bird_sound,
                (play_step_sounds, tick_steps_timers).run_if(in_state(GameState::Gaming)),
            ),
        )
        .init_resource::<StepsTimer>()
        .add_systems(
            OnEnter(GameState::Gaming),
            (spawn_bird_sound, spawn_cricket_sound),
        );
    }
}
