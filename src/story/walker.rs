//! The walker: plays the story the way a player could, to check it and to find the way
//! to a start point.
//!
//! The story is the graph (`graph.rs`, `assets/dialogue/graph_route1.yarn`): boxes of
//! steps. The walker plays one box from its entry node and tries every action, until an
//! exit of the box is done. It runs on a bare `Dialogue` without Bevy systems, so it also
//! works on wasm, with the graph's functions and the commands `done` and `enter_box` played
//! on its own storage.
//!
//! An action is one available option of a hotspot node's popup (or the whole node, when it
//! opens with a line), or reading a pending text. A `<<next_scene>>` plays after the node
//! that queued it (so does the entry node of the box an exit leads to), and any other
//! choice inside a run branches the search. World commands are only collected, for start
//! points to replay. A state is the story variables plus the phone's pending texts and
//! notes.
//!
//! The box checks (tests below) walk every box with an entry node: every way of playing
//! reaches an exit, and every step an exit needs can be done. Start points inside a box
//! replay the walker's shortest path to their steps (`start_point.rs`).

use std::collections::hash_map::DefaultHasher;
use std::collections::{BTreeMap, HashMap, HashSet, VecDeque};
use std::hash::{Hash, Hasher};
use std::sync::{Arc, Mutex};

use bevy::prelude::*;
use bevy_yarnspinner::default_impl::{MemoryVariableStorage, StringTableTextProvider};
use bevy_yarnspinner::prelude::*;
use story_graph::{StoryGraph, BOX_VARIABLE, STEP_PREFIX};
use yarnspinner::runtime::{Dialogue, DialogueEvent, OptionId, VariableStorageError};

use super::graph::{self, Graph};

/// Walks with more states than this fail, so a box that grows too wide gets noticed.
pub const STATE_CAP: usize = 50_000;

/// A command of a run that changes the world, as (name, parameters).
pub type WorldCommand = (String, Vec<String>);

/// Commands whose end state a start point replays.
const WORLD_COMMANDS: &[&str] = &[
    "walk",
    "place",
    "face",
    "show",
    "hide",
    "open_door",
    "close_door",
    "fade_out",
    "fade_in",
];

/// Yarn keeps visit counts in variables with this prefix. Story conditions don't read
/// `visited()`, so they are left out of the state.
const VISIT_PREFIX: &str = "$Yarn.Internal";

/// A note on the phone, as `phone::Note`.
#[derive(Clone, Debug, PartialEq)]
pub struct Note {
    pub id: String,
    pub text: String,
    pub done: bool,
}

/// What the walker knows about a point in the story.
#[derive(Clone, Debug, Default)]
pub struct State {
    /// Story variables that differ from their declared default.
    pub vars: BTreeMap<String, YarnValue>,
    /// Texts delivered and not read yet, oldest first.
    pub unread: Vec<String>,
    /// In the order they were added.
    pub notes: Vec<Note>,
    /// `<<end_demo>>` ran.
    pub ended: bool,
}

impl State {
    /// A state with these variables set, e.g. what an earlier box leaves behind.
    pub fn with_vars(vars: impl IntoIterator<Item = (String, YarnValue)>) -> Self {
        Self {
            vars: vars.into_iter().collect(),
            ..Self::default()
        }
    }

    /// The current box, empty before the first one is entered.
    pub fn box_id(&self) -> String {
        match self.vars.get(BOX_VARIABLE) {
            Some(YarnValue::String(current)) => current.clone(),
            _ => String::new(),
        }
    }

    /// Whether the step is done.
    pub fn step(&self, box_id: &str, id: &str) -> bool {
        matches!(
            self.vars.get(&story_graph::step_variable(box_id, id)),
            Some(YarnValue::Boolean(true))
        )
    }

    #[cfg(test)]
    pub fn has_open_note(&self) -> bool {
        self.notes.iter().any(|note| !note.done)
    }

    /// Equal for states that play the same. Only variables in `read` and the steps count: a
    /// variable that no condition reads can't change what happens.
    fn key(&self, read: &HashSet<String>) -> u64 {
        let mut hasher = DefaultHasher::new();
        for (name, value) in &self.vars {
            if read.contains(name) || name.starts_with(STEP_PREFIX) {
                name.hash(&mut hasher);
                value.to_string().hash(&mut hasher);
            }
        }
        self.unread.hash(&mut hasher);
        self.ended.hash(&mut hasher);
        for note in &self.notes {
            (&note.id, &note.text, note.done).hash(&mut hasher);
        }
        hasher.finish()
    }

