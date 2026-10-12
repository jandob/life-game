use bevy::prelude::*;
use bevy_rapier2d::prelude::*;

use crate::player::{Player, PlayerState};
use crate::story::scripted::ScriptedWalk;
use crate::animation::{SpriteAnimator, KEY_ICON, SHIFT_ICON};
use crate::{
    world::camera::YSort,
    GameAssets, GameState,
};

const ANCHOR_DIS: f32 = 90.0;
const BUTTON_DIS: f32 = 35.0;
const SHIFT_DIS: f32 = 35.0;
const ICON_SIZE: f32 = 0.5;

#[derive(Component)]
struct KeyboardIcon;
#[derive(Component)]
pub struct KeyboardHint;

enum Icon {
    Down,
    Up,
    Left,
    Right,
    Shift,
}

fn icon_to_texture(
    assets: &Res<GameAssets>,
    icon: &Icon,
) -> (Handle<Image>, Handle<TextureAtlasLayout>) {
    match icon {
        Icon::Down => (
            assets.ui_down_key_texture.clone(),
            assets.ui_down_key_layout.clone(),
        ),
        Icon::Up => (
            assets.ui_up_key_texture.clone(),
            assets.ui_up_key_layout.clone(),
        ),
        Icon::Left => (
            assets.ui_left_key_texture.clone(),
            assets.ui_left_key_layout.clone(),
        ),
        Icon::Right => (
            assets.ui_right_key_texture.clone(),
            assets.ui_right_key_layout.clone(),
        ),
        Icon::Shift => (
            assets.ui_shift_key_texture.clone(),
            assets.ui_shift_key_layout.clone(),
        ),
    }
}

fn spawn_icon(
    commands: &mut Commands,
    assets: &Res<GameAssets>,
    root: Entity,
    icon: Icon,
    offset: Vec2,
) -> Entity {
    let (texture, layout) = icon_to_texture(assets, &icon);
    let transform = Transform::from_translation(offset.extend(0.0));

    let icon = commands
        .spawn((
            KeyboardIcon,
            Sprite {
                image: texture,
                texture_atlas: Some(TextureAtlas {
                    layout,
                    index: KEY_ICON.first_frame,
                }),
                ..default()
            },
            transform,
        ))
        .id();
    commands.entity(root).add_child(icon);
    icon
}

fn spawn_key_buttons(
    commands: &mut Commands,
    assets: &Res<GameAssets>,
    root: Entity,
    icon: Icon,
    offset: Vec2,
) {
    let entity = spawn_icon(commands, assets, root, icon, offset);

    commands
        .entity(entity)
        .insert((Collider::cuboid(16.0, 16.0), SpriteAnimator::looping(KEY_ICON)));
}

fn spawn_arrows_icon(commands: &mut Commands, assets: &Res<GameAssets>, root: Entity) {
    let icon = commands
        .spawn((
            KeyboardIcon,
            Sprite {
                image: assets.ui_arrows_key.clone(),
                ..default()
            },
            Transform::from_scale(Vec3::splat(1.0)),
        ))
        .id();

    commands.entity(root).add_child(icon);
}

fn spawn_shift_icon(
    commands: &mut Commands,
    assets: &Res<GameAssets>,
    root: Entity,
    icon: Icon,
    offset: Vec2,
) {
    let entity = spawn_icon(commands, assets, root, icon, offset);

    commands
        .entity(entity)
        .insert((Collider::cuboid(16.0, 16.0), SpriteAnimator::looping(SHIFT_ICON)));
}

/// Determine the direction for the keyboard hint UI.
/// With Tiled maps, the hint is placed at a fixed offset from the player spawn point.
fn calculate_hint_direction() -> Vec2 {
    // Default: right direction
    Vec2::new(1.0, 0.0)
}

fn spawn_keyboard_ui(mut commands: Commands, assets: Res<GameAssets>) {
    let dir = calculate_hint_direction();
    let transform = Transform::from_translation(
        dir.normalize_or_zero().extend(0.0) * ANCHOR_DIS,
    )
    .with_scale(Vec3::splat(ICON_SIZE));
    let root = commands
        .spawn((KeyboardHint, YSort(-200.0), transform, Visibility::Inherited))
        .id();

    spawn_key_buttons(
        &mut commands,
        &assets,
        root,
        Icon::Down,
        Vec2::new(0.0, -BUTTON_DIS),
    );
    spawn_key_buttons(
        &mut commands,
        &assets,
        root,
        Icon::Up,
        Vec2::new(0.0, BUTTON_DIS),
    );
    spawn_key_buttons(
        &mut commands,
        &assets,
        root,
        Icon::Left,
        Vec2::new(-BUTTON_DIS, 0.0),
    );
    spawn_key_buttons(
        &mut commands,
        &assets,
        root,
        Icon::Right,
        Vec2::new(BUTTON_DIS, 0.0),
    );
    spawn_arrows_icon(&mut commands, &assets, root);
    spawn_shift_icon(
        &mut commands,
        &assets,
        root,
        Icon::Shift,
        Vec2::new(SHIFT_DIS, SHIFT_DIS),
    );
}

/// The hint is a first-steps tutorial: gone for good once the player has moved
/// by himself, hidden while he talks or is walked by a script.
fn update_keyboard_hint(
    mut commands: Commands,
    q_player: Query<(&Player, Has<ScriptedWalk>)>,
    mut q_hint: Query<(Entity, &mut Visibility), With<KeyboardHint>>,
) {
    let Ok((player, scripted)) = q_player.single() else {
        return;
    };
    for (entity, mut visibility) in &mut q_hint {
        if !scripted && matches!(player.state, PlayerState::Walking | PlayerState::Running) {
            commands.entity(entity).despawn();
            continue;
        }
        let vis = if scripted || player.state == PlayerState::Talking {
            Visibility::Hidden
        } else {
            Visibility::Inherited
        };
        visibility.set_if_neq(vis);
    }
}

pub struct KeyboardUiPlugin;

impl Plugin for KeyboardUiPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(GameState::Gaming), spawn_keyboard_ui)
            .add_systems(Update, update_keyboard_hint.run_if(in_state(GameState::Gaming)));
    }
}