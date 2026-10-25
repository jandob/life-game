use bevy::prelude::*;
use bevy_yarnspinner::prelude::*;

use crate::{ui::dialogue::runner::RunnerFlags, GameState};

use super::{input::PlayerInput, Player, PlayerState};

/// Yarn node tag of scenes the player cannot leave with Escape.
const CUTSCENE_TAG: &str = "cutscene";

/// The player starts a conversation, e.g. by clicking a hotspot (see `world::side_view`).
#[derive(Message)]
pub struct PlayerStartedChat {
    pub node: String,
    pub direction: Vec2,
}
#[derive(Message)]
pub struct PlayerStoppedChat;

/// Whether the active conversation is in a node tagged `cutscene`.
fn in_cutscene(q_runners: &Query<(&DialogueRunner, &RunnerFlags)>) -> bool {
    q_runners
        .iter()
        .filter(|(_, flags)| flags.active)
        .any(|(runner, _)| {
            runner
                .current_node()
                .and_then(|node| runner.get_tags_for_node(&node))
                .is_some_and(|tags| tags.iter().any(|tag| tag == CUTSCENE_TAG))
        })
}

fn stop_chat(
    player_input: Res<PlayerInput>,
    q_player: Query<&Player>,
    q_runners: Query<(&DialogueRunner, &RunnerFlags)>,
    mut ev_player_stopped_chat: MessageWriter<PlayerStoppedChat>,
) {
    let player = match q_player.single() {
        Ok(r) => r,
        Err(_) => return,
    };

    if !player_input.escape {
        return;
    }

    if player.state != PlayerState::Talking {
        return;
    }

    if in_cutscene(&q_runners) {
        return;
    }

    ev_player_stopped_chat.write(PlayerStoppedChat);
}

pub struct PlayerChatPlugin;

impl Plugin for PlayerChatPlugin {
    fn build(&self, app: &mut App) {
        app.add_message::<PlayerStartedChat>()
            .add_message::<PlayerStoppedChat>()
            .add_systems(Update, stop_chat.run_if(in_state(GameState::Gaming)));
    }
}
