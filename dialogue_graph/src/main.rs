#[cfg(test)]
mod test;

use core::panic;
use std::{
    collections::HashMap,
    fs::{self, create_dir, remove_dir_all, DirEntry, File},
    io::{Error, Read, Write},
    path::Path,
};

use petgraph::{dot::Dot, prelude::*};

const PATH_TO_DIALOGUES: &str = "assets/dialogue";
const DOT_FILES_OUTPUT_PATH: &str = "graphs";

const ATTR_DELIMETER: &str = "|BREAK|";
const LEAF_NODE_COLOR: &str = "red";
const SINGLE_OPTION_NODE_COLOR: &str = "blue";
const TITLE_NODE_STYLE: &str = "bold";
const TITLE_NODE_SHAPE: &str = "diamond";

const FIN_NODE_LABEL: &str = "FIN";

struct Container {
    title: NodeIndex,
    player_options: [Option<NodeIndex>; 10],
    graph: Graph<String, usize, Directed>,
    title_indices: HashMap<String, NodeIndex>,
}

fn try_read_yarn_contents(entry: Result<DirEntry, Error>) -> Option<(String, String)> {
    let entry = entry.expect("Can't get entry in current dir");
    let npc_file_name = entry
        .file_name()
        .into_string()
        .expect("Can't convert OsString to String")
        .split('.')
        .collect::<Vec<&str>>()[0]
        .to_string();
    let path = entry.path();

    if !path.is_file() {
        return None;
    }

    if let Some(ext) = path.extension() {
        if ext == "yarn" {
            return Some((
                (fs::read_to_string(path).expect("Should have been able to read the file")),
                npc_file_name,
            ));
        }
    }
    None
}

/// Counts the whitespaces at the start of the string.
/// As soon as a non-whitespace character is encountered, break.
fn count_whitespaces(line: &str) -> usize {
    let mut count = 0;
    for c in line.chars() {
        if !c.is_whitespace() {
            break;
        }
        count += 1;
    }
    count
}

fn index_from_whitespaces(line: &str) -> usize {
    let whitespaces = count_whitespaces(line);
    assert!(
        whitespaces % 4 == 0,
        "Whitespaces should always be 4 chars long, {}",
        line
    );
    whitespaces / 4
}

fn handle_player_option(container: &mut Container, line: &str) {
    let index = index_from_whitespaces(line);

    let end = container.graph.add_node(line.trim().to_string());
    let start = if index == 0 {
        container.title
    } else {
        container.player_options[index - 1].unwrap_or(container.title)
    };
    container.graph.update_edge(start, end, index);
    container.player_options[index] = Some(end);
}

fn handle_jump_command(container: &mut Container, line: &str) {
    let title: &str = &format!(
        "title: {}",
        line.trim().split(" ").collect::<Vec<&str>>()[1]
            .strip_suffix(">>")
            .expect("Jump commands should always end on '>>'"),
    );
    let title_node = *container
        .title_indices
        .get(title)
        .expect("Titles should all be set");

    fn get_option(player_options: [Option<NodeIndex>; 10], index: usize) -> Option<NodeIndex> {
        if index == 0 {
            return None;
        }

        match player_options[index - 1] {
            Some(r) => Some(r),
            None => get_option(player_options, index - 1),
        }
    }

    let index = index_from_whitespaces(line);
    let option_node = get_option(container.player_options, index).unwrap_or(container.title);
    container.graph.update_edge(option_node, title_node, index);
}

fn handle_ending_command(container: &mut Container, line: &str) {
    let weight = index_from_whitespaces(line);

    let start = if weight == 0 {
        container.title
    } else {
        get_option(container.player_options, weight)
    };

    fn get_option(player_options: [Option<NodeIndex>; 10], weight: usize) -> NodeIndex {
        if weight == 0 {
            panic!("current_player_options is empty but it's supposed to have at least one non-empty value");
        }

        match player_options[weight - 1] {
            Some(r) => r,
            None => get_option(player_options, weight - 1),
        }
    }

    let end = container.graph.add_node(FIN_NODE_LABEL.to_string());
    container.graph.update_edge(start, end, weight);
}

