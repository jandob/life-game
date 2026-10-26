//! The story chart (see `openspec/changes/story-chart`): the story as chapters of gates,
//! and a walker that plays it the way a player could.
//!
//! The chart lives in Yarn, in nodes tagged `chart` that never run
//! (`assets/dialogue/chart_route1.yarn`). Story state is plain Yarn: `$chapter` names the
//! current chapter and `$gate_<id>` is true once a gate is done. Each chapter's start node
//! is the only node that sets `$chapter` to it.
//!
//! The walker plays on a bare `Dialogue`, without Bevy systems, so it also runs on wasm.
//! An action is one available option of a hotspot node's popup (or the whole node, when it
//! opens with a line), or reading a pending text. A `<<next_scene>>` plays after the node
//! that queued it, and any other choice inside a run branches the search. World commands
//! are only collected, for start points to replay. A state is the story variables plus
//! the phone's pending texts and notes.
//!
//! The chart checks walk every chapter (tests below and in `ui/dialogue/test.rs`), and
//! start points replay the walker's shortest path to their chapter (`start_point.rs`).

use std::collections::hash_map::DefaultHasher;
use std::collections::{BTreeMap, HashMap, HashSet, VecDeque};
use std::hash::{Hash, Hasher};
use std::sync::{Arc, Mutex};

use bevy::prelude::*;
use bevy_yarnspinner::default_impl::{MemoryVariableStorage, StringTableTextProvider};
use bevy_yarnspinner::prelude::*;
use yarnspinner::runtime::{Dialogue, DialogueEvent, OptionId, VariableStorageError};

#[cfg(test)]
/// Yarn node tag of chart nodes.
pub const CHART_TAG: &str = "chart";
/// The node a new game starts with: the first chapter's start node.
pub const FIRST_NODE: &str = "Route1Start";
/// The Yarn variable that names the current chapter.
pub const CHAPTER: &str = "$chapter";
/// Walks with more states than this fail, so a chart that grows too wide gets noticed.
pub const STATE_CAP: usize = 50_000;

