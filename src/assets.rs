use bevy::audio::AudioSource;
use bevy::prelude::*;
use bevy_asset_loader::prelude::*;

use crate::look::Look;

#[derive(AssetCollection, Resource)]
pub struct GameAssets {
    // --- LOOKS (see look.rs) ---
    #[asset(path = "library/characters/looks/player_main/look.ron")]
    pub player_look: Handle<Look>,
    #[asset(path = "library/characters/looks/sam_casual/look.ron")]
    pub samantha_look: Handle<Look>,
    #[asset(path = "library/characters/looks/sam_ponytail/look.ron")]
    #[allow(dead_code)]
    pub samantha_ponytail_look: Handle<Look>,

    // --- MAP ---
    // Start map: `world_map` in assets/start.assets.ron
    #[asset(key = "world_map")]
    pub world_map: Handle<crate::world::map::tiled_map::TiledMap>,

    // --- UI ---
    #[asset(path = "library/ui/white_pixel.png")]
    pub white_pixel: Handle<Image>,

    #[asset(path = "library/ui/button.png")]
    pub button: Handle<Image>,
    #[asset(path = "library/ui/discord.png")]
    pub discord_button: Handle<Image>,

    #[asset(path = "library/ui/dialogue_edge.png")]
    pub dialogue_edge: Handle<Image>,
    #[asset(path = "library/ui/dialogue_continue.png")]
    pub dialogue_continue: Handle<Image>,

    #[asset(path = "library/portraits/samantha.png")]
    pub samantha_icon: Handle<Image>,
    #[asset(path = "library/portraits/player.png")]
    pub player_icon: Handle<Image>,

    // --- SCENE IMAGES (`<<frame>>`, see story/transition.rs) ---
    #[asset(path = "story/frames/route1_notebook/f1.png")]
    pub route1_notebook_f1: Handle<Image>,
    #[asset(path = "story/frames/route1_notebook/f2.png")]
    pub route1_notebook_f2: Handle<Image>,
    #[asset(path = "story/frames/route1_notebook/f3.png")]
    pub route1_notebook_f3: Handle<Image>,
    #[asset(path = "story/frames/route1_notebook/f4.png")]
    pub route1_notebook_f4: Handle<Image>,
    #[asset(path = "story/frames/route1_notebook/f5.png")]
    pub route1_notebook_f5: Handle<Image>,
    #[asset(path = "story/frames/route1_notebook/f6.png")]
    pub route1_notebook_f6: Handle<Image>,
    #[asset(path = "story/frames/route1_notebook/f7.png")]
    pub route1_notebook_f7: Handle<Image>,
    #[asset(path = "story/frames/route1_notebook/f8.png")]
    pub route1_notebook_f8: Handle<Image>,

    // --- AUDIO ---
    #[asset(path = "audio/player_footstep.ogg")]
    pub player_footstep: Handle<AudioSource>,

    #[asset(path = "audio/ui/button_hover.ogg")]
    pub ui_button_hover_sound: Handle<AudioSource>,
    #[asset(path = "audio/ui/button_press.ogg")]
    pub ui_button_press_sound: Handle<AudioSource>,

    // --- FONT ---
    #[asset(path = "fonts/PressStart2P.ttf")]
    pub pixel_font: Handle<Font>,
    #[asset(path = "fonts/Silver.ttf")]
    pub silver_font: Handle<Font>,
}

impl GameAssets {
    /// The scene image `NAME` of `<<frame "NAME">>`, i.e. the path under `story/frames/`
    /// without `.png`. Listed by hand: wasm can't list a folder to load it whole.
    pub fn frame(&self, name: &str) -> Option<&Handle<Image>> {
        Some(match name {
            "route1_notebook/f1" => &self.route1_notebook_f1,
            "route1_notebook/f2" => &self.route1_notebook_f2,
            "route1_notebook/f3" => &self.route1_notebook_f3,
            "route1_notebook/f4" => &self.route1_notebook_f4,
            "route1_notebook/f5" => &self.route1_notebook_f5,
            "route1_notebook/f6" => &self.route1_notebook_f6,
            "route1_notebook/f7" => &self.route1_notebook_f7,
            "route1_notebook/f8" => &self.route1_notebook_f8,
            _ => return None,
        })
    }
}