    fn deliver(&mut self, node: String) {
        if !self.unread.contains(&node) {
            self.unread.push(node);
        }
    }

    fn note(&mut self, id: String, text: String) {
        match self.notes.iter_mut().find(|note| note.id == id) {
            Some(note) => {
                note.text = text;
                note.done = false;
            }
            None => self.notes.push(Note {
                id,
                text,
                done: false,
            }),
        }
    }

    fn note_done(&mut self, id: &str) {
        if let Some(note) = self.notes.iter_mut().find(|note| note.id == id) {
            note.done = true;
        }
    }
}

/// One player action: a hotspot node or a pending text, played with these choices.
#[derive(Clone, Debug)]
pub struct Step {
    pub node: String,
    /// Reading a text, which marks it read once it completes.
    pub read: bool,
    /// The option ids picked, in order: the popup first, then any choice inside the run.
    pub choices: Vec<usize>,
    /// For people: the node and the texts of the options picked.
    pub label: String,
}

/// How far a run got.
enum Run {
    Done(State, Vec<WorldCommand>),
    /// Waiting for a choice the run wasn't given: the available options as (id, text).
    Choose(Vec<(usize, String)>),
    /// A popup with no available action.
    Nothing,
}

/// The states a walk reached, and how.
pub struct Walk {
    pub states: Vec<State>,
    /// How each state was first reached: (previous state, action). None for the start.
    pub came_from: Vec<Option<(usize, Step)>>,
    /// The states each state leads to.
    pub edges: Vec<Vec<usize>>,
    /// States where the walk stopped, in the order they were found.
    pub exits: Vec<usize>,
}

impl Walk {
    /// The actions from the start to state `i`.
    pub fn path(&self, mut i: usize) -> Vec<Step> {
        let mut path = Vec::new();
        while let Some((from, step)) = &self.came_from[i] {
            path.push(step.clone());
            i = *from;
        }
        path.reverse();
        path
    }

    /// The path to state `i` as one line, for failure messages.
    pub fn describe(&self, i: usize) -> String {
        let labels: Vec<String> = self.path(i).into_iter().map(|s| s.label).collect();
        if labels.is_empty() {
            "(the start)".to_string()
        } else {
            labels.join(" -> ")
        }
    }
}

/// Variable storage that notes which variables a run reads and sets.
#[derive(Debug, Clone, Default)]
struct TrackedStorage {
    inner: MemoryVariableStorage,
    reads: Arc<Mutex<HashSet<String>>>,
    writes: Arc<Mutex<Vec<(String, YarnValue)>>>,
}

impl TrackedStorage {
    /// Loads `vars` and forgets what was read and set before.
    fn load(&mut self, vars: &BTreeMap<String, YarnValue>) -> Result<(), VariableStorageError> {
        self.inner.clear();
        if let Ok(mut reads) = self.reads.lock() {
            reads.clear();
        }
        if let Ok(mut writes) = self.writes.lock() {
            writes.clear();
        }
        self.inner.extend(vars.clone().into_iter().collect())
    }

    fn take_reads(&self) -> HashSet<String> {
        let reads = self.reads.lock().map(|mut r| std::mem::take(&mut *r));
        reads.unwrap_or_default()
    }

    fn take_writes(&self) -> Vec<(String, YarnValue)> {
        let writes = self.writes.lock().map(|mut w| std::mem::take(&mut *w));
        writes.unwrap_or_default()
    }
}

impl VariableStorage for TrackedStorage {
    fn clone_shallow(&self) -> Box<dyn VariableStorage> {
        Box::new(self.clone())
    }

    fn set(&mut self, name: String, value: YarnValue) -> Result<(), VariableStorageError> {
        if let Ok(mut writes) = self.writes.lock() {
            writes.push((name.clone(), value.clone()));
        }
        self.inner.set(name, value)
    }

    fn get(&self, name: &str) -> Result<YarnValue, VariableStorageError> {
        if let Ok(mut reads) = self.reads.lock() {
            reads.insert(name.to_string());
        }
        self.inner.get(name)
    }

