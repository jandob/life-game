use crate::{world::MainCamera, GameState};

use super::{
    tiled_map::TiledMap, ABOVE_ZINDEX, BACKGROUND_ZINDEX_ABS, CHUNK_SIZE, RENDERED_CHUNKS_RADIUS,
};
use bevy::{math::Vec3Swizzles, prelude::*};
use bevy_ecs_tilemap::prelude::*;
use std::collections::{HashMap, HashSet};

const RENDER_CHUNK_SIZE: UVec2 = UVec2 {
    x: CHUNK_SIZE * 2,
    y: CHUNK_SIZE * 2,
};

#[derive(Default, Debug, Resource)]
pub struct ChunkManager {
    spawned_chunks: HashSet<IVec2>,
}

#[derive(Component, Deref)]
pub struct ChunkIndex(pub IVec2);

/// Name of the Tiled tile layer a tilemap entity was spawned from.
#[derive(Component)]
pub struct TileLayerName(pub String);

fn spawn_chunk(commands: &mut Commands, tiled_map: &Res<TiledMap>, chunk_pos: IVec2) {
    let render_tile_size = TilemapTileSize {
        x: tiled_map.tile_size,
        y: tiled_map.tile_size,
    };
    // The root carries the chunk's xy position (colliders hang off it); the
    // tilemaps are its children and only differ in z.
    let chunk_entity = commands
        .spawn((
            ChunkIndex(chunk_pos),
            Transform::from_translation(Vec3::new(
                chunk_pos.x as f32 * CHUNK_SIZE as f32 * render_tile_size.x,
                chunk_pos.y as f32 * CHUNK_SIZE as f32 * render_tile_size.y,
                0.0,
            )),
            Visibility::default(),
        ))
        .id();

    let mut above_index = 0;
    let mut below_index = 0;
    for (layer_index, layer) in tiled_map.layers.iter().enumerate() {
        let z = if layer.above {
            above_index += 1;
            ABOVE_ZINDEX + (above_index - 1) as f32
        } else {
            below_index += 1;
            -BACKGROUND_ZINDEX_ABS + (below_index - 1) as f32
        };
        if !layer.visible {
            continue;
        }

        // One tilemap per tileset used in this chunk and layer.
        let mut tilemaps: HashMap<usize, (Entity, TileStorage)> = HashMap::new();
        for x in 0..CHUNK_SIZE {
            for y in 0..CHUNK_SIZE {
                let v = IVec2::new(
                    x as i32 + chunk_pos.x * CHUNK_SIZE as i32,
                    y as i32 + chunk_pos.y * CHUNK_SIZE as i32,
                );
                // Out of bounds or empty tile: nothing to spawn
                let Some(tile) = tiled_map.tile_at(layer_index, v.x, v.y) else {
                    continue;
                };
                let tile_pos = TilePos { x, y };

                let (tilemap_entity, storage) = tilemaps.entry(tile.tileset).or_insert_with(|| {
                    let entity = commands.spawn_empty().id();
                    commands.entity(chunk_entity).add_child(entity);
                    (
                        entity,
                        TileStorage::empty(TilemapSize::new(CHUNK_SIZE, CHUNK_SIZE)),
                    )
                });
                let tile_entity = commands
                    .spawn(TileBundle {
                        position: tile_pos,
                        tilemap_id: TilemapId(*tilemap_entity),
                        texture_index: TileTextureIndex(tile.local),
                        flip: TileFlip {
                            x: tile.flip.x,
                            y: tile.flip.y,
                            d: tile.flip.d,
                        },
                        ..Default::default()
                    })
                    .id();
                commands.entity(*tilemap_entity).add_child(tile_entity);
                storage.set(&tile_pos, tile_entity);
            }
        }

        for (tileset, (tilemap_entity, storage)) in tilemaps {
            commands.entity(tilemap_entity).insert((
                TileLayerName(layer.name.clone()),
                TilemapBundle {
                    grid_size: render_tile_size.into(),
                    size: TilemapSize::new(CHUNK_SIZE, CHUNK_SIZE),
                    storage,
                    texture: TilemapTexture::Single(tiled_map.tilesets[tileset].image.clone()),
                    tile_size: render_tile_size,
                    transform: Transform::from_translation(Vec3::new(0.0, 0.0, z)),
                    render_settings: TilemapRenderSettings {
                        render_chunk_size: RENDER_CHUNK_SIZE,
                        ..Default::default()
                    },
                    ..Default::default()
                },
            ));
        }
    }
}

