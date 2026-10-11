use bevy::prelude::*;
use bevy_rapier2d::{dynamics::Velocity, plugin::PhysicsSet};
use bevy_yarnspinner::events::DialogueCompleted;

use crate::animation::{character_clip, play_character_clip, CharacterAnim, SpriteAnimator};
use crate::GameState;

use super::{chat::PlayerStoppedChat, input::PlayerInput, Player};

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

    let anim = match player.state {
        PlayerState::Idling | PlayerState::Talking => CharacterAnim::Idle,
        PlayerState::Walking => CharacterAnim::Walk,
        PlayerState::Running => CharacterAnim::Run,
    };

    let clip = character_clip(player.current_direction, anim);
    play_character_clip(&mut animator, &mut sprite, clip);
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
