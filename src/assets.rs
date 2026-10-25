use bevy::audio::AudioSource;
use bevy::prelude::*;
use bevy_asset_loader::prelude::*;

#[derive(AssetCollection, Resource)]
pub struct GameAssets {
    #[asset(path = "library/characters/player/player.png")]
    pub player_texture: Handle<Image>,
    // Sheet format: character::REALISTIC (96x192 cells).
    #[asset(texture_atlas(tile_size_x = 96, tile_size_y = 192, columns = 10, rows = 12))]
    pub player_layout: Handle<TextureAtlasLayout>,

    // --- NPC ---
    #[asset(path = "library/characters/samantha/samantha.png")]
    pub samantha_texture: Handle<Image>,
    // Sheet format: character::REALISTIC (96x192 cells).
    #[asset(texture_atlas(tile_size_x = 96, tile_size_y = 192, columns = 10, rows = 12))]
    pub samantha_layout: Handle<TextureAtlasLayout>,

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
