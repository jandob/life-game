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
    #[asset(path = "library/characters/wanderer/wanderer.png")]
    pub wanderer_texture: Handle<Image>,
    // Sheet format: character::LEGACY (64x128 cells).
    #[asset(texture_atlas(tile_size_x = 64, tile_size_y = 128, columns = 10, rows = 12))]
    pub wanderer_layout: Handle<TextureAtlasLayout>,

    #[asset(path = "library/characters/samantha/samantha.png")]
    pub samantha_texture: Handle<Image>,
    // Sheet format: character::REALISTIC (96x192 cells).
    #[asset(texture_atlas(tile_size_x = 96, tile_size_y = 192, columns = 10, rows = 12))]
    pub samantha_layout: Handle<TextureAtlasLayout>,

    // --- MAP ---
    // Start map: `world_map` in assets/start.assets.ron
    #[asset(key = "world_map")]
    pub world_map: Handle<crate::world::map::tiled_map::TiledMap>,

    // --- FLORA ---
    #[asset(path = "library/props/forest/tree.png")]
    pub tree: Handle<Image>,
    #[asset(path = "library/props/forest/tree_trunk.png")]
    pub tree_trunk: Handle<Image>,
    #[asset(path = "library/props/forest/tree_shadow.png")]
    pub tree_shadow: Handle<Image>,
    #[asset(path = "library/props/forest/tree_pedal.png")]
    pub tree_petal: Handle<Image>,

    #[asset(path = "library/props/forest/bush1.png")]
    pub bush1: Handle<Image>,
    #[asset(path = "library/props/forest/bush2.png")]
    pub bush2: Handle<Image>,

    #[asset(path = "library/props/forest/rocks.png")]
    pub rocks_texture: Handle<Image>,
    #[asset(texture_atlas(tile_size_x = 16, tile_size_y = 16, columns = 3, rows = 1))]
    pub rocks_layout: Handle<TextureAtlasLayout>,

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
    #[asset(path = "library/ui/dialogue_start_hint.png")]
    pub dialogue_start_hint_texture: Handle<Image>,
    #[asset(texture_atlas(tile_size_x = 32, tile_size_y = 32, columns = 2, rows = 1))]
    pub dialogue_start_hint_layout: Handle<TextureAtlasLayout>,

    #[asset(path = "library/portraits/samantha.png")]
    pub samantha_icon: Handle<Image>,
    #[asset(path = "library/portraits/player.png")]
    pub player_icon: Handle<Image>,

    #[asset(path = "library/ui/keys/arrows.png")]
    pub ui_arrows_key: Handle<Image>,
    #[asset(path = "library/ui/keys/down_key.png")]
    pub ui_down_key_texture: Handle<Image>,
    #[asset(texture_atlas(tile_size_x = 34, tile_size_y = 34, columns = 3, rows = 1))]
    pub ui_down_key_layout: Handle<TextureAtlasLayout>,
    #[asset(path = "library/ui/keys/up_key.png")]
    pub ui_up_key_texture: Handle<Image>,
    #[asset(texture_atlas(tile_size_x = 34, tile_size_y = 34, columns = 3, rows = 1))]
    pub ui_up_key_layout: Handle<TextureAtlasLayout>,
    #[asset(path = "library/ui/keys/left_key.png")]
    pub ui_left_key_texture: Handle<Image>,
    #[asset(texture_atlas(tile_size_x = 34, tile_size_y = 34, columns = 3, rows = 1))]
    pub ui_left_key_layout: Handle<TextureAtlasLayout>,
    #[asset(path = "library/ui/keys/right_key.png")]
    pub ui_right_key_texture: Handle<Image>,
    #[asset(texture_atlas(tile_size_x = 34, tile_size_y = 34, columns = 3, rows = 1))]
    pub ui_right_key_layout: Handle<TextureAtlasLayout>,
    #[asset(path = "library/ui/keys/shift_key.png")]
    pub ui_shift_key_texture: Handle<Image>,
    #[asset(texture_atlas(tile_size_x = 34, tile_size_y = 34, columns = 2, rows = 1))]
    pub ui_shift_key_layout: Handle<TextureAtlasLayout>,

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
