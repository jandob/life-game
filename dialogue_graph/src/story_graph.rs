//! Draws the story graph (`graph` nodes, see `assets/dialogue/graph_route1.yarn`): one
//! Graphviz file for the story level and one for the inside of each box.

use std::collections::HashSet;

use crate::{parse_command, quote};

const BLUE: &str = "#3b5b8c";
const BLUE_FILL: &str = "#eef3fb";
const YELLOW: &str = "#b58a2a";
const YELLOW_FILL: &str = "#fff6e0";
const GREEN: &str = "#2e7d4f";
const GREEN_FILL: &str = "#e6f4ea";
const RED: &str = "#c0392b";
const RED_FILL: &str = "#fdeceb";
const GREY: &str = "#999999";
const CLUE_BLUE: &str = "#1f6fb2";

#[derive(Clone, Copy, PartialEq)]
pub enum BoxKind {
    Chapter,
    Hub,
    Side,
    Retry,
    Stub,
}

#[derive(Clone, Copy, PartialEq)]
pub enum NodeKind {
    Gate,
    Item,
    Clue,
    Choice,
    Exit,
}

pub struct GraphNode {
    pub kind: NodeKind,
    pub id: String,
    pub label: String,
    pub detail: Option<String>,
    /// All of these are needed; each is a list of alternatives, any one of which will do.
    pub requires: Vec<Vec<String>>,
    pub to: Option<String>,
}

pub struct GraphBox {
    pub id: String,
    pub label: String,
    pub kind: BoxKind,
    pub goal: Option<String>,
    pub nodes: Vec<GraphNode>,
    /// (choice, option id, option label)
    pub options: Vec<(String, String, String)>,
}

/// The steps that scenes mark with `<<done BOX ID>>`, as (box, step id).
pub type Done = HashSet<(String, String)>;

/// The `<<done BOX ID>>` marks of a scene file.
pub fn done_marks(contents: &str) -> Done {
    contents
        .lines()
        .map(str::trim)
        .filter_map(parse_command)
        .filter(|(command, args)| command == "done" && args.len() == 2)
        .map(|(_, mut args)| (args.remove(0), args.remove(0)))
        .collect()
}

/// How much of a box a scene performs.
#[derive(Clone, Copy, PartialEq)]
enum Progress {
    Written,
    Partly,
    Planned,
}

/// A step of a box is written once a scene marks it. A choice is written when all its
/// options are.
fn step_written(b: &GraphBox, node: &GraphNode, done: &Done) -> bool {
    let marked = |id: &str| done.contains(&(b.id.clone(), id.to_string()));
    let has_options = b.options.iter().any(|(choice, _, _)| *choice == node.id);
    if node.kind == NodeKind::Choice && has_options {
        return b
            .options
            .iter()
            .filter(|(choice, _, _)| *choice == node.id)
            .all(|(_, option, _)| marked(option));
    }
    marked(&node.id)
}

/// (steps written, steps) of a box. The entry needs nothing.
fn steps_written(b: &GraphBox, done: &Done) -> (usize, usize) {
    let written = b.nodes.iter().filter(|n| step_written(b, n, done)).count();
    (written, b.nodes.len())
}

fn progress(b: &GraphBox, done: &Done) -> Progress {
    match steps_written(b, done) {
        (written, steps) if steps > 0 && written == steps => Progress::Written,
        (0, _) => Progress::Planned,
        _ => Progress::Partly,
    }
}

