use std::collections::HashSet;

use rand::{thread_rng, Rng};

use bevy::audio::{AudioPlayer, AudioSource, PlaybackMode, PlaybackSettings, Volume};
use bevy::prelude::*;

use crate::GameState;

#[derive(Message)]
pub struct PlaySound {
    pub clip: Handle<AudioSource>,
    pub volume: f64,
    /// Playback rate, default is 1.0.
    pub playback_rate: f64,
    /// Playback offset intensity. This will add a random offset
    /// to the playback rate by this intensity.
    /// Useful for pitch shifting a sound by a certain range.
    pub rand_speed_intensity: f64,
    pub repeat: bool,
}

impl Default for PlaySound {
    fn default() -> Self {
        Self {
            clip: Handle::default(),
            volume: 1.0,
            playback_rate: 1.0,
            rand_speed_intensity: 0.0,
            repeat: false,
        }
    }
}

fn play_sounds(mut commands: Commands, mut ev_play_sound: MessageReader<PlaySound>) {
    let mut rng = thread_rng();
    let mut added_sounds: HashSet<Handle<AudioSource>> = HashSet::new();

    for ev in ev_play_sound.read() {
        if added_sounds.contains(&ev.clip) {
            continue;
        }
        added_sounds.insert(ev.clip.clone());

        let speed_offset = if ev.rand_speed_intensity == 0.0 {
            0.0
        } else {
            rng.gen_range(-1.0..1.0) * ev.rand_speed_intensity
        };

        commands.spawn((
            AudioPlayer(ev.clip.clone()),
            PlaybackSettings {
                mode: if ev.repeat {
                    PlaybackMode::Loop
                } else {
                    PlaybackMode::Despawn
                },
                volume: Volume::Linear(ev.volume as f32),
                speed: (ev.playback_rate + speed_offset) as f32,
                ..default()
            },
        ));
    }
}

pub struct GameSoundPlugin;

impl Plugin for GameSoundPlugin {
    fn build(&self, app: &mut App) {
        app.add_message::<PlaySound>().add_systems(
            Update,
            play_sounds.run_if(not(in_state(GameState::AssetLoading))),
        );
    }
}
