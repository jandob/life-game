use bevy::camera::ScalingMode;
#[cfg(not(target_arch = "wasm32"))]
use bevy::render::view::window::screenshot::{save_to_disk, Screenshot};
use bevy::window::PrimaryWindow;
#[cfg(not(target_arch = "wasm32"))]
use bevy::window::{MonitorSelection, VideoModeSelection, WindowMode};
use bevy::{prelude::*, transform::TransformSystems};

use super::camera_shake::{update_camera, CameraShake};
use crate::player::input::PlayerInput;
use crate::player::Player;
use crate::utils::DebugActive;

/// Art px visible vertically that the integer scale aims for.
const TARGET_VISIBLE_HEIGHT: f32 = 540.0;

/// The F3 zoom factor, on top of the integer pixel scale.
#[derive(Resource)]
struct DebugZoom(f32);

/// Physical screen px per art px: a whole number, so every pixel is drawn equally big.
fn pixel_scale(physical_height: u32) -> f32 {
    (physical_height as f32 / TARGET_VISIBLE_HEIGHT)
        .round()
        .max(1.0)
}

#[derive(Component)]
pub struct MainCamera;

fn spawn_camera(mut commands: Commands) {
    commands.spawn((
        MainCamera,
        Camera2d,
        // `WindowSize` maps one world unit to one logical px at scale 1;
        // `update_projection_scale` sets the scale for whole physical px per art px.
        Projection::Orthographic(OrthographicProjection {
            scaling_mode: ScalingMode::WindowSize,
            ..OrthographicProjection::default_2d()
        }),
    ));
}

pub(crate) fn update_camera_target(
    mut shake: ResMut<CameraShake>,
    q_player: Query<&Transform, With<Player>>,
) {
    let player_transform = match q_player.single() {
        Ok(r) => r,
        Err(_) => return,
    };
    shake.update_target(player_transform.translation.truncate());
}

fn zoom_camera(
    player_input: Res<PlayerInput>,
    debug_active: Res<DebugActive>,
    mut zoom: ResMut<DebugZoom>,
) {
    if !**debug_active {
        return;
    }
    zoom.0 = (zoom.0 + player_input.scroll).clamp(1.0, 10.0);
}

/// Keeps `ortho.scale = scale_factor / t * debug_zoom`, which follows window size
/// and scale factor changes.
fn update_projection_scale(
    zoom: Res<DebugZoom>,
    q_window: Query<&Window, With<PrimaryWindow>>,
    mut q_projection: Query<&mut Projection, With<MainCamera>>,
) {
    let Ok(window) = q_window.single() else {
        return;
    };
    let Ok(mut projection) = q_projection.single_mut() else {
        return;
    };
    let Projection::Orthographic(ortho) = &*projection else {
        return;
    };
    let scale = window.scale_factor() / pixel_scale(window.physical_height()) * zoom.0;
    if ortho.scale != scale {
        if let Projection::Orthographic(ortho) = &mut *projection {
            ortho.scale = scale;
        }
    }
}

#[cfg(not(target_arch = "wasm32"))]
fn toggle_full_screen(
    mut main_window: Query<&mut Window, With<PrimaryWindow>>,
    player_input: Res<PlayerInput>,
) {
    if !player_input.toggle_fullscreen {
        return;
    }

    let mut window = match main_window.single_mut() {
        Ok(w) => w,
        Err(err) => {
            error!("there is not exactly one window, {}", err);
            return;
        }
    };

    window.mode = if window.mode == WindowMode::Windowed {
        WindowMode::Fullscreen(MonitorSelection::Current, VideoModeSelection::Current)
    } else {
        WindowMode::Windowed
    }
}

#[cfg(not(target_arch = "wasm32"))]
fn take_screenshot(
    keys: Res<ButtonInput<KeyCode>>,
    mut commands: Commands,
    mut counter: Local<u32>,
) {
    if !keys.just_pressed(KeyCode::F12) {
        return;
    }

    let path = format!("./screenshot-{}.png", *counter);
    *counter += 1;
    commands
        .spawn(Screenshot::primary_window())
        .observe(save_to_disk(path));
}

pub struct CameraPlugin;

impl Plugin for CameraPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(DebugZoom(1.0))
            .add_systems(Startup, spawn_camera)
            .add_systems(
                Update,
                (
                    #[cfg(not(target_arch = "wasm32"))]
                    toggle_full_screen,
                    #[cfg(not(target_arch = "wasm32"))]
                    take_screenshot,
                    (zoom_camera, update_projection_scale).chain(),
                ),
            )
            .add_systems(
                PostUpdate,
                update_camera_target
                    .before(TransformSystems::Propagate)
                    .before(update_camera),
            );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pixel_scale_is_a_whole_number_near_540_visible() {
        assert_eq!(pixel_scale(360), 1.0);
        assert_eq!(pixel_scale(720), 1.0);
        assert_eq!(pixel_scale(900), 2.0);
        assert_eq!(pixel_scale(1080), 2.0);
        assert_eq!(pixel_scale(1440), 3.0);
        assert_eq!(pixel_scale(2160), 4.0);
    }
}
