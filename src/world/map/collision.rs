use bevy::prelude::*;
use bevy_rapier2d::prelude::*;

use super::{
    chunk_manager::{despawn_chunks, spawn_chunks, ChunkIndex},
    tiled_map::TiledMap,
    CHUNK_SIZE,
};
use crate::GameState;

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

                // Every colliding layer contributes the shape of its tile
                for (layer_index, layer) in tiled_map.layers.iter().enumerate() {
                    if !layer.collides {
                        continue;
                    }
                    if let Some(collider) = tiled_map.tile_collision_shape(layer_index, v.x, v.y) {
                        let pos = Vec3::new(x as f32 * tiled_map.tile_size, y as f32 * tiled_map.tile_size, 0.0);
                        let collision = commands
                            .spawn((collider, Transform::from_translation(pos)))
                            .id();
                        commands.entity(entity).add_children(&[collision]);
                    }
                }
            }
        }
    }
}

/// Spawn invisible walls just outside the map so the player can't leave the world.
fn spawn_map_border(mut commands: Commands, tiled_map: Res<TiledMap>) {
    let bounds = tiled_map.world_bounds();
    let half = bounds.half_size();
    let center = bounds.center();
    let border = tiled_map.tile_size;
    let t = border / 2.0;

    // (offset from map center, half extents) for left, right, bottom, top
    let walls = [
        (Vec2::new(-half.x - t, 0.0), Vec2::new(t, half.y + border)),
        (Vec2::new(half.x + t, 0.0), Vec2::new(t, half.y + border)),
        (Vec2::new(0.0, -half.y - t), Vec2::new(half.x + border, t)),
        (Vec2::new(0.0, half.y + t), Vec2::new(half.x + border, t)),
    ];

    for (offset, half_extents) in walls {
        commands.spawn((
            Name::new("MapBorder"),
            RigidBody::Fixed,
            Collider::cuboid(half_extents.x, half_extents.y),
            Transform::from_translation((center + offset).extend(0.0)),
        ));
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
        )
        .add_systems(OnEnter(GameState::Gaming), spawn_map_border);
    }
}