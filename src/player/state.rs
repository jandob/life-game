use std::f32::consts::PI;

use bevy::prelude::*;
use bevy_rapier2d::{dynamics::Velocity, plugin::PhysicsSet};
use bevy_yarnspinner::events::DialogueCompleted;

use crate::animation::{SpriteAnimator, PLAYER_CLIPS};
use crate::GameState;

use super::{chat::PlayerStoppedChat, input::PlayerInput, Player};

// Used to make sure we always play up/down animation when player moves diagonally.
const MOVEMENT_ANIMATION_ANGLE_BUFFER: f32 = 0.05;

#[derive(Debug, Default, PartialEq, Clone, Copy)]
pub enum PlayerState {
    #[default]
    Idling,
    Walking,
    Running,
    Talking,
}

fn switch_to_idling_from_talking(mut q_player: Query<&mut Player>) {
    let mut player = match q_player.single_mut() {
        Ok(r) => r,
        Err(_) => return,
    };
    player.state = PlayerState::Idling;
}

fn switch_to_idling_from_talking_on_completed(
    _trigger: On<DialogueCompleted>,
    mut q_player: Query<&mut Player>,
) {
    if let Ok(mut player) = q_player.single_mut() {
        player.state = PlayerState::Idling;
    }
}

fn switch_player_move_state(
    player_input: Res<PlayerInput>,
    mut q_player: Query<(&Velocity, &mut Player)>,
) {
    let (velocity, mut player) = match q_player.single_mut() {
        Ok(p) => p,
        Err(_) => return,
    };

    if player.state == PlayerState::Talking {
        return;
    }

    let state = if velocity.linear == Vec2::ZERO {
        PlayerState::Idling
    } else if player_input.running {
        PlayerState::Running
    } else {
        PlayerState::Walking
    };
    player.state = state;
}

fn update_animation(mut q_player: Query<(&mut SpriteAnimator, &mut Sprite, &Player)>) {
    let (mut animator, mut sprite, player) = match q_player.single_mut() {
        Ok(r) => r,
        Err(_) => return,
    };

    let dir = if player.current_direction == Vec2::ZERO {
        Vec2::NEG_X
    } else {
        player.current_direction
    };

    let angle = Vec2::X.angle_to(dir);
    let direction_index = if (-3.0 / 4.0 * PI - MOVEMENT_ANIMATION_ANGLE_BUFFER
        ..=-1.0 / 4.0 * PI + MOVEMENT_ANIMATION_ANGLE_BUFFER)
        .contains(&angle)
    {
        // Down
        0
    } else if (1.0 / 4.0 * PI - MOVEMENT_ANIMATION_ANGLE_BUFFER
        ..=3.0 / 4.0 * PI + MOVEMENT_ANIMATION_ANGLE_BUFFER)
        .contains(&angle)
    {
        // Up
        3
    } else if !(-3.0 / 4.0 * PI..=3.0 / 4.0 * PI).contains(&angle) {
        // Left
        1
    } else {
        // Right
        2
    };

    let clip = match player.state {
        PlayerState::Idling => PLAYER_CLIPS[direction_index],
        PlayerState::Walking => PLAYER_CLIPS[4 + direction_index],
        PlayerState::Running => PLAYER_CLIPS[8 + direction_index],
        PlayerState::Talking => PLAYER_CLIPS[direction_index],
    };

    // Set the atlas index immediately when switching clips, so the sprite
    // doesn't show a stale frame from the old clip until the next timer tick.
    if animator.clip != clip {
        if let Some(atlas) = &mut sprite.texture_atlas {
            atlas.index = clip.first_frame;
        }
    }

    animator.play(clip);
}

pub struct PlayerStatePlugin;

impl Plugin for PlayerStatePlugin {
    fn build(&self, app: &mut App) {
        app.add_observer(switch_to_idling_from_talking_on_completed)
            .add_systems(
                PostUpdate,
                (
                    switch_to_idling_from_talking
                        .run_if(on_message::<PlayerStoppedChat>),
                    switch_player_move_state,
                    update_animation,
                )
                    .chain()
                    .before(PhysicsSet::Writeback)
                    .run_if(in_state(GameState::Gaming)),
            );
    }
}
