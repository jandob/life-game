//! The inventory and phone panels, the key hint for them, and the "Got:" notice.
//!
//! `I` opens the inventory, `P` the phone. With an unread text, `P` plays it instead of
//! opening the panel. While a panel is open the player doesn't walk or talk
//! (`InputBlocked`); `I`, `P`, E, Space, Enter or Escape close it.

use bevy::prelude::*;
use bevy_yarnspinner::prelude::*;

use crate::player::chat::PlayerStartedChat;
use crate::player::input::InputBlocked;
use crate::player::{Player, PlayerState};
use crate::story::inventory::{carried, ItemGained};
use crate::story::phone::Phone;
use crate::story::transition::QueuedScene;
use crate::story::StoryVars;
use crate::ui::dialogue::runner::RunnerFlags;
use crate::{GameAssets, GameState};

const BACKGROUND_ALPHA: f32 = 0.9;
const PANEL_WIDTH: f32 = 700.0;
const TOAST_SECONDS: f32 = 2.5;
/// Lines of message history the phone shows.
const MESSAGES_SHOWN: usize = 8;
const DONE_COLOR: Color = Color::srgb(0.55, 0.55, 0.55);
const HEADING_COLOR: Color = Color::srgb(1.0, 0.75, 0.8);

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Panel {
    Inventory,
    Phone,
}

#[derive(Resource, Default)]
pub struct OpenPanel(pub Option<Panel>);

#[derive(Component)]
struct PanelRoot;
#[derive(Component)]
struct PanelContent;
#[derive(Component)]
struct KeyHint;
#[derive(Component)]
struct Toast(Timer);

fn font(assets: &GameAssets, size: f32, color: Color) -> (TextFont, TextColor) {
    (
        TextFont {
            font: assets.silver_font.clone().into(),
            font_size: size.into(),
            ..default()
        },
        TextColor(color),
    )
}

fn spawn_hud(mut commands: Commands, assets: Res<GameAssets>) {
    commands.spawn((
        KeyHint,
        Text::new(""),
        font(&assets, 32.0, Color::WHITE.with_alpha(0.8)),
        Node {
            position_type: PositionType::Absolute,
            left: Val::Px(16.0),
            top: Val::Px(8.0),
            ..default()
        },
        ZIndex(400),
    ));

    let content = commands
        .spawn((
            PanelContent,
            Node {
                flex_direction: FlexDirection::Column,
                row_gap: Val::Px(6.0),
                ..default()
            },
        ))
        .id();
    commands
        .spawn((
            PanelRoot,
            Node {
                width: Val::Percent(100.0),
                height: Val::Percent(100.0),
                position_type: PositionType::Absolute,
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                ..default()
            },
            ZIndex(450),
            Visibility::Hidden,
        ))
        .with_children(|parent| {
            parent
                .spawn((
                    Node {
                        width: Val::Px(PANEL_WIDTH),
                        max_height: Val::Percent(80.0),
                        padding: UiRect::all(Val::Px(24.0)),
                        overflow: Overflow::clip_y(),
                        ..default()
                    },
                    BackgroundColor(Color::BLACK.with_alpha(BACKGROUND_ALPHA)),
                ))
                .add_child(content);
        });
}

fn conversation_running(q_runners: &Query<&RunnerFlags>) -> bool {
    q_runners.iter().any(|flags| flags.active)
}

fn toggle_panels(
    keys: Res<ButtonInput<KeyCode>>,
    queued: Res<QueuedScene>,
    q_runners: Query<&RunnerFlags>,
    mut open: ResMut<OpenPanel>,
    mut blocked: ResMut<InputBlocked>,
    phone: Res<Phone>,
    mut q_player: Query<&mut Player>,
    mut ev_player_started_chat: MessageWriter<PlayerStartedChat>,
) {
    let inventory = keys.just_pressed(KeyCode::KeyI);
    let phone_key = keys.just_pressed(KeyCode::KeyP);

    if open.0.is_some() {
        let close = inventory
            || phone_key
            || keys.any_just_pressed([
                KeyCode::KeyE,
                KeyCode::Space,
                KeyCode::Enter,
                KeyCode::Escape,
            ]);
        if close {
            open.0 = None;
        }
    } else if inventory || phone_key {
        let Ok(mut player) = q_player.single_mut() else {
            return;
        };
        if player.state == PlayerState::Talking
            || queued.0.is_some()
            || conversation_running(&q_runners)
        {
            return;
        }
        if inventory {
            open.0 = Some(Panel::Inventory);
        } else if let Some(node) = phone.unread.front().cloned() {
            // An unread text plays like a conversation; it is read once it completes.
            player.state = PlayerState::Talking;
            ev_player_started_chat.write(PlayerStartedChat {
                node,
                direction: player.current_direction,
            });
        } else {
            open.0 = Some(Panel::Phone);
        }
    }
    blocked.0 = open.0.is_some();
}

fn inventory_lines(story_vars: &StoryVars) -> Vec<(String, f32, Color)> {
    let mut lines = vec![("Inventory".to_string(), 44.0, HEADING_COLOR)];
    let items = carried(&story_vars.0);
    if items.is_empty() {
        lines.push(("Nothing.".to_string(), 36.0, DONE_COLOR));
    }
    for item in items {
        lines.push((item.name.to_string(), 38.0, Color::WHITE));
        lines.push((format!("  {}", item.about), 32.0, DONE_COLOR));
    }
    lines
}