    fn extend(
        &mut self,
        values: bevy::platform::collections::HashMap<String, YarnValue>,
    ) -> Result<(), VariableStorageError> {
        self.inner.extend(values)
    }

    fn variables(&self) -> bevy::platform::collections::HashMap<String, YarnValue> {
        self.inner.variables()
    }

    fn clear(&mut self) {
        self.inner.clear()
    }

    fn as_any(&self) -> &dyn std::any::Any {
        self
    }

    fn as_any_mut(&mut self) -> &mut dyn std::any::Any {
        self
    }
}

/// Yarn's opcode for reading a variable (`PUSH_VARIABLE`).
const PUSH_VARIABLE: i32 = 13;

/// A run's change to the phone or the story's end.
#[derive(Clone)]
enum Effect {
    Deliver(String),
    Note(String, String),
    NoteDone(String),
    End,
}

/// What a run does, as changes that apply to any state that reads the same.
#[derive(Clone)]
enum Outcome {
    Done {
        writes: Vec<(String, YarnValue)>,
        effects: Vec<Effect>,
        commands: Vec<WorldCommand>,
    },
    Choose(Vec<(usize, String)>),
    Nothing,
}

/// A run played before: the values it read, and what it did. A run reads only
/// variables, so it plays the same from every state with these values.
struct Memo {
    reads: Vec<(String, Option<YarnValue>)>,
    outcome: Outcome,
}

/// Plays the story on a bare `Dialogue`.
pub struct Walker {
    dialogue: Dialogue,
    /// Shared with the dialogue: loading a state writes into it.
    storage: TrackedStorage,
    defaults: HashMap<String, YarnValue>,
    /// The variables some condition or line reads, and the current box: they tell states
    /// apart.
    read: HashSet<String>,
    /// Runs played before, by (node, choices).
    memo: HashMap<(String, Vec<usize>), Vec<Memo>>,
    /// The nodes of the map's hotspots, each once.
    hotspots: Vec<String>,
    graph: Arc<StoryGraph>,
    world: World,
}

impl Walker {
    pub fn new(project: &YarnProject, hotspots: &[String], graph: &Graph) -> Result<Self, String> {
        let compilation = project.compilation();
        let program = compilation
            .program
            .clone()
            .ok_or("the Yarn project has no program")?;
        let defaults = program
            .initial_values
            .iter()
            .map(|(name, operand)| (name.clone(), YarnValue::from(operand.clone())))
            .collect();
        let mut text = StringTableTextProvider::new();
        text.extend_base_language(
            compilation
                .string_table
                .iter()
                .map(|(id, info)| (id.clone(), info.text.clone())),
        );
        let mut read: HashSet<String> = program
            .nodes
            .values()
            .flat_map(|node| &node.instructions)
            .filter(|i| i.opcode == PUSH_VARIABLE)
            .filter_map(|i| i.operands.first())
            .map(|operand| YarnValue::from(operand.clone()).to_string())
            .collect();
        read.insert(BOX_VARIABLE.to_string());
        let storage = TrackedStorage::default();
        let mut dialogue = Dialogue::new(Box::new(storage.clone()), Box::new(text));
        graph::add_functions(dialogue.library_mut(), &graph.0, &storage);
        dialogue.add_program(program);
        let mut unique = Vec::new();
        for node in hotspots {
            if !unique.contains(node) {
                unique.push(node.clone());
            }
        }
        Ok(Self {
            dialogue,
            storage,
            defaults,
            read,
            memo: HashMap::new(),
            hotspots: unique,
            graph: graph.0.clone(),
            world: World::new(),
        })
    }

    /// Plays `node` from `state` with the given choices, or looks up how it played
    /// before from a state that reads the same.
    fn run(&mut self, state: &State, node: &str, choices: &[usize]) -> Result<Run, String> {
        let key = (node.to_string(), choices.to_vec());
        let known = self.memo.get(&key).and_then(|memos| {
            memos.iter().find(|memo| {
                memo.reads
                    .iter()
                    .all(|(name, value)| state.vars.get(name) == value.as_ref())
            })
        });
        if let Some(memo) = known {
            let outcome = memo.outcome.clone();
            return Ok(self.apply(state, &outcome));
        }
        let outcome = self.play(state, node, choices)?;
        let reads = self
            .storage
            .take_reads()
            .into_iter()
            .map(|name| {
                let value = state.vars.get(&name).cloned();
                (name, value)
            })
            .collect();
        let run = self.apply(state, &outcome);
        self.memo
            .entry(key)
            .or_default()
            .push(Memo { reads, outcome });
        Ok(run)
    }