/// Escapes text for a Graphviz HTML-like label.
fn html(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

/// The boxes of the nodes tagged `graph`, in file order. Everything up to the next `<<box>>`
/// belongs to a box.
pub fn graph_boxes(contents: &str) -> Vec<GraphBox> {
    let mut boxes: Vec<GraphBox> = Vec::new();
    let mut tagged = false;
    let mut in_body = false;
    for line in contents.lines().map(str::trim) {
        if in_body {
            if line == "===" {
                in_body = false;
                tagged = false;
                continue;
            }
            if tagged {
                add_line(&mut boxes, line);
            }
        } else if let Some(tags) = line.strip_prefix("tags:") {
            tagged = tags.split_whitespace().any(|t| t == "graph");
        } else if line == "---" {
            in_body = true;
        }
    }
    boxes
}

fn add_line(boxes: &mut Vec<GraphBox>, line: &str) {
    let Some((command, mut args)) = parse_command(line) else {
        return;
    };
    if args.len() < 2 {
        return;
    }
    let id = args.remove(0);
    let label = args.remove(0);
    let value = |args: &[String], key: &str| {
        args.iter()
            .find_map(|a| a.strip_prefix(&format!("{key}=")))
            .map(str::to_string)
    };
    if command == "box" {
        let kind = match value(&args, "kind").as_deref() {
            Some("hub") => BoxKind::Hub,
            Some("side") => BoxKind::Side,
            Some("retry") => BoxKind::Retry,
            Some("stub") => BoxKind::Stub,
            _ => BoxKind::Chapter,
        };
        boxes.push(GraphBox {
            id,
            label,
            kind,
            goal: value(&args, "goal"),
            nodes: Vec::new(),
            options: Vec::new(),
        });
        return;
    }
    let Some(current) = boxes.last_mut() else {
        return;
    };
    let kind = match command.as_str() {
        "gate" => NodeKind::Gate,
        "item" => NodeKind::Item,
        "clue" => NodeKind::Clue,
        "choice" => NodeKind::Choice,
        "exit" => NodeKind::Exit,
        "option" => {
            // `<<option CHOICE ID "LABEL">>`: the first two words were read as id and label.
            let (option, label) = (label, args.remove(0));
            current.options.push((id, option, label));
            return;
        }
        _ => return,
    };
    let detail = value(&args, "detail");
    let to = value(&args, "to");
    let requires = args
        .iter()
        .filter(|a| !a.starts_with("to=") && !a.starts_with("detail="))
        .map(|a| a.split('|').map(str::to_string).collect())
        .collect();
    current.nodes.push(GraphNode {
        kind,
        id,
        label,
        detail,
        requires,
        to,
    });
}

fn find<'a>(boxes: &'a [GraphBox], id: &str) -> Option<&'a GraphBox> {
    boxes.iter().find(|b| b.id == id)
}

/// A cross-box requirement `BOX.clue`.
fn cross_box(requirement: &str) -> Option<(&str, &str)> {
    requirement.split_once('.')
}

/// Boxes that are drawn on their own: a stub, or a box without nodes, has nothing to show.
pub fn has_content(b: &GraphBox) -> bool {
    b.kind != BoxKind::Stub && !b.nodes.is_empty()
}

fn story_node(b: &GraphBox, done: &Done) -> String {
    let progress = progress(b, done);
    let dashed = if progress == Progress::Planned {
        ",dashed"
    } else {
        ""
    };
    let (shape, style, fill, color) = match b.kind {
        BoxKind::Hub => ("hexagon", "filled", YELLOW_FILL, YELLOW),
        BoxKind::Side => ("box", "filled", "#fbfbfb", GREY),
        BoxKind::Retry => ("box", "rounded,filled", RED_FILL, RED),
        _ if progress == Progress::Written => ("box", "rounded,filled", BLUE_FILL, BLUE),
        _ if progress == Progress::Partly => ("box", "rounded,filled", "#f4f4f4", BLUE),
        _ => ("box", "rounded,filled", "#f4f4f4", "#777777"),
    };
    let mut lines = String::new();
    if let Some(goal) = &b.goal {
        lines += &format!(
            "<br/><font point-size=\"10\">Goal: {}</font>",
            html(&lowercase_first(goal))
        );
    }
    let (written, steps) = steps_written(b, done);
    if progress != Progress::Written && b.kind != BoxKind::Stub && steps > 0 {
        lines += &format!("<br/><font point-size=\"10\">{written} of {steps} steps written</font>");
    }
    format!(
        "    {} [label=<<b>{}</b>{lines}>, shape={shape}, style=\"{style}{dashed}\", fillcolor=\"{fill}\", color=\"{color}\"];\n",
        quote(&b.id),
        html(&b.label)
    )
}

