use std::collections::HashMap;

use bevy::asset::{io::Reader, AssetLoader, LoadContext};
use bevy::prelude::*;
use bevy_rapier2d::prelude::*;
use bevy_rapier2d::rapier::math::Pose;
use bevy_rapier2d::rapier::parry::shape::SharedShape;
use serde_json::Value;

use super::TILE_SIZE;
use crate::{GameAssets, GameState};

/// Parsed Tiled map data (loaded from a `.tmj` file plus its `.tsj` tileset).
///
/// Loaded through the asset server (so it works on wasm) as part of
/// `GameAssets`, then copied into a resource when asset loading finishes.
#[derive(Asset, Resource, TypePath, Clone)]
pub struct TiledMap {
    /// Map width in tiles
    pub width: u32,
    /// Map height in tiles
    pub height: u32,
    /// Tile layer data: row-major vec of tile GIDs (0 = empty)
    pub tile_data: Vec<u32>,
    /// GID of the first tile in the tileset
    first_gid: u32,
    /// Collision shapes per tileset tile index, in tile-local game space
    /// (origin at tile center, y-up).
    tile_colliders: HashMap<u32, Collider>,
    /// Object layers
    pub object_layers: Vec<ObjectLayerData>,
}

/// Parsed object layer data from the TMJ file.
#[derive(Clone)]
pub struct ObjectLayerData {
    pub name: String,
    pub objects: Vec<TiledObject>,
}

/// A single object from a Tiled object layer.
#[derive(Clone)]
pub struct TiledObject {
    pub name: String,
    pub obj_type: String,
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
}

#[derive(Debug)]
pub struct TiledMapError(String);

impl std::fmt::Display for TiledMapError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for TiledMapError {}

impl From<String> for TiledMapError {
    fn from(value: String) -> Self {
        Self(value)
    }
}

impl From<&str> for TiledMapError {
    fn from(value: &str) -> Self {
        Self(value.to_string())
    }
}

/// Convert a point in Tiled tile-local space (top-left origin, y-down) to
/// tile-local game space (tile center origin, y-up).
fn tile_local_to_game(x: f32, y: f32) -> Vect {
    Vect::new(x - TILE_SIZE / 2.0, TILE_SIZE / 2.0 - y)
}

/// Build the convex pieces of a single Tiled collision object, positioned
/// inside the tile. Pieces are kept flat because compound shapes can't nest.
fn parse_collision_object(obj: &Value) -> Vec<(Pose, SharedShape)> {
    let x = obj["x"].as_f64().unwrap_or(0.0) as f32;
    let y = obj["y"].as_f64().unwrap_or(0.0) as f32;

    if obj["rotation"].as_f64().unwrap_or(0.0) != 0.0 {
        warn!("Rotated tile collision shapes are not supported, ignoring rotation");
    }

    if let Some(points) = obj["polygon"].as_array() {
        let vertices: Vec<Vect> = points
            .iter()
            .map(|p| {
                tile_local_to_game(
                    x + p["x"].as_f64().unwrap_or(0.0) as f32,
                    y + p["y"].as_f64().unwrap_or(0.0) as f32,
                )
            })
            .collect();
        if vertices.len() < 3 {
            return Vec::new();
        }
        let n = vertices.len() as u32;
        let indices: Vec<[u32; 2]> = (0..n).map(|i| [i, (i + 1) % n]).collect();
        // Hand-drawn polygons are often concave, so decompose instead of taking the hull.
        let decomposition = SharedShape::convex_decomposition(&vertices, &indices);
        return match decomposition.as_compound() {
            Some(compound) => compound.shapes().to_vec(),
            None => vec![(Pose::new(Vect::ZERO, 0.0), decomposition)],
        };
    }

    // Ellipses and points are not supported; everything else is a rectangle.
    if obj["ellipse"].as_bool().unwrap_or(false) || obj["point"].as_bool().unwrap_or(false) {
        warn!("Unsupported tile collision shape (ellipse/point), skipping");
        return Vec::new();
    }
    let width = obj["width"].as_f64().unwrap_or(0.0) as f32;
    let height = obj["height"].as_f64().unwrap_or(0.0) as f32;
    if width <= 0.0 || height <= 0.0 {
        return Vec::new();
    }
    let center = tile_local_to_game(x + width / 2.0, y + height / 2.0);
    vec![(
        Pose::new(center, 0.0),
        SharedShape::cuboid(width / 2.0, height / 2.0),
    )]
}

