use std::collections::HashMap;

use bevy::asset::{io::Reader, AssetLoader, LoadContext};
use bevy::prelude::*;
use serde_json::Value;

use crate::character::SPRITE_FEET_BELOW_CENTRE;
use crate::{GameAssets, GameState};

/// Parsed Tiled map data of a side-view map (see `world::side_view`), from a `.tmj` file.
/// Its art is image layers; tile layers are ignored.
///
/// Loaded through the asset server (so it works on wasm) as part of
/// `GameAssets`, then copied into a resource when asset loading finishes.
#[derive(Asset, Resource, TypePath, Clone)]
pub struct TiledMap {
    /// Tile width and height in px (`tilewidth`, equal to `tileheight`)
    pub tile_size: f32,
    /// Map width in tiles
    pub width: u32,
    /// Map height in tiles
    pub height: u32,
    /// Object layers
    pub object_layers: Vec<ObjectLayerData>,
    /// Image layers in file order (bottom to top)
    pub image_layers: Vec<ImageLayer>,
    /// What shows outside the rooms (`backgroundcolor`, `#rrggbb` or `#aarrggbb`)
    pub background: Option<Color>,
}

/// An image layer of the map: one picture placed at its offset.
#[derive(Clone)]
pub struct ImageLayer {
    pub name: String,
    pub image: Handle<Image>,
    /// Top-left corner in Tiled px
    pub offset: Vec2,
    /// Draws over the characters (`above = true`), e.g. a foreground
    pub above: bool,
}

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

    pub fn prop_f32(&self, name: &str) -> Option<f32> {
        match self.properties.get(name)? {
            PropValue::Float(f) => Some(*f as f32),
            PropValue::Int(i) => Some(*i as f32),
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
    /// The rectangle covered by the map's tiles, in game world coordinates.
    pub fn world_bounds(&self) -> Rect {
        // Tile x spans -width/2 ..= width - width/2 - 1 and tiles are centered
        // on their grid position, so the outer edges sit half a tile further out.
        let min = Vec2::new(
            -((self.width / 2) as f32) * self.tile_size - self.tile_size / 2.0,
            -((self.height - self.height / 2) as f32) * self.tile_size - self.tile_size / 2.0,
        );
        let size = Vec2::new(self.width as f32, self.height as f32) * self.tile_size;
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
    /// Path points sit on the floor line, where the sprite's feet stand, so every point is
    /// raised by `feet_offset`.
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
                .map(|p| self.tiled_to_game(p.x, p.y) + Vec2::new(0.0, self.feet_offset()))
                .collect(),
        )
    }

    /// How far a character's transform sits above the point its feet stand on.
    pub fn feet_offset(&self) -> f32 {
        SPRITE_FEET_BELOW_CENTRE
    }

    /// Convert a Tiled pixel position (top-left origin, y-down) to
    /// game world position (centered origin, y-up).
    ///
    /// Game tiles are centered on their grid position, so tile (0, 0) spans
    /// half a tile either side of the origin in game space; the half-tile shift keeps objects aligned with
    /// the ground as drawn in Tiled.
    pub fn tiled_to_game(&self, tiled_x: f32, tiled_y: f32) -> Vec2 {
        // Integer halves, like `world_bounds`, so odd-sized maps stay on the grid.
        let half_w = (self.width / 2) as f32 * self.tile_size;
        let half_h = (self.height / 2) as f32 * self.tile_size;
        Vec2::new(
            tiled_x - half_w - self.tile_size / 2.0,
            half_h - tiled_y - self.tile_size / 2.0,
        )
    }
}

/// Loads `.tmj` maps.
#[derive(Default, TypePath)]
pub struct TiledMapLoader;

