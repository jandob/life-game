use bevy::prelude::*;
use bevy_yarnspinner::prelude::*;

use crate::{
    player::{chat::PlayerStoppedChat, Player, PlayerState},
    world::ending::{Ending, EndingTriggered},
};

use super::runner::RunnerFlags;

pub fn stop_chat_command(
    In(_): In<()>,
    q_player: Query<&Player>,
    mut q_runner_flags: Query<&mut RunnerFlags>,
    mut ev_player_stopped_chat: MessageWriter<PlayerStoppedChat>,
) {
    let player = match q_player.single() {
        Ok(r) => r,
        Err(_) => return,
    };

    if player.state != PlayerState::Talking {
        error!("Got 'stop_chat_command' but player is not currently talking! Should never happend");
        return;
    }

    for mut flags in &mut q_runner_flags {
        if flags.active {
            // We are setting the line to `...` because you are always
            // supposed to follow a <<stop_chat>> with a `...`.
            // The reason we have to set this explicitely is because
            // the `PresentLine` doesn't fire quickly enough
            // and doesn't update the `flags.line` automatically.
            // This results in a problem with the displayed lines.
            flags.line = Some(LocalizedLine {
                id: LineId(String::new()),
                text: "...".to_string(),
                attributes: Vec::new(),
                metadata: Vec::new(),
                assets: LineAssets::new(),
            });
        }
    }

    ev_player_stopped_chat.write(PlayerStoppedChat);
}

/// `<<end_demo>>`: ends the slice with the end card.
pub fn end_demo_command(In(_): In<()>, mut ev_ending_triggered: MessageWriter<EndingTriggered>) {
    ev_ending_triggered.write(EndingTriggered {
        ending: Ending::Demo,
        npc: None,
    });
}
