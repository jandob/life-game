//! Side view (see `openspec/changes/side-view`): rooms seen side-on, walked by clicking.
//!
//! The map holds image layers for the art and, per room (`Rooms`, see `rooms.rs`), a
//! `Floor` polyline whose y is the line every character's feet stand on and whose x span
//! is walkable. `Hotspots` are rectangles over the art with a Yarn `node`, a `label`
//! shown on hover and the `stand_x` the player walks to before the node starts; with
//! `actor` set, a hotspot moves with that actor. Image layers named like a door are its
//! leaf, hidden while the door is open.

use bevy::prelude::*;
use bevy::time::Real;
use bevy::window::{CursorIcon, PrimaryWindow, SystemCursorIcon};
use bevy_yarnspinner::prelude::DialogueRunner;

use super::camera::{update_camera_target, MainCamera};
use super::camera_shake::{update_camera, CameraShake};
use super::map::doors::DoorStates;
use super::map::tiled_map::TiledMap;
use crate::character::SPRITE_FEET_BELOW_CENTRE;
use crate::player::chat::PlayerStartedChat;
use crate::player::input::{InputBlocked, MouseWorldCoords};
use crate::player::{Player, PlayerState, RUN_SPEED, WALK_SPEED};
use crate::story::scripted::{Actor, ScriptedWalk};
use crate::story::transition::scene_queued;
use crate::ui::dialogue::runner::RunnerFlags;
use crate::{GameAssets, GameState};

pub mod rooms;

pub use rooms::SideRooms;

/// Behind every character (see `character::CHARACTER_Z`).
const BACKGROUND_Z: f32 = -800.0;
/// In front of every character.
const FOREGROUND_Z: f32 = 500.0;
/// The player has arrived when this close to the target x, in px.
const ARRIVE_DISTANCE: f32 = 4.0;
/// A second click within this many seconds runs instead of walks.
const DOUBLE_CLICK_SECONDS: f64 = 0.35;
/// Clicks this soon after a conversation ends are the click that ended it.
const AFTER_TALK_SECONDS: f64 = 0.2;

/// Something in a room the player can click.
#[derive(Component)]
pub struct Hotspot {
    pub label: String,
    pub node: String,
    pub area: Rect,
    pub stand_x: f32,
    /// The actor this hotspot moves with (property `actor`), e.g. Samantha
    pub follow: Option<String>,
    /// Off while the actor it follows is hidden
    pub enabled: bool,
}

/// Where a click sent the player, and the hotspot to use on arrival.
#[derive(Component)]
pub struct ClickWalk {
    pub target_x: f32,
    pub run: bool,
    pub hotspot: Option<Entity>,
}

/// A sprite drawn from the image layer of this name. A layer named like a door is that
/// door's leaf, hidden while the door is open.
#[derive(Component)]
struct ImageLayerName(String);

#[derive(Component)]
struct HoverLabel;

