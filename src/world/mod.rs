pub mod camera;
pub mod camera_shake;
pub mod ending;
pub mod map;
pub mod side_view;

pub use camera::MainCamera;
// pub use camera_shake::CameraShake;

use bevy::prelude::*;

pub struct WorldPlugin;

impl Plugin for WorldPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins((
            camera::CameraPlugin,
            camera_shake::CameraShakePlugin,
            map::MapPlugin,
            ending::EndingPlugin,
            side_view::SideViewPlugin,
        ));
    }
}