    /// `outcome` applied to `state`.
    fn apply(&self, state: &State, outcome: &Outcome) -> Run {
        let (writes, effects, commands) = match outcome {
            Outcome::Done {
                writes,
                effects,
                commands,
            } => (writes, effects, commands),
            Outcome::Choose(options) => return Run::Choose(options.clone()),
            Outcome::Nothing => return Run::Nothing,
        };
        let mut next = state.clone();
        for (name, value) in writes {
            if name.starts_with(VISIT_PREFIX) {
                continue;
            }
            // A step that is not done is missing, as in the game's storage.
            let not_done = name.starts_with(STEP_PREFIX) && *value == YarnValue::Boolean(false);
            if not_done || self.defaults.get(name) == Some(value) {
                next.vars.remove(name);
            } else {
                next.vars.insert(name.clone(), value.clone());
            }
        }
        for effect in effects {
            match effect {
                Effect::Deliver(node) => next.deliver(node.clone()),
                Effect::Note(id, text) => next.note(id.clone(), text.clone()),
                Effect::NoteDone(id) => next.note_done(id),
                Effect::End => next.ended = true,
            }
        }
        Run::Done(next, commands.clone())
    }

    /// Plays `node` from `state` with the given choices on the dialogue.
    fn play(&mut self, state: &State, node: &str, choices: &[usize]) -> Result<Outcome, String> {
        self.storage
            .load(&state.vars)
            .map_err(|err| err.to_string())?;
        let mut effects = Vec::new();
        let mut commands = Vec::new();
        let mut queued: Option<String> = None;
        let mut chosen = 0;
        let mut current = node.to_string();
        self.dialogue
            .set_node(&current)
            .map_err(|err| format!("cannot start '{current}': {err}"))?;
        for _ in 0..100_000 {
            let events = self
                .dialogue
                .continue_with_world(&mut self.world)
                .map_err(|err| format!("while playing '{current}': {err}"))?;
            let mut complete = false;
            for event in events {
                match event {
                    DialogueEvent::Options(options) => {
                        let available: Vec<(usize, String)> = options
                            .iter()
                            .filter(|o| o.is_available)
                            .map(|o| (o.id.0, o.line.text.clone()))
                            .collect();
                        if available.is_empty() {
                            self.dialogue.stop();
                            return if chosen == 0 && current == node {
                                Ok(Outcome::Nothing)
                            } else {
                                Err(format!("'{current}' offers no available option"))
                            };
                        }
                        let Some(&id) = choices.get(chosen) else {
                            self.dialogue.stop();
                            return Ok(Outcome::Choose(available));
                        };
                        chosen += 1;
                        self.dialogue
                            .set_selected_option(OptionId(id))
                            .map_err(|err| format!("while playing '{current}': {err}"))?;
                    }
                    DialogueEvent::Command(command) => {
                        let mut params = command.parameters.iter().map(|p| p.to_string());
                        let mut arg = || params.next().unwrap_or_default();
                        match command.name.as_str() {
                            "phone" => effects.push(Effect::Deliver(arg())),
                            "note" => {
                                let id = arg();
                                effects.push(Effect::Note(id, arg()));
                            }
                            "note_done" => effects.push(Effect::NoteDone(arg())),
                            "next_scene" => queued = Some(arg()),
                            "done" => {
                                let box_id = arg();
                                let id = arg();
                                let entry =
                                    graph::mark_done(&self.graph, &mut self.storage, &box_id, &id)?;
                                queued = entry.or(queued);
                            }
                            "enter_box" => {
                                graph::enter_box(&self.graph, &mut self.storage, &arg())?
                            }
                            "end_demo" => effects.push(Effect::End),
                            name if WORLD_COMMANDS.contains(&name) => {
                                let params = command.parameters.iter().map(|p| p.to_string());
                                commands.push((command.name.clone(), params.collect()));
                            }
                            _ => {}
                        }
                    }
                    DialogueEvent::DialogueComplete => complete = true,
                    _ => {}
                }
            }
            if !complete {
                continue;
            }
            match queued.take() {
                Some(scene) => {
                    current = scene;
                    self.dialogue
                        .set_node(&current)
                        .map_err(|err| format!("cannot start '{current}': {err}"))?;
                }
                None => {
                    return Ok(Outcome::Done {
                        writes: self.storage.take_writes(),
                        effects,
                        commands,
                    });
                }
            }
        }
        Err(format!("'{node}' does not finish"))
    }

