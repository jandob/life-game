pub mod chat;
pub mod input;
pub mod state;

mod audio;
mod movement;
mod spawn;

pub use state::PlayerState;

use bevy::prelude::*;

pub const WALK_SPEED: f32 = 300.0;
pub const RUN_SPEED: f32 = 450.0;

pub struct PlayerPlugin;

impl Plugin for PlayerPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins((
            input::InputPlugin,
            state::PlayerStatePlugin,
            audio::PlayerAudioPlugin,
            chat::PlayerChatPlugin,
            spawn::PlayerSpawnPlugin,
            movement::PlayerMovementPlugin,
        ));
    }
}

#[derive(Component)]
pub struct Player {
    pub state: PlayerState,
    pub current_direction: Vec2,
}

impl Default for Player {
    fn default() -> Self {
        Self {
            state: PlayerState::default(),
            current_direction: Vec2::NEG_Y,
        }
    }
}
