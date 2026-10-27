//! The story graph at runtime: the graph drives the game (see
//! `openspec/changes/story-graph`, D8 to D11).
//!
//! The graph is the `graph` nodes of `assets/dialogue/graph_route1.yarn`, boxes of steps.
//! It is compiled into the game (`include_str!`, so it also works on wasm) and parsed by
//! the `story_graph` crate, which `dialogue_graph` uses to draw it.
//!
//! State is plain Yarn variables in the shared story storage ([`StoryVars`]):
//! - `$box`: the current box.
//! - `$step_<box>_<id>`, lower case: true once the step is done. Never declared, so a
//!   step nobody did is simply missing, which reads as false.
//!
//! Scenes never read these. They ask the graph through Yarn functions that read the
//! storage:
//! - `can("BOX", "ID")`: `BOX` is the current box, the step is not done and its
//!   requirements inside the box hold. For an option of a choice, no option of that
//!   choice is done either.
//! - `is_done("BOX", "ID")`: the step is done; a choice is done once one of its options is.
//! - `in_box("BOX")`: `BOX` is the current box, for lines that depend on where the story
//!   is (`$chapter == "X"` before the graph).
//!
//! and change it with two commands:
//! - `<<done BOX ID>>`: the step is done. If it is an exit into a box that has a scene, that
//!   box's entry node is queued, like `<<next_scene>>`.
//! - `<<enter_box BOX>>`: run first by a box's entry node. Sets `$box` and clears every
//!   step of the box, so a box starts the same way every time.
//!
//! The functions and the logic of the commands work on any [`VariableStorage`], so the
//! walker (`walker.rs`) plays the same rules on a bare `Dialogue`.

use std::sync::Arc;

use bevy::prelude::*;
use bevy_yarnspinner::prelude::*;
use story_graph::{box_step_prefix, step_variable, StoryGraph, BOX_VARIABLE};

use super::transition::QueuedScene;
use super::StoryVars;

/// Yarn node tag of story graph nodes: data, never run.
#[cfg(test)]
pub const GRAPH_TAG: &str = "graph";

/// The route 1 graph file, compiled into the game.
const ROUTE1: &str = include_str!("../../assets/dialogue/graph_route1.yarn");

/// The story graph, shared by every runner.
#[derive(Resource, Clone)]
pub struct Graph(pub Arc<StoryGraph>);

impl Graph {
    /// The graph of route 1.
    pub fn route1() -> Self {
        Self(Arc::new(StoryGraph::parse(ROUTE1)))
    }
}

/// The current box, empty before the first one is entered.
pub fn current_box(storage: &dyn VariableStorage) -> String {
    match storage.get(BOX_VARIABLE) {
        Ok(YarnValue::String(current)) => current,
        _ => String::new(),
    }
}

/// Whether the step is done. A step nobody did has no variable and reads as false.
pub fn step_done(storage: &dyn VariableStorage, box_id: &str, id: &str) -> bool {
    matches!(
        storage.get(&step_variable(box_id, id)),
        Ok(YarnValue::Boolean(true))
    )
}

/// Registers `can`, `is_done` and `in_box` on a library. They read `storage`, which has to
/// be the storage the runner uses.
pub fn add_functions<S>(library: &mut YarnLibrary, graph: &Arc<StoryGraph>, storage: &S)
where
    S: VariableStorage + Clone + 'static,
{
    let (g, s) = (graph.clone(), storage.clone());
    library.add_function("can", move |box_id: String, id: String| -> bool {
        g.can(&current_box(&s), &box_id, &id, &|b, step| {
            step_done(&s, b, step)
        })
    });
    let (g, s) = (graph.clone(), storage.clone());
    library.add_function("is_done", move |box_id: String, id: String| -> bool {
        g.is_done(&box_id, &id, &|b, step| step_done(&s, b, step))
    });
    let s = storage.clone();
    library.add_function("in_box", move |box_id: String| -> bool {
        current_box(&s) == box_id
    });
}

/// Records a step as done. Returns the entry node to start when the step is an exit into a
/// box that has a scene.
pub fn mark_done(
    graph: &StoryGraph,
    storage: &mut dyn VariableStorage,
    box_id: &str,
    id: &str,
) -> Result<Option<String>, String> {
    if !graph.find(box_id).is_some_and(|b| b.has_step(id)) {
        return Err(format!("done: unknown step {box_id} {id}"));
    }
    storage
        .set(step_variable(box_id, id), YarnValue::Boolean(true))
        .map_err(|err| format!("done {box_id} {id}: {err}"))?;
    Ok(graph.exit_entry(box_id, id).map(str::to_string))
}

/// Makes `box_id` the current box and clears every step of it.
pub fn enter_box(
    graph: &StoryGraph,
    storage: &mut dyn VariableStorage,
    box_id: &str,
) -> Result<(), String> {
    if graph.find(box_id).is_none() {
        return Err(format!("enter_box: unknown box {box_id}"));
    }
    let prefix = box_step_prefix(box_id);
    let steps: Vec<String> = storage
        .variables()
        .into_iter()
        .filter(|(name, value)| name.starts_with(&prefix) && *value == YarnValue::Boolean(true))
        .map(|(name, _)| name)
        .collect();
    for name in steps {
        storage
            .set(name, YarnValue::Boolean(false))
            .map_err(|err| format!("enter_box {box_id}: {err}"))?;
    }
    storage
        .set(
            BOX_VARIABLE.to_string(),
            YarnValue::String(box_id.to_string()),
        )
        .map_err(|err| format!("enter_box {box_id}: {err}"))
}

