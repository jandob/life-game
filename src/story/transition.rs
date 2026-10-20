//! Transitions between scenes: screen fades, title cards, placing actors and
//! starting the next scene once the current one has finished.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use bevy::prelude::*;
use bevy::time::Real;
use bevy_rapier2d::prelude::*;

use super::scripted::{Actor, ScriptedWalk};
use crate::player::chat::PlayerStartedChat;
use crate::player::{Player, PlayerState};
use crate::ui::dialogue::runner::RunnerFlags;
use crate::world::ending::EndingTriggered;
use crate::world::map::tiled_map::TiledMap;
use crate::{GameAssets, GameState};

/// Seconds for a full fade to or from black.
const FADE_SECONDS: f32 = 1.0;
/// Seconds a title card stays on screen.
const CARD_SECONDS: f32 = 2.5;
/// Above the dialogue box, below the end card text (1001).
const OVERLAY_Z: i32 = 500;

/// The scene that `<<next_scene>>` starts after the current dialogue has completed.
/// While it is set the player can't start another conversation.
#[derive(Resource, Default)]
pub struct QueuedScene(pub Option<String>);

/// The black overlay used by `<<fade_out>>` and `<<fade_in>>`.
#[derive(Resource, Default)]
pub struct ScreenFade {
    alpha: f32,
    target: f32,
    done: Option<Arc<AtomicBool>>,
}

impl ScreenFade {
    fn start(&mut self, target: f32) -> Arc<AtomicBool> {
        if let Some(old) = self.done.take() {
            old.store(true, Ordering::Relaxed);
        }
        let done = Arc::new(AtomicBool::new(false));
        self.target = target;
        self.done = Some(done.clone());
        done
    }

    /// Clears the screen at once, e.g. when a queued scene could not start.
    pub fn clear(&mut self) {
        self.start(0.0).store(true, Ordering::Relaxed);
        self.alpha = 0.0;
    }

    /// Makes the screen black at once, e.g. for a start point after a `<<fade_out>>`.
    pub fn black(&mut self) {
        self.start(1.0).store(true, Ordering::Relaxed);
        self.alpha = 1.0;
    }
}

/// The title card shown by `<<card>>`.
#[derive(Resource, Default)]
pub struct Card {
    timer: Option<Timer>,
    done: Option<Arc<AtomicBool>>,
}

#[derive(Component)]
struct FadeOverlay;

#[derive(Component)]
pub struct CardText;

/// `<<next_scene NODE>>`
pub fn next_scene_command(In(node): In<String>, mut queued: ResMut<QueuedScene>) {
    if let Some(old) = queued.0.replace(node) {
        warn!("next_scene: replacing the queued scene '{old}'");
    }
}

/// `<<fade_out>>`: blocks until the screen is black.
pub fn fade_out_command(In(_): In<()>, mut fade: ResMut<ScreenFade>) -> Arc<AtomicBool> {
    fade.start(1.0)
}

/// `<<fade_in>>`: blocks until the screen is clear.
pub fn fade_in_command(In(_): In<()>, mut fade: ResMut<ScreenFade>) -> Arc<AtomicBool> {
    fade.start(0.0)
}

/// `<<card "TEXT">>`: shows a title card over the black screen for a moment.
pub fn card_command(
    In(text): In<String>,
    mut card: ResMut<Card>,
    mut q_text: Query<&mut Text, With<CardText>>,
) -> Arc<AtomicBool> {
    if let Some(old) = card.done.take() {
        old.store(true, Ordering::Relaxed);
    }
    for mut t in &mut q_text {
        t.0 = text.clone();
    }
    let done = Arc::new(AtomicBool::new(false));
    card.timer = Some(Timer::from_seconds(CARD_SECONDS, TimerMode::Once));
    card.done = Some(done.clone());
    done
}