    /// Every way to play `node` from `state` to its end.
    fn plays(
        &mut self,
        state: &State,
        node: &str,
        read: bool,
    ) -> Result<Vec<(Step, State, Vec<WorldCommand>)>, String> {
        let mut plays = Vec::new();
        let mut pending: Vec<(Vec<usize>, Vec<String>)> = vec![(Vec::new(), Vec::new())];
        while let Some((choices, labels)) = pending.pop() {
            match self.run(state, node, &choices)? {
                Run::Done(mut next, commands) => {
                    if read {
                        next.unread.retain(|text| text != node);
                    }
                    let label = match (read, labels.is_empty()) {
                        (true, _) => format!("read {node}"),
                        (false, true) => node.to_string(),
                        (false, false) => format!("{node}: {}", labels.join(" / ")),
                    };
                    let step = Step {
                        node: node.to_string(),
                        read,
                        choices,
                        label,
                    };
                    plays.push((step, next, commands));
                }
                Run::Choose(options) => {
                    for (id, text) in options.into_iter().rev() {
                        let mut choices = choices.clone();
                        choices.push(id);
                        let mut labels = labels.clone();
                        labels.push(text);
                        pending.push((choices, labels));
                    }
                }
                Run::Nothing => {}
            }
        }
        Ok(plays)
    }

    /// Every action the player can take in `state`, with where it leads. Actions that
    /// change nothing are left out.
    pub fn actions(&mut self, state: &State) -> Result<Vec<(Step, State)>, String> {
        let mut actions = Vec::new();
        let key = state.key(&self.read);
        let sources: Vec<(String, bool)> = (self.hotspots.iter().map(|n| (n.clone(), false)))
            .chain(state.unread.iter().map(|n| (n.clone(), true)))
            .collect();
        for (node, read) in sources {
            for (step, next, _) in self.plays(state, &node, read)? {
                if next.key(&self.read) != key {
                    actions.push((step, next));
                }
            }
        }
        Ok(actions)
    }

    /// Plays the entry node of `box_id` from `state` (what the story has set before it): the
    /// way into the box. Returns the step, the state and the world commands.
    pub fn enter(
        &mut self,
        state: &State,
        box_id: &str,
    ) -> Result<(Step, State, Vec<WorldCommand>), String> {
        let entry = self
            .graph
            .find(box_id)
            .and_then(|b| b.entry.clone())
            .ok_or_else(|| format!("box '{box_id}' has no entry node"))?;
        let mut plays = self.plays(state, &entry, false)?;
        if plays.len() != 1 {
            return Err(format!("{entry} must play one way"));
        }
        Ok(plays.remove(0))
    }

    #[cfg(test)]
    /// Breadth-first from `start` until no new state is left. States where `stop` is true
    /// are exits and are not played on from.
    pub fn walk(
        &mut self,
        start: State,
        stop: impl Fn(&State) -> bool,
        cap: usize,
    ) -> Result<Walk, String> {
        self.search(start, stop, cap, false)
    }

    fn search(
        &mut self,
        start: State,
        stop: impl Fn(&State) -> bool,
        cap: usize,
        first_exit: bool,
    ) -> Result<Walk, String> {
        let mut walk = Walk {
            states: Vec::new(),
            came_from: Vec::new(),
            edges: Vec::new(),
            exits: Vec::new(),
        };
        let mut index = HashMap::new();
        index.insert(start.key(&self.read), 0);
        walk.states.push(start);
        walk.came_from.push(None);
        walk.edges.push(Vec::new());
        let mut queue = VecDeque::from([0]);
        while let Some(i) = queue.pop_front() {
            if stop(&walk.states[i]) {
                walk.exits.push(i);
                if first_exit {
                    return Ok(walk);
                }
                continue;
            }
            let state = walk.states[i].clone();
            for (step, next) in self
                .actions(&state)
                .map_err(|err| format!("{err}, after {}", walk.describe(i)))?
            {
                let key = next.key(&self.read);
                let j = match index.get(&key) {
                    Some(&j) => j,
                    None => {
                        let j = walk.states.len();
                        if j >= cap {
                            return Err(format!("more than {cap} states"));
                        }
                        index.insert(key, j);
                        walk.states.push(next);
                        walk.came_from.push(Some((i, step)));
                        walk.edges.push(Vec::new());
                        queue.push_back(j);
                        j
                    }
                };
                if !walk.edges[i].contains(&j) {
                    walk.edges[i].push(j);
                }
            }
        }
        Ok(walk)
    }

