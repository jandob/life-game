use std::collections::HashMap;

use bevy::asset::{io::Reader, AssetLoader, LoadContext};
use bevy::prelude::*;
use bevy::render::renderer::RenderDevice;
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
    /// Tile layers in file order (bottom to top)
    pub layers: Vec<TileLayer>,
    /// Tilesets sorted by `first_gid`
    pub tilesets: Vec<Tileset>,
    /// Object layers
    pub object_layers: Vec<ObjectLayerData>,
}

/// A tile layer of the map.
#[derive(Clone)]
pub struct TileLayer {
    pub name: String,
    /// Row-major tile GIDs including flip bits (0 = empty)
    data: Vec<u32>,
    /// Renders above the player and every YSorted entity (`above = true`)
    pub above: bool,
    /// Whether tiles of this layer spawn colliders (`collides`, default `!above`)
    pub collides: bool,
    /// Hidden layers are not drawn but still collide when `collides` is set.
    pub visible: bool,
}

/// A tileset referenced by the map.
#[derive(Clone)]
pub struct Tileset {
    pub first_gid: u32,
    pub tile_count: u32,
    pub image: Handle<Image>,
    /// Collision shapes per local tile id, in tile-local game space
    /// (origin at tile center, y-up).
    colliders: HashMap<u32, Collider>,
}

/// Tiled's flip flags of a cell.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct TileFlags {
    pub x: bool,
    pub y: bool,
    pub d: bool,
}

/// A resolved cell: which tileset, which tile in it, and how it is flipped.
#[derive(Clone, Copy, Debug)]
pub struct TileRef {
    pub tileset: usize,
    pub local: u32,
    pub flip: TileFlags,
}

/// Height of a character's transform above its feet (collider centre), in px.
const FEET_TO_TRANSFORM: f32 = 16.0;

const FLIP_H: u32 = 0x8000_0000;
const FLIP_V: u32 = 0x4000_0000;
const FLIP_D: u32 = 0x2000_0000;
const FLIP_HEX: u32 = 0x1000_0000;
const FLIP_MASK: u32 = FLIP_H | FLIP_V | FLIP_D | FLIP_HEX;

fn layer_bool_property(layer: &Value, name: &str) -> Option<bool> {
    layer["properties"]
        .as_array()?
        .iter()
        .find(|p| p["name"].as_str() == Some(name))
        .and_then(|p| p["value"].as_bool())
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
    /// Custom properties
    pub properties: HashMap<String, PropValue>,
    /// Polyline points in absolute Tiled coordinates (empty for other shapes)
    pub points: Vec<Vec2>,
}

/// A custom property value of a Tiled object.
#[derive(Clone, Debug, PartialEq)]
pub enum PropValue {
    Str(String),
    Bool(bool),
    Int(i64),
    Float(f64),
}

impl TiledObject {
    pub fn prop_str(&self, name: &str) -> Option<&str> {
        match self.properties.get(name)? {
            PropValue::Str(s) => Some(s),
            _ => None,
        }
    }

    pub fn prop_bool(&self, name: &str) -> Option<bool> {
        match self.properties.get(name)? {
            PropValue::Bool(b) => Some(*b),
            _ => None,
        }
    }
}

fn parse_properties(obj: &Value) -> HashMap<String, PropValue> {
    let Some(props) = obj["properties"].as_array() else {
        return HashMap::new();
    };
    props
        .iter()
        .filter_map(|p| {
            let name = p["name"].as_str()?.to_string();
            let value = &p["value"];
            let value = match p["type"].as_str().unwrap_or("string") {
                "bool" => PropValue::Bool(value.as_bool()?),
                "int" => PropValue::Int(value.as_i64()?),
                "float" => PropValue::Float(value.as_f64()?),
                "string" => PropValue::Str(value.as_str()?.to_string()),
                _ => return None,
            };
            Some((name, value))
        })
        .collect()
}