/// `<<place ACTOR PATH>>`: puts the actor on the first point of the path at once.
pub fn place_command(
    In((actor, path)): In<(String, String)>,
    mut commands: Commands,
    tiled_map: Res<TiledMap>,
    mut q_actors: Query<(
        Entity,
        &Actor,
        &mut Transform,
        Option<&ScriptedWalk>,
        Option<&mut Velocity>,
    )>,
) {
    let Some((entity, _, mut transform, walk, velocity)) =
        q_actors.iter_mut().find(|(_, a, ..)| a.0 == actor)
    else {
        error!("place: unknown actor '{actor}'");
        return;
    };
    let Some(point) = tiled_map.path(&path).and_then(|p| p.first().copied()) else {
        error!("place: unknown or empty path '{path}'");
        return;
    };
    if let Some(walk) = walk {
        walk.finish();
        commands.entity(entity).remove::<ScriptedWalk>();
    }
    if let Some(mut velocity) = velocity {
        velocity.linear = Vec2::ZERO;
    }
    transform.translation.x = point.x;
    transform.translation.y = point.y;
}

fn spawn_overlay(mut commands: Commands, assets: Res<GameAssets>) {
    commands
        .spawn((
            FadeOverlay,
            Node {
                position_type: PositionType::Absolute,
                width: Val::Percent(100.0),
                height: Val::Percent(100.0),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                ..default()
            },
            BackgroundColor(Color::NONE),
            ZIndex(OVERLAY_Z),
            Pickable::IGNORE,
        ))
        .with_child((
            CardText,
            Text::new(String::new()),
            TextFont {
                font: assets.silver_font.clone().into(),
                font_size: 80.0.into(),
                ..default()
            },
            TextColor::WHITE,
        ));
}

/// Fades on real time, so a fade never stalls a scene while virtual time stands still.
fn update_fade(
    real_time: Res<Time<Real>>,
    mut fade: ResMut<ScreenFade>,
    mut q_overlay: Query<&mut BackgroundColor, With<FadeOverlay>>,
) {
    let step = real_time.delta_secs() / FADE_SECONDS;
    let target = fade.target;
    fade.alpha = if fade.alpha < target {
        (fade.alpha + step).min(target)
    } else {
        (fade.alpha - step).max(target)
    };
    if fade.alpha == target {
        if let Some(done) = fade.done.take() {
            done.store(true, Ordering::Relaxed);
        }
    }
    for mut color in &mut q_overlay {
        color.0 = Color::srgba(0.0, 0.0, 0.0, fade.alpha);
    }
}

fn update_card(
    real_time: Res<Time<Real>>,
    mut card: ResMut<Card>,
    mut q_text: Query<&mut Text, With<CardText>>,
) {
    let Some(timer) = card.timer.as_mut() else {
        return;
    };
    timer.tick(real_time.delta());
    if !timer.is_finished() {
        return;
    }
    card.timer = None;
    if let Some(done) = card.done.take() {
        done.store(true, Ordering::Relaxed);
    }
    for mut t in &mut q_text {
        t.0.clear();
    }
}

/// Starts the queued scene once the previous dialogue runner is gone.
pub(crate) fn start_queued_scene(
    mut queued: ResMut<QueuedScene>,
    q_runner_flags: Query<&RunnerFlags>,
    mut q_player: Query<&mut Player>,
    mut ev_player_started_chat: MessageWriter<PlayerStartedChat>,
) {
    if queued.0.is_none() || q_runner_flags.iter().any(|flags| flags.active) {
        return;
    }
    let Ok(mut player) = q_player.single_mut() else {
        return;
    };
    let node = queued.0.take().unwrap();
    player.state = PlayerState::Talking;
    ev_player_started_chat.write(PlayerStartedChat {
        node,
        direction: player.current_direction,
    });
}

/// The end card or leaving the game drops a queued scene and clears the screen.
fn reset_transitions(mut queued: ResMut<QueuedScene>, mut fade: ResMut<ScreenFade>) {
    queued.0 = None;
    fade.clear();
}

pub struct TransitionPlugin;

impl Plugin for TransitionPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<QueuedScene>()
            .init_resource::<ScreenFade>()
            .init_resource::<Card>()
            .add_systems(OnEnter(GameState::Gaming), spawn_overlay)
            .add_systems(OnExit(GameState::Gaming), reset_transitions)
            .add_systems(
                Update,
                (
                    (update_fade, update_card).run_if(not(in_state(GameState::AssetLoading))),
                    reset_transitions.run_if(on_message::<EndingTriggered>),
                ),
            );
    }
}

/// Whether a conversation may start now: not while a scene is queued.
pub fn scene_queued(queued: Option<Res<QueuedScene>>) -> bool {
    queued.is_some_and(|q| q.0.is_some())
}