    /// The shortest actions from the entry of `box_id` (played from `base`) to a state where
    /// every one of `steps` is done. The entry node is the first action.
    pub fn path_in_box(
        &mut self,
        base: &State,
        box_id: &str,
        steps: &[&str],
    ) -> Result<Vec<Step>, String> {
        let (first, state, _) = self.enter(base, box_id)?;
        let mut path = vec![first];
        let reached = |s: &State| steps.iter().all(|id| s.step(box_id, id));
        let walk = self.search(
            state,
            |s| reached(s) || s.ended || s.box_id() != box_id,
            STATE_CAP,
            true,
        )?;
        let Some(&exit) = walk.exits.first() else {
            return Err(format!("{box_id}: the steps {steps:?} can't be reached"));
        };
        if !reached(&walk.states[exit]) {
            return Err(format!(
                "{box_id}: the box ends before the steps {steps:?} are done"
            ));
        }
        path.extend(walk.path(exit));
        Ok(path)
    }

    /// Plays `path` from `state`. Returns the end state and the world commands of every
    /// step, in order.
    pub fn replay_from(
        &mut self,
        mut state: State,
        path: &[Step],
    ) -> Result<(State, Vec<WorldCommand>), String> {
        let mut commands = Vec::new();
        for step in path {
            match self.run(&state, &step.node, &step.choices)? {
                Run::Done(mut next, mut more) => {
                    if step.read {
                        next.unread.retain(|text| *text != step.node);
                    }
                    state = next;
                    commands.append(&mut more);
                }
                _ => return Err(format!("'{}' did not play to its end", step.label)),
            }
        }
        Ok((state, commands))
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use std::collections::HashSet;

    use story_graph::{GraphBox, NodeKind};

    use super::*;
    use crate::story::load_real_project;
    use crate::story::start_point::base_vars;

    /// The hotspot nodes of the side-view map.
    pub(crate) fn route1_hotspots() -> Vec<String> {
        let map: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string("assets/maps/side/route1.tmj").unwrap())
                .unwrap();
        let mut nodes = Vec::new();
        for layer in map["layers"].as_array().unwrap() {
            if layer["name"] != "Hotspots" {
                continue;
            }
            for object in layer["objects"].as_array().unwrap() {
                for property in object["properties"].as_array().unwrap() {
                    if property["name"] == "node" {
                        nodes.push(property["value"].as_str().unwrap().to_string());
                    }
                }
            }
        }
        nodes
    }

    fn walker() -> Walker {
        let app = load_real_project();
        let project = app.world().resource::<YarnProject>();
        Walker::new(project, &route1_hotspots(), &Graph::route1()).unwrap()
    }

    /// Steps whose requirements the scenes don't meet, with why: the step is done before
    /// something the graph needs for it. The graph is the design, the scenes are to follow
    /// (task 3b.6).
    const KNOWN_ORDER_MISMATCHES: &[(&str, &str)] = &[];

    /// The steps that exit `id` needs, directly or not. Alternatives (`a|b`) and clues from
    /// other boxes are no must.
    fn needed_by(b: &GraphBox, id: &str, needed: &mut HashSet<String>) {
        let id = b.choice_of(id).unwrap_or(id);
        let Some(node) = b.node(id) else {
            return;
        };
        for alternatives in node.requires.iter().filter(|a| a.len() == 1) {
            let requirement = &alternatives[0];
            if story_graph::cross_box(requirement).is_some() {
                continue;
            }
            let step = requirement
                .split_once('=')
                .map_or(requirement.as_str(), |(_, option)| option);
            if needed.insert(step.to_string()) {
                needed_by(b, step, needed);
            }
        }
    }