fn parse_polyline(obj: &Value) -> Vec<Vec2> {
    let x = obj["x"].as_f64().unwrap_or(0.0) as f32;
    let y = obj["y"].as_f64().unwrap_or(0.0) as f32;
    obj["polyline"]
        .as_array()
        .map(|points| {
            points
                .iter()
                .map(|p| {
                    Vec2::new(
                        x + p["x"].as_f64().unwrap_or(0.0) as f32,
                        y + p["y"].as_f64().unwrap_or(0.0) as f32,
                    )
                })
                .collect()
        })
        .unwrap_or_default()
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
                    properties: parse_properties(obj),
                    points: parse_polyline(obj),
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    ObjectLayerData { name, objects }
}

impl TiledMap {
    /// Resolve the cell of `layer` at the given world tile coordinate.
    /// Returns `None` if out of bounds, empty (GID = 0) or not covered by a tileset.
    pub fn tile_at(&self, layer: usize, x: i32, y: i32) -> Option<TileRef> {
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
        let raw = *self.layers.get(layer)?.data.get(idx)?;
        let gid = raw & !FLIP_MASK;
        if gid == 0 {
            return None;
        }
        // Tilesets are sorted by first_gid: the last one starting at or below gid.
        let tileset = self.tilesets.partition_point(|t| t.first_gid <= gid).checked_sub(1)?;
        let local = gid - self.tilesets[tileset].first_gid;
        if local >= self.tilesets[tileset].tile_count {
            return None;
        }
        Some(TileRef {
            tileset,
            local,
            flip: TileFlags {
                x: raw & FLIP_H != 0,
                y: raw & FLIP_V != 0,
                d: raw & FLIP_D != 0,
            },
        })
    }

    /// Get the collision shape for a tile of `layer` at the given world tile
    /// coordinate, as drawn in the tileset's collision editor. The collider is
    /// centered on the tile. Flipped tiles use their unflipped shape.
    pub fn tile_collision_shape(&self, layer: usize, x: i32, y: i32) -> Option<Collider> {
        let tile = self.tile_at(layer, x, y)?;
        self.tilesets[tile.tileset].colliders.get(&tile.local).cloned()
    }

    /// Whether any colliding layer has a tile with a collision shape here.
    pub fn has_collision(&self, x: i32, y: i32) -> bool {
        self.layers
            .iter()
            .enumerate()
            .any(|(i, layer)| layer.collides && self.tile_collision_shape(i, x, y).is_some())
    }

    /// Flipped collision is not supported yet: warn once per map about every
    /// flipped colliding tile (which keeps its unflipped shape).
    fn warn_flipped_colliders(&self) {
        let flipped = self
            .layers
            .iter()
            .filter(|layer| layer.collides)
            .flat_map(|layer| layer.data.iter())
            .filter(|&&raw| raw & (FLIP_H | FLIP_V | FLIP_D) != 0)
            .filter(|&&raw| {
                let gid = raw & !FLIP_MASK;
                let Some(i) = self.tilesets.partition_point(|t| t.first_gid <= gid).checked_sub(1)
                else {
                    return false;
                };
                let t = &self.tilesets[i];
                t.colliders.contains_key(&(gid - t.first_gid))
            })
            .count();
        if flipped > 0 {
            warn!("{flipped} flipped tile(s) with collision shapes: flipped collision is not supported, using the unflipped shape");
        }
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

    /// A named route from the `Paths` object layer as transform-space points.
    ///
    /// Path points are authored at the feet. Characters are drawn at scale 0.5 with
    /// their collider 32 px below the transform, so every point is raised by 16 px.
    /// A polyline gives all its points; a point or rectangle object gives its centre.
    pub fn path(&self, name: &str) -> Option<Vec<Vec2>> {
        let obj = self
            .object_layer("Paths")
            .iter()
            .find(|obj| obj.name == name)?;
        let tiled_points = if obj.points.is_empty() {
            vec![Vec2::new(obj.x + obj.width / 2.0, obj.y + obj.height / 2.0)]
        } else {
            obj.points.clone()
        };
        Some(
            tiled_points
                .into_iter()
                .map(|p| self.tiled_to_game(p.x, p.y) + Vec2::new(0.0, FEET_TO_TRANSFORM))
                .collect(),
        )
    }

    /// Convert a Tiled pixel position (top-left origin, y-down) to
    /// game world position (centered origin, y-up).
    ///
    /// Game tiles are centered on their grid position, so tile (0, 0) spans
    /// -8..8 in game space; the half-tile shift keeps objects aligned with
    /// the ground as drawn in Tiled.
    pub fn tiled_to_game(&self, tiled_x: f32, tiled_y: f32) -> Vec2 {
        // Integer halves, like `tile_at` and `world_bounds`, so odd-sized maps stay on the grid.
        let half_w = (self.width / 2) as f32 * TILE_SIZE;
        let half_h = (self.height / 2) as f32 * TILE_SIZE;
        Vec2::new(
            tiled_x - half_w - TILE_SIZE / 2.0,
            half_h - tiled_y - TILE_SIZE / 2.0,
        )
    }
}

/// Loads `.tmj` maps and the external or embedded tilesets they reference.
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

