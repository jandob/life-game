use bevy::prelude::*;

use super::{
    chunk_manager::{despawn_chunks, spawn_chunks, ChunkIndex},
    tiled_map::TiledMap,
    CHUNK_SIZE, TILE_SIZE,
};

/// Spawn collision shapes for tiles that have collision defined in the tileset.
/// Runs on entities with `Added<ChunkIndex>` (same pattern as before).
pub fn spawn_water_collisions(
    mut commands: Commands,
    tiled_map: Res<TiledMap>,
    q_chunks: Query<(Entity, &ChunkIndex), Added<ChunkIndex>>,
) {
    for (entity, chunk) in &q_chunks {
        for x in 0..CHUNK_SIZE {
            for y in 0..CHUNK_SIZE {
                let v = IVec2::new(
                    x as i32 + chunk.x * CHUNK_SIZE as i32,
                    y as i32 + chunk.y * CHUNK_SIZE as i32,
                );

                // Query the TiledMap for a collision shape on this tile
                if let Some(collider) = tiled_map.tile_collision_shape(v.x, v.y) {
                    let pos = Vec3::new(
                        x as f32 * TILE_SIZE,
                        y as f32 * TILE_SIZE,
                        0.0,
                    );
                    let collision = commands
                        .spawn((collider, Transform::from_translation(pos)))
                        .id();
                    commands.entity(entity).add_children(&[collision]);
                }
            }
        }
    }
}

pub struct MapCollisionPlugin;

impl Plugin for MapCollisionPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(
            Update,
            spawn_water_collisions
                .run_if(resource_exists::<TiledMap>)
                .before(spawn_chunks)
                .before(despawn_chunks),
        );
    }
}