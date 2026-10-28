//! Checks of the Yarn conventions in `assets/dialogue/*.yarn`.
//! Subdirectories such as `assets/dialogue/forest/` (the retired story) are not checked.

use std::{collections::HashSet, fs};

use story_graph::{parse_command, BoxKind, GraphBox, NodeKind};
use strsim::levenshtein;

const PATH_TO_DIR: &str = "assets/dialogue";

const MAX_SIMILARITY_DISTANCE: usize = 4;

/// Custom commands with their allowed number of arguments.
const CUSTOM_COMMANDS: [(&str, std::ops::RangeInclusive<usize>); 26] = [
    ("stop_chat", 0..=0),
    ("end_demo", 0..=0),
    ("walk", 2..=3),
    ("await_walks", 0..=0),
    ("face", 2..=2),
    ("show", 1..=1),
    ("hide", 1..=1),
    ("open_door", 1..=1),
    ("close_door", 1..=1),
    ("place", 2..=2),
    ("fade_out", 0..=0),
    ("fade_in", 0..=0),
    ("card", 1..=1),
    ("next_scene", 1..=1),
    ("phone", 1..=1),
    ("note", 2..=2),
    ("note_done", 1..=1),
    // Story graph data (assets/dialogue/graph_*.yarn): never run, read by the game
    // (story/graph.rs) and by dialogue_graph.
    ("box", 2..=6),
    ("gate", 2..=20),
    ("item", 2..=20),
    ("clue", 2..=20),
    ("choice", 2..=20),
    ("option", 3..=3),
    ("exit", 3..=20),
    // Scenes drive the story graph (story/graph.rs): a step is done, a box is entered.
    ("done", 2..=2),
    ("enter_box", 1..=1),
];

/// Commands that Yarn Spinner itself provides.
const BUILTIN_COMMANDS: [&str; 14] = [
    "jump", "set", "declare", "if", "elseif", "else", "endif", "wait", "detour", "enum", "endenum",
    "once", "endonce", "return",
];

/// All yarn files directly in `PATH_TO_DIR` as (file name without extension, contents).
fn yarn_files() -> Vec<(String, String)> {
    let mut files = Vec::new();
    for entry in fs::read_dir(PATH_TO_DIR).expect("Can't read entries in current dir") {
        let path = entry.expect("Can't get entry in current dir").path();
        if !path.is_file() || path.extension().is_none_or(|ext| ext != "yarn") {
            continue;
        }
        let name = path.file_stem().unwrap().to_string_lossy().to_string();
        let contents = fs::read_to_string(&path).expect("Should have been able to read the file");
        files.push((name, contents));
    }
    files
}

/// Loop over all yarn files and apply the predicate on each trimmed line.
fn validate_lines<F>(mut predicate: F)
where
    F: FnMut(&str, &str),
{
    for (file_name, contents) in yarn_files() {
        for line in contents.lines().map(str::trim) {
            predicate(line, &file_name)
        }
    }
}

/// The nodes of a file as (title, body lines after `---`).
pub(crate) fn nodes(contents: &str) -> Vec<(String, Vec<&str>)> {
    let mut nodes = Vec::new();
    let mut title = None;
    let mut body: Option<Vec<&str>> = None;
    for line in contents.lines().map(str::trim) {
        match &mut body {
            None => {
                if let Some(t) = line.strip_prefix("title:") {
                    title = Some(t.trim().to_string());
                } else if line == "---" {
                    body = Some(Vec::new());
                }
            }
            Some(lines) => {
                if line == "===" {
                    nodes.push((title.take().unwrap_or_default(), body.take().unwrap()));
                } else {
                    lines.push(line);
                }
            }
        }
    }
    nodes
}