        let tileset_refs = json["tilesets"]
            .as_array()
            .filter(|t| !t.is_empty())
            .ok_or("Map references no tileset")?;
        let mut tilesets = Vec::new();
        for tileset_ref in tileset_refs {
            let first_gid = tileset_ref["firstgid"].as_u64().unwrap_or(1) as u32;
            // `image` is relative to the file that defines the tileset.
            let (tileset, base) = match tileset_ref["source"].as_str() {
                Some(source) => {
                    let tileset_path = load_context
                        .path()
                        .resolve_embed_str(source)
                        .map_err(|e| format!("Invalid tileset path {source}: {e}"))?;
                    let tileset_bytes = load_context
                        .read_asset_bytes(tileset_path.clone())
                        .await
                        .map_err(|e| format!("Failed to read tileset {source}: {e}"))?;
                    let tileset: Value = serde_json::from_slice(&tileset_bytes)
                        .map_err(|e| format!("Failed to parse TSJ {source}: {e}"))?;
                    (tileset, tileset_path)
                }
                // Embedded tileset
                None => (tileset_ref.clone(), load_context.path().clone()),
            };
            let image_src = tileset["image"]
                .as_str()
                .ok_or_else(|| format!("Tileset at firstgid {first_gid} has no image"))?;
            let image_path = base
                .resolve_embed_str(image_src)
                .map_err(|e| format!("Invalid tileset image path {image_src}: {e}"))?;
            let tile_count = match tileset["tilecount"].as_u64() {
                Some(count) => count as u32,
                None => {
                    let columns = tileset["columns"].as_u64().unwrap_or(0);
                    let tile_h = tileset["tileheight"].as_u64().unwrap_or(0).max(1);
                    let rows = tileset["imageheight"].as_u64().unwrap_or(0) / tile_h;
                    (columns * rows) as u32
                }
            };
            tilesets.push(Tileset {
                first_gid,
                tile_count,
                image: load_context.load(image_path),
                colliders: parse_tile_colliders(&tileset),
            });
        }
        tilesets.sort_by_key(|t| t.first_gid);

        let layers_json = json["layers"].as_array().ok_or("Missing layers array")?;

        let mut layers = Vec::new();
        let mut object_layers = Vec::new();

        for layer in layers_json {
            match layer["type"].as_str().unwrap_or("") {
                "tilelayer" => {
                    let data = layer["data"]
                        .as_array()
                        .ok_or("Missing data in tile layer")?;
                    let above = layer_bool_property(layer, "above").unwrap_or(false);
                    layers.push(TileLayer {
                        name: layer["name"].as_str().unwrap_or("").to_string(),
                        data: data
                            .iter()
                            .map(|v| v.as_u64().unwrap_or(0) as u32)
                            .collect(),
                        above,
                        collides: layer_bool_property(layer, "collides").unwrap_or(!above),
                        visible: layer["visible"].as_bool().unwrap_or(true),
                    });
                }
                "objectgroup" => object_layers.push(parse_object_layer(layer)),
                "group" => warn!(
                    "Layer group {:?} is not supported, its layers are ignored",
                    layer["name"].as_str().unwrap_or("")
                ),
                _ => {}
            }
        }

