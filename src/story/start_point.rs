//! Start points: launch the game at a point in the story, with the story state as if
//! the earlier scenes had been played, so a scene can be tested without a playthrough.
//!
//! - Native: `cargo run -- --start movein`, `cargo run -- --start list`
//! - Web: `index.html?start=movein`
//!
//! `--set NAME=VALUE` (web: `&set=NAME=VALUE`) overrides a Yarn variable afterwards,
//! e.g. to try another branch. See `docs/start-points.md`.
//!
//! The earlier scenes are fast-forwarded without being shown: the first available
//! option at every choice, lines skipped. That sets every variable and visit count as
//! real play would. Of their commands only the end state of the world is replayed:
//! actors placed where their walks end, faced, shown or hidden, doors opened or closed,
//! the screen left black or clear.

use bevy::prelude::*;
use bevy_yarnspinner::default_impl::{MemoryVariableStorage, StringTableTextProvider};
use bevy_yarnspinner::prelude::*;
use yarnspinner::runtime::{Dialogue, DialogueEvent};

use super::inventory::ItemsSeen;
use super::phone::Phone;
use super::scripted::{face_command, hide_command, show_command, Actor, ScriptedWalk};
use super::transition::{place_command, QueuedScene, ScreenFade};
use super::StoryVars;
use crate::player::Player;
use crate::world::map::doors::{close_door_command, open_door_command};
use crate::world::map::tiled_map::TiledMap;
use crate::GameState;

/// A point in the story the game can start at.
pub struct StartPoint {
    pub name: &'static str,
    pub about: &'static str,
    /// The scenes played before this point, in story order. Only nodes the game starts
    /// itself (`<<next_scene>>` targets): a node reached by `<<jump>>` is played with
    /// the node that jumps to it.
    pub played: &'static [&'static str],
    pub begin: Begin,
}

pub enum Begin {
    /// Starts this scene at once.
    Scene(&'static str),
    /// Hands control to the player.
    Roam,
}

const VIEWING: &[&str] = &["Route1Viewing"];
const MOVE_IN: &[&str] = &["Route1Viewing", "Route1MoveIn"];

/// Every start point, in story order. Add one for each new scene.
pub const START_POINTS: &[StartPoint] = &[
    StartPoint {
        name: "viewing",
        about: "Saturday: the viewing of 3B, Samantha opens the door across the hall",
        played: &[],
        begin: Begin::Scene("Route1Viewing"),
    },
    StartPoint {
        name: "movein",
        about: "Moving day: keys, the sock check and her house rules",
        played: VIEWING,
        begin: Begin::Scene("Route1MoveIn"),
    },
    StartPoint {
        name: "sunday",
        about: "Sunday morning on the landing, free to walk (knock on 3A)",
        played: MOVE_IN,
        begin: Begin::Roam,
    },
    StartPoint {
        name: "croissant",
        about: "Sunday morning: the croissant at her door",
        played: MOVE_IN,
        begin: Begin::Scene("Route1Croissant"),
    },
];

pub fn find(name: &str) -> Option<&'static StartPoint> {
    START_POINTS.iter().find(|p| p.name == name)
}

/// The start points as a table, one per line.
pub fn list() -> String {
    let width = START_POINTS.iter().map(|p| p.name.len()).max().unwrap_or(0);
    START_POINTS
        .iter()
        .map(|p| format!("{:width$}  {}\n", p.name, p.about))
        .collect()
}

/// What the game was launched with: `--start NAME` and `--set NAME=VALUE`, or the same
/// as URL query parameters on the web.
#[derive(Resource, Default, Debug, PartialEq)]
pub struct LaunchOptions {
    pub start: Option<String>,
    pub sets: Vec<(String, String)>,
}

impl LaunchOptions {
    pub fn from_environment() -> Self {
        #[cfg(not(target_arch = "wasm32"))]
        {
            Self::from_args(std::env::args().skip(1))
        }
        #[cfg(target_arch = "wasm32")]
        {
            let search = web_sys::window()
                .and_then(|w| w.location().search().ok())
                .unwrap_or_default();
            Self::from_query(&search)
        }
    }