fn spawn_rooms(mut commands: Commands, map: Res<TiledMap>, assets: Res<GameAssets>) {
    if let Some(colour) = map.background {
        commands.insert_resource(ClearColor(colour));
    }
    // Layers draw in file order: each one a little in front of the one before.
    let behind = map.image_layers.iter().filter(|l| !l.above).count() as f32;
    for (i, layer) in map.image_layers.iter().enumerate() {
        let corner = map.tiled_to_game(layer.offset.x, layer.offset.y);
        let z = if layer.above {
            FOREGROUND_Z + i as f32
        } else {
            BACKGROUND_Z - behind + i as f32
        };
        commands.spawn((
            Name::new(format!("Image layer {}", layer.name)),
            ImageLayerName(layer.name.clone()),
            Sprite::from_image(layer.image.clone()),
            bevy::sprite::Anchor::TOP_LEFT,
            Transform::from_translation(corner.extend(z)),
        ));
    }

    let rooms = SideRooms::from_map(&map);
    for obj in map.object_layer("Hotspots") {
        let Some(node) = obj.prop_str("node") else {
            warn!("Hotspot '{}' has no 'node' property, skipping", obj.name);
            continue;
        };
        let area = Rect::from_corners(
            map.tiled_to_game(obj.x, obj.y),
            map.tiled_to_game(obj.x + obj.width, obj.y + obj.height),
        );
        let stand_x = obj
            .prop_f32("stand_x")
            .map(|x| map.tiled_to_game(x, 0.0).x)
            .unwrap_or(area.center().x);
        let stand_x = match rooms.room_at(area.center()).map(|r| &rooms.rooms[r]) {
            Some(room) => stand_x.clamp(room.min_x, room.max_x),
            None => stand_x,
        };
        commands.spawn((
            Name::new(format!("Hotspot {}", obj.name)),
            Hotspot {
                label: obj.prop_str("label").unwrap_or(&obj.name).to_string(),
                node: node.to_string(),
                area,
                stand_x,
                follow: obj.prop_str("actor").map(str::to_string),
                enabled: true,
            },
        ));
    }
    commands.insert_resource(rooms);

    commands.spawn((
        HoverLabel,
        Text::new(""),
        TextFont {
            font: assets.silver_font.clone().into(),
            font_size: 28.0.into(),
            ..default()
        },
        TextColor(Color::WHITE),
        TextShadow::default(),
        Node {
            position_type: PositionType::Absolute,
            padding: UiRect::axes(Val::Px(6.0), Val::Px(2.0)),
            ..default()
        },
        BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.7)),
        Visibility::Hidden,
        GlobalZIndex(400),
    ));
}

/// Puts every character's feet on the floor line of its room when it appears.
fn stand_on_floor(rooms: Res<SideRooms>, mut q_actors: Query<&mut Transform, Added<Actor>>) {
    for mut transform in &mut q_actors {
        if let Some(room) = rooms.room_at(transform.translation.xy()) {
            transform.translation.y = rooms.rooms[room].stand_y;
        }
    }
}

/// Moves hotspots that follow an actor with it, and turns them off while it's hidden.
fn follow_actors(
    mut q_hotspots: Query<&mut Hotspot>,
    q_actors: Query<(&Actor, &Transform, &Visibility)>,
) {
    for mut hotspot in &mut q_hotspots {
        let Some(name) = hotspot.follow.as_deref() else {
            continue;
        };
        let Some((_, transform, visibility)) = q_actors.iter().find(|(a, ..)| a.0 == name) else {
            continue;
        };
        let feet = transform.translation.xy() - Vec2::new(0.0, SPRITE_FEET_BELOW_CENTRE);
        let size = hotspot.area.size();
        let area = Rect::from_corners(
            feet - Vec2::new(size.x / 2.0, 0.0),
            feet + Vec2::new(size.x / 2.0, size.y),
        );
        let enabled = *visibility != Visibility::Hidden;
        if hotspot.area != area || hotspot.enabled != enabled {
            hotspot.area = area;
            hotspot.stand_x = feet.x;
            hotspot.enabled = enabled;
        }
    }
}

/// Shows a door's leaf while the door is closed.
fn sync_door_leaves(
    states: Option<Res<DoorStates>>,
    mut q_layers: Query<(&ImageLayerName, &mut Visibility)>,
) {
    let Some(states) = states else {
        return;
    };
    if !states.is_changed() {
        return;
    }
    for (layer, mut visibility) in &mut q_layers {
        if let Some(&open) = states.0.get(&layer.0) {
            visibility.set_if_neq(if open {
                Visibility::Hidden
            } else {
                Visibility::Inherited
            });
        }
    }
}

/// The hotspot under `point`, the smallest one where several overlap.
fn hotspot_at<'a>(
    point: Vec2,
    hotspots: impl IntoIterator<Item = (Entity, &'a Hotspot)>,
) -> Option<(Entity, &'a Hotspot)> {
    hotspots
        .into_iter()
        .filter(|(_, h)| h.enabled && h.area.contains(point))
        .min_by(|a, b| {
            let area = |h: &Hotspot| h.area.width() * h.area.height();
            area(a.1).total_cmp(&area(b.1))
        })
}

/// Whether the player is busy: talking, in a cutscene, or in a panel.
fn busy(
    player: &Player,
    blocked: &InputBlocked,
    q_runners: &Query<&RunnerFlags, With<DialogueRunner>>,
) -> bool {
    player.state == PlayerState::Talking || blocked.0 || q_runners.iter().any(|f| f.active)
}