        let map = TiledMap {
            width,
            height,
            layers,
            tilesets,
            object_layers,
        };
        map.warn_flipped_colliders();
        Ok(map)
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
    render_device: Option<Res<RenderDevice>>,
) {
    let Some(map) = maps.get(&assets.world_map) else {
        error!("Tiled map asset missing after loading");
        return;
    };
    // Each tileset becomes a 2D texture array with one layer per tile.
    if let Some(device) = render_device {
        let max_layers = device.limits().max_texture_array_layers;
        for (i, tileset) in map.tilesets.iter().enumerate() {
            if tileset.tile_count > max_layers {
                warn!(
                    "Tileset #{i} has {} tiles, more than the device's max_texture_array_layers ({max_layers})",
                    tileset.tile_count
                );
            }
        }
    }
    commands.insert_resource(map.clone());
}

pub struct TiledMapPlugin;

impl Plugin for TiledMapPlugin {
    fn build(&self, app: &mut App) {
        app.init_asset::<TiledMap>()
            .init_asset_loader::<TiledMapLoader>()
            .add_systems(OnExit(GameState::AssetLoading), insert_tiled_map_resource);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn map_with_objects(layer_json: &str) -> TiledMap {
        let layer: Value = serde_json::from_str(layer_json).unwrap();
        TiledMap {
            width: 30,
            height: 20,
            layers: Vec::new(),
            tilesets: Vec::new(),
            object_layers: vec![parse_object_layer(&layer)],
        }
    }

    #[test]
    fn polyline_path_in_game_space_at_feet() {
        let map = map_with_objects(
            r#"{"name":"Paths","type":"objectgroup","objects":[
                {"name":"Walk","x":100,"y":50,"polyline":[
                    {"x":0,"y":0},{"x":32,"y":0},{"x":32,"y":-16}]}]}"#,
        );
        let path = map.path("Walk").unwrap();
        let expected = |x: f32, y: f32| map.tiled_to_game(x, y) + Vec2::new(0.0, 16.0);
        assert_eq!(
            path,
            vec![expected(100.0, 50.0), expected(132.0, 50.0), expected(132.0, 34.0)]
        );
        assert!(map.path("Missing").is_none());
    }

    #[test]
    fn point_and_rectangle_paths_use_their_centre() {
        let map = map_with_objects(
            r#"{"name":"Paths","type":"objectgroup","objects":[
                {"name":"P","x":10,"y":20,"point":true},
                {"name":"R","x":0,"y":0,"width":32,"height":16}]}"#,
        );
        let at = |x: f32, y: f32| vec![map.tiled_to_game(x, y) + Vec2::new(0.0, 16.0)];
        assert_eq!(map.path("P").unwrap(), at(10.0, 20.0));
        assert_eq!(map.path("R").unwrap(), at(16.0, 8.0));
    }

    #[test]
    fn object_properties_are_read() {
        let map = map_with_objects(
            r#"{"name":"Interact","type":"objectgroup","objects":[
                {"name":"Door3B","x":0,"y":0,"width":16,"height":16,"properties":[
                    {"name":"node","type":"string","value":"Route1Viewing"},
                    {"name":"hidden","type":"bool","value":true},
                    {"name":"count","type":"int","value":3},
                    {"name":"speed","type":"float","value":1.5}]}]}"#,
        );
        let obj = &map.object_layer("Interact")[0];
        assert_eq!(obj.prop_str("node"), Some("Route1Viewing"));
        assert_eq!(obj.prop_bool("hidden"), Some(true));
        assert_eq!(obj.properties["count"], PropValue::Int(3));
        assert_eq!(obj.properties["speed"], PropValue::Float(1.5));
        // Wrong type or missing
        assert_eq!(obj.prop_bool("node"), None);
        assert_eq!(obj.prop_str("missing"), None);
    }
}
