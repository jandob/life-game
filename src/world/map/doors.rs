//! Doors from the Tiled `Doors` object layer: whether each one is open. A door's leaf
//! is an image layer named like the door, hidden while it is open (see `side_view`).

use bevy::platform::collections::HashMap;
use bevy::prelude::*;

use super::tiled_map::TiledMap;
use crate::GameState;

/// Open (`true`) or closed state of every door of the map.
/// Rebuilt from the `Doors` properties when the map is entered.
#[derive(Resource, Default)]
pub struct DoorStates(pub HashMap<String, bool>);

fn spawn_doors(mut commands: Commands, tiled_map: Res<TiledMap>) {
    let mut states = HashMap::new();
    for obj in tiled_map.object_layer("Doors") {
        if obj.name.is_empty() {
            warn!("Door without a name in the Doors layer, skipping");
            continue;
        }
        states.insert(obj.name.clone(), obj.prop_bool("open").unwrap_or(false));
    }
    commands.insert_resource(DoorStates(states));
}

/// `<<open_door NAME>>`
pub fn open_door_command(In(name): In<String>, states: ResMut<DoorStates>) {
    set_door(name, true, states);
}

/// `<<close_door NAME>>`
pub fn close_door_command(In(name): In<String>, states: ResMut<DoorStates>) {
    set_door(name, false, states);
}

fn set_door(name: String, open: bool, mut states: ResMut<DoorStates>) {
    match states.0.get(&name) {
        Some(&current) if current == open => {}
        Some(_) => {
            states.0.insert(name, open);
        }
        None => error!("Unknown door '{name}'"),
    }
}

pub struct DoorsPlugin;

impl Plugin for DoorsPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<DoorStates>()
            .add_systems(OnEnter(GameState::Gaming), spawn_doors);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn open_and_close_change_the_door_state() {
        let mut app = App::new();
        app.insert_resource(DoorStates(
            [("Door3B".to_string(), false)].into_iter().collect(),
        ));
        let open = app.world_mut().register_system(open_door_command);
        let close = app.world_mut().register_system(close_door_command);
        let state = |app: &App| app.world().resource::<DoorStates>().0["Door3B"];

        app.world_mut()
            .run_system_with(open, "Door3B".to_string())
            .unwrap();
        assert!(state(&app));
        app.world_mut()
            .run_system_with(close, "Door3B".to_string())
            .unwrap();
        assert!(!state(&app));

        // Unknown doors only log
        app.world_mut()
            .run_system_with(open, "Nowhere".to_string())
            .unwrap();
        assert_eq!(app.world().resource::<DoorStates>().0.len(), 1);
    }
}
