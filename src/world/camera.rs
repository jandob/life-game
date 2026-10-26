use bevy::camera::visibility::RenderLayers;
use bevy::camera::{ScalingMode, Viewport};
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

/// The virtual resolution the game is drawn at, whatever the window size.
pub const VIEW_WIDTH: f32 = 1280.0;
pub const VIEW_HEIGHT: f32 = 720.0;

/// The F3 zoom factor, on top of the fixed view.
#[derive(Resource)]
pub(crate) struct DebugZoom(pub f32);

/// Physical size of the largest `VIEW_WIDTH` x `VIEW_HEIGHT` view that fits the window:
/// a whole-number multiple once the window is big enough, otherwise scaled down to fit.
pub fn view_size(physical_width: u32, physical_height: u32) -> UVec2 {
    let fit = (physical_width as f32 / VIEW_WIDTH).min(physical_height as f32 / VIEW_HEIGHT);
    if fit >= 1.0 {
        let k = fit.floor();
        UVec2::new((VIEW_WIDTH * k) as u32, (VIEW_HEIGHT * k) as u32)
    } else {
        let w = ((VIEW_WIDTH * fit) as u32).max(1);
        let h = ((VIEW_HEIGHT * fit) as u32).max(1);
        UVec2::new(w, h)
    }
}

#[derive(Component)]
pub struct MainCamera;

fn spawn_camera(mut commands: Commands) {
    commands.spawn((
        MainCamera,
        Camera2d,
        // The view is always VIEW_WIDTH x VIEW_HEIGHT world units; `update_viewport`
        // letterboxes the camera into the window.
        Projection::Orthographic(OrthographicProjection {
            scaling_mode: ScalingMode::Fixed {
                width: VIEW_WIDTH,
                height: VIEW_HEIGHT,
            },
            ..OrthographicProjection::default_2d()
        }),
    ));
    // Draws nothing, only clears the whole window black so the bars are black.
    commands.spawn((
        Camera2d,
        Camera {
            order: -1,
            clear_color: ClearColorConfig::Custom(Color::BLACK),
            ..default()
        },
        RenderLayers::none(),
    ));
}

fn update_viewport(
    q_window: Query<&Window, With<PrimaryWindow>>,
    mut q_camera: Query<&mut Camera, With<MainCamera>>,
) {
    let (Ok(window), Ok(mut camera)) = (q_window.single(), q_camera.single_mut()) else {
        return;
    };
    let (w, h) = (window.physical_width(), window.physical_height());
    if w == 0 || h == 0 {
        return;
    }
    let size = view_size(w, h);
    let viewport = Viewport {
        physical_position: (UVec2::new(w, h) - size) / 2,
        physical_size: size,
        ..default()
    };
    let same = camera.viewport.as_ref().is_some_and(|v| {
        v.physical_position == viewport.physical_position
            && v.physical_size == viewport.physical_size
    });
    if !same {
        camera.viewport = Some(viewport);
    }
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
                    zoom_camera,
                    update_viewport,
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
    fn view_is_a_whole_multiple_when_it_fits() {
        assert_eq!(view_size(1280, 720), UVec2::new(1280, 720));
        assert_eq!(view_size(1920, 1080), UVec2::new(1280, 720));
        assert_eq!(view_size(2560, 1440), UVec2::new(2560, 1440));
        assert_eq!(view_size(3000, 1440), UVec2::new(2560, 1440));
    }

    #[test]
    fn view_scales_down_in_small_windows_and_keeps_the_aspect() {
        assert_eq!(view_size(640, 360), UVec2::new(640, 360));
        assert_eq!(view_size(640, 1000), UVec2::new(640, 360));
        assert_eq!(view_size(2000, 300), UVec2::new(533, 300));
    }
}