/// A Tiled colour, `#rrggbb` or `#aarrggbb`.
fn parse_colour(hex: &str) -> Option<Color> {
    let hex = hex.strip_prefix('#')?;
    let byte = |i: usize| u8::from_str_radix(hex.get(i..i + 2)?, 16).ok();
    match hex.len() {
        6 => Some(Color::srgb_u8(byte(0)?, byte(2)?, byte(4)?)),
        8 => Some(Color::srgba_u8(byte(2)?, byte(4)?, byte(6)?, byte(0)?)),
        _ => None,
    }
}

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

        let tile_size = json["tilewidth"].as_u64().ok_or("Missing tilewidth")?;
        if json["tileheight"].as_u64() != Some(tile_size) || tile_size == 0 {
            return Err("Map tiles must be square (tilewidth equal to tileheight)".into());
        }
        let tile_size = tile_size as f32;

        let layers_json = json["layers"].as_array().ok_or("Missing layers array")?;

        let mut object_layers = Vec::new();
        let mut image_layers = Vec::new();

        for layer in layers_json {
            match layer["type"].as_str().unwrap_or("") {
                "tilelayer" => warn!(
                    "Tile layer {:?} is ignored: side-view maps draw image layers",
                    layer["name"].as_str().unwrap_or("")
                ),
                "objectgroup" => object_layers.push(parse_object_layer(layer)),
                "imagelayer" => {
                    let image_src = layer["image"].as_str().unwrap_or("");
                    if image_src.is_empty() {
                        continue;
                    }
                    let image_path = load_context
                        .path()
                        .resolve_embed_str(image_src)
                        .map_err(|e| format!("Invalid image layer path {image_src}: {e}"))?;
                    image_layers.push(ImageLayer {
                        name: layer["name"].as_str().unwrap_or("").to_string(),
                        image: load_context.load(image_path),
                        offset: Vec2::new(
                            layer["offsetx"].as_f64().unwrap_or(0.0) as f32,
                            layer["offsety"].as_f64().unwrap_or(0.0) as f32,
                        ),
                        above: layer_bool_property(layer, "above").unwrap_or(false),
                    });
                }
                "group" => warn!(
                    "Layer group {:?} is not supported, its layers are ignored",
                    layer["name"].as_str().unwrap_or("")
                ),
                _ => {}
            }
        }

        let background = json["backgroundcolor"].as_str().and_then(parse_colour);

        Ok(TiledMap {
            tile_size,
            width,
            height,
            object_layers,
            image_layers,
            background,
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
    let Some(map) = maps.get(&assets.world_map) else {
        error!("Tiled map asset missing after loading");
        return;
    };
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

    #[test]
    fn tiled_colours_parse_with_and_without_alpha() {
        assert_eq!(parse_colour("#3b3e4f"), Some(Color::srgb_u8(59, 62, 79)));
        assert_eq!(
            parse_colour("#803b3e4f"),
            Some(Color::srgba_u8(59, 62, 79, 128))
        );
        assert_eq!(parse_colour("3b3e4f"), None);
        assert_eq!(parse_colour("#3b3e"), None);
    }

    fn map_with_objects(layer_json: &str) -> TiledMap {
        let layer: Value = serde_json::from_str(layer_json).unwrap();
        TiledMap {
            tile_size: 48.0,
            width: 30,
            height: 20,
            image_layers: Vec::new(),
            background: None,
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
        let expected =
            |x: f32, y: f32| map.tiled_to_game(x, y) + Vec2::new(0.0, SPRITE_FEET_BELOW_CENTRE);
        assert_eq!(
            path,
            vec![
                expected(100.0, 50.0),
                expected(132.0, 50.0),
                expected(132.0, 34.0)
            ]
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
        let at = |x: f32, y: f32| {
            vec![map.tiled_to_game(x, y) + Vec2::new(0.0, SPRITE_FEET_BELOW_CENTRE)]
        };
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

    #[test]
    fn inline_48px_map_uses_its_tile_size() {
        let map = TiledMap {
            tile_size: 48.0,
            width: 10,
            height: 8,
            image_layers: Vec::new(),
            background: None,
            object_layers: Vec::new(),
        };
        // Tile (0, 0) of the game grid is centred on the origin, so Tiled's
        // (5 * 48 + 24, 3 * 48 + 24) is the centre of that tile.
        assert_eq!(
            map.tiled_to_game(5.0 * 48.0 + 24.0, 3.0 * 48.0 + 24.0),
            Vec2::ZERO
        );
        let bounds = map.world_bounds();
        assert_eq!(
            bounds.min,
            Vec2::new(-5.0 * 48.0 - 24.0, -4.0 * 48.0 - 24.0)
        );
        assert_eq!(bounds.size(), Vec2::new(480.0, 384.0));
    }
}