    pub fn wants_list(&self) -> bool {
        self.start.as_deref() == Some("list")
    }

    #[cfg_attr(target_arch = "wasm32", allow(dead_code))]
    fn from_args(args: impl IntoIterator<Item = String>) -> Self {
        let mut options = Self::default();
        let mut args = args.into_iter();
        while let Some(arg) = args.next() {
            let (key, inline) = match arg.split_once('=') {
                Some((key, value)) if key.starts_with("--") => (key.to_string(), Some(value)),
                _ => (arg.clone(), None),
            };
            if key != "--start" && key != "--set" {
                continue;
            }
            let Some(value) = inline.map(str::to_string).or_else(|| args.next()) else {
                eprintln!("{key} needs a value");
                continue;
            };
            options.add(&key[2..], value);
        }
        options
    }

    #[cfg_attr(not(target_arch = "wasm32"), allow(dead_code))]
    fn from_query(search: &str) -> Self {
        let mut options = Self::default();
        for pair in search.trim_start_matches('?').split('&') {
            if let Some((key, value)) = pair.split_once('=') {
                options.add(&percent_decode(key), percent_decode(value));
            }
        }
        options
    }

    fn add(&mut self, key: &str, value: String) {
        match key {
            "start" => self.start = Some(value),
            "set" => match value.split_once('=') {
                Some((name, value)) => self.sets.push((name.to_string(), value.to_string())),
                None => eprintln!("set: expected NAME=VALUE, got '{value}'"),
            },
            _ => {}
        }
    }
}

/// Decodes `%XX` escapes and `+` in a URL query component.
fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'+' => out.push(b' '),
            b'%' => match s
                .get(i + 1..i + 3)
                .and_then(|h| u8::from_str_radix(h, 16).ok())
            {
                Some(byte) => {
                    out.push(byte);
                    i += 2;
                }
                None => out.push(b'%'),
            },
            byte => out.push(byte),
        }
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// A start point waiting to be applied once the game world is up.
#[derive(Resource)]
struct StartRequest {
    point: &'static StartPoint,
    sets: Vec<(String, String)>,
}

/// A command of a fast-forwarded scene that changes the world, as (name, parameters).
type WorldCommand = (String, Vec<String>);

/// Commands whose end state is replayed after a fast-forward.
const REPLAYED: &[&str] = &[
    "walk",
    "place",
    "face",
    "show",
    "hide",
    "open_door",
    "close_door",
    "fade_out",
    "fade_in",
    "phone",
    "note",
    "note_done",
];

/// Plays `nodes` on `storage` without presenting anything: the first available option at
/// every choice, lines skipped. Returns the commands in `REPLAYED`, in order.
pub fn fast_forward(
    project: &YarnProject,
    storage: &MemoryVariableStorage,
    nodes: &[&str],
) -> Result<Vec<WorldCommand>, String> {
    let compilation = project.compilation();
    let program = compilation
        .program
        .clone()
        .ok_or("the Yarn project has no program")?;
    let mut text = StringTableTextProvider::new();
    text.extend_base_language(
        compilation
            .string_table
            .iter()
            .map(|(id, info)| (id.clone(), info.text.clone())),
    );
    let mut dialogue = Dialogue::new(Box::new(storage.clone()), Box::new(text));
    dialogue.add_program(program);

    // Yarn functions get a world; the standard ones (visited, dice, ...) don't use it.
    let mut world = World::new();
    let mut replayed = Vec::new();
    for &node in nodes {
        dialogue
            .set_node(node)
            .map_err(|err| format!("cannot start '{node}': {err}"))?;
        'node: for _ in 0..100_000 {
            let events = dialogue
                .continue_with_world(&mut world)
                .map_err(|err| format!("while playing '{node}': {err}"))?;
            for event in events {
                match event {
                    DialogueEvent::Options(options) => {
                        let option = options
                            .iter()
                            .find(|o| o.is_available)
                            .or(options.first())
                            .ok_or_else(|| format!("'{node}' offers no options"))?;
                        dialogue
                            .set_selected_option(option.id)
                            .map_err(|err| format!("while playing '{node}': {err}"))?;
                    }
                    DialogueEvent::Command(command)
                        if REPLAYED.contains(&command.name.as_str()) =>
                    {
                        let params = command.parameters.iter().map(|p| p.to_string()).collect();
                        replayed.push((command.name, params));
                    }
                    DialogueEvent::DialogueComplete => break 'node,
                    _ => {}
                }
            }
        }
    }
    Ok(replayed)
}