/// The goals are written as sentences; after "Goal: " they read better in lowercase.
fn lowercase_first(text: &str) -> String {
    let mut chars = text.chars();
    match (chars.next(), chars.next()) {
        (Some(c), second) if c.is_uppercase() && second.is_none_or(|s| !s.is_uppercase()) => {
            c.to_lowercase().chain(text.chars().skip(1)).collect()
        }
        _ => text.to_string(),
    }
}

/// `route1` is drawn as "Route 1".
fn route_title(route: &str) -> String {
    match route.strip_prefix("route") {
        Some(number) => format!("Route {number}"),
        None => route.to_string(),
    }
}

/// The story level: a node per box, an edge per exit and the clues carried between boxes.
pub fn story_dot(boxes: &[GraphBox], route: &str, done: &Done) -> String {
    let mut dot = format!(
        "digraph {} {{\n  graph [rankdir=TB, fontname=\"Inter\", fontsize=13, nodesep=0.5, ranksep=0.42, bgcolor=\"white\", pad=0.4, labelloc=t,\n         label=<<b>{}, story level</b><br/><font point-size=\"11\">Each box is one puzzle stretch with a goal. Solid: written. Dashed: not written yet. 'N of M steps' counts steps a scene marks with &lt;&lt;done&gt;&gt;.<br/><font color=\"{RED}\">Red: a wrong move ends the box early, and a short retry follows.</font> <font color=\"{CLUE_BLUE}\">Blue dotted: a clue used in a later box.</font></font>>];\n",
        quote(route),
        html(&route_title(route))
    );
    dot += "  node [fontname=\"Inter\", fontsize=12, penwidth=1.4, margin=\"0.18,0.08\"];\n  edge [fontname=\"Inter\", fontsize=10, color=\"#555555\"];\n\n";
    for b in boxes {
        dot += &story_node(b, done);
    }
    dot.push('\n');

    for b in boxes {
        for node in b.nodes.iter().filter(|n| n.kind == NodeKind::Exit) {
            let Some(target) = node.to.as_deref().and_then(|t| find(boxes, t)) else {
                continue;
            };
            let from = quote(&b.id);
            let to = quote(&target.id);
            let hub_side = matches!(
                (b.kind, target.kind),
                (BoxKind::Hub, BoxKind::Side) | (BoxKind::Side, BoxKind::Hub)
            );
            if hub_side {
                // Side puzzles hang off their hub: the way back is not a step forward.
                let rank = if b.kind == BoxKind::Side {
                    ", constraint=false"
                } else {
                    ""
                };
                dot += &format!("  {from} -> {to} [style=dashed, color=\"{GREY}\"{rank}];\n");
            } else if b.kind == BoxKind::Retry || target.kind == BoxKind::Retry {
                dot += &format!(
                    "  {from} -> {to} [label={}, color=\"{RED}\", fontcolor=\"{RED}\", penwidth=1.6];\n",
                    quote(&format!(" {}", node.label))
                );
            } else {
                dot += &format!(
                    "  {from} -> {to} [label={}];\n",
                    quote(&format!(" {}", node.label))
                );
            }
        }
    }

    // The clues a box uses from earlier boxes: one edge per pair of boxes.
    let mut pairs: Vec<((&str, &str), Vec<String>)> = Vec::new();
    for b in boxes {
        for requirement in b.nodes.iter().flat_map(|n| n.requires.iter().flatten()) {
            let Some((source, clue)) = cross_box(requirement) else {
                continue;
            };
            let label = clue_label(boxes, source, clue);
            let pair = (source, b.id.as_str());
            match pairs.iter_mut().find(|(p, _)| *p == pair) {
                Some((_, labels)) if labels.contains(&label) => {}
                Some((_, labels)) => labels.push(label),
                None => pairs.push((pair, vec![label])),
            }
        }
    }
    for ((source, target), labels) in pairs {
        let label = labels
            .iter()
            .map(|l| format!("&nbsp;{}", html(l)))
            .collect::<Vec<_>>()
            .join("<br/>");
        dot += &format!(
            "  {} -> {} [label=<{label}>, style=dotted, color=\"{CLUE_BLUE}\", fontcolor=\"{CLUE_BLUE}\", penwidth=1.4, constraint=false, arrowhead=vee];\n",
            quote(source),
            quote(target)
        );
    }
    dot + "}\n"
}

