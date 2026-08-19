use bevy::prelude::*;
use bevy_tweening::{lens::*, *};
use bevy_yarnspinner::prelude::*;

use crate::{GameAssets, GameState};

use super::option_selection::OptionSelection;

// The master root of the dialogue
#[derive(Component)]
pub struct DialogueRoot;
#[derive(Component)]
pub struct DialogueContent;
#[derive(Component)]
pub struct DialogueNameNode;
#[derive(Component)]
pub struct DialogueCharacterIcon;
#[derive(Component)]
pub struct DialogueContinueNode;

#[derive(Component)]
pub struct OptionsNode;
#[derive(Component)]
pub struct OptionsBackground;
#[derive(Component)]
pub struct OptionsText;
#[derive(Component)]
pub struct OptionButton(pub OptionId);

const BACKGROUND_ALPHA: f32 = 0.9;
const DIALOG_WIDTH: f32 = 800.0;
const OPTIONS_WIDTH: f32 = 500.0;
const TEXT_BORDER_HORIZONTAL: f32 = 40.0;
const TEXT_BORDER_VERTICAL: f32 = 20.0;
const OPTIONS_TEXT_BORDER: f32 = 10.0;

const CONTINUE_BOTTOM: f32 = -5.0;
const CONTINUE_BOB_DURATION: f32 = 1.0;
const CONTINUE_BOB_OFFSET: f32 = 5.0;

fn style_standard(_assets: &Res<GameAssets>) -> Node {
    Node {
        max_width: Val::Px(DIALOG_WIDTH - 2.0 * TEXT_BORDER_HORIZONTAL),
        ..default()
    }
}

fn text_style_standard(assets: &Res<GameAssets>) -> (TextFont, TextColor) {
    (
        TextFont {
            font: assets.silver_font.clone().into(),
            font_size: 50.0.into(),
            ..default()
        },
        TextColor::WHITE,
    )
}

fn text_style_name(assets: &Res<GameAssets>) -> (TextFont, TextColor) {
    (
        TextFont {
            font: assets.silver_font.clone().into(),
            font_size: 46.0.into(),
            ..default()
        },
        TextColor::WHITE,
    )
}

fn text_style_option_text(assets: &Res<GameAssets>) -> (TextFont, TextColor) {
    (
        TextFont {
            font: assets.silver_font.clone().into(),
            font_size: 50.0.into(),
            ..default()
        },
        TextColor::WHITE,
    )
}

fn spawn_dialogue_content(commands: &mut Commands, assets: &Res<GameAssets>) -> Entity {
    let text = commands
        .spawn((
            DialogueContent,
            Label,
            Text::new(String::new()),
            text_style_standard(assets),
            style_standard(assets),
        ))
        .with_children(|parent| {
            // Reserve the remaining (not yet typed) text as an invisible span so
            // the text box keeps its size while the typewriter catches up.
            parent.spawn((TextSpan(String::new()), TextColor(Color::NONE)));
        })
        .id();

    commands
        .spawn((
            Node {
                width: Val::Px(DIALOG_WIDTH),
                min_height: Val::Px(50.0),
                flex_direction: FlexDirection::Column,
                justify_content: JustifyContent::SpaceAround,
                align_items: AlignItems::FlexStart,
                padding: UiRect {
                    left: Val::Px(TEXT_BORDER_HORIZONTAL),
                    right: Val::Px(TEXT_BORDER_HORIZONTAL),
                    top: Val::Px(TEXT_BORDER_VERTICAL),
                    bottom: Val::Px(TEXT_BORDER_VERTICAL),
                },
                ..default()
            },
            BackgroundColor(Color::BLACK.with_alpha(BACKGROUND_ALPHA)),
        ))
        .add_children(&[text])
        .id()
}

fn spawn_dialogue_bottom(commands: &mut Commands, assets: &Res<GameAssets>) -> Entity {
    let tween = Tween::new(
        EaseFunction::SineInOut,
        std::time::Duration::from_secs_f32(CONTINUE_BOB_DURATION),
        UiPositionLens {
            start: UiRect::new(
                Val::Auto,
                Val::Auto,
                Val::Auto,
                Val::Px(CONTINUE_BOTTOM + CONTINUE_BOB_OFFSET),
            ),
            end: UiRect::new(
                Val::Auto,
                Val::Auto,
                Val::Auto,
                Val::Px(CONTINUE_BOTTOM - CONTINUE_BOB_OFFSET),
            ),
        },
    )
    .with_repeat_count(RepeatCount::Infinite)
    .with_repeat_strategy(RepeatStrategy::MirroredRepeat);

    let continue_node = commands
        .spawn((
            DialogueContinueNode,
            TweenAnim::new(tween),
            Node {
                position_type: PositionType::Absolute,
                ..default()
            },
            ImageNode::new(assets.dialogue_continue.clone()),
            ZIndex(1),
            Visibility::Hidden,
        ))
        .id();

    let icon_node = commands
        .spawn((
            Node {
                width: Val::Px(128.0),
                height: Val::Px(128.0),
                ..default()
            },
            ImageNode::new(assets.eleonore_icon.clone()),
            ZIndex(1),
            DialogueCharacterIcon,
        ))
        .id();

    let name_node = commands
        .spawn((
            Text::new(String::new()),
            text_style_name(assets),
            ZIndex(1),
            DialogueNameNode,
            Label,
        ))
        .id();

    let character_icon_node = commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                left: Val::Px(-550.0),
                bottom: Val::Px(0.0),
                width: Val::Px(140.0),
                height: Val::Px(180.0),
                align_items: AlignItems::Center,
                flex_direction: FlexDirection::Column,
                ..default()
            },
            ZIndex(1),
            BackgroundColor(Color::BLACK.with_alpha(BACKGROUND_ALPHA)),
        ))
        .add_children(&[icon_node, name_node])
        .id();

    commands
        .spawn((
            Node {
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                flex_direction: FlexDirection::Column,
                ..default()
            },
        ))
        .add_children(&[character_icon_node, continue_node])
        .id()
}