    /// Checks one walk of box `b` from its entry.
    fn check_box(b: &GraphBox, walk: &Walk) {
        let id = &b.id;
        // No dead ends: an exit can be reached from every state.
        let mut reaches = vec![false; walk.states.len()];
        for &exit in &walk.exits {
            reaches[exit] = true;
        }
        let mut changed = true;
        while changed {
            changed = false;
            for (i, targets) in walk.edges.iter().enumerate() {
                if !reaches[i] && targets.iter().any(|&j| reaches[j]) {
                    reaches[i] = true;
                    changed = true;
                }
            }
        }
        if let Some(stuck) = reaches.iter().position(|r| !r) {
            panic!(
                "{id}: dead end, no exit can be reached after: {}",
                walk.describe(stuck)
            );
        }
        assert!(!walk.exits.is_empty(), "{id}: the walk has no exit");
        // There is always something to do: an open note on the phone.
        let exits: HashSet<usize> = walk.exits.iter().copied().collect();
        for (i, state) in walk.states.iter().enumerate() {
            if !exits.contains(&i) {
                assert!(
                    state.has_open_note(),
                    "{id}: no open note after: {}",
                    walk.describe(i)
                );
            }
        }

        // Steps are done in some state. The exits reached and everything they need must be.
        let done_somewhere = |step: &str| walk.states.iter().any(|s| s.step(id, step));
        let exits_of_box: Vec<&str> = b
            .nodes
            .iter()
            .filter(|n| n.kind == NodeKind::Exit)
            .map(|n| n.id.as_str())
            .collect();
        let reached: Vec<&str> = exits_of_box
            .iter()
            .copied()
            .filter(|exit| done_somewhere(exit))
            .collect();
        assert!(!reached.is_empty(), "{id}: no exit of the box is ever done");
        let mut needed = HashSet::new();
        for exit in &reached {
            needed_by(b, exit, &mut needed);
        }
        for step in &needed {
            assert!(done_somewhere(step), "{id}: step '{step}' is never done");
        }
        let all: Vec<&str> = b
            .nodes
            .iter()
            .map(|n| n.id.as_str())
            .chain(b.options.iter().map(|(_, o, _)| o.as_str()))
            .collect();
        let never: Vec<&str> = all
            .into_iter()
            .filter(|step| b.node(step).is_none_or(|n| n.kind != NodeKind::Choice))
            .filter(|step| !done_somewhere(step))
            .collect();
        eprintln!(
            "{id}: {} states, exits done {reached:?}, never done {never:?}",
            walk.states.len()
        );

        // Steps are done after what the graph needs for them.
        for (i, targets) in walk.edges.iter().enumerate() {
            for &j in targets {
                let (from, to) = (&walk.states[i], &walk.states[j]);
                for node in &b.nodes {
                    if from.step(id, &node.id) || !to.step(id, &node.id) {
                        continue;
                    }
                    if !b.requirements_hold(&node.id, &|step| to.step(id, step)) {
                        assert!(
                            KNOWN_ORDER_MISMATCHES.contains(&(id.as_str(), node.id.as_str())),
                            "{id}: step '{}' is done before what the graph needs for it: {}",
                            node.id,
                            walk.describe(j)
                        );
                    }
                }
            }
        }
    }

    /// Walks every box with a scene from its entry node, trying every action.
    #[test]
    fn every_box_can_be_finished_in_any_order() {
        let graph = Graph::route1();
        let mut walker = walker();
        for b in graph.0.boxes.iter().filter(|b| b.entry.is_some()) {
            let base = State::with_vars(base_vars(&b.id));
            let (_, start, _) = walker.enter(&base, &b.id).unwrap();
            assert_eq!(start.box_id(), b.id, "the entry node enters its box");
            let exits: Vec<String> = b
                .nodes
                .iter()
                .filter(|n| n.kind == NodeKind::Exit)
                .map(|n| n.id.clone())
                .collect();
            let walk = walker
                .walk(
                    start,
                    |s| s.ended || s.box_id() != b.id || exits.iter().any(|e| s.step(&b.id, e)),
                    STATE_CAP,
                )
                .unwrap_or_else(|err| panic!("{}: {err}", b.id));
            check_box(b, &walk);
        }
    }
}