/// This essentially tests for typos in the commands of the yarn files.
#[test]
fn validate_custom_commands() {
    validate_lines(|line, file| {
        let Some((command, _)) = parse_command(line) else {
            return;
        };
        let command = command.as_str();
        if BUILTIN_COMMANDS.contains(&command) {
            return;
        }

        let (closest_command, closest_distance) = CUSTOM_COMMANDS
            .iter()
            .map(|(name, _)| (*name, levenshtein(command, name)))
            .min_by_key(|(_, distance)| *distance)
            .unwrap();

        if closest_distance < MAX_SIMILARITY_DISTANCE {
            assert!(
                command == closest_command,
                "{command} and {closest_command} are {closest_distance} levenshtein close but don't match! (in {file})"
            );
        }
    });
}

#[test]
fn validate_scripted_command_arity() {
    validate_lines(|line, file| {
        let Some((command, args)) = parse_command(line) else {
            return;
        };
        let Some((_, allowed)) = CUSTOM_COMMANDS
            .iter()
            .find(|(name, _)| *name == command.as_str())
        else {
            return;
        };
        assert!(
            allowed.contains(&args.len()),
            "<<{command}>> takes {allowed:?} arguments but has {} in {file}: '{line}'",
            args.len()
        );
        if command == "walk" && args.len() == 3 {
            assert!(
                args[2] == "no_wait",
                "Third argument of <<walk>> must be 'no_wait' in {file}: '{line}'"
            );
        }
    });
}

#[test]
fn validate_stop_chat_command() {
    validate_lines(|line, _| {
        if line.starts_with("<<stop_chat") {
            assert!(line == "<<stop_chat>>");
        }
    })
}

#[test]
fn validate_node_title_uniqueness() {
    let mut titles = HashSet::new();

    validate_lines(|line, file| {
        if let Some(title) = line.strip_prefix("title: ") {
            assert!(
                titles.insert(title.to_string()),
                "Title already exists! title: {title}, in file: {file}",
            );
        }
    });
}

/// This test ensures that all yarn files only jump to nodes that are within that file.
/// While it works to jump to nodes that are definied in other files,
/// I don't see any reason to make use of this feature in this game.
/// It seems like it will just lead to bugs.
#[test]
fn validate_node_exists() {
    for (file, contents) in yarn_files() {
        let titles: HashSet<String> = nodes(&contents).into_iter().map(|(t, _)| t).collect();
        for line in contents.lines().map(str::trim) {
            if let Some(command) = line.strip_prefix("<<jump ") {
                let title = command.trim_end_matches(">>");
                assert!(
                    titles.contains(title),
                    "Referenced title: '{title}' in file: '{file}' doesn't exist! (jump command)"
                );
            }
        }
    }
}

/// Every `<<next_scene NODE>>` starts a node that exists in one of the files.
#[test]
fn validate_next_scene_exists() {
    let files = yarn_files();
    let titles: HashSet<String> = files
        .iter()
        .flat_map(|(_, contents)| nodes(contents))
        .map(|(title, _)| title)
        .collect();
    validate_lines(|line, file| {
        let Some((command, args)) = parse_command(line) else {
            return;
        };
        if command == "next_scene" {
            assert!(
                args.first().is_some_and(|node| titles.contains(node)),
                "<<next_scene>> in {file} names a node that doesn't exist: '{line}'"
            );
        }
    });
}

/// Every `{$variable}: line` speaker needs a `<<declare $variable ...>>` in one of the files
/// (Yarn allows a single declaration per project, so later scenes reuse the first one).
#[test]
fn validate_speaker_variables_declared() {
    let files = yarn_files();
    let declared: HashSet<String> = files
        .iter()
        .flat_map(|(_, contents)| contents.lines())
        .map(str::trim)
        .filter_map(|line| line.strip_prefix("<<declare "))
        .filter_map(|rest| rest.split_whitespace().next())
        .map(str::to_string)
        .collect();

    for (file, contents) in files {
        for line in contents.lines().map(str::trim) {
            let Some(rest) = line.strip_prefix("{$") else {
                continue;
            };
            let Some((name, _)) = rest.split_once("}:") else {
                continue;
            };
            let variable = format!("${name}");
            assert!(
                declared.contains(&variable),
                "Speaker variable {variable} in {file} is not declared in any yarn file"
            );
        }
    }
}

