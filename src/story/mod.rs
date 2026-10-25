//! Story state and scripted scenes.

pub mod inventory;
pub mod phone;
pub mod scripted;
pub mod start_point;
pub mod transition;

use bevy::prelude::*;
use bevy_yarnspinner::default_impl::MemoryVariableStorage;
use bevy_yarnspinner::prelude::*;

use crate::GameState;

/// Game-wide Yarn variables, shared by every dialogue runner. Values (including
/// node visit counts) survive the runner that set them.
#[derive(Resource, Clone, Default)]
pub struct StoryVars(pub MemoryVariableStorage);

/// Builds a runner on the shared story variables.
///
/// Building a runner resets every variable it knows to its declared default, so the
/// values the story has already set are restored right after.
pub fn build_story_runner(
    project: &YarnProject,
    commands: &mut Commands,
    story_vars: &StoryVars,
) -> DialogueRunner {
    let saved = story_vars.0.variables();
    let mut runner = project
        .build_dialogue_runner(commands)
        .with_variable_storage(story_vars.0.clone_shallow())
        .build();
    if let Err(err) = runner.variable_storage_mut().extend(saved) {
        error!("Could not restore the story variables: {err}");
    }
    runner
}

fn reset_story_vars(mut commands: Commands) {
    commands.insert_resource(StoryVars::default());
}

pub struct StoryPlugin;

impl Plugin for StoryPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<StoryVars>()
            .add_plugins((
                scripted::ScriptedPlugin,
                inventory::InventoryPlugin,
                phone::PhonePlugin,
                transition::TransitionPlugin,
                start_point::StartPointPlugin,
            ))
            .add_systems(OnExit(GameState::MainMenu), reset_story_vars);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use bevy::ecs::system::SystemState;

    fn app_with_project() -> App {
        let mut app = App::new();
        app.add_plugins((
            MinimalPlugins,
            AssetPlugin {
                file_path: "src/story/test_assets".to_string(),
                ..default()
            },
            YarnSpinnerPlugin::with_yarn_source(YarnFileSource::file("storyvars.yarn"))
                .with_development_file_generation(DevelopmentFileGeneration::None),
        ));
        for _ in 0..2000 {
            if app.world().contains_resource::<YarnProject>() {
                return app;
            }
            app.update();
            std::thread::sleep(std::time::Duration::from_millis(2));
        }
        panic!("The test yarn project did not load");
    }

    #[test]
    fn story_vars_survive_building_the_next_runner() {
        let mut app = app_with_project();
        let story_vars = StoryVars::default();
        let mut state: SystemState<(Commands, Res<YarnProject>)> =
            SystemState::new(app.world_mut());
        let (mut commands, project) = state.get_mut(app.world_mut()).unwrap();

        let mut first = build_story_runner(&project, &mut commands, &story_vars);
        assert_eq!(
            first.variable_storage().get("$flag").unwrap().to_string(),
            "unset"
        );
        first
            .variable_storage_mut()
            .set("$flag".to_string(), "set".into())
            .unwrap();
        drop(first);

        let second = build_story_runner(&project, &mut commands, &story_vars);
        assert_eq!(
            second.variable_storage().get("$flag").unwrap().to_string(),
            "set"
        );
        assert_eq!(story_vars.0.get("$flag").unwrap().to_string(), "set");

        // Without the restore, building resets the variable to its declared default.
        let plain = project
            .build_dialogue_runner(&mut commands)
            .with_variable_storage(story_vars.0.clone_shallow())
            .build();
        assert_eq!(
            plain.variable_storage().get("$flag").unwrap().to_string(),
            "unset"
        );
    }

    #[derive(Resource, Default)]
    struct Presented(Vec<String>);

    /// A blocking `walk` holds the dialogue until the actor arrived; `no_wait` does not.
    #[test]
    fn walk_command_blocks_the_dialogue() {
        use crate::world::map::tiled_map::{ObjectLayerData, TiledMap, TiledObject};
        use bevy::time::TimeUpdateStrategy;
        use bevy_yarnspinner::events::PresentLine;
        use scripted::{walk_command, Actor};

        let mut app = app_with_project();
        let points = vec![Vec2::new(100.0, 100.0), Vec2::new(160.0, 100.0)];
        app.insert_resource(TimeUpdateStrategy::ManualDuration(
            std::time::Duration::from_millis(50),
        ))
        .insert_resource(TiledMap {
            tile_size: 48.0,
            width: 40,
            height: 40,
            image_layers: Vec::new(),
            background: None,
            object_layers: vec![ObjectLayerData {
                name: "Paths".to_string(),
                objects: vec![TiledObject {
                    name: "There".to_string(),
                    obj_type: String::new(),
                    x: points[0].x,
                    y: points[0].y,
                    width: 0.0,
                    height: 0.0,
                    properties: Default::default(),
                    points,
                }],
            }],
        })
        .init_resource::<Presented>()
        .add_observer(
            |trigger: On<PresentLine>, mut presented: ResMut<Presented>| {
                presented
                    .0
                    .push(trigger.event().line.text_without_character_name());
            },
        )
        .add_systems(Update, scripted::scripted_walk);
        app.world_mut()
            .spawn((Actor("Walker".to_string()), Transform::default()));

        let mut state: SystemState<(Commands, Res<YarnProject>)> =
            SystemState::new(app.world_mut());
        let (mut commands, project) = state.get_mut(app.world_mut()).unwrap();
        let mut runner = build_story_runner(&project, &mut commands, &StoryVars::default());
        let walk = commands.register_system(walk_command);
        runner.commands_mut().add_command("walk", walk);
        assert_eq!(
            runner.get_tags_for_node("Walk"),
            Some(vec!["cutscene".to_string()])
        );
        runner.start_node("Walk");
        state.apply(app.world_mut());
        let runner = app.world_mut().spawn(runner).id();

        let step = |app: &mut App, press: bool| {
            if press {
                app.world_mut()
                    .get_mut::<DialogueRunner>(runner)
                    .unwrap()
                    .continue_in_next_update();
            }
            app.update();
        };
        let presented = |app: &App| app.world().resource::<Presented>().0.clone();

        app.update();
        assert_eq!(presented(&app), ["Before"]);

        // The player continues; the walk starts and holds the dialogue.
        step(&mut app, true);
        for _ in 0..5 {
            step(&mut app, false);
        }
        assert_eq!(presented(&app), ["Before"], "walking, no new line yet");

        for _ in 0..400 {
            step(&mut app, false);
        }
        assert_eq!(presented(&app), ["Before", "Arrived"]);

        // `no_wait` returns finished at once.
        step(&mut app, true);
        for _ in 0..3 {
            step(&mut app, false);
        }
        assert_eq!(presented(&app), ["Before", "Arrived", "Without waiting"]);
    }
}
