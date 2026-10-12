use std::time::Duration;

use bevy::prelude::*;

use crate::{
    world::ending::{Ending, EndingTriggered},
    GameAssets, GameState,
};

#[derive(Component)]
struct WriteableText {
    written_text: String,
    text_left: String,
    timer: Timer,
    time_between_chars: f32,
}

impl WriteableText {
    fn new(text_left: &str, time_between_chars: f32, start_delay: f32) -> Self {
        Self {
            written_text: String::new(),
            text_left: text_left.to_string(),
            timer: Timer::from_seconds(start_delay, TimerMode::Repeating),
            time_between_chars,
        }
    }
}

fn text_style_standard(assets: &Res<GameAssets>) -> (TextFont, TextColor) {
    (
        TextFont {
            font: assets.silver_font.clone().into(),
            font_size: 100.0.into(),
            ..default()
        },
        TextColor::WHITE,
    )
}

fn spawn_text(
    commands: &mut Commands,
    assets: &Res<GameAssets>,
    text: &str,
    time_between_chars: f32,
    start_delay: f32,
) -> Entity {
    commands
        .spawn((
            Text::new(String::new()),
            text_style_standard(assets),
            ZIndex(1),
            WriteableText::new(text, time_between_chars, start_delay),
        ))
        .id()
}

fn spawn_end_card(
    mut commands: Commands,
    assets: Res<GameAssets>,
    mut ev_ending_triggered: MessageReader<EndingTriggered>,
) {
    for ev in ev_ending_triggered.read() {
        let (header, thanks) = match ev.ending {
            Ending::Demo => ("To be continued", "Thanks for Playing"),
        };
        let header_text = spawn_text(&mut commands, &assets, header, 0.12, 2.5);
        let thanks_text = spawn_text(&mut commands, &assets, thanks, 0.1, 6.5);

        commands
            .spawn((
                Node {
                    position_type: PositionType::Absolute,
                    top: Val::Percent(40.0),
                    width: Val::Percent(100.0),
                    flex_direction: FlexDirection::Column,
                    row_gap: Val::Vh(25.0),
                    align_items: AlignItems::Center,
                    ..default()
                },
                ZIndex(1001),
            ))
            .add_children(&[header_text, thanks_text]);
    }
}

fn write_texts(time: Res<Time>, mut q_writable_texts: Query<(&mut Text, &mut WriteableText)>) {
    for (mut text, mut writeable_text) in &mut q_writable_texts {
        writeable_text.timer.tick(time.delta());
        if writeable_text.timer.just_finished() {
            if writeable_text.text_left.is_empty() {
                writeable_text.timer.set_mode(TimerMode::Once);
                continue;
            }

            // This was the start delay
            if writeable_text.written_text.is_empty() {
                let duration = Duration::from_secs_f32(writeable_text.time_between_chars);
                writeable_text.timer.set_duration(duration);
            }

            let next_char = writeable_text.text_left.remove(0);
            writeable_text.written_text.push(next_char);
        }
        text.0 = writeable_text.written_text.clone();
    }
}

pub struct EndingTextPlugin;

impl Plugin for EndingTextPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(
            Update,
            (
                spawn_end_card,
                write_texts,
            )
                .run_if(not(in_state(GameState::AssetLoading))),
        );
    }
}