/// A conversation with an NPC opens with the NPC's line, or with the actions at a talk
/// target (options before any line, shown as a popup). Nodes without NPC lines are
/// exempt: staging nodes that only run commands, and the player's own remarks at an
/// object (an interactable such as a door). Graph nodes never run and are exempt too.
#[test]
fn validate_first_line_is_npc_line() {
    let graphs = graph_nodes();
    for (file, contents) in yarn_files() {
        for (title, body) in nodes(&contents) {
            if graphs.contains(&title) {
                continue;
            }
            let is_dialogue = |line: &&&str| {
                !(line.is_empty() || line.starts_with("<<") || line.starts_with("//"))
            };
            if !body
                .iter()
                .filter(is_dialogue)
                .any(|line| line.starts_with("{$"))
            {
                continue;
            }
            let first = body.iter().find(is_dialogue).unwrap();
            assert!(
                !first.starts_with("You:"),
                "The first line of node {title} in {file} must be spoken by an NPC or be an action, found '{first}'"
            );
        }
    }
}

/// Make sure there are no narrator lines.
/// This is a problem because the visuals from the profile icon (portrait)
/// would look really strange.
#[test]
fn assert_no_narrator_lines() {
    for (file, contents) in yarn_files() {
        for line in contents.lines().map(str::trim) {
            if !(line.starts_with("{$")
                || line.starts_with("You:")
                || line.starts_with("<<")
                || line.starts_with("===")
                || line.starts_with("---")
                || line.starts_with("title:")
                || line.starts_with("tags:")
                || line.starts_with("->")
                || line.starts_with("//")
                || line.is_empty())
            {
                panic!(
                    "There should be no narrator lines, i.e. dialogue lines that don't start with a '<name>: <dialogue content>'\nIn line: '{line}'\nIn file: '{file}'"
                );
            }
        }
    }
}

#[test]
fn nodes_are_split_at_markers() {
    let nodes = nodes("title: A\ntags: x\n---\nline\n===\ntitle: B\n---\nother\n===\n");
    assert_eq!(nodes.len(), 2);
    assert_eq!(nodes[0], ("A".to_string(), vec!["line"]));
    assert_eq!(nodes[1], ("B".to_string(), vec!["other"]));
}

