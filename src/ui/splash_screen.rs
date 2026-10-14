use std::time::Duration;

use bevy::prelude::*;
use bevy_tweening::{lens::UiTransformScaleLens, CycleCompletedEvent, Tween, TweenAnim};

use crate::GameState;

#[derive(Component)]
struct SplashScreen;

fn spawn_splash_screen(mut commands: Commands, asset_server: Res<AssetServer>) {
    let icon = asset_server.load("library/ui/bevy_icon.png");
    let image = commands
        .spawn((
            Node {
                width: Val::Px(200.0),
                ..default()
            },
            ImageNode::new(icon),
            ZIndex(1000),
        ))
        .id();

    commands
        .spawn((
            Node {
                align_items: AlignItems::Center,
                justify_content: JustifyContent::Center,
                width: Val::Percent(100.0),
                height: Val::Percent(100.0),
                ..default()
            },
            SplashScreen,
        ))
        .add_child(image);
}

fn fade_out_splash_screen(
    mut commands: Commands,
    q_splash_screen: Query<Entity, With<SplashScreen>>,
) {
    for entity in &q_splash_screen {
        let tween = Tween::new(
            EaseFunction::ExponentialIn,
            Duration::from_secs_f32(0.5),
            UiTransformScaleLens {
                start: Vec2::ONE,
                end: Vec2::ZERO,
            },
        )
        .with_cycle_completed_event(true);
        commands.entity(entity).insert(TweenAnim::new(tween));
    }
}

fn despawn_splash_screen(
    mut commands: Commands,
    mut ev_tween_completed: MessageReader<CycleCompletedEvent>,
) {
    for ev in ev_tween_completed.read() {
        commands.entity(ev.anim_entity).despawn();
    }
}

pub struct SplashScreenPlugin;

impl Plugin for SplashScreenPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(GameState::AssetLoading), spawn_splash_screen)
            .add_systems(OnExit(GameState::AssetLoading), fade_out_splash_screen)
            .add_systems(Update, (despawn_splash_screen,));
    }
}