fn spawn_dialogue_options(commands: &mut Commands, _assets: &Res<GameAssets>) -> Entity {
    let options = commands
        .spawn((
            OptionsNode,
            Node {
                display: Display::Flex,
                flex_direction: FlexDirection::Column,
                justify_content: JustifyContent::FlexEnd,
                align_items: AlignItems::FlexStart,
                ..default()
            },
        ))
        .id();

    commands
        .spawn((
            OptionsBackground,
            Node {
                width: Val::Px(OPTIONS_WIDTH),
                min_height: Val::Px(100.0),
                max_height: Val::Px(720.0),
                flex_direction: FlexDirection::Column,
                justify_content: JustifyContent::SpaceAround,
                align_items: AlignItems::FlexStart,
                padding: UiRect {
                    top: Val::Px(20.0),
                    bottom: Val::Px(20.0),
                    left: Val::Px(20.0),
                    right: Val::Px(OPTIONS_WIDTH + 10.0),
                },
                top: Val::Percent(0.0),
                right: Val::Percent(0.0),
                position_type: PositionType::Absolute,
                ..default()
            },
            BackgroundColor(Color::BLACK.with_alpha(BACKGROUND_ALPHA)),
            Visibility::Hidden,
        ))
        .add_children(&[options])
        .id()
}

fn spawn_dialogue(mut commands: Commands, assets: Res<GameAssets>) {
    let dialogue_options = spawn_dialogue_options(&mut commands, &assets);

    let dialogue_content = spawn_dialogue_content(&mut commands, &assets);
    let dialogue_bottom = spawn_dialogue_bottom(&mut commands, &assets);

    let dialogue_root = commands
        .spawn((
            Node {
                width: Val::Percent(100.0),
                height: Val::Percent(100.0),
                justify_content: JustifyContent::FlexEnd,
                align_items: AlignItems::Center,
                padding: UiRect::bottom(Val::Px(30.0)),
                flex_direction: FlexDirection::Column,
                ..default()
            },
        ))
        .add_children(&[dialogue_content, dialogue_bottom])
        .id();

    commands
        .spawn((
            DialogueRoot,
            Node {
                width: Val::Percent(100.0),
                height: Val::Percent(100.0),
                position_type: PositionType::Absolute,
                ..default()
            },
            Visibility::Hidden,
        ))
        .add_children(&[dialogue_options, dialogue_root]);
}

fn spawn_dialogue_main_menu(mut commands: Commands, assets: Res<GameAssets>) {
    let dialogue_content = spawn_dialogue_content(&mut commands, &assets);

    let dialogue_root = commands
        .spawn((
            Node {
                width: Val::Percent(100.0),
                height: Val::Percent(100.0),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                padding: UiRect::top(Val::Px(30.0)),
                flex_direction: FlexDirection::Column,
                top: Val::Px(-200.0),
                ..default()
            },
        ))
        .add_child(dialogue_content)
        .id();

    commands
        .spawn((
            DialogueRoot,
            Node {
                width: Val::Percent(100.0),
                height: Val::Percent(100.0),
                position_type: PositionType::Absolute,
                ..default()
            },
        ))
        .add_child(dialogue_root);
}

fn despawn_dialogue_main_menu(
    mut commands: Commands,
    q_dialogue_root: Query<Entity, With<DialogueRoot>>,
) {
    for entity in &q_dialogue_root {
        commands.entity(entity).despawn();
    }
}

pub fn set_dialogue_text(
    text: &mut Text,
    span: &mut TextSpan,
    visible: &str,
    invisible: &str,
) {
    text.0 = visible.to_string();
    span.0 = invisible.to_string();
}

fn spawn_option(
    commands: &mut Commands,
    assets: &Res<GameAssets>,
    option: DialogueOption,
    entity: Entity,
) {
    let (font, color) = text_style_option_text(assets);
    let text = commands
        .spawn((
            OptionsText,
            Label,
            Text::new(format!("- {}", option.line.text.clone())),
            font,
            color,
            Node {
                width: Val::Px(OPTIONS_WIDTH - 2.0 * OPTIONS_TEXT_BORDER),
                ..default()
            },
        ))
        .id();

    let button = commands
        .spawn((
            Button,
            Node {
                justify_content: JustifyContent::FlexStart,
                ..default()
            },
            BackgroundColor(Color::NONE),
            OptionButton(option.id),
        ))
        .add_child(text)
        .id();
    commands.entity(entity).add_child(button);
}

pub fn spawn_options(
    commands: &mut Commands,
    assets: &Res<GameAssets>,
    options: &OptionSelection,
    entity: Entity,
) {
    for option in options.get_options() {
        spawn_option(commands, assets, option, entity);
    }
}

pub struct DialogueSpawnPlugin;

impl Plugin for DialogueSpawnPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(GameState::MainMenu), spawn_dialogue_main_menu)
            .add_systems(OnExit(GameState::MainMenu), despawn_dialogue_main_menu)
            .add_systems(OnEnter(GameState::Gaming), spawn_dialogue);
    }
}
