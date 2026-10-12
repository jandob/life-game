mod chunk_manager;
mod collision;
pub(crate) mod doors;
mod flora;
pub(crate) mod tiled_map;

use bevy::prelude::*;

// The tile size comes from each map (`TiledMap::tile_size`).
const CHUNK_SIZE: u32 = 16;
const BACKGROUND_ZINDEX_ABS: f32 = 800.0;
// Above layers draw over every YSorted entity (z is roughly within +-1, see camera.rs)
// and stay inside the camera's 1000 range.
// Above every YSort value. Note: this also draws over world-space hints and the
// ending sequence where they overlap an above layer.
const ABOVE_ZINDEX: f32 = 500.0;

const RENDERED_CHUNKS_RADIUS: u32 = 3;

pub struct MapPlugin;

impl Plugin for MapPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins((
            chunk_manager::ChunkManagerPlugin,
            collision::MapCollisionPlugin,
            doors::DoorsPlugin,
            flora::FloraPlugin,
            tiled_map::TiledMapPlugin,
        ));
    }
}