fn clear_player_options(container: &mut Container, line: &str) {
    let index = index_from_whitespaces(line);
    for i in (index..container.player_options.len()).rev() {
        container.player_options[i] = None;
    }
}

fn get_leaf_nodes(graph: &Graph<String, usize>) -> Vec<NodeIndex> {
    graph
        .node_indices()
        .filter(|i| {
            graph.edges(*i).count() == 0
                && graph.node_weight(*i).unwrap_or(&String::new()) != FIN_NODE_LABEL
        })
        .collect()
}

fn get_single_option_nodes(graph: &Graph<String, usize>) -> Vec<NodeIndex> {
    graph
        .node_indices()
        .filter(|i| {
            if graph.edges(*i).count() != 1 {
                return false;
            }

            let target_index = graph.edges(*i).next().unwrap().target();
            graph.node_weight(target_index).unwrap().starts_with("-> ")
        })
        .collect()
}

fn get_title_nodes(graph: &Graph<String, usize>) -> Vec<NodeIndex> {
    graph
        .node_indices()
        .filter(|i| graph.node_weight(*i).unwrap().starts_with("title: "))
        .collect()
}

fn label_graph_with_attributes(container: &mut Container) {
    let leaf_nodes = get_leaf_nodes(&container.graph);
    for index in leaf_nodes {
        *container.graph.node_weight_mut(index).unwrap() +=
            &format!("{}color={}", ATTR_DELIMETER, LEAF_NODE_COLOR);
    }

    let title_nodes = get_title_nodes(&container.graph);
    for index in title_nodes {
        *container.graph.node_weight_mut(index).unwrap() += &format!(
            "{}style={}{}shape={}",
            ATTR_DELIMETER, TITLE_NODE_STYLE, ATTR_DELIMETER, TITLE_NODE_SHAPE
        );
    }

    let single_option_nodes = get_single_option_nodes(&container.graph);
    for index in single_option_nodes {
        *container.graph.node_weight_mut(index).unwrap() +=
            &format!("{}color={}", ATTR_DELIMETER, SINGLE_OPTION_NODE_COLOR);
    }
}

fn parse_labels_dot_file(path: &str) {
    fn read_file_content(buf: &mut String, path: &str) {
        let mut file =
            File::open(path).unwrap_or_else(|_| panic!("Can't open file, '{}', to read", path));
        file.read_to_string(buf)
            .unwrap_or_else(|_| panic!("Can't read content of file, '{}'", path));
    }

    let mut content = String::new();
    read_file_content(&mut content, path);
    let mut output_content = String::new();

    for line in content.split("\n") {
        if !line.contains(ATTR_DELIMETER) {
            output_content += &(line.to_string() + "\n");
            continue;
        }

        // The label is between the first and the last quote; it may hold escaped quotes.
        let (Some(start), Some(end)) = (line.find('"'), line.rfind('"')) else {
            panic!("A labelled line without quotes: '{line}'");
        };
        let parts = [&line[..start], &line[start + 1..end], &line[end + 1..]];
        let label = parts[1];

        assert!(label.contains(ATTR_DELIMETER));
        let attr_parts: Vec<&str> = label.split(ATTR_DELIMETER).collect();
        let true_label = &format!("\"{}\"", attr_parts[0]);

        let mut appendix = String::new();

        for attr_part in attr_parts.iter().skip(1) {
            appendix += &format!(" [ {} ]", attr_part);
        }

        let final_line = parts[0].to_string() + true_label + parts[2] + &appendix;
        output_content += &(final_line + "\n");
    }

    let mut file =
        File::create(path).unwrap_or_else(|_| panic!("Can't open file, '{}', to read", path));
    file.write_all(output_content.as_bytes())
        .unwrap_or_else(|_| panic!("Couldn't write to file: '{}'", path));
}