fn clue_label(boxes: &[GraphBox], source: &str, clue: &str) -> String {
    find(boxes, source)
        .and_then(|s| {
            s.nodes
                .iter()
                .find(|n| n.kind == NodeKind::Clue && n.id == clue)
        })
        .map_or_else(|| clue.to_string(), |n| n.label.clone())
}

fn box_node_id(id: &str) -> String {
    quote(&format!("n_{id}"))
}

fn option_node_id(choice: &str, option: &str) -> String {
    quote(&format!("o_{choice}_{option}"))
}

/// The inside of one box: what the player does, gets and learns, and the way out.
pub fn box_dot(boxes: &[GraphBox], b: &GraphBox, done: &Done) -> String {
    let goal = match &b.goal {
        Some(goal) => format!("<br/><font point-size=\"10\">{}</font>", html(goal)),
        None => String::new(),
    };
    let mut dot = format!(
        "digraph {} {{\n  graph [rankdir=TB, fontname=\"Inter\", fontsize=13, nodesep=0.35, ranksep=0.45, bgcolor=\"white\", pad=0.4, labelloc=t,\n         label=<<b>Inside one box: {}</b><br/><font point-size=\"11\">Arrows mean \"needs\". Dashed arrows: any one of them will do. Puzzles in blue, items in yellow,<br/>clues in grey, clues from earlier boxes in grey notes. Exits in green; red leads to a retry or back round.<br/>Solid outline: a scene performs the step. Dashed outline: not written yet.</font>>];\n",
        quote(&b.id),
        html(&b.label)
    );
    dot += "  node [fontname=\"Inter\", fontsize=11, margin=\"0.16,0.07\"];\n  edge [fontname=\"Inter\", fontsize=10, color=\"#555555\"];\n\n";
    dot += &format!(
        "  \"entry\" [label=<<b>{}</b>{goal}>, shape=box, style=\"filled\", fillcolor=\"{BLUE}\", color=\"{BLUE}\", fontcolor=\"white\"];\n",
        html(&b.label)
    );

    let mut notes: Vec<(String, String)> = Vec::new();
    for node in &b.nodes {
        dot += &node_line(boxes, b, node, done);
        for (choice, option, label) in &b.options {
            if *choice == node.id {
                dot += &format!(
                    "  {} [label={}, shape=ellipse, style=\"filled{}\", fillcolor=white, color=\"{BLUE}\", fontsize=10];\n  {} -> {};\n",
                    option_node_id(choice, option),
                    quote(label),
                    dashed(done.contains(&(b.id.clone(), option.clone()))),
                    box_node_id(&node.id),
                    option_node_id(choice, option)
                );
            }
        }
    }
    dot.push('\n');

    for node in &b.nodes {
        let red = is_loop_exit(boxes, b, node);
        if node.requires.is_empty() {
            dot += &format!("  \"entry\" -> {};\n", box_node_id(&node.id));
        }
        for alternatives in &node.requires {
            let dashed = alternatives.len() > 1;
            for alternative in alternatives {
                if let Some((source, clue)) = cross_box(alternative) {
                    let note = format!("x_{source}_{clue}");
                    if !notes.iter().any(|(id, _)| *id == note) {
                        notes.push((note.clone(), clue_note(boxes, source, clue)));
                    }
                    dot += &format!(
                        "  {} -> {} [style=dashed, color=\"{GREY}\"];\n",
                        quote(&note),
                        box_node_id(&node.id)
                    );
                    continue;
                }
                let from = match alternative.split_once('=') {
                    Some((choice, option)) => option_node_id(choice, option),
                    None => box_node_id(alternative),
                };
                let mut attrs = Vec::new();
                if dashed {
                    attrs.push("style=dashed".to_string());
                }
                if red {
                    attrs.push(format!("color=\"{RED}\", penwidth=1.6"));
                }
                let attrs = if attrs.is_empty() {
                    String::new()
                } else {
                    format!(" [{}]", attrs.join(", "))
                };
                dot += &format!("  {from} -> {}{attrs};\n", box_node_id(&node.id));
            }
        }
    }
    for (id, label) in notes {
        dot += &format!(
            "  {} [label={}, shape=note, style=filled, fillcolor=\"#f0f0f0\", color=\"{GREY}\", fontcolor=\"#333333\"];\n",
            quote(&id),
            quote(&label)
        );
    }
    dot + "}\n"
}