/// Sets `$NAME` (the `$` is optional) to `value`, typed like the variable's current or
/// declared value.
pub fn set_variable(
    project: &YarnProject,
    storage: &mut MemoryVariableStorage,
    name: &str,
    value: &str,
) -> Result<(), String> {
    let name = format!("${}", name.trim_start_matches('$'));
    let current = storage.get(&name).ok().or_else(|| {
        project
            .compilation()
            .program
            .as_ref()
            .and_then(|p| p.initial_values.get(&name))
            .map(|operand| YarnValue::from(operand.clone()))
    });
    let typed = match current {
        None => return Err(format!("unknown variable '{name}'")),
        Some(YarnValue::String(_)) => YarnValue::String(value.to_string()),
        Some(YarnValue::Number(_)) => YarnValue::Number(
            value
                .parse()
                .map_err(|_| format!("'{name}' is a number, got '{value}'"))?,
        ),
        Some(YarnValue::Boolean(_)) => YarnValue::Boolean(
            value
                .parse()
                .map_err(|_| format!("'{name}' is true or false, got '{value}'"))?,
        ),
    };
    storage
        .set(name.clone(), typed)
        .map_err(|err| format!("cannot set '{name}': {err}"))
}

/// Restores the end state of the replayed commands.
/// Texts (`<<phone>>`) are pending unless their node is in `played`.
fn replay(world: &mut World, commands: Vec<WorldCommand>, played: &[&str]) {
    for (name, params) in commands {
        let arg = |i: usize| params.get(i).cloned().unwrap_or_default();
        let result = match name.as_str() {
            "walk" => {
                put_at_end_of_path(world, &arg(0), &arg(1));
                Ok(())
            }
            "place" => world
                .run_system_cached_with(place_command, (arg(0), arg(1)))
                .map_err(|e| e.to_string()),
            "face" => world
                .run_system_cached_with(face_command, (arg(0), arg(1)))
                .map_err(|e| e.to_string()),
            "show" => world
                .run_system_cached_with(show_command, arg(0))
                .map_err(|e| e.to_string()),
            "hide" => world
                .run_system_cached_with(hide_command, arg(0))
                .map_err(|e| e.to_string()),
            "open_door" => world
                .run_system_cached_with(open_door_command, arg(0))
                .map_err(|e| e.to_string()),
            "close_door" => world
                .run_system_cached_with(close_door_command, arg(0))
                .map_err(|e| e.to_string()),
            "fade_out" => {
                world.resource_mut::<ScreenFade>().black();
                Ok(())
            }
            "fade_in" => {
                world.resource_mut::<ScreenFade>().clear();
                Ok(())
            }
            "phone" => {
                // Yarn only counts visits of nodes some `visited()` asks about, so a
                // text counts as read when the start point lists it as played.
                if !played.contains(&arg(0).as_str()) {
                    world.resource_mut::<Phone>().deliver(arg(0));
                }
                Ok(())
            }
            "note" => {
                world.resource_mut::<Phone>().note(arg(0), arg(1));
                Ok(())
            }
            "note_done" => {
                world.resource_mut::<Phone>().note_done(&arg(0));
                Ok(())
            }
            _ => Ok(()),
        };
        if let Err(err) = result {
            error!("Start point: replaying <<{name}>> failed: {err}");
        }
        world.flush();
    }
}

