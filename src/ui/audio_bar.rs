use bevy::prelude::*;

use crate::{audio::GameAudio, player::input::PlayerInput, GameAssets, GameState};

#[derive(Component)]
struct Bar {
    timer: Timer,
}
#[derive(Component)]
struct BarText;

impl Default for Bar {
    fn default() -> Self {
        Self {
            timer: Timer::from_seconds(0.5, TimerMode::Once),
        }
    }
}

fn spawn_bar(mut commands: Commands, assets: Res<GameAssets>) {
    let text = commands
        .spawn((
            BarText,
            Text::new(String::new()),
            TextFont {
                font: assets.pixel_font.clone().into(),
                font_size: 30.0.into(),
                ..default()
            },
            TextColor::WHITE,
        ))
        .id();

    commands
        .spawn((
            Bar::default(),
            Node {
                bottom: Val::Percent(15.0),
                width: Val::Percent(100.0),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                position_type: PositionType::Absolute,
                ..default()
            },
            Visibility::Hidden,
            ZIndex(101),
        ))
        .add_children(&[text]);
}

fn string_bar(x: f64) -> String {
    fn round_near_5(n: usize) -> usize {
        n.div_ceil(5) * 5
    }

    let percent = round_near_5((x * 100.0) as usize);
    let bars = percent / 5;

    "X".repeat(bars) + &"_".repeat(20 - bars)
}

fn update_bar(game_audio: Res<GameAudio>, mut q_bar: Query<&mut Text, With<BarText>>) {
    let mut text = match q_bar.single_mut() {
        Ok(r) => r,
        Err(_) => return,
    };

    text.0 = format!("VOLUME: {}", string_bar(game_audio.main_volume));
}

fn tick_bar_timer(time: Res<Time>, mut q_bar: Query<&mut Bar>) {
    let mut bar = match q_bar.single_mut() {
        Ok(r) => r,
        Err(_) => return,
    };

    bar.timer.tick(time.delta());
}

fn show_bar(player_input: Res<PlayerInput>, mut q_bar: Query<(&mut Visibility, &mut Bar)>) {
    if player_input.scroll == 0.0 {
        return;
    }

    let (mut visibility, mut bar) = match q_bar.single_mut() {
        Ok(r) => r,
        Err(_) => return,
    };

    *visibility = Visibility::Visible;
    bar.timer.reset();
}

fn hide_bar(mut q_bar: Query<(&mut Visibility, &Bar)>) {
    let (mut visibility, bar) = match q_bar.single_mut() {
        Ok(r) => r,
        Err(_) => return,
    };

    if bar.timer.just_finished() {
        *visibility = Visibility::Hidden;
    }
}

pub struct AudioBarPlugin;

impl Plugin for AudioBarPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, (tick_bar_timer, update_bar, show_bar, hide_bar))
            .add_systems(OnExit(GameState::AssetLoading), spawn_bar);
    }
}
