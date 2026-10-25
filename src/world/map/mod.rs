pub(crate) mod doors;
pub(crate) mod tiled_map;

use bevy::prelude::*;

pub struct MapPlugin;

impl Plugin for MapPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins((doors::DoorsPlugin, tiled_map::TiledMapPlugin));
    }
}