/// Where a `<<walk ACTOR PATH>>` ends: the last point of the path.
fn put_at_end_of_path(world: &mut World, actor: &str, path: &str) {
    let Some(point) = world
        .resource::<TiledMap>()
        .path(path)
        .and_then(|p| p.last().copied())
    else {
        error!("Start point: unknown or empty path '{path}'");
        return;
    };
    let mut q_actors = world.query_filtered::<(&Actor, &mut Transform), Without<ScriptedWalk>>();
    match q_actors.iter_mut(world).find(|(a, _)| a.0 == actor) {
        Some((_, mut transform)) => {
            transform.translation.x = point.x;
            transform.translation.y = point.y;
        }
        None => error!("Start point: unknown actor '{actor}'"),
    }
}

/// Turns the launch options into a start request, or reports why not.
fn request_start_point(mut commands: Commands, options: Option<Res<LaunchOptions>>) {
    let Some(options) = options else {
        return;
    };
    let Some(name) = options.start.as_deref() else {
        return;
    };
    if options.wants_list() {
        info!("Start points:\n{}", list());
        return;
    }
    let Some(point) = find(name) else {
        error!("Unknown start point '{name}'. Start points:\n{}", list());
        return;
    };
    info!("Starting at '{}': {}", point.name, point.about);
    commands.insert_resource(StartRequest {
        point,
        sets: options.sets.clone(),
    });
}

fn skip_main_menu(mut next_state: ResMut<NextState<GameState>>) {
    next_state.set(GameState::Gaming);
}

fn world_is_ready(q_player: Query<(), With<Player>>) -> bool {
    !q_player.is_empty()
}

/// Fast-forwards to the requested start point once the world is spawned. Runs once:
/// returning to the menu later plays normally.
fn apply_start_point(world: &mut World) {
    let Some(request) = world.remove_resource::<StartRequest>() else {
        return;
    };
    let mut storage = world.resource::<StoryVars>().0.clone();
    let project = world.resource::<YarnProject>();
    let commands = match fast_forward(project, &storage, request.point.played) {
        Ok(commands) => commands,
        Err(err) => {
            error!("Start point '{}': {err}", request.point.name);
            return;
        }
    };
    for (name, value) in &request.sets {
        if let Err(err) = set_variable(project, &mut storage, name, value) {
            error!("--set {name}={value}: {err}");
        }
    }
    replay(world, commands, request.point.played);
    let storage = world.resource::<StoryVars>().0.clone();
    world.resource_mut::<ItemsSeen>().rebaseline(&storage);
    if let Begin::Scene(node) = request.point.begin {
        world.resource_mut::<QueuedScene>().0 = Some(node.to_string());
    }
}

pub struct StartPointPlugin;

