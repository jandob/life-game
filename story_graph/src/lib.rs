//! The story graph (`graph` nodes of `assets/dialogue/graph_*.yarn`, see
//! `openspec/changes/story-graph`): boxes of steps that scenes mark with `<<done BOX ID>>`.
//!
//! This crate only parses the graph and evaluates its rules. It does not depend on Bevy
//! or Yarn, so the game (which plays by the graph) and `dialogue_graph` (which draws it)
//! share one parser, and it builds for wasm.
//!
//! A step is done when a scene says so; the game keeps that in the Yarn variable
//! [`step_variable`]. The rules are asked through callbacks that tell whether a step is
//! done, so the same code serves the game, the walker and the tests.

/// The Yarn variable that names the current box.
pub const BOX_VARIABLE: &str = "$box";

/// Prefix of the Yarn variables of steps: `$step_<box>_<id>`, lower case.
pub const STEP_PREFIX: &str = "$step_";

/// The Yarn variable that is true once step `id` of `box_id` is done.
pub fn step_variable(box_id: &str, id: &str) -> String {
    format!(
        "{STEP_PREFIX}{}_{}",
        box_id.to_lowercase(),
        id.to_lowercase()
    )
}

/// The prefix of every step variable of `box_id`.
pub fn box_step_prefix(box_id: &str) -> String {
    format!("{STEP_PREFIX}{}_", box_id.to_lowercase())
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum BoxKind {
    Chapter,
    Hub,
    Side,
    Retry,
    Stub,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum NodeKind {
    Gate,
    Item,
    Clue,
    Choice,
    Exit,
}

#[derive(Clone, Debug)]
pub struct GraphNode {
    pub kind: NodeKind,
    pub id: String,
    pub label: String,
    pub detail: Option<String>,
    /// All of these are needed; each is a list of alternatives, any one of which will do.
    pub requires: Vec<Vec<String>>,
    pub to: Option<String>,
}

#[derive(Clone, Debug)]
pub struct GraphBox {
    pub id: String,
    pub label: String,
    pub kind: BoxKind,
    pub goal: Option<String>,
    /// The Yarn node that enters the box. Boxes without a scene have none.
    pub entry: Option<String>,
    pub parent: Option<String>,
    pub nodes: Vec<GraphNode>,
    /// (choice, option id, option label)
    pub options: Vec<(String, String, String)>,
}

/// Command name and arguments of a `<<name arg "quoted arg">>` line. Like Yarn, a quoted
/// argument may contain spaces and loses its quotes.
pub fn parse_command(line: &str) -> Option<(String, Vec<String>)> {
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

/// The boxes of the nodes tagged `graph`, in file order. Everything up to the next
/// `<<box>>` belongs to a box.
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
            entry: value(&args, "entry"),
            parent: value(&args, "parent"),
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

/// A cross-box requirement `BOX.clue`: a hint, the player remembers it.
pub fn cross_box(requirement: &str) -> Option<(&str, &str)> {
    requirement.split_once('.')
}

impl GraphBox {
    pub fn node(&self, id: &str) -> Option<&GraphNode> {
        self.nodes.iter().find(|n| n.id == id)
    }

    /// The choice that option `id` belongs to.
    pub fn choice_of(&self, option: &str) -> Option<&str> {
        self.options
            .iter()
            .find(|(_, o, _)| o == option)
            .map(|(choice, _, _)| choice.as_str())
    }

    /// The option ids of `choice`.
    pub fn options_of<'a>(&'a self, choice: &'a str) -> impl Iterator<Item = &'a str> {
        self.options
            .iter()
            .filter(move |(c, _, _)| c == choice)
            .map(|(_, o, _)| o.as_str())
    }

    /// Whether `id` names a step of the box: a node or an option.
    pub fn has_step(&self, id: &str) -> bool {
        self.node(id).is_some() || self.choice_of(id).is_some()
    }

    /// Whether `id` is an exit of the box.
    pub fn is_exit(&self, id: &str) -> bool {
        self.node(id).is_some_and(|n| n.kind == NodeKind::Exit)
    }

    /// Whether step `id` is done. A choice is done once one of its options is.
    pub fn is_done(&self, id: &str, step_done: &dyn Fn(&str) -> bool) -> bool {
        let mut options = self.options_of(id).peekable();
        if options.peek().is_some() {
            options.any(step_done)
        } else {
            step_done(id)
        }
    }

    /// Whether the requirements of step `id` hold inside the box. An option takes its
    /// choice's. A requirement is a node id (done), `a|b` (any one), `choice=option`
    /// (that option is done) or `BOX.clue`, which is a hint and always holds. An unknown
    /// step has no requirements.
    pub fn requirements_hold(&self, id: &str, step_done: &dyn Fn(&str) -> bool) -> bool {
        let id = self.choice_of(id).unwrap_or(id);
        let Some(node) = self.node(id) else {
            return true;
        };
        node.requires.iter().all(|alternatives| {
            alternatives.iter().any(|requirement| {
                if cross_box(requirement).is_some() {
                    true
                } else if let Some((_, option)) = requirement.split_once('=') {
                    step_done(option)
                } else {
                    self.is_done(requirement, step_done)
                }
            })
        })
    }

    /// Whether step `id` can be done now inside the box: it is not done, its requirements
    /// hold and, for an option, no option of its choice is done.
    pub fn can(&self, id: &str, step_done: &dyn Fn(&str) -> bool) -> bool {
        if !self.has_step(id) || self.is_done(id, step_done) {
            return false;
        }
        if let Some(choice) = self.choice_of(id) {
            if self.is_done(choice, step_done) {
                return false;
            }
        }
        self.requirements_hold(id, step_done)
    }
}

/// The boxes of a story graph file.
#[derive(Clone, Debug, Default)]
pub struct StoryGraph {
    pub boxes: Vec<GraphBox>,
}

impl StoryGraph {
    /// The graph of the `graph` nodes in `contents`.
    pub fn parse(contents: &str) -> Self {
        Self {
            boxes: graph_boxes(contents),
        }
    }

    pub fn find(&self, id: &str) -> Option<&GraphBox> {
        self.boxes.iter().find(|b| b.id == id)
    }

    /// `can("BOX", "ID")` of the scenes: `box_id` is the current box (`current`), the step
    /// is not done and its requirements hold. `is_done(box, step)` tells which steps are
    /// done.
    pub fn can(
        &self,
        current: &str,
        box_id: &str,
        id: &str,
        is_done: &dyn Fn(&str, &str) -> bool,
    ) -> bool {
        current == box_id
            && self
                .find(box_id)
                .is_some_and(|b| b.can(id, &|step| is_done(box_id, step)))
    }

    /// `is_done("BOX", "ID")` of the scenes: a choice is done once one of its options is.
    pub fn is_done(&self, box_id: &str, id: &str, raw: &dyn Fn(&str, &str) -> bool) -> bool {
        match self.find(box_id) {
            Some(b) => b.is_done(id, &|step| raw(box_id, step)),
            None => raw(box_id, id),
        }
    }

    /// The entry node of the box that exit `id` of `box_id` leads to, if it has a scene.
    pub fn exit_entry(&self, box_id: &str, id: &str) -> Option<&str> {
        let node = self.find(box_id)?.node(id)?;
        if node.kind != NodeKind::Exit {
            return None;
        }
        self.find(node.to.as_deref()?)?.entry.as_deref()
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use super::*;

    const GRAPH: &str = "title: GraphA\ntags: graph\n---\n<<box A \"First\" entry=AStart parent=P>>\n<<gate knock \"Knock\">>\n<<clue wine \"She drinks\" knock>>\n<<gate fetch \"Fetch\" knock Z.hint|A.wine>>\n<<choice still \"At her door\" fetch>>\n<<option still wait \"Stand still\">>\n<<option still reach \"Reach\">>\n<<gate night \"Night\" still=wait>>\n<<gate any \"Any\" knock|fetch>>\n<<exit on \"Go on\" night to=B>>\n<<exit no \"Closed\" still=reach to=C>>\n===\ntitle: GraphB\ntags: graph\n---\n<<box B \"Second\" entry=BStart>>\n<<gate door \"Door\">>\n<<exit end \"End\" door to=C>>\n===\ntitle: Other\n---\n<<gate x \"not a graph node\">>\n===\ntitle: GraphC\ntags: graph\n---\n<<box C \"Later\" kind=stub>>\n===\n";

    fn done<'a>(steps: &'a [&'a str]) -> impl Fn(&str) -> bool + 'a {
        let set: HashSet<&str> = steps.iter().copied().collect();
        move |id| set.contains(id)
    }

    #[test]
    fn parses_boxes_with_entry_and_parent() {
        let graph = StoryGraph::parse(GRAPH);
        assert_eq!(graph.boxes.len(), 3);
        let a = graph.find("A").unwrap();
        assert_eq!(a.entry.as_deref(), Some("AStart"));
        assert_eq!(a.parent.as_deref(), Some("P"));
        assert_eq!(a.nodes.len(), 8);
        assert_eq!(a.options.len(), 2);
        assert_eq!(graph.find("C").unwrap().entry, None);
        assert_eq!(graph.find("C").unwrap().kind, BoxKind::Stub);
        assert_eq!(a.node("fetch").unwrap().requires[1], ["Z.hint", "A.wine"]);
        assert_eq!(a.node("on").unwrap().to.as_deref(), Some("B"));
    }

    #[test]
    fn step_variables_are_lower_case() {
        assert_eq!(step_variable("R1Dinner2", "Wait"), "$step_r1dinner2_wait");
        assert!(step_variable("R1Dinner2Retry", "text").starts_with("$step_r1dinner2retry_"));
        assert!(!step_variable("R1Dinner2Retry", "text").starts_with(&box_step_prefix("R1Dinner2")));
    }

    #[test]
    fn requirements_all_any_option_and_clue() {
        let a = &StoryGraph::parse(GRAPH).boxes[0];
        // No requirement: follows the entry.
        assert!(a.requirements_hold("knock", &done(&[])));
        // All of: knock. The clue Z.hint is a hint, so alternatives with it hold.
        assert!(!a.requirements_hold("fetch", &done(&[])));
        assert!(a.requirements_hold("fetch", &done(&["knock"])));
        // Any of.
        assert!(!a.requirements_hold("any", &done(&[])));
        assert!(a.requirements_hold("any", &done(&["fetch"])));
        // choice=option.
        assert!(!a.requirements_hold("night", &done(&["reach"])));
        assert!(a.requirements_hold("night", &done(&["wait"])));
        // An option takes the requirements of its choice.
        assert!(!a.requirements_hold("wait", &done(&["knock"])));
        assert!(a.requirements_hold("wait", &done(&["fetch"])));
        // A choice is done once one of its options is.
        assert!(a.requirements_hold("on", &done(&["night"])));
        assert!(a.is_done("still", &done(&["reach"])));
        assert!(!a.is_done("still", &done(&["fetch"])));
    }

    #[test]
    fn can_needs_the_box_the_step_open_and_one_option_per_choice() {
        let graph = StoryGraph::parse(GRAPH);
        let marks = |steps: &'static [&'static str]| {
            move |box_id: &str, step: &str| box_id == "A" && steps.contains(&step)
        };
        assert!(graph.can("A", "A", "knock", &marks(&[])));
        assert!(!graph.can("B", "A", "knock", &marks(&[])), "another box");
        assert!(!graph.can("A", "A", "knock", &marks(&["knock"])), "done");
        assert!(!graph.can("A", "A", "fetch", &marks(&[])));
        assert!(graph.can("A", "A", "fetch", &marks(&["knock"])));
        assert!(!graph.can("A", "A", "nothing", &marks(&[])), "unknown step");
        // The options of a choice: not once one is done, nor the choice itself.
        assert!(graph.can("A", "A", "wait", &marks(&["knock", "fetch"])));
        assert!(graph.can("A", "A", "still", &marks(&["knock", "fetch"])));
        assert!(!graph.can("A", "A", "wait", &marks(&["knock", "fetch", "reach"])));
        assert!(!graph.can("A", "A", "reach", &marks(&["knock", "fetch", "wait"])));
        assert!(!graph.can("A", "A", "still", &marks(&["knock", "fetch", "wait"])));
        // An exit is a step too.
        assert!(!graph.can("A", "A", "no", &marks(&["knock", "fetch", "wait"])));
        assert!(graph.can("A", "A", "no", &marks(&["knock", "fetch", "reach"])));
        assert!(graph.is_done("A", "still", &marks(&["wait"])));
    }

    #[test]
    fn exits_name_the_entry_of_the_box_they_lead_to() {
        let graph = StoryGraph::parse(GRAPH);
        assert_eq!(graph.exit_entry("A", "on"), Some("BStart"));
        // C has no scene, a gate is no exit.
        assert_eq!(graph.exit_entry("B", "end"), None);
        assert_eq!(graph.exit_entry("A", "knock"), None);
    }
}