fn write_meta_data(path: &str, graph: Graph<String, usize>) {
    fn read_file_content(buf: &mut String, path: &str) {
        let mut file =
            File::open(path).unwrap_or_else(|_| panic!("Can't open file, '{}', to read", path));
        file.read_to_string(buf)
            .unwrap_or_else(|_| panic!("Can't read content of file, '{}'", path));
    }

    let leaf_node_count = get_leaf_nodes(&graph).len();
    let single_option_node_count = get_single_option_nodes(&graph).len();

    let mut output_content = String::new();
    output_content += "/*\n";
    output_content += "--- START METADATA ---\n";
    output_content += &format!("Leaf Nodes: {}\n", leaf_node_count);
    output_content += &format!("Single Option Nodes: {}\n", single_option_node_count);
    output_content += "--- END   METADATA ---\n";
    output_content += "*/\n\n";
    read_file_content(&mut output_content, path);

    let mut file =
        File::create(path).unwrap_or_else(|_| panic!("Can't open file, '{}', to read", path));
    file.write_all(output_content.as_bytes())
        .unwrap_or_else(|_| panic!("Couldn't write to file: '{}'", path));
}

fn construct_graph(contents: String) -> Graph<String, usize, Directed> {
    let dialogue_lines = contents.lines();

    let mut container = Container {
        title: NodeIndex::new(0),
        player_options: [None; 10],
        graph: Graph::default(),
        title_indices: HashMap::new(),
    };

    for title in dialogue_lines
        .clone()
        .filter(|l| l.trim().starts_with("title: "))
    {
        let index = container.graph.add_node(title.trim().to_string());
        assert!(
            container.title_indices.insert(title.trim().to_string(), index).is_none(),
            "There are two titles with the same name. The tests should cover this, are the tests passing?"
        );
    }

    for line in dialogue_lines {
        clear_player_options(&mut container, line);
        if line.trim().starts_with("title: ") {
            container.title = *container.title_indices.get(line).unwrap();
        } else if line.trim().starts_with("-> ") {
            handle_player_option(&mut container, line);
        } else if line.trim().starts_with("<<jump ") {
            handle_jump_command(&mut container, line);
        } else if line.trim().starts_with("<<trigger_ending ") {
            handle_ending_command(&mut container, line);
        }
    }

    label_graph_with_attributes(&mut container);
    container.graph
}

/// The titles of the nodes tagged `chart` (story chart data, see `src/story/chart.rs`).
fn chart_titles(contents: &str) -> Vec<String> {
    let mut titles = Vec::new();
    let mut title = None;
    for line in contents.lines().map(str::trim) {
        if let Some(t) = line.strip_prefix("title:") {
            title = Some(t.trim().to_string());
        } else if let Some(tags) = line.strip_prefix("tags:") {
            if tags.split_whitespace().any(|t| t == "chart") {
                titles.extend(title.take());
            }
        } else if line == "---" {
            title = None;
        }
    }
    titles
}

/// Command name and arguments of a `<<name arg "quoted arg">>` line.
fn parse_command(line: &str) -> Option<(String, Vec<String>)> {
    let inner = line.strip_prefix("<<")?.strip_suffix(">>")?;
    let mut words = Vec::new();
    let mut current = String::new();
    let mut quoted = false;
    for c in inner.chars() {
        match c {
            '"' => quoted = !quoted,
            c if c.is_whitespace() && !quoted => {
                if !current.is_empty() {
                    words.push(std::mem::take(&mut current));
                }
            }
            c => current.push(c),
        }
    }
    if !current.is_empty() {
        words.push(current);
    }
    let mut words = words.into_iter();
    Some((words.next()?, words.collect()))
}