fn camera_pos_to_chunk_pos(camera_pos: &Vec2, tile_size: f32) -> IVec2 {
    let camera_pos = camera_pos.as_ivec2();
    let chunk_size = IVec2::ONE * CHUNK_SIZE as i32;
    let tile_size = IVec2::ONE * tile_size as i32;

    let offset = IVec2::new(
        if camera_pos.x < 0 { -1 } else { 0 },
        if camera_pos.y < 0 { -1 } else { 0 },
    );

    camera_pos / (chunk_size * tile_size) + offset
}

pub fn spawn_chunks(
    mut commands: Commands,
    mut chunk_manager: ResMut<ChunkManager>,
    tiled_map: Res<TiledMap>,
    q_camera: Query<&Transform, With<MainCamera>>,
) {
    let camera_transform = match q_camera.single() {
        Ok(r) => r,
        Err(_) => return,
    };

    let camera_chunk_pos =
        camera_pos_to_chunk_pos(&camera_transform.translation.xy(), tiled_map.tile_size);
    let chunks_radius = IVec2::new(RENDERED_CHUNKS_RADIUS as i32, RENDERED_CHUNKS_RADIUS as i32);

    for y in (camera_chunk_pos.y - chunks_radius.y)..=(camera_chunk_pos.y + chunks_radius.y) {
        for x in (camera_chunk_pos.x - chunks_radius.x)..=(camera_chunk_pos.x + chunks_radius.x) {
            if !chunk_manager.spawned_chunks.contains(&IVec2::new(x, y)) {
                let chunk_pos = IVec2::new(x, y);
                chunk_manager.spawned_chunks.insert(chunk_pos);
                spawn_chunk(&mut commands, &tiled_map, chunk_pos);
            }
        }
    }
}

pub fn despawn_chunks(
    mut commands: Commands,
    mut chunk_manager: ResMut<ChunkManager>,
    tiled_map: Option<Res<TiledMap>>,
    q_camera: Query<&Transform, With<MainCamera>>,
    q_chunks: Query<(Entity, &ChunkIndex)>,
) {
    let camera_transform = match q_camera.single() {
        Ok(r) => r,
        Err(_) => return,
    };

    let Some(tiled_map) = tiled_map else {
        return;
    };
    let camera_chunk =
        camera_pos_to_chunk_pos(&camera_transform.translation.xy(), tiled_map.tile_size);

    for (entity, chunk) in &q_chunks {
        if (chunk.x - camera_chunk.x).unsigned_abs() > RENDERED_CHUNKS_RADIUS
            || (chunk.y - camera_chunk.y).unsigned_abs() > RENDERED_CHUNKS_RADIUS
        {
            let chunk_pos = IVec2::new(chunk.x, chunk.y);
            chunk_manager.spawned_chunks.remove(&chunk_pos);
            commands.entity(entity).despawn();
        }
    }
}

pub struct ChunkManagerPlugin;

impl Plugin for ChunkManagerPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(TilemapPlugin)
            .insert_resource(ChunkManager::default())
            .add_systems(
                Update,
                (
                    spawn_chunks.run_if(resource_exists::<TiledMap>),
                    despawn_chunks,
                )
                    .run_if(in_state(GameState::Gaming)),
            );
    }
}