#[test]
fn quoted_command_arguments_stay_whole() {
    let (name, args) = parse_command(r#"<<card "Saturday. Moving day.">>"#).unwrap();
    assert_eq!(name, "card");
    assert_eq!(args, vec!["Saturday. Moving day.".to_string()]);
}

/// The node titles with their `tags:` header, of every file.
fn node_tags() -> Vec<(String, Vec<String>)> {
    let mut result = Vec::new();
    for (_, contents) in yarn_files() {
        let mut title = None;
        let mut tags = Vec::new();
        for line in contents.lines().map(str::trim) {
            if let Some(t) = line.strip_prefix("title:") {
                title = Some(t.trim().to_string());
                tags.clear();
            } else if let Some(t) = line.strip_prefix("tags:") {
                tags = t.split_whitespace().map(str::to_string).collect();
            } else if line == "---" {
                if let Some(title) = title.take() {
                    result.push((title, std::mem::take(&mut tags)));
                }
            }
        }
    }
    result
}

/// Every `<<phone NODE>>` delivers a node that exists and is tagged `phone`.
#[test]
fn validate_phone_nodes() {
    let tags = node_tags();
    validate_lines(|line, file| {
        let Some((command, args)) = parse_command(line) else {
            return;
        };
        if command != "phone" {
            return;
        }
        let node = args.first().cloned().unwrap_or_default();
        let found = tags.iter().find(|(title, _)| *title == node);
        assert!(
            found.is_some_and(|(_, tags)| tags.iter().any(|t| t == crate::story::phone::PHONE_TAG)),
            "<<phone {node}>> in {file} needs an existing node tagged 'phone'"
        );
    });
}

/// Every `$item_` variable is declared and has a row in the item table, and every row is
/// declared.
#[test]
fn validate_items() {
    use crate::story::inventory::{variable, ITEMS};
    let declared: HashSet<String> = yarn_files()
        .iter()
        .flat_map(|(_, contents)| {
            contents
                .lines()
                .map(str::trim)
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .filter_map(|line| {
            let rest = line.strip_prefix("<<declare ")?;
            let name = rest.split_whitespace().next()?;
            name.starts_with("$item_").then(|| name.to_string())
        })
        .collect();
    for item in ITEMS {
        assert!(
            declared.contains(&variable(item.id)),
            "Item '{}' needs <<declare {} = false>> in items.yarn",
            item.id,
            variable(item.id)
        );
    }
    for name in &declared {
        assert!(
            ITEMS.iter().any(|item| variable(item.id) == *name),
            "{name} is declared but has no row in ITEMS (src/story/inventory.rs)"
        );
    }
    validate_lines(|line, file| {
        if line.starts_with("//") {
            return;
        }
        for word in line.split(|c: char| !(c.is_alphanumeric() || c == '_' || c == '$')) {
            if word.starts_with("$item_") {
                assert!(
                    declared.contains(word),
                    "{word} in {file} is not a declared item"
                );
            }
        }
    });
}

/// The titles of nodes tagged `tag`.
fn tagged_nodes(tag: &str) -> HashSet<String> {
    node_tags()
        .into_iter()
        .filter(|(_, tags)| tags.iter().any(|t| t == tag))
        .map(|(title, _)| title)
        .collect()
}

/// The titles of nodes tagged `graph`: story graph data, never run.
fn graph_nodes() -> HashSet<String> {
    tagged_nodes(crate::story::graph::GRAPH_TAG)
}

/// Story conditions read the story graph (`can()`, `is_done()`), items and flags, never
/// `visited()`.
#[test]
fn story_conditions_do_not_read_visits() {
    validate_lines(|line, file| {
        assert!(
            line.starts_with("//") || !line.contains("visited("),
            "{file} reads visited(): '{line}'"
        );
    });
}

/// The boxes of every `graph` node of every file, in file name order.
fn graph_boxes() -> Vec<GraphBox> {
    let mut files = yarn_files();
    files.sort();
    files
        .iter()
        .flat_map(|(_, contents)| story_graph::graph_boxes(contents))
        .collect()
}

/// The scene nodes (not graph data) of every file as (file, title, body lines).
fn scene_nodes() -> Vec<(String, String, Vec<String>)> {
    let graphs = graph_nodes();
    let mut scenes = Vec::new();
    for (file, contents) in yarn_files() {
        for (title, body) in nodes(&contents) {
            if !graphs.contains(&title) {
                let body = body.into_iter().map(str::to_string).collect();
                scenes.push((file.clone(), title, body));
            }
        }
    }
    scenes
}

#[test]
fn graph_is_well_formed() {
    let boxes = graph_boxes();
    assert!(!boxes.is_empty(), "no graph nodes");
    let known: HashSet<&str> = boxes.iter().map(|b| b.id.as_str()).collect();
    assert_eq!(known.len(), boxes.len(), "a box id is used twice");
    let titles: HashSet<String> = yarn_files()
        .iter()
        .flat_map(|(_, contents)| nodes(contents))
        .map(|(title, _)| title)
        .collect();
    let mut entries = HashSet::new();

    for b in &boxes {
        let ids: HashSet<&str> = b.nodes.iter().map(|n| n.id.as_str()).collect();
        assert_eq!(ids.len(), b.nodes.len(), "{} has a node id twice", b.id);
        if let Some(entry) = &b.entry {
            assert!(
                titles.contains(entry),
                "{}: the entry node '{entry}' does not exist",
                b.id
            );
            assert!(entries.insert(entry), "{entry} is the entry of two boxes");
        }
        for (choice, option, _) in &b.options {
            assert!(
                b.nodes
                    .iter()
                    .any(|n| n.kind == NodeKind::Choice && &n.id == choice),
                "{}: option {option} of unknown choice {choice}",
                b.id
            );
            assert!(
                !ids.contains(option.as_str()),
                "{}: option {option} is also a node",
                b.id
            );
        }
        for node in b.nodes.iter().filter(|n| n.kind == NodeKind::Exit) {
            let target = node.to.as_deref().unwrap_or_default();
            assert!(
                known.contains(target),
                "{}: exit {} leads to unknown box '{target}'",
                b.id,
                node.id
            );
        }
        for node in &b.nodes {
            for req in node.requires.iter().flatten() {
                if let Some((box_id, clue)) = story_graph::cross_box(req) {
                    let source = boxes.iter().find(|o| o.id == box_id);
                    assert!(
                        source.is_some_and(|s| s
                            .nodes
                            .iter()
                            .any(|n| n.kind == NodeKind::Clue && n.id == clue)),
                        "{}: {} needs unknown clue {req}",
                        b.id,
                        node.id
                    );
                } else if let Some((choice, option)) = req.split_once('=') {
                    assert!(
                        b.options.iter().any(|(c, o, _)| c == choice && o == option),
                        "{}: {} needs unknown option {req}",
                        b.id,
                        node.id
                    );
                } else {
                    assert!(
                        ids.contains(req.as_str()) && *req != node.id,
                        "{}: {} needs unknown node {req}",
                        b.id,
                        node.id
                    );
                }
            }
        }
        assert!(
            b.kind == BoxKind::Stub || b.nodes.iter().any(|n| n.kind == NodeKind::Exit),
            "box {} has no exit",
            b.id
        );
    }
}

/// Every `<<done BOX ID>>` of a scene names a step of a box of the story graph.
#[test]
fn done_marks_name_known_steps() {
    let boxes = graph_boxes();
    for (file, title, body) in scene_nodes() {
        for line in body {
            let Some((command, args)) = parse_command(&line) else {
                continue;
            };
            if command != "done" || args.len() != 2 {
                continue;
            }
            let (box_id, step) = (&args[0], &args[1]);
            let known = boxes
                .iter()
                .find(|b| &b.id == box_id)
                .is_some_and(|b| b.has_step(step));
            assert!(
                known,
                "{file}/{title}: <<done {box_id} {step}>> names an unknown box or step"
            );
        }
    }
}

/// `<<enter_box BOX>>` is run by the entry node of that box and only there, once.
#[test]
fn entry_nodes_enter_their_box() {
    let boxes = graph_boxes();
    for (file, title, body) in scene_nodes() {
        let entered: Vec<String> = body
            .iter()
            .filter_map(|line| parse_command(line))
            .filter(|(command, _)| command == "enter_box")
            .map(|(_, args)| args.first().cloned().unwrap_or_default())
            .collect();
        let entry_of = boxes
            .iter()
            .find(|b| b.entry.as_deref() == Some(title.as_str()));
        match entry_of {
            Some(b) => assert_eq!(
                entered,
                std::slice::from_ref(&b.id),
                "{file}/{title} is the entry of {} and must run <<enter_box {}>> once",
                b.id,
                b.id
            ),
            None => assert!(
                entered.is_empty(),
                "{file}/{title} runs <<enter_box>> but is no entry node"
            ),
        }
    }
}

/// An exit starts the next box through `<<done>>`. A box without a scene (free time) can't,
/// so the scene of the exit leading into it starts the next box with a scene itself:
/// `<<next_scene ENTRY>>` of a box is only allowed together with such an exit.
#[test]
fn entry_nodes_are_started_by_exits() {
    let boxes = graph_boxes();
    let entries: HashSet<&str> = boxes.iter().filter_map(|b| b.entry.as_deref()).collect();
    for (file, title, body) in scene_nodes() {
        let commands: Vec<(String, Vec<String>)> =
            body.iter().filter_map(|line| parse_command(line)).collect();
        let into_a_hub = commands.iter().any(|(command, args)| {
            command == "done"
                && args.len() == 2
                && boxes
                    .iter()
                    .find(|b| b.id == args[0])
                    .and_then(|b| b.node(&args[1]))
                    .filter(|n| n.kind == NodeKind::Exit)
                    .and_then(|n| boxes.iter().find(|t| Some(&t.id) == n.to.as_ref()))
                    .is_some_and(|target| target.entry.is_none())
        });
        for (command, args) in &commands {
            if command == "next_scene" && args.first().is_some_and(|a| entries.contains(a.as_str()))
            {
                assert!(
                    into_a_hub,
                    "{file}/{title}: <<next_scene {}>> starts a box; leave it to an exit's <<done>>",
                    args[0]
                );
            }
        }
    }
}

/// Every exit that leads to a box with a scene is done by some scene.
#[test]
fn every_exit_into_a_scene_is_done_somewhere() {
    let boxes = graph_boxes();
    let marks: HashSet<(String, String)> = scene_nodes()
        .iter()
        .flat_map(|(_, _, body)| body.iter().filter_map(|line| parse_command(line)))
        .filter(|(command, args)| command == "done" && args.len() == 2)
        .map(|(_, args)| (args[0].clone(), args[1].clone()))
        .collect();
    for b in &boxes {
        for exit in b.nodes.iter().filter(|n| n.kind == NodeKind::Exit) {
            let target = boxes.iter().find(|t| Some(&t.id) == exit.to.as_ref());
            if b.entry.is_some() && target.is_some_and(|t| t.entry.is_some()) {
                assert!(
                    marks.contains(&(b.id.clone(), exit.id.clone())),
                    "no scene does <<done {} {}>>, the exit into {:?}",
                    b.id,
                    exit.id,
                    exit.to
                );
            }
        }
    }
}

/// The arguments of the calls to `function(` in a line, e.g. `can("A", "b")` is [A, b].
fn calls(line: &str, function: &str) -> Vec<Vec<String>> {
    let pattern = format!("{function}(");
    let mut found = Vec::new();
    for (at, _) in line.match_indices(&pattern) {
        let before = line[..at].chars().next_back();
        if before.is_some_and(|c| c.is_alphanumeric() || c == '_' || c == '$') {
            continue;
        }
        let Some(end) = line[at..].find(')') else {
            continue;
        };
        let args = line[at + pattern.len()..at + end]
            .split(',')
            .map(|a| a.trim().trim_matches('"').to_string())
            .collect();
        found.push(args);
    }
    found
}

/// `can()`, `is_done()` and `in_box()` in the scenes name steps of the graph.
#[test]
fn scenes_ask_known_steps() {
    let boxes = graph_boxes();
    let mut asked = 0;
    for (file, title, body) in scene_nodes() {
        for line in body.iter().filter(|l| !l.starts_with("//")) {
            for function in ["can", "is_done", "in_box"] {
                for args in calls(line, function) {
                    asked += 1;
                    let wanted = if function == "in_box" { 1 } else { 2 };
                    assert_eq!(
                        args.len(),
                        wanted,
                        "{file}/{title}: {function}() takes {wanted} arguments: '{line}'"
                    );
                    let Some(b) = boxes.iter().find(|b| b.id == args[0]) else {
                        panic!("{file}/{title}: unknown box '{}': '{line}'", args[0]);
                    };
                    assert!(
                        b.entry.is_some(),
                        "{file}/{title}: box {} has no scene: '{line}'",
                        b.id
                    );
                    if wanted == 2 {
                        assert!(
                            b.has_step(&args[1]),
                            "{file}/{title}: box {} has no step '{}': '{line}'",
                            b.id,
                            args[1]
                        );
                    }
                }
            }
        }
    }
    assert!(
        asked > 50,
        "the scenes ask the graph, found only {asked} calls"
    );
}

/// The graph's variables and the retired chart's are the engine's: scenes ask through
/// `can()`, `is_done()` and `in_box()` and change them through `<<done>>` and `<<enter_box>>`.
#[test]
fn scenes_do_not_touch_graph_variables() {
    for (file, title, body) in scene_nodes() {
        for line in body.iter().filter(|l| !l.starts_with("//")) {
            for name in ["$box", "$step_", "$chapter", "$gate_"] {
                assert!(
                    !line.contains(name),
                    "{file}/{title}: '{line}' touches {name}"
                );
            }
        }
    }
}