/// The Yarn variable of a gate.
pub fn gate_variable(id: &str) -> String {
    format!("$gate_{id}")
}

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
    pub fn is_true(&self, name: &str) -> bool {
        matches!(self.vars.get(name), Some(YarnValue::Boolean(true)))
    }

    pub fn gate(&self, id: &str) -> bool {
        self.is_true(&gate_variable(id))
    }

    pub fn chapter(&self) -> String {
        match self.vars.get(CHAPTER) {
            Some(YarnValue::String(chapter)) => chapter.clone(),
            _ => String::new(),
        }
    }

    #[cfg(test)]
    pub fn has_open_note(&self) -> bool {
        self.notes.iter().any(|note| !note.done)
    }

    /// Equal for states that play the same. Only variables in `read` count: a variable
    /// that no condition reads can't change what happens.
    fn key(&self, read: &HashSet<String>) -> u64 {
        let mut hasher = DefaultHasher::new();
        for (name, value) in &self.vars {
            if read.contains(name) {
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
    /// The variables some condition or line reads, and the chart's: they tell states
    /// apart.
    read: HashSet<String>,
    /// The variables runs have read, for `take_reads`.
    reads_seen: HashSet<String>,
    /// Runs played before, by (node, choices).
    memo: HashMap<(String, Vec<usize>), Vec<Memo>>,
    /// The nodes of the map's hotspots, each once.
    hotspots: Vec<String>,
    world: World,
}

impl Walker {
    pub fn new(project: &YarnProject, hotspots: &[String]) -> Result<Self, String> {
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
        read.extend(
            program
                .initial_values
                .keys()
                .filter(|name| name.starts_with("$gate_"))
                .cloned(),
        );
        read.insert(CHAPTER.to_string());
        let storage = TrackedStorage::default();
        let mut dialogue = Dialogue::new(Box::new(storage.clone()), Box::new(text));
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
            reads_seen: HashSet::new(),
            memo: HashMap::new(),
            hotspots: unique,
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
            self.reads_seen
                .extend(memo.reads.iter().map(|(name, _)| name.clone()));
            return Ok(self.apply(state, &outcome));
        }
        let outcome = self.play(state, node, choices)?;
        let reads = self.storage.take_reads();
        self.reads_seen.extend(reads.iter().cloned());
        let reads = reads
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
            if self.defaults.get(name) == Some(value) {
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

    #[cfg(test)]
    /// Equal for states that play the same (see `State::key`).
    pub fn key(&self, state: &State) -> u64 {
        state.key(&self.read)
    }

    #[cfg(test)]
    /// Forgets the variables read so far and returns them.
    pub fn take_reads(&mut self) -> HashSet<String> {
        std::mem::take(&mut self.reads_seen)
    }

    #[cfg(test)]
    /// Whether two states agree on every variable in `names`.
    pub fn agree(a: &State, b: &State, names: &HashSet<String>) -> bool {
        names
            .iter()
            .all(|name| a.vars.get(name) == b.vars.get(name))
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

    /// The state of a new game: `FIRST_NODE` played.
    pub fn start(&mut self) -> Result<(Step, State), String> {
        let mut plays = self.plays(&State::default(), FIRST_NODE, false)?;
        if plays.len() != 1 {
            return Err(format!("{FIRST_NODE} must play one way"));
        }
        let (step, state, _) = plays.remove(0);
        Ok((step, state))
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

    /// The shortest actions from a new game to a state where `goal` holds, chapter by
    /// chapter: in each chapter the shortest way to the goal or, if it lies further on,
    /// to the next chapter.
    pub fn path_to(&mut self, goal: impl Fn(&State) -> bool) -> Result<Vec<Step>, String> {
        let (first, mut state) = self.start()?;
        let mut path = vec![first];
        while !goal(&state) {
            if state.ended {
                return Err("the story ends before".to_string());
            }
            let chapter = state.chapter();
            let walk = self.search(
                state,
                |s| goal(s) || s.ended || s.chapter() != chapter,
                STATE_CAP,
                true,
            )?;
            let Some(&exit) = walk.exits.first() else {
                return Err(format!("chapter '{chapter}' has no way on"));
            };
            path.extend(walk.path(exit));
            state = walk.states[exit].clone();
        }
        Ok(path)
    }

    /// Plays `path` from a new game. Returns the end state and the world commands of every
    /// step, in order.
    pub fn replay(&mut self, path: &[Step]) -> Result<(State, Vec<WorldCommand>), String> {
        self.replay_from(State::default(), path)
    }

    /// Plays `path` from `state`, as `replay`.
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
    use std::collections::{HashMap, HashSet};

    use super::*;
    use crate::story::load_real_project;
    use crate::ui::dialogue::test::{chart, ChartChapter};

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
        Walker::new(project, &route1_hotspots()).unwrap()
    }

    /// Checks one walk of `chapter`. Returns its exits.
    fn check_walk(
        walk: &Walk,
        chapter: &ChartChapter,
        next: Option<&ChartChapter>,
        requires: &HashMap<String, Vec<String>>,
    ) -> Vec<State> {
        let id = &chapter.id;
        for gate in chapter.gates.iter().chain([&chapter.bottleneck]) {
            assert!(
                walk.states.iter().any(|s| s.gate(&gate.id)),
                "{id}: gate '{}' is never reached",
                gate.id
            );
        }
        for (i, targets) in walk.edges.iter().enumerate() {
            for &j in targets {
                let (from, to) = (&walk.states[i], &walk.states[j]);
                for (gate, needs) in requires {
                    if from.gate(gate) || !to.gate(gate) {
                        continue;
                    }
                    for need in needs {
                        assert!(
                            to.gate(need),
                            "{id}: gate '{gate}' is set before '{need}': {}",
                            walk.describe(j)
                        );
                    }
                }
            }
        }
        // No dead ends: the exits can be reached from every state.
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
                "{id}: dead end, the bottleneck can't be reached after: {}",
                walk.describe(stuck)
            );
        }
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
        assert!(!walk.exits.is_empty(), "{id}: the walk has no exit");
        walk.exits
            .iter()
            .map(|&exit| {
                let state = &walk.states[exit];
                assert!(
                    state.gate(&chapter.bottleneck.id),
                    "{id}: left without its bottleneck: {}",
                    walk.describe(exit)
                );
                match next {
                    Some(next) => assert_eq!(
                        state.chapter(),
                        next.id,
                        "{id}: the bottleneck leads elsewhere: {}",
                        walk.describe(exit)
                    ),
                    None => assert!(
                        state.ended,
                        "{id}: the last chapter must end the demo: {}",
                        walk.describe(exit)
                    ),
                }
                state.clone()
            })
            .collect()
    }

    /// Walks every chapter from every way the chapter before it can end.
    #[test]
    fn every_chapter_can_be_finished_in_any_order() {
        let chapters = chart();
        let requires: HashMap<String, Vec<String>> = chapters
            .iter()
            .flat_map(|c| c.gates.iter().chain([&c.bottleneck]))
            .map(|g| (g.id.clone(), g.requires.clone()))
            .collect();
        let mut walker = walker();
        let (_, start) = walker.start().unwrap();
        let mut entries = vec![start];
        for (i, chapter) in chapters.iter().enumerate() {
            let id = chapter.id.clone();
            let mut exits: Vec<State> = Vec::new();
            let mut seen = HashSet::new();
            let mut states = 0;
            // Walks so far, with their entry and the variables they read. An entry that
            // agrees with a walked one on all of those, and on texts and notes, plays the
            // same: its exits are the same paths played from it.
            let mut walked: Vec<(State, HashSet<String>, Walk)> = Vec::new();
            for entry in &entries {
                assert_eq!(entry.chapter(), id, "the chapter after its start node");
                let same = walked.iter().find(|(other, reads, _)| {
                    other.unread == entry.unread
                        && other.notes == entry.notes
                        && Walker::agree(other, entry, reads)
                });
                let found = match same {
                    // The last chapter's exits lead nowhere.
                    Some(_) if i + 1 == chapters.len() => Vec::new(),
                    Some((_, _, walk)) => walk
                        .exits
                        .iter()
                        .map(|&exit| {
                            walker
                                .replay_from(entry.clone(), &walk.path(exit))
                                .unwrap()
                                .0
                        })
                        .collect(),
                    None => {
                        walker.take_reads();
                        let walk = walker
                            .walk(entry.clone(), |s| s.ended || s.chapter() != id, STATE_CAP)
                            .unwrap_or_else(|err| panic!("{id}: {err}"));
                        states += walk.states.len();
                        eprintln!(
                            "{id}: walk {} has {} states",
                            walked.len() + 1,
                            walk.states.len()
                        );
                        let found = check_walk(&walk, chapter, chapters.get(i + 1), &requires);
                        walked.push((entry.clone(), walker.take_reads(), walk));
                        found
                    }
                };
                for exit in found {
                    if seen.insert(walker.key(&exit)) {
                        exits.push(exit);
                    }
                }
            }
            println!(
                "{id}: {} ways in, {} walks, {states} states, {} ways out",
                entries.len(),
                walked.len(),
                exits.len()
            );
            entries = exits;
        }
    }

    #[test]
    fn start_points_find_every_chapter() {
        let mut walker = walker();
        for chapter in chart() {
            let path = walker
                .path_to(|s| s.chapter() == chapter.id)
                .unwrap_or_else(|err| panic!("{}: {err}", chapter.id));
            let (state, _) = walker.replay(&path).unwrap();
            assert_eq!(state.chapter(), chapter.id);
            assert!(chapter.gates.iter().all(|g| !state.gate(&g.id)));
        }
    }
}