fn quote(text: &str) -> String {
    format!("\"{}\"", text.replace('"', "\\\""))
}

/// The story chart of a file as Graphviz: one cluster per chapter, labelled with its card,
/// a box per gate, an edge per requirement and the bottleneck in bold. Each bottleneck
/// leads on to the gates of the next chapter that need nothing else.
fn chart_dot(contents: &str) -> String {
    struct Gate {
        id: String,
        label: String,
        requires: Vec<String>,
        bottleneck: bool,
    }
    let mut chapters: Vec<(String, String, Vec<Gate>)> = Vec::new();
    for line in contents.lines().map(str::trim) {
        let Some((command, mut args)) = parse_command(line) else {
            continue;
        };
        if !matches!(command.as_str(), "chapter" | "gate" | "bottleneck") || args.len() < 2 {
            continue;
        }
        let id = args.remove(0);
        let label = args.remove(0);
        if command == "chapter" {
            chapters.push((id, label, Vec::new()));
        } else if let Some((_, _, gates)) = chapters.last_mut() {
            gates.push(Gate {
                id,
                label,
                requires: args,
                bottleneck: command == "bottleneck",
            });
        }
    }

    let mut dot = String::from("digraph chart {\n    rankdir=TB;\n    node [shape=box];\n");
    for (i, (id, card, gates)) in chapters.iter().enumerate() {
        dot += &format!(
            "    subgraph cluster_{i} {{\n        label={};\n",
            quote(&format!("{id}: {card}"))
        );
        for gate in gates {
            let style = if gate.bottleneck { ", style=bold" } else { "" };
            dot += &format!(
                "        {} [label={}{style}];\n",
                quote(&gate.id),
                quote(&gate.label)
            );
        }
        dot += "    }\n";
    }
    for (i, (_, _, gates)) in chapters.iter().enumerate() {
        for gate in gates {
            for need in &gate.requires {
                dot += &format!("    {} -> {};\n", quote(need), quote(&gate.id));
            }
        }
        let Some((_, _, next)) = chapters.get(i + 1) else {
            continue;
        };
        let Some(bottleneck) = gates.iter().find(|g| g.bottleneck) else {
            continue;
        };
        for gate in next.iter().filter(|g| g.requires.is_empty()) {
            dot += &format!(
                "    {} -> {} [style=dashed];\n",
                quote(&bottleneck.id),
                quote(&gate.id)
            );
        }
    }
    dot + "}\n"
}

fn main() {
    if Path::new(DOT_FILES_OUTPUT_PATH).exists() {
        remove_dir_all(DOT_FILES_OUTPUT_PATH).expect("Couldn't hard remove graph output dir");
    }
    create_dir(DOT_FILES_OUTPUT_PATH).expect("Couldn't create graph output dir");

    for entry in fs::read_dir(PATH_TO_DIALOGUES).expect("Can't read entries in current dir") {
        let (contents, npc_file_name) = match try_read_yarn_contents(entry) {
            Some(r) => r,
            None => continue,
        };

        // A file of chart nodes is drawn as the story chart instead.
        if !chart_titles(&contents).is_empty() {
            let path = &format!("{}/{}.dot", DOT_FILES_OUTPUT_PATH, npc_file_name);
            fs::write(path, chart_dot(&contents))
                .unwrap_or_else(|_| panic!("Couldn't write to file: '{}'", path));
            continue;
        }

        let path = &format!("{}/{}.dot", DOT_FILES_OUTPUT_PATH, npc_file_name);
        let mut file = match File::create(path) {
            Ok(r) => r,
            Err(err) => panic!("Can't create/open file: '{}', {}", path, err),
        };

        let graph = construct_graph(contents);
        file.write_all(Dot::new(&graph).to_string().as_bytes())
            .unwrap_or_else(|_| panic!("Couldn't write to file: '{}'", path));
        parse_labels_dot_file(path);
        write_meta_data(path, graph);
    }
}
