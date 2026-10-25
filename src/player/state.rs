use bevy::prelude::*;
use bevy_yarnspinner::events::DialogueCompleted;

use crate::animation::{character_clip, play_character_clip, CharacterAnim, SpriteAnimator};
use crate::story::scripted::ScriptedWalk;
use crate::story::transition::QueuedScene;
use crate::world::side_view::ClickWalk;
use crate::GameState;

use super::{chat::PlayerStoppedChat, Player};

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
    queued: Option<Res<QueuedScene>>,
    mut q_player: Query<&mut Player>,
) {
    // The next scene starts right away; the player stays in the conversation.
    if queued.is_some_and(|q| q.0.is_some()) {
        return;
    }
    if let Ok(mut player) = q_player.single_mut() {
        player.state = PlayerState::Idling;
    }
}

/// Idle unless a click (which sets walking or running) or a scene walks the player.
fn switch_player_move_state(mut q_player: Query<(&mut Player, Has<ClickWalk>, Has<ScriptedWalk>)>) {
    let Ok((mut player, click_walk, scripted_walk)) = q_player.single_mut() else {
        return;
    };
    if player.state == PlayerState::Talking || click_walk {
        return;
    }
    player.state = if scripted_walk {
        PlayerState::Walking
    } else {
        PlayerState::Idling
    };
}

fn update_animation(
    mut q_player: Query<(&mut SpriteAnimator, &mut Sprite, &Player, Has<ScriptedWalk>)>,
) {
    let (mut animator, mut sprite, player, walking_scripted) = match q_player.single_mut() {
        Ok(r) => r,
        Err(_) => return,
    };

    let anim = match player.state {
        PlayerState::Talking if walking_scripted => CharacterAnim::Walk,
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
                    switch_to_idling_from_talking.run_if(on_message::<PlayerStoppedChat>),
                    switch_player_move_state,
                    update_animation,
                )
                    .chain()
                    .run_if(in_state(GameState::Gaming)),
            );
    }
}
