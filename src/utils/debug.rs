use bevy::prelude::*;

use crate::player::input::PlayerInput;

#[derive(Resource, Default, Deref, DerefMut)]
pub struct DebugActive(pub bool);

fn toggle_debug_mod(player_input: Res<PlayerInput>, mut debug_active: ResMut<DebugActive>) {
    if player_input.toggle_debug {
        **debug_active = !**debug_active;
    }
}

pub struct DebugPlugin;

impl Plugin for DebugPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<DebugActive>()
            .add_systems(Update, toggle_debug_mod);
    }
}
