//! Doors from the Tiled `Doors` object layer, and talk targets from `Interact`.
//!
//! A door is a fixed collider that blocks while it is closed. Its leaf is drawn on a
//! tile layer named like the door, which is hidden while the door is open.

use bevy::platform::collections::HashMap;
use bevy::prelude::*;
use bevy_rapier2d::prelude::*;

use super::chunk_manager::TileLayerName;
use super::tiled_map::TiledMap;
use crate::player::chat::Talkable;
use crate::GameState;

#[derive(Component)]
pub struct Door(pub String);

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
        let open = obj.prop_bool("open").unwrap_or(false);
        states.insert(obj.name.clone(), open);

        let center = tiled_map.tiled_to_game(obj.x + obj.width / 2.0, obj.y + obj.height / 2.0);
        let mut door = commands.spawn((
            Name::new(format!("Door {}", obj.name)),
            Door(obj.name.clone()),
            Collider::cuboid(obj.width / 2.0, obj.height / 2.0),
            Transform::from_translation(center.extend(0.0)),
        ));
        if open {
            door.insert(ColliderDisabled);
        }
    }
    commands.insert_resource(DoorStates(states));
}

fn spawn_interactables(mut commands: Commands, tiled_map: Res<TiledMap>) {
    for obj in tiled_map.object_layer("Interact") {
        let Some(node) = obj.prop_str("node") else {
            warn!(
                "Interactable '{}' has no 'node' property, skipping",
                obj.name
            );
            continue;
        };
        let center = tiled_map.tiled_to_game(obj.x + obj.width / 2.0, obj.y + obj.height / 2.0);
        commands.spawn((
            Name::new(format!("Interact {}", obj.name)),
            Talkable {
                node: node.to_string(),
            },
            Transform::from_translation(center.extend(0.0)),
        ));
    }
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

fn sync_door_colliders(
    mut commands: Commands,
    states: Res<DoorStates>,
    q_doors: Query<(Entity, &Door)>,
) {
    for (entity, door) in &q_doors {
        match states.0.get(&door.0) {
            Some(true) => {
                commands.entity(entity).insert(ColliderDisabled);
            }
            _ => {
                commands.entity(entity).remove::<ColliderDisabled>();
            }
        }
    }
}

/// Hides the door leaf layers of open doors, also on chunks spawned later.
fn sync_door_layers(
    states: Res<DoorStates>,
    q_new: Query<(), Added<TileLayerName>>,
    mut q_layers: Query<(&TileLayerName, &mut Visibility)>,
) {
    if !states.is_changed() && q_new.is_empty() {
        return;
    }
    for (layer, mut visibility) in &mut q_layers {
        let Some(&open) = states.0.get(&layer.0) else {
            continue;
        };
        *visibility = if open {
            Visibility::Hidden
        } else {
            Visibility::Inherited
        };
    }
}

pub struct DoorsPlugin;

impl Plugin for DoorsPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<DoorStates>()
            .add_systems(
                OnEnter(GameState::Gaming),
                (spawn_doors, spawn_interactables),
            )
            .add_systems(
                Update,
                (
                    sync_door_colliders.run_if(resource_changed::<DoorStates>),
                    sync_door_layers,
                )
                    .run_if(in_state(GameState::Gaming)),
            );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn open_and_close_toggle_collider_and_door_layer() {
        let mut app = App::new();
        app.insert_resource(DoorStates(
            [("Door3B".to_string(), false)].into_iter().collect(),
        ))
        .add_systems(Update, (sync_door_colliders, sync_door_layers));
        let door = app.world_mut().spawn(Door("Door3B".to_string())).id();
        let layer = app
            .world_mut()
            .spawn((TileLayerName("Door3B".to_string()), Visibility::Inherited))
            .id();
        let other_layer = app
            .world_mut()
            .spawn((TileLayerName("Floor".to_string()), Visibility::Inherited))
            .id();
        let open = app.world_mut().register_system(open_door_command);
        let close = app.world_mut().register_system(close_door_command);

        app.world_mut()
            .run_system_with(open, "Door3B".to_string())
            .unwrap();
        app.update();
        assert!(app.world().get::<ColliderDisabled>(door).is_some());
        assert_eq!(
            app.world().get::<Visibility>(layer),
            Some(&Visibility::Hidden)
        );
        assert_eq!(
            app.world().get::<Visibility>(other_layer),
            Some(&Visibility::Inherited)
        );

        app.world_mut()
            .run_system_with(close, "Door3B".to_string())
            .unwrap();
        app.update();
        assert!(app.world().get::<ColliderDisabled>(door).is_none());
        assert_eq!(
            app.world().get::<Visibility>(layer),
            Some(&Visibility::Inherited)
        );

        // Unknown doors only log
        app.world_mut()
            .run_system_with(open, "Nowhere".to_string())
            .unwrap();
    }

    #[test]
    fn respawned_door_layer_follows_the_state() {
        let mut app = App::new();
        app.insert_resource(DoorStates(
            [("Door3B".to_string(), true)].into_iter().collect(),
        ))
        .add_systems(Update, sync_door_layers);
        app.update();
        let layer = app
            .world_mut()
            .spawn((TileLayerName("Door3B".to_string()), Visibility::Inherited))
            .id();
        app.update();
        assert_eq!(
            app.world().get::<Visibility>(layer),
            Some(&Visibility::Hidden)
        );
    }
}