/// Parse per-tile collision shapes from a TSJ tileset.
fn parse_tile_colliders(tileset: &Value) -> HashMap<u32, Collider> {
    let mut colliders = HashMap::new();
    let Some(tiles) = tileset["tiles"].as_array() else {
        return colliders;
    };

    for tile in tiles {
        let Some(id) = tile["id"].as_u64() else {
            continue;
        };
        let Some(objects) = tile["objectgroup"]["objects"].as_array() else {
            continue;
        };

        let shapes: Vec<(Pose, SharedShape)> =
            objects.iter().flat_map(parse_collision_object).collect();

        if !shapes.is_empty() {
            colliders.insert(id as u32, Collider::from(SharedShape::compound(shapes)));
        }
    }

    colliders
}

fn parse_object_layer(layer: &Value) -> ObjectLayerData {
    let name = layer["name"].as_str().unwrap_or("").to_string();
    let objects = layer["objects"]
        .as_array()
        .map(|objs| {
            objs.iter()
                .map(|obj| TiledObject {
                    name: obj["name"].as_str().unwrap_or("").to_string(),
                    obj_type: obj["type"].as_str().unwrap_or("").to_string(),
                    x: obj["x"].as_f64().unwrap_or(0.0) as f32,
                    y: obj["y"].as_f64().unwrap_or(0.0) as f32,
                    width: obj["width"].as_f64().unwrap_or(0.0) as f32,
                    height: obj["height"].as_f64().unwrap_or(0.0) as f32,
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    ObjectLayerData { name, objects }
}

impl TiledMap {
    /// Get the tile index at the given world tile coordinate.
    /// Returns `None` if out of bounds or empty (GID = 0).
    ///
    /// The returned index is 0-based and matches the tileset image position.
    pub fn tile_at(&self, x: i32, y: i32) -> Option<u32> {
        let map_width = self.width as i32;
        let map_height = self.height as i32;

        // Convert from game coordinates (centered origin, y-up) to Tiled coordinates
        // (top-left origin, y-down), so the map looks the same in Tiled and in game.
        let tx = x + map_width / 2;
        let ty = map_height / 2 - 1 - y;

        if tx < 0 || ty < 0 || tx >= map_width || ty >= map_height {
            return None;
        }

        let idx = ty as usize * self.width as usize + tx as usize;
        let gid = *self.tile_data.get(idx)?;
        if gid < self.first_gid {
            return None;
        }
        Some(gid - self.first_gid)
    }

    /// Get the collision shape for a tile at the given world tile coordinate,
    /// as drawn in the tileset's collision editor. The collider is centered
    /// on the tile.
    pub fn tile_collision_shape(&self, x: i32, y: i32) -> Option<Collider> {
        let index = self.tile_at(x, y)?;
        self.tile_colliders.get(&index).cloned()
    }

    /// The rectangle covered by the map's tiles, in game world coordinates.
    pub fn world_bounds(&self) -> Rect {
        // Tile x spans -width/2 ..= width - width/2 - 1 and tiles are centered
        // on their grid position, so the outer edges sit half a tile further out.
        let min = Vec2::new(
            -((self.width / 2) as f32) * TILE_SIZE - TILE_SIZE / 2.0,
            -((self.height - self.height / 2) as f32) * TILE_SIZE - TILE_SIZE / 2.0,
        );
        let size = Vec2::new(self.width as f32, self.height as f32) * TILE_SIZE;
        Rect::from_corners(min, min + size)
    }

    /// Get all objects from an object layer by name.
    pub fn object_layer(&self, name: &str) -> &[TiledObject] {
        for layer in &self.object_layers {
            if layer.name == name {
                return &layer.objects;
            }
        }
        &[]
    }

    /// Convert a Tiled pixel position (top-left origin, y-down) to
    /// game world position (centered origin, y-up).
    ///
    /// Game tiles are centered on their grid position, so tile (0, 0) spans
    /// -8..8 in game space; the half-tile shift keeps objects aligned with
    /// the ground as drawn in Tiled.
    pub fn tiled_to_game(&self, tiled_x: f32, tiled_y: f32) -> Vec2 {
        let half_w = self.width as f32 * TILE_SIZE / 2.0;
        let half_h = self.height as f32 * TILE_SIZE / 2.0;
        Vec2::new(
            tiled_x - half_w - TILE_SIZE / 2.0,
            half_h - tiled_y - TILE_SIZE / 2.0,
        )
    }
}

/// Loads `.tmj` maps and the (single) external `.tsj` tileset they reference.
#[derive(Default, TypePath)]
pub struct TiledMapLoader;

impl AssetLoader for TiledMapLoader {
    type Asset = TiledMap;
    type Settings = ();
    type Error = TiledMapError;

    async fn load(
        &self,
        reader: &mut dyn Reader,
        _settings: &(),
        load_context: &mut LoadContext<'_>,
    ) -> Result<TiledMap, TiledMapError> {
        let mut bytes = Vec::new();
        reader
            .read_to_end(&mut bytes)
            .await
            .map_err(|e| format!("Failed to read map file: {e}"))?;
        let json: Value =
            serde_json::from_slice(&bytes).map_err(|e| format!("Failed to parse TMJ: {e}"))?;

        let width = json["width"].as_u64().ok_or("Missing width")? as u32;
        let height = json["height"].as_u64().ok_or("Missing height")? as u32;

        let tileset_ref = json["tilesets"]
            .as_array()
            .and_then(|t| t.first())
            .ok_or("Map references no tileset")?;
        let first_gid = tileset_ref["firstgid"].as_u64().unwrap_or(1) as u32;
        let tile_colliders = match tileset_ref["source"].as_str() {
            Some(source) => {
                let tileset_path = load_context
                    .path()
                    .resolve_embed_str(source)
                    .map_err(|e| format!("Invalid tileset path {source}: {e}"))?;
                let tileset_bytes = load_context
                    .read_asset_bytes(tileset_path)
                    .await
                    .map_err(|e| format!("Failed to read tileset {source}: {e}"))?;
                let tileset: Value = serde_json::from_slice(&tileset_bytes)
                    .map_err(|e| format!("Failed to parse TSJ {source}: {e}"))?;
                parse_tile_colliders(&tileset)
            }
            // Embedded tileset
            None => parse_tile_colliders(tileset_ref),
        };

        let layers = json["layers"].as_array().ok_or("Missing layers array")?;

        let mut tile_data = Vec::new();
        let mut object_layers = Vec::new();

        for layer in layers {
            match layer["type"].as_str().unwrap_or("") {
                "tilelayer" => {
                    let data = layer["data"]
                        .as_array()
                        .ok_or("Missing data in tile layer")?;
                    tile_data = data
                        .iter()
                        .map(|v| v.as_u64().unwrap_or(0) as u32)
                        .collect();
                }
                "objectgroup" => object_layers.push(parse_object_layer(layer)),
                _ => {}
            }
        }

        Ok(TiledMap {
            width,
            height,
            tile_data,
            first_gid,
            tile_colliders,
            object_layers,
        })
    }

    fn extensions(&self) -> &[&str] {
        &["tmj"]
    }
}

/// Copy the loaded map asset into a resource for easy access by gameplay systems.
fn insert_tiled_map_resource(
    mut commands: Commands,
    assets: Res<GameAssets>,
    maps: Res<Assets<TiledMap>>,
) {
    match maps.get(&assets.world_map) {
        Some(map) => commands.insert_resource(map.clone()),
        None => error!("Tiled map asset missing after loading"),
    }
}

pub struct TiledMapPlugin;

impl Plugin for TiledMapPlugin {
    fn build(&self, app: &mut App) {
        app.init_asset::<TiledMap>()
            .init_asset_loader::<TiledMapLoader>()
            .add_systems(OnExit(GameState::AssetLoading), insert_tiled_map_resource);
    }
}