fn clue_note(boxes: &[GraphBox], source: &str, clue: &str) -> String {
    let from = find(boxes, source).map_or(source, |s| s.label.as_str());
    format!("From {from}:\\n{}", clue_label(boxes, source, clue))
}

/// An exit that leads to a retry box, or round again into its own box.
fn is_loop_exit(boxes: &[GraphBox], b: &GraphBox, node: &GraphNode) -> bool {
    node.kind == NodeKind::Exit
        && node.to.as_deref().is_some_and(|to| {
            to == b.id || find(boxes, to).is_some_and(|t| t.kind == BoxKind::Retry)
        })
}

/// A step that no scene performs yet has a dashed outline.
fn dashed(written: bool) -> &'static str {
    if written {
        ""
    } else {
        ",dashed"
    }
}

fn node_line(boxes: &[GraphBox], b: &GraphBox, node: &GraphNode, done: &Done) -> String {
    let dashed = dashed(step_written(b, node, done));
    let label = html(&node.label);
    let detail = match &node.detail {
        Some(detail) => format!("<br/><font point-size=\"9\">{}</font>", html(detail)),
        None => String::new(),
    };
    let attrs = match node.kind {
        NodeKind::Gate => format!(
            "label=<<b>{label}</b>{detail}>, shape=box, style=\"rounded,filled{dashed}\", fillcolor=\"{BLUE_FILL}\", color=\"{BLUE}\""
        ),
        NodeKind::Item => format!(
            "label=<{label}>, shape=box, style=\"filled{dashed}\", fillcolor=\"{YELLOW_FILL}\", color=\"{YELLOW}\""
        ),
        NodeKind::Clue => format!(
            "label=<{label}>, shape=note, style=\"filled{dashed}\", fillcolor=\"#f0f0f0\", color=\"{GREY}\", fontcolor=\"#333333\""
        ),
        NodeKind::Choice => format!(
            "label=<<b>{label}</b>{detail}>, shape=diamond, style=\"filled{dashed}\", fillcolor=\"{BLUE_FILL}\", color=\"{BLUE}\""
        ),
        NodeKind::Exit => {
            let target = node
                .to
                .as_deref()
                .and_then(|t| find(boxes, t))
                .map_or("?", |t| t.label.as_str());
            let (fill, color) = if is_loop_exit(boxes, b, node) {
                (RED_FILL, RED)
            } else {
                (GREEN_FILL, GREEN)
            };
            format!(
                "label=<<b>{label}</b><br/><font point-size=\"9\">to {}</font>>, shape=box, style=\"rounded,filled,bold{dashed}\", fillcolor=\"{fill}\", color=\"{color}\"",
                html(target)
            )
        }
    };
    format!("  {} [{attrs}];\n", box_node_id(&node.id))
}
