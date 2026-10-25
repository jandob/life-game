use std::time::Duration;

use bevy::prelude::*;
use bevy_tweening::{lens::*, *};

use crate::{
    npc::{Npc, NpcDialogue},
    player::Player,
    GameAssets, GameState,
};

const FADE_OUT_DURATION: f32 = 2.0;
const BLACK_OUT_FADE_DURATION: f32 = 4.5;
const BLACK_OUT_DELAY: f32 = 10.0;
const START_COLOR: Color = Color::srgba(0.0, 0.0, 0.0, 0.0);
const END_COLOR: Color = Color::srgba(0.0, 0.0, 0.0, 1.0);

/// The black sprite covers the rooms, foreground layers included (z 500 and up)...
const BLACK_SPRITE_Z: f32 = 600.0;
/// ...and the characters step in front of it.
const CHARACTER_ENDING_Z: f32 = 700.0;

/// Which ending sequence to play.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Ending {
    /// The end of the playable slice: "To be continued".
    Demo,
}

#[derive(Message)]
pub struct EndingTriggered {
    pub ending: Ending,
    /// A character to show above the black fade next to the player.
    pub npc: Option<NpcDialogue>,
}

fn bring_characters_forward(
    mut q_player: Query<&mut Transform, With<Player>>,
    mut q_npcs: Query<(&mut Transform, &Npc), Without<Player>>,
    mut ev_ending_triggered: MessageReader<EndingTriggered>,
) {
    let mut player = match q_player.single_mut() {
        Ok(r) => r,
        Err(_) => return,
    };

    for ev in ev_ending_triggered.read() {
        player.translation.z = CHARACTER_ENDING_Z;

        for (mut npc, id) in &mut q_npcs {
            if ev.npc == Some(id.id) {
                npc.translation.z = CHARACTER_ENDING_Z;
            }
        }
    }
}

/// This fades in a black sprite that covers everything except the two characters and some text.
fn fade_in_black_sprite(mut commands: Commands, assets: Res<GameAssets>) {
    let tween = Tween::new(
        EaseFunction::CubicIn,
        std::time::Duration::from_secs_f32(FADE_OUT_DURATION),
        SpriteColorLens {
            start: START_COLOR,
            end: END_COLOR,
        },
    );

    commands.spawn((
        TweenAnim::new(tween),
        Sprite {
            image: assets.white_pixel.clone(),
            color: START_COLOR,
            ..default()
        },
        Transform::from_xyz(0.0, 0.0, BLACK_SPRITE_Z).with_scale(Vec3::splat(10_000.0)),
    ));
}

/// This fades in a black screen that overlays everything.
/// It fades in after a delay
fn fade_in_black_screen(
    mut commands: Commands,
    time: Res<Time>,
    mut timer: Local<Timer>,
    mut is_started: Local<bool>,
    mut is_finished: Local<bool>,
) {
    if *is_finished {
        return;
    }

    if !*is_started {
        *is_started = true;
        timer.set_duration(Duration::from_secs_f32(BLACK_OUT_DELAY));
        timer.set_elapsed(Duration::ZERO);
    }

    timer.tick(time.delta());
    if !timer.just_finished() {
        return;
    }

    *is_finished = true;
    let tween = Tween::new(
        EaseFunction::QuadraticIn,
        std::time::Duration::from_secs_f32(BLACK_OUT_FADE_DURATION),
        UiBackgroundColorLens {
            start: START_COLOR,
            end: END_COLOR,
        },
    );

    commands.spawn((
        TweenAnim::new(tween),
        Node {
            width: Val::Vw(110.0),
            height: Val::Vh(110.0),
            ..default()
        },
        BackgroundColor(START_COLOR),
        ZIndex(100),
    ));
}

fn change_game_state(mut next_state: ResMut<NextState<GameState>>) {
    next_state.set(GameState::Ending);
}

pub struct EndingPlugin;

impl Plugin for EndingPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(
            Update,
            (
                bring_characters_forward.run_if(not(in_state(GameState::AssetLoading))),
                fade_in_black_sprite.run_if(
                    on_message::<EndingTriggered>.and_then(not(in_state(GameState::AssetLoading))),
                ),
                change_game_state.run_if(
                    on_message::<EndingTriggered>.and_then(not(in_state(GameState::AssetLoading))),
                ),
            ),
        )
        .add_message::<EndingTriggered>()
        .add_systems(
            Update,
            fade_in_black_screen.run_if(in_state(GameState::Ending)),
        );
    }
}