fn phone_lines(phone: &Phone) -> Vec<(String, f32, Color)> {
    let mut lines = vec![("Notes".to_string(), 44.0, HEADING_COLOR)];
    if phone.notes.is_empty() {
        lines.push(("Nothing to do.".to_string(), 34.0, DONE_COLOR));
    }
    for note in phone.sorted_notes() {
        if note.done {
            lines.push((format!("[x] {}", note.text), 34.0, DONE_COLOR));
        } else {
            lines.push((format!("[ ] {}", note.text), 34.0, Color::WHITE));
        }
    }
    lines.push(("Messages".to_string(), 44.0, HEADING_COLOR));
    if phone.messages.is_empty() {
        lines.push(("No messages.".to_string(), 34.0, DONE_COLOR));
    }
    let skip = phone.messages.len().saturating_sub(MESSAGES_SHOWN);
    for message in phone.messages.iter().skip(skip) {
        lines.push((
            format!("{}: {}", message.speaker, message.text),
            34.0,
            Color::WHITE,
        ));
    }
    lines
}

fn update_panel(
    mut commands: Commands,
    assets: Res<GameAssets>,
    open: Res<OpenPanel>,
    story_vars: Res<StoryVars>,
    phone: Res<Phone>,
    mut q_root: Query<&mut Visibility, With<PanelRoot>>,
    q_content: Query<Entity, With<PanelContent>>,
) {
    if !open.is_changed() {
        return;
    }
    let Ok(mut visibility) = q_root.single_mut() else {
        return;
    };
    let Ok(content) = q_content.single() else {
        return;
    };
    commands.entity(content).despawn_children();
    let lines = match open.0 {
        None => {
            *visibility = Visibility::Hidden;
            return;
        }
        Some(Panel::Inventory) => inventory_lines(&story_vars),
        Some(Panel::Phone) => phone_lines(&phone),
    };
    *visibility = Visibility::Inherited;
    for (text, size, color) in lines {
        let line = commands
            .spawn((
                Text::new(text),
                font(&assets, size, color),
                Node {
                    max_width: Val::Px(PANEL_WIDTH - 48.0),
                    ..default()
                },
            ))
            .id();
        commands.entity(content).add_child(line);
    }
}

fn update_key_hint(
    phone: Res<Phone>,
    open: Res<OpenPanel>,
    mut q_hint: Query<&mut Text, With<KeyHint>>,
) {
    if !phone.is_changed() && !open.is_changed() {
        return;
    }
    let Ok(mut text) = q_hint.single_mut() else {
        return;
    };
    let unread = match phone.unread.len() {
        0 => String::new(),
        1 => "  (1 new text)".to_string(),
        n => format!("  ({n} new texts)"),
    };
    text.0 = format!("[I] Items   [P] Phone{unread}");
}

fn show_toast(
    mut commands: Commands,
    assets: Res<GameAssets>,
    q_toasts: Query<Entity, With<Toast>>,
    mut ev_item_gained: MessageReader<ItemGained>,
) {
    let names: Vec<_> = ev_item_gained.read().map(|ev| ev.0.name).collect();
    if names.is_empty() {
        return;
    }
    for entity in &q_toasts {
        commands.entity(entity).despawn();
    }
    commands.spawn((
        Toast(Timer::from_seconds(TOAST_SECONDS, TimerMode::Once)),
        Text::new(format!("Got: {}", names.join(", "))),
        font(&assets, 40.0, HEADING_COLOR),
        Node {
            position_type: PositionType::Absolute,
            left: Val::Px(16.0),
            top: Val::Px(48.0),
            ..default()
        },
        BackgroundColor(Color::BLACK.with_alpha(0.6)),
        ZIndex(400),
    ));
}

fn expire_toasts(
    mut commands: Commands,
    time: Res<Time>,
    mut q_toasts: Query<(Entity, &mut Toast)>,
) {
    for (entity, mut toast) in &mut q_toasts {
        if toast.0.tick(time.delta()).is_finished() {
            commands.entity(entity).despawn();
        }
    }
}

fn despawn_hud(
    mut commands: Commands,
    mut open: ResMut<OpenPanel>,
    mut blocked: ResMut<InputBlocked>,
    q_hud: Query<Entity, Or<(With<PanelRoot>, With<KeyHint>, With<Toast>)>>,
) {
    open.0 = None;
    blocked.0 = false;
    for entity in &q_hud {
        commands.entity(entity).despawn();
    }
}

pub struct HudPlugin;

impl Plugin for HudPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<OpenPanel>()
            .add_systems(OnEnter(GameState::Gaming), spawn_hud)
            .add_systems(OnExit(GameState::Gaming), despawn_hud)
            .add_systems(
                Update,
                (
                    toggle_panels.run_if(resource_exists::<YarnProject>),
                    update_panel,
                    update_key_hint,
                    show_toast,
                    expire_toasts,
                )
                    .chain()
                    .run_if(in_state(GameState::Gaming)),
            );
    }
}