fn click_to_walk(
    mut commands: Commands,
    time: Res<Time<Real>>,
    mouse_buttons: Res<ButtonInput<MouseButton>>,
    mouse: Res<MouseWorldCoords>,
    blocked: Res<InputBlocked>,
    rooms: Res<SideRooms>,
    q_runners: Query<&RunnerFlags, With<DialogueRunner>>,
    q_player: Query<(Entity, &Player, &Transform), Without<ScriptedWalk>>,
    q_hotspots: Query<(Entity, &Hotspot)>,
    mut last_busy: Local<f64>,
    mut last_click: Local<f64>,
) {
    let Ok((entity, player, transform)) = q_player.single() else {
        return;
    };
    let now = time.elapsed_secs_f64();
    if busy(player, &blocked, &q_runners) {
        *last_busy = now;
        return;
    }
    if !mouse_buttons.just_pressed(MouseButton::Left) || now - *last_busy < AFTER_TALK_SECONDS {
        return;
    }
    let run = now - *last_click < DOUBLE_CLICK_SECONDS;
    *last_click = now;

    let Some(room) = rooms.room_at(transform.translation.xy()) else {
        return;
    };
    // Only this room is on screen, so only its hotspots and floor can be clicked.
    let in_room = q_hotspots
        .iter()
        .filter(|(_, h)| rooms.room_at(h.area.center()) == Some(room));
    let floor = &rooms.rooms[room];
    let (target_x, hotspot) = match hotspot_at(mouse.0, in_room) {
        Some((hotspot_entity, hotspot)) => (hotspot.stand_x, Some(hotspot_entity)),
        None => (mouse.0.x.clamp(floor.min_x, floor.max_x), None),
    };
    commands.entity(entity).insert(ClickWalk {
        target_x,
        run,
        hotspot,
    });
}

fn walk_to_target(
    mut commands: Commands,
    time: Res<Time>,
    mut q_player: Query<(Entity, &mut Transform, &mut Player, &ClickWalk), Without<ScriptedWalk>>,
    q_hotspots: Query<&Hotspot>,
    mut ev_started_chat: MessageWriter<PlayerStartedChat>,
) {
    let Ok((entity, mut transform, mut player, walk)) = q_player.single_mut() else {
        return;
    };
    let dx = walk.target_x - transform.translation.x;
    if dx.abs() > ARRIVE_DISTANCE {
        let speed = if walk.run { RUN_SPEED } else { WALK_SPEED };
        transform.translation.x += dx.signum() * (speed * time.delta_secs()).min(dx.abs());
        player.current_direction = Vec2::new(dx.signum(), 0.0);
        player.state = if walk.run {
            PlayerState::Running
        } else {
            PlayerState::Walking
        };
        return;
    }

    player.state = PlayerState::Idling;
    commands.entity(entity).remove::<ClickWalk>();
    let pos = transform.translation.xy();
    let Some(hotspot) = walk.hotspot.and_then(|e| q_hotspots.get(e).ok()) else {
        return;
    };
    // Facing the hotspot: up for the back wall, sideways for things beside the player.
    let direction = hotspot.area.center() - pos;
    player.current_direction = direction;
    player.state = PlayerState::Talking;
    ev_started_chat.write(PlayerStartedChat {
        node: hotspot.node.clone(),
        direction,
    });
}

/// Stops a click walk when a conversation or a scripted walk takes the player over.
fn cancel_click_walk(
    mut commands: Commands,
    q_player: Query<(Entity, &Player, Has<ScriptedWalk>), With<ClickWalk>>,
) {
    for (entity, player, scripted) in &q_player {
        if scripted || player.state == PlayerState::Talking {
            commands.entity(entity).remove::<ClickWalk>();
        }
    }
}