/// `<<done BOX ID>>`
pub fn done_command(
    In((box_id, id)): In<(String, String)>,
    graph: Res<Graph>,
    story_vars: Res<StoryVars>,
    mut queued: ResMut<QueuedScene>,
) {
    let mut storage = story_vars.0.clone();
    match mark_done(&graph.0, &mut storage, &box_id, &id) {
        Ok(Some(entry)) => {
            if let Some(old) = queued.0.replace(entry) {
                warn!("done {box_id} {id}: replacing the queued scene '{old}'");
            }
        }
        Ok(None) => {}
        Err(err) => error!("{err}"),
    }
}

/// `<<enter_box BOX>>`
pub fn enter_box_command(In(box_id): In<String>, graph: Res<Graph>, story_vars: Res<StoryVars>) {
    if let Err(err) = enter_box(&graph.0, &mut story_vars.0.clone(), &box_id) {
        error!("{err}");
    }
}

#[cfg(test)]
mod tests {
    use bevy_yarnspinner::default_impl::MemoryVariableStorage;

    use super::*;

    fn route1() -> Arc<StoryGraph> {
        Graph::route1().0
    }

    #[test]
    fn route1_boxes_with_a_scene_have_an_entry_node() {
        let graph = route1();
        let entries: Vec<(&str, &str)> = graph
            .boxes
            .iter()
            .filter_map(|b| Some((b.id.as_str(), b.entry.as_deref()?)))
            .collect();
        assert_eq!(
            entries,
            [
                ("R1Viewing", "Route1Start"),
                ("R1MoveIn", "Route1MoveInStart"),
                ("R1Breakfast", "Route1SundayStart"),
                ("R1Dinner1", "Route1Thu1Start"),
                ("R1Dinner2", "Route1Thu2Start"),
                ("R1Dinner2Retry", "Route1RetryStart"),
                ("R1Knock", "Route1KnockStart"),
                ("R1Notebook", "Route1NotebookStart"),
            ]
        );
    }

    #[test]
    fn done_and_enter_box_keep_the_steps_of_the_current_box() {
        let graph = route1();
        let mut storage = MemoryVariableStorage::new();
        assert!(!step_done(&storage, "R1MoveIn", "keys"));
        enter_box(&graph, &mut storage, "R1MoveIn").unwrap();
        assert_eq!(current_box(&storage), "R1MoveIn");
        assert_eq!(
            mark_done(&graph, &mut storage, "R1MoveIn", "keys"),
            Ok(None)
        );
        assert!(step_done(&storage, "R1MoveIn", "keys"));
        assert!(storage.get("$step_r1movein_keys").is_ok());
        // An exit into a box with a scene starts its entry node.
        assert_eq!(
            mark_done(&graph, &mut storage, "R1MoveIn", "bed"),
            Ok(Some("Route1SundayStart".to_string()))
        );
        // An exit into a box without one does not.
        assert_eq!(
            mark_done(&graph, &mut storage, "R1Breakfast", "bed"),
            Ok(None)
        );
        assert!(mark_done(&graph, &mut storage, "R1MoveIn", "nope").is_err());
        assert!(mark_done(&graph, &mut storage, "Nope", "keys").is_err());

        // Entering the box again clears its steps, and only its steps.
        mark_done(&graph, &mut storage, "R1Dinner2Retry", "text").unwrap();
        enter_box(&graph, &mut storage, "R1Dinner2").unwrap();
        enter_box(&graph, &mut storage, "R1MoveIn").unwrap();
        assert!(!step_done(&storage, "R1MoveIn", "keys"));
        assert!(!step_done(&storage, "R1MoveIn", "bed"));
        assert!(step_done(&storage, "R1Dinner2Retry", "text"));
        assert!(enter_box(&graph, &mut storage, "Nope").is_err());
    }

    #[test]
    fn functions_read_the_shared_storage() {
        let graph = route1();
        let mut storage = MemoryVariableStorage::new();
        let mut library = YarnLibrary::new();
        add_functions(&mut library, &graph, &storage);
        enter_box(&graph, &mut storage, "R1MoveIn").unwrap();
        let call = |name: &str, args: &[&str]| -> bool {
            let function = library.get(name).unwrap();
            let args: Vec<YarnValue> = args.iter().map(|a| YarnValue::from(*a)).collect();
            bool::try_from(function.call(args)).unwrap()
        };
        assert!(call("can", &["R1MoveIn", "keys"]));
        assert!(!call("can", &["R1MoveIn", "carry"]));
        assert!(call("in_box", &["R1MoveIn"]));
        assert!(!call("in_box", &["R1Viewing"]));
        mark_done(&graph, &mut storage, "R1MoveIn", "keys").unwrap();
        assert!(!call("can", &["R1MoveIn", "keys"]));
        assert!(call("can", &["R1MoveIn", "carry"]));
        assert!(call("is_done", &["R1MoveIn", "keys"]));
        assert!(!call("is_done", &["R1MoveIn", "carry"]));
    }
}