impl Plugin for StartPointPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, request_start_point)
            .add_systems(
                OnEnter(GameState::MainMenu),
                skip_main_menu.run_if(resource_exists::<StartRequest>),
            )
            .add_systems(
                Update,
                apply_start_point.run_if(
                    in_state(GameState::Gaming)
                        .and_then(resource_exists::<StartRequest>)
                        .and_then(resource_exists::<YarnProject>)
                        .and_then(world_is_ready),
                ),
            );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn real_project() -> App {
        let files: Vec<YarnFileSource> = std::fs::read_dir("assets/dialogue")
            .unwrap()
            .map(|e| e.unwrap().path())
            .filter(|p| p.extension().is_some_and(|ext| ext == "yarn"))
            .map(|p| {
                let name = p.file_name().unwrap().to_string_lossy();
                YarnFileSource::file(format!("dialogue/{name}"))
            })
            .collect();
        let mut app = App::new();
        app.add_plugins((
            MinimalPlugins,
            AssetPlugin {
                file_path: "assets".to_string(),
                ..default()
            },
            YarnSpinnerPlugin::with_yarn_sources(files)
                .with_development_file_generation(DevelopmentFileGeneration::None),
        ));
        for _ in 0..5000 {
            if app.world().contains_resource::<YarnProject>() {
                return app;
            }
            app.update();
            std::thread::sleep(std::time::Duration::from_millis(2));
        }
        panic!("The yarn project did not load");
    }

    fn get(storage: &MemoryVariableStorage, name: &str) -> String {
        storage.get(name).map(|v| v.to_string()).unwrap_or_default()
    }

    #[test]
    fn every_start_point_fast_forwards_and_its_scene_exists() {
        let app = real_project();
        let project = app.world().resource::<YarnProject>();
        let program = project.compilation().program.as_ref().unwrap();
        let mut names = std::collections::HashSet::new();
        for point in START_POINTS {
            assert!(names.insert(point.name), "'{}' twice", point.name);
            assert_ne!(point.name, "list", "'list' lists the start points");
            if let Begin::Scene(node) = point.begin {
                assert!(
                    program.nodes.contains_key(node),
                    "{}: no node '{node}'",
                    point.name
                );
            }
            fast_forward(project, &MemoryVariableStorage::new(), point.played)
                .unwrap_or_else(|err| panic!("{}: {err}", point.name));
        }
    }

    #[test]
    fn sunday_is_after_moving_day_with_the_first_options() {
        let app = real_project();
        let project = app.world().resource::<YarnProject>();
        let storage = MemoryVariableStorage::new();
        let commands = fast_forward(project, &storage, find("sunday").unwrap().played).unwrap();

        assert_eq!(get(&storage, "$Yarn.Internal.Visiting.Route1Viewing"), "1");
        // Yarn only counts visits of nodes that some `visited()` asks about.
        assert_eq!(get(&storage, "$samantha_name"), "Samantha");
        assert_eq!(get(&storage, "$r1_viewing_opening"), "keen");
        assert_eq!(get(&storage, "$r1_movein_keys"), "hand");

        // Moving day ends on the landing, the screen clear again.
        let place = commands.iter().rposition(|(n, _)| n == "place").unwrap();
        assert_eq!(commands[place].1, ["Player", "PlayerArrive"]);
        let last_fade = commands.iter().rev().find(|(n, _)| n.starts_with("fade_"));
        assert_eq!(last_fade.unwrap().0, "fade_in");
        // The viewing alone ends in black, before moving day fades in.
        let commands = fast_forward(project, &MemoryVariableStorage::new(), VIEWING).unwrap();
        let last_fade = commands.iter().rev().find(|(n, _)| n.starts_with("fade_"));
        assert_eq!(last_fade.unwrap().0, "fade_out");
    }

    #[test]
    fn set_variable_keeps_the_declared_type() {
        let app = real_project();
        let project = app.world().resource::<YarnProject>();
        let mut storage = MemoryVariableStorage::new();
        set_variable(project, &mut storage, "r1_movein_rules", "fair").unwrap();
        assert_eq!(get(&storage, "$r1_movein_rules"), "fair");
        set_variable(project, &mut storage, "$r1_movein_rules", "deal").unwrap();
        assert_eq!(get(&storage, "$r1_movein_rules"), "deal");
        assert!(set_variable(project, &mut storage, "no_such_variable", "x").is_err());
    }

    #[test]
    fn launch_options_from_args_and_query() {
        let args = |a: &[&str]| LaunchOptions::from_args(a.iter().map(|s| s.to_string()));
        let expected = LaunchOptions {
            start: Some("movein".to_string()),
            sets: vec![("r1_viewing_why".to_string(), "money".to_string())],
        };
        assert_eq!(
            args(&["--start", "movein", "--set", "r1_viewing_why=money"]),
            expected
        );
        assert_eq!(
            args(&["--start=movein", "--other", "--set=r1_viewing_why=money"]),
            expected
        );
        assert_eq!(
            LaunchOptions::from_query("?start=movein&set=r1_viewing_why%3Dmoney&x=1"),
            expected
        );
        assert_eq!(
            LaunchOptions::from_query("?start=movein&set=r1_viewing_why=money"),
            expected
        );
        assert_eq!(LaunchOptions::from_query(""), LaunchOptions::default());
        assert!(args(&["--start", "list"]).wants_list());
        assert_eq!(percent_decode("a+b%20c%zz"), "a b c%zz");
    }
}
