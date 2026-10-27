//! Start points: launch the game at a point in the story, with the story state as if
//! the earlier chapters had been played, so a scene can be tested without a playthrough.
//!
//! - Native: `cargo run -- --start r1thu2`, `cargo run -- --start list`
//! - Web: `index.html?start=r1thu2`
//!
//! `--set NAME=VALUE` (web: `&set=NAME=VALUE`) overrides a Yarn variable afterwards,
//! e.g. a gate inside a chapter. See `docs/start-points.md`.
//!
//! The story chart's walker (`chart.rs`) finds the shortest way to the point, chapter by
//! chapter, and plays it without showing it. That sets every variable, text and note as
//! real play would. Of its commands only the end state of the world is replayed: actors
//! placed where their walks end, faced, shown or hidden, doors opened or closed, the
//! screen left black or clear.

use bevy::prelude::*;
use bevy_yarnspinner::default_impl::MemoryVariableStorage;
use bevy_yarnspinner::prelude::*;

use super::chart::{self, Walker, WorldCommand};
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
    pub begin: Begin,
}

pub enum Begin {
    /// The start of a chapter of the chart (`$chapter`), its start node played.
    Chapter(&'static str),
    /// Inside a chapter: the first point where this gate is done.
    Gate(&'static str),
}

/// Every start point, in story order: one per chapter, and points inside chapters
/// where they help.
pub const START_POINTS: &[StartPoint] = &[
    StartPoint {
        name: "r1viewing",
        about: "Saturday: the viewing of 3B (knock on 3B)",
        begin: Begin::Chapter("R1Viewing"),
    },
    StartPoint {
        name: "r1viewing3b",
        about: "The viewing, inside 3B: the window, the kitchen and the bath",
        begin: Begin::Gate("r1_view_knock"),
    },
    StartPoint {
        name: "r1movein",
        about: "Moving day: keys, the box, the socks and her rules",
        begin: Begin::Chapter("R1MoveIn"),
    },
    StartPoint {
        name: "r1sunday",
        about: "Sunday morning: her text and the croissant at her door",
        begin: Begin::Chapter("R1Sunday"),
    },
    StartPoint {
        name: "r1thu1",
        about: "The first Thursday: her text, dinner at hers at eight",
        begin: Begin::Chapter("R1Thu1"),
    },
    StartPoint {
        name: "r1thu1dishes",
        about: "The first Thursday after dinner: wash up at her sink",
        begin: Begin::Gate("r1_thu1_sit"),
    },
    StartPoint {
        name: "r1thu2",
        about: "The second Thursday on the landing, her riddle unread",
        begin: Begin::Chapter("R1Thu2"),
    },
    StartPoint {
        name: "r1thu2door",
        about: "The second Thursday at her open door: give her things, shoes off",
        begin: Begin::Gate("r1_thu2_door"),
    },
    StartPoint {
        name: "r1thu2dinner",
        about: "The second Thursday, the wine open: sit down for the dinner",
        begin: Begin::Gate("r1_thu2_open"),
    },
    StartPoint {
        name: "r1thu2night",
        about: "The second Thursday, home in 3B: her night text unread, then bed",
        begin: Begin::Gate("r1_thu2_stand"),
    },
];

impl Begin {
    fn reached(&self, state: &chart::State) -> bool {
        match self {
            Begin::Chapter(chapter) => state.chapter() == *chapter,
            Begin::Gate(gate) => state.gate(gate),
        }
    }
}

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

/// Restores the end state of the world commands of a walk.
fn replay(world: &mut World, commands: Vec<WorldCommand>) {
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

/// The nodes of the map's hotspots: what the walker can use.
fn hotspot_nodes(map: &TiledMap) -> Vec<String> {
    map.object_layer("Hotspots")
        .iter()
        .filter_map(|obj| obj.prop_str("node").map(str::to_string))
        .collect()
}

/// Walks to the requested start point once the world is spawned and replays its end
/// state. Runs once: returning to the menu later plays normally.
fn apply_start_point(world: &mut World) {
    let Some(request) = world.remove_resource::<StartRequest>() else {
        return;
    };
    let hotspots = hotspot_nodes(world.resource::<TiledMap>());
    let project = world.resource::<YarnProject>();
    let walked = Walker::new(project, &hotspots).and_then(|mut walker| {
        let path = walker.path_to(|state| request.point.begin.reached(state))?;
        walker.replay(&path)
    });
    let (state, commands) = match walked {
        Ok(walked) => walked,
        Err(err) => {
            error!("Start point '{}': {err}", request.point.name);
            return;
        }
    };
    let mut storage = world.resource::<StoryVars>().0.clone();
    if let Err(err) = storage.extend(state.vars.into_iter().collect()) {
        error!("Start point '{}': {err}", request.point.name);
    }
    for (name, value) in &request.sets {
        if let Err(err) = set_variable(project, &mut storage, name, value) {
            error!("--set {name}={value}: {err}");
        }
    }
    replay(world, commands);
    let mut phone = world.resource_mut::<Phone>();
    phone.unread = state.unread.into();
    for note in state.notes {
        phone.note(note.id.clone(), note.text);
        if note.done {
            phone.note_done(&note.id);
        }
    }
    world.resource_mut::<ItemsSeen>().rebaseline(&storage);
}

/// A new game starts with the first chapter's start node, unless a start point takes
/// over.
fn start_new_game(mut queued: ResMut<QueuedScene>, request: Option<Res<StartRequest>>) {
    if request.is_none() {
        queued.0 = Some(chart::FIRST_NODE.to_string());
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
            .add_systems(OnEnter(GameState::Gaming), start_new_game)
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

    use crate::story::chart::tests::route1_hotspots;
    use crate::story::load_real_project;

    fn get(storage: &MemoryVariableStorage, name: &str) -> String {
        storage.get(name).map(|v| v.to_string()).unwrap_or_default()
    }

    #[test]
    fn every_start_point_is_reached() {
        let app = load_real_project();
        let project = app.world().resource::<YarnProject>();
        let mut walker = Walker::new(project, &route1_hotspots()).unwrap();
        let mut names = std::collections::HashSet::new();
        for point in START_POINTS {
            assert!(names.insert(point.name), "'{}' twice", point.name);
            assert_ne!(point.name, "list", "'list' lists the start points");
            let path = walker
                .path_to(|state| point.begin.reached(state))
                .unwrap_or_else(|err| panic!("{}: {err}", point.name));
            let (state, _) = walker.replay(&path).unwrap();
            assert!(point.begin.reached(&state), "{}", point.name);
        }
    }

    #[test]
    fn the_second_thursday_starts_with_her_riddle_unread() {
        let app = load_real_project();
        let project = app.world().resource::<YarnProject>();
        let mut walker = Walker::new(project, &route1_hotspots()).unwrap();
        let point = find("r1thu2").unwrap();
        let path = walker.path_to(|s| point.begin.reached(s)).unwrap();
        let (state, commands) = walker.replay(&path).unwrap();
        assert_eq!(state.unread, ["PhoneThursday2"]);
        assert!(state.gate("r1_thu1_bed") && !state.gate("r1_thu2_text"));
        // Every earlier bottleneck is done.
        for gate in ["r1_view_end", "r1_move_bed", "r1_sun_bed"] {
            assert!(state.gate(gate), "{gate}");
        }
        // The landing, the screen clear again.
        let place = commands.iter().rposition(|(n, _)| n == "place").unwrap();
        assert_eq!(commands[place].1, ["Player", "PlayerFromShop"]);
        let last_fade = commands.iter().rev().find(|(n, _)| n.starts_with("fade_"));
        assert_eq!(last_fade.unwrap().0, "fade_in");
    }

    #[test]
    fn set_variable_keeps_the_declared_type() {
        let app = load_real_project();
        let project = app.world().resource::<YarnProject>();
        let mut storage = MemoryVariableStorage::new();
        set_variable(project, &mut storage, "r1_movein_socks", "refuse").unwrap();
        assert_eq!(get(&storage, "$r1_movein_socks"), "refuse");
        set_variable(project, &mut storage, "$gate_r1_thu2_wine", "true").unwrap();
        assert_eq!(get(&storage, "$gate_r1_thu2_wine"), "true");
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