/// Shows the hovered hotspot's name next to the cursor, with a pointer cursor.
fn hover_hotspot(
    mut commands: Commands,
    mouse: Res<MouseWorldCoords>,
    blocked: Res<InputBlocked>,
    q_runners: Query<&RunnerFlags, With<DialogueRunner>>,
    q_player: Query<&Player>,
    q_hotspots: Query<(Entity, &Hotspot)>,
    q_window: Query<(Entity, &Window), With<PrimaryWindow>>,
    mut q_label: Query<(&mut Text, &mut Node, &mut Visibility), With<HoverLabel>>,
    mut pointing: Local<bool>,
) {
    let Ok((window_entity, window)) = q_window.single() else {
        return;
    };
    let Ok((mut text, mut node, mut visibility)) = q_label.single_mut() else {
        return;
    };
    let player_busy = q_player
        .single()
        .is_ok_and(|player| busy(player, &blocked, &q_runners));
    let hovered = match window.cursor_position() {
        Some(cursor) if !player_busy => {
            hotspot_at(mouse.0, q_hotspots.iter()).map(|(_, h)| (cursor, h.label.clone()))
        }
        _ => None,
    };

    let point = hovered.is_some();
    match hovered {
        Some((cursor, label)) => {
            if text.0 != label {
                text.0 = label;
            }
            node.left = Val::Px(cursor.x + 16.0);
            node.top = Val::Px(cursor.y - 12.0);
            *visibility = Visibility::Inherited;
        }
        None => *visibility = Visibility::Hidden,
    }
    if point != *pointing {
        *pointing = point;
        let icon = if point {
            SystemCursorIcon::Pointer
        } else {
            SystemCursorIcon::Default
        };
        commands
            .entity(window_entity)
            .insert(CursorIcon::from(icon));
    }
}

/// The camera follows the player along x, stops at the edges of the player's room and
/// keeps the room's vertical middle.
fn clamp_camera(
    rooms: Res<SideRooms>,
    mut shake: ResMut<CameraShake>,
    q_window: Query<&Window, With<PrimaryWindow>>,
    q_projection: Query<&Projection, With<MainCamera>>,
) {
    let (Ok(window), Ok(Projection::Orthographic(ortho))) =
        (q_window.single(), q_projection.single())
    else {
        return;
    };
    let Some(room) = rooms.room_at(shake.target()).map(|r| &rooms.rooms[r]) else {
        return;
    };
    let half_width = window.width() * ortho.scale / 2.0;
    let x = if room.bounds.width() <= 2.0 * half_width {
        room.bounds.center().x
    } else {
        shake.target().x.clamp(
            room.bounds.min.x + half_width,
            room.bounds.max.x - half_width,
        )
    };
    shake.update_target(Vec2::new(x, room.bounds.center().y));
}

pub struct SideViewPlugin;

impl Plugin for SideViewPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(GameState::Gaming), spawn_rooms)
            .add_systems(
                Update,
                (
                    stand_on_floor,
                    follow_actors,
                    sync_door_leaves,
                    (
                        click_to_walk.run_if(not(scene_queued)),
                        walk_to_target,
                        cancel_click_walk,
                    )
                        .chain(),
                    hover_hotspot,
                )
                    .run_if(in_state(GameState::Gaming).and_then(resource_exists::<SideRooms>)),
            )
            .add_systems(
                PostUpdate,
                clamp_camera
                    .after(update_camera_target)
                    .before(update_camera)
                    .run_if(resource_exists::<SideRooms>),
            );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hotspot(min: Vec2, max: Vec2) -> Hotspot {
        Hotspot {
            label: String::new(),
            node: String::new(),
            area: Rect::from_corners(min, max),
            stand_x: 0.0,
            follow: None,
            enabled: true,
        }
    }

    #[test]
    fn the_smallest_overlapping_hotspot_wins() {
        let big = hotspot(Vec2::ZERO, Vec2::splat(100.0));
        let small = hotspot(Vec2::splat(40.0), Vec2::splat(60.0));
        let (a, b) = (
            Entity::from_raw_u32(1).unwrap(),
            Entity::from_raw_u32(2).unwrap(),
        );
        let hotspots = [(a, &big), (b, &small)];
        assert_eq!(
            hotspot_at(Vec2::splat(50.0), hotspots).map(|h| h.0),
            Some(b)
        );
        assert_eq!(
            hotspot_at(Vec2::splat(10.0), hotspots).map(|h| h.0),
            Some(a)
        );
        assert!(hotspot_at(Vec2::splat(150.0), hotspots).is_none());
    }
}
