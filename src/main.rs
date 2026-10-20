#![allow(clippy::too_many_arguments, clippy::type_complexity)]

mod animation;
mod assets;
mod audio;
mod character;
mod npc;
mod player;
mod story;
mod ui;
mod utils;
mod world;

pub use assets::GameAssets;
pub type GameRng = rand_xoshiro::Xoshiro256PlusPlus;

use bevy::asset::AssetMetaCheck;
use bevy::prelude::*;
use bevy::window::{PresentMode, Window, WindowMode, WindowResolution};

use bevy_asset_loader::prelude::*;
use bevy_hanabi::prelude::*;
use bevy_rapier2d::prelude::*;
use bevy_tweening::*;
use bevy_yarnspinner::prelude::*;

const BACKGROUND_COLOR: Color = Color::BLACK;
const DEFAULT_WINDOW_WIDTH: f32 = 1280.0;

#[derive(States, Clone, Eq, PartialEq, Debug, Hash, Default)]
pub enum GameState {
    #[default]
    AssetLoading,
    MainMenu,
    Gaming,
    Ending,
}

fn main() {
    const DEFAULT_WINDOW_WIDTH_PX: u32 = 1280;
    const DEFAULT_WINDOW_HEIGHT_PX: u32 = (DEFAULT_WINDOW_WIDTH * 9.0 / 16.0) as u32;

    // `--start NAME` starts at a point in the story, `--start list` lists them.
    let launch = story::start_point::LaunchOptions::from_environment();
    #[cfg(not(target_arch = "wasm32"))]
    if launch.wants_list() {
        print!("{}", story::start_point::list());
        return;
    }

    App::new()
        .add_plugins((
            DefaultPlugins
                .set(ImagePlugin::default_nearest())
                .set(AssetPlugin {
                    meta_check: AssetMetaCheck::Never,
                    ..default()
                })
                .set(WindowPlugin {
                    primary_window: Some(Window {
                        present_mode: PresentMode::Fifo,
                        mode: WindowMode::Windowed,
                        resizable: false,
                        fit_canvas_to_parent: false,
                        canvas: Some("#game-canvas".to_string()),
                        resolution: WindowResolution::new(
                            DEFAULT_WINDOW_WIDTH_PX,
                            DEFAULT_WINDOW_HEIGHT_PX,
                        ),
                        ..default()
                    }),
                    ..default()
                })
                .build(),
            RapierPhysicsPlugin::<NoUserData>::default(),
            RapierDebugRenderPlugin {
                enabled: false,
                ..default()
            },
            HanabiPlugin,
            animation::SpriteAnimationPlugin,
            {
                let plugin = YarnSpinnerPlugin::with_yarn_sources([
                    YarnFileSource::file("dialogue/route1_viewing.yarn"),
                    YarnFileSource::file("dialogue/route1_movein.yarn"),
                    YarnFileSource::file("dialogue/route1_croissant.yarn"),
                    YarnFileSource::file("dialogue/door_3a.yarn"),
                    YarnFileSource::file("dialogue/door_3b.yarn"),
                    YarnFileSource::file("dialogue/items.yarn"),
                    YarnFileSource::file("dialogue/phone_route1.yarn"),
                    YarnFileSource::file("dialogue/route1_dinner.yarn"),
                    YarnFileSource::file("dialogue/table_3a.yarn"),
                    YarnFileSource::file("dialogue/sink_3a.yarn"),
                    YarnFileSource::file("dialogue/shelf_3a.yarn"),
                    YarnFileSource::file("dialogue/samantha_3a.yarn"),
                    YarnFileSource::file("dialogue/door_3a_inside.yarn"),
                ]);
                #[cfg(not(target_arch = "wasm32"))]
                let plugin =
                    plugin.with_development_file_generation(DevelopmentFileGeneration::None);
                plugin
            },
            TweeningPlugin,
        ))
        .init_state::<GameState>()
        .add_loading_state(
            LoadingState::new(GameState::AssetLoading)
                .continue_to_state(GameState::MainMenu)
                .with_dynamic_assets_file::<StandardDynamicAssetCollection>("start.assets.ron")
                .load_collection::<GameAssets>(),
        )
        .insert_resource(ClearColor(BACKGROUND_COLOR))
        .insert_resource(launch)
        .add_plugins((
            world::WorldPlugin,
            ui::UiPlugin,
            audio::GameAudioPlugin,
            player::PlayerPlugin,
            npc::NpcPlugin,
            story::StoryPlugin,
            utils::UtilsPlugin,
        ))
        .run();
}
