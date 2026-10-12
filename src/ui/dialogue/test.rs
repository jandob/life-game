//! Checks of the Yarn conventions in `assets/dialogue/*.yarn`.
//! Subdirectories such as `assets/dialogue/forest/` (the retired story) are not checked.

use std::{collections::HashSet, fs};

use strsim::levenshtein;

const PATH_TO_DIR: &str = "assets/dialogue";

const MAX_SIMILARITY_DISTANCE: usize = 4;

/// Custom commands with their allowed number of arguments.
const CUSTOM_COMMANDS: [(&str, std::ops::RangeInclusive<usize>); 9] = [
    ("stop_chat", 0..=0),
    ("end_demo", 0..=0),
    ("walk", 2..=3),
    ("await_walks", 0..=0),
    ("face", 2..=2),
    ("show", 1..=1),
    ("hide", 1..=1),
    ("open_door", 1..=1),
    ("close_door", 1..=1),
];

/// Commands that Yarn Spinner itself provides.
const BUILTIN_COMMANDS: [&str; 14] = [
    "jump", "set", "declare", "if", "elseif", "else", "endif", "wait", "detour", "enum",
    "endenum", "once", "endonce", "return",
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

/// Command name and arguments of a `<<name arg arg>>` line.
fn parse_command(line: &str) -> Option<(&str, Vec<&str>)> {
    let inner = line.strip_prefix("<<")?.strip_suffix(">>")?;
    let mut words = inner.split_whitespace();
    let name = words.next()?;
    Some((name, words.collect()))
}

/// The nodes of a file as (title, body lines after `---`).
fn nodes(contents: &str) -> Vec<(String, Vec<&str>)> {
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
        let Some((_, allowed)) = CUSTOM_COMMANDS.iter().find(|(name, _)| *name == command) else {
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

/// Every `{$variable}: line` speaker needs a `<<declare $variable ...>>` in its file.
#[test]
fn validate_speaker_variables_declared() {
    for (file, contents) in yarn_files() {
        let declared: HashSet<&str> = contents
            .lines()
            .map(str::trim)
            .filter_map(|line| line.strip_prefix("<<declare "))
            .filter_map(|rest| rest.split_whitespace().next())
            .collect();

        for line in contents.lines().map(str::trim) {
            let Some(rest) = line.strip_prefix("{$") else {
                continue;
            };
            let Some((name, _)) = rest.split_once("}:") else {
                continue;
            };
            let variable = format!("${name}");
            assert!(
                declared.contains(variable.as_str()),
                "Speaker variable {variable} is not declared in {file}"
            );
        }
    }
}

/// The first line of every node is spoken by a non-player character.
#[test]
fn validate_first_line_is_npc_line() {
    for (file, contents) in yarn_files() {
        for (title, body) in nodes(&contents) {
            let first = body
                .iter()
                .find(|line| {
                    !(line.is_empty() || line.starts_with("<<") || line.starts_with("//"))
                })
                .unwrap_or_else(|| panic!("Node {title} in {file} has no dialogue line"));
            assert!(
                !first.starts_with("You:") && !first.starts_with("->"),
                "The first line of node {title} in {file} must be spoken by an NPC, found '{first}'"
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
