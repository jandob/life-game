use bevy::prelude::*;

use crate::GameState;

use super::chat::PlayerStartedChat;
use super::Player;

fn face_npc(
    mut q_player: Query<&mut Player>,
    mut ev_player_started_chat: MessageReader<PlayerStartedChat>,
) {
    for ev in ev_player_started_chat.read() {
        let mut player = match q_player.single_mut() {
            Ok(p) => p,
            Err(_) => return,
        };

        player.current_direction = ev.direction;
    }
}

pub struct PlayerMovementPlugin;

impl Plugin for PlayerMovementPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, face_npc.run_if(in_state(GameState::Gaming)));
    }
}
