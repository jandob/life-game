use std::fs::{read_dir, read_to_string};

use petgraph::{dot::Dot, Direction};
use pretty_assertions::assert_eq;
use story_graph::graph_boxes;

use crate::{
    construct_graph,
    draw::{box_dot, done_marks, has_content, story_dot, Done},
    tagged_titles, try_read_yarn_contents, PATH_TO_DIALOGUES,
};

const PATH_TO_YARN: &str = "./DUMMY.yarn";
const PATH_TO_DOT: &str = "./DUMMY.dot";

#[test]
fn graph_construction() {
    let contents = read_to_string(PATH_TO_YARN)
        .unwrap_or_else(|_| panic!("Can't read file: '{}'", PATH_TO_YARN));
    let dot_contents = read_to_string(PATH_TO_DOT)
        .unwrap_or_else(|_| panic!("Can't read file: '{}'", PATH_TO_DOT));

    let graph = construct_graph(contents);
    let dot = Dot::new(&graph);
    assert_eq!(dot_contents, dot.to_string());
}

/// Titles started with `<<next_scene NODE>>` from any dialogue file, and the entry nodes of
/// the story graph's boxes (started by an exit). Like a file's first node, they are entry
/// points and need no incoming jump.
fn next_scene_targets() -> Vec<String> {
    read_dir(format!("../{}", PATH_TO_DIALOGUES))
        .expect("Can't read entries in current dir")
        .filter_map(try_read_yarn_contents)
        .flat_map(|(contents, _)| {
            let entries = graph_boxes(&contents).into_iter().filter_map(|b| b.entry);
            let scenes = contents
                .lines()
                .filter_map(|line| {
                    // Scenes and phone texts are both started by the engine, not jumped to.
                    let line = line.trim();
                    let target = line
                        .strip_prefix("<<next_scene ")
                        .or_else(|| line.strip_prefix("<<phone "))?;
                    Some(target.trim_end_matches(">>").trim().to_string())
                })
                .collect::<Vec<_>>();
            entries.chain(scenes).collect::<Vec<_>>()
        })
        .collect()
}

#[test]
fn validate_no_hanging_nodes() {
    let entry_points = next_scene_targets();
    for entry in
        read_dir(format!("../{}", PATH_TO_DIALOGUES)).expect("Can't read entries in current dir")
    {
        let (contents, npc_file_name) = match try_read_yarn_contents(entry) {
            Some(r) => r,
            None => continue,
        };

        // Graph nodes are data, never run.
        let data = tagged_titles(&contents, "graph");
        let graph = construct_graph(contents);
        for index in graph.node_indices().skip(1) {
            let weight = graph.node_weight(index).expect("Node should exist");
            let title = weight
                .strip_prefix("title: ")
                .and_then(|t| t.split('|').next())
                .unwrap_or_default();
            if entry_points.iter().any(|t| t == title) || data.iter().any(|t| t == title) {
                continue;
            }
            assert!(
                graph.edges_directed(index, Direction::Incoming).count() != 0,
                "There is a node that doesn't have any incoming edges. This should only be the case for the very first node.\nfile: '{}', node: '{}'",
                npc_file_name,
                graph.node_weight(index).expect("Node should exist")
            );
        }
    }
}

const GRAPH: &str = "title: GraphA\ntags: graph\n---\n<<box A \"First\" goal=\"Get in\">>\n<<gate knock \"Knock\">>\n<<clue wine \"She drinks <Fox> & co\" knock>>\n<<choice still \"At her door\" knock>>\n<<option still wait \"Stand still\">>\n<<option still reach \"Reach\">>\n<<exit on \"Go on\" still=wait to=B>>\n<<exit no \"Closed\" still=reach to=R>>\n===\ntitle: GraphB\ntags: graph\n---\n<<box B \"Second\" goal=\"Be on time\">>\n<<gate door \"Door\" A.wine|knock>>\n<<exit end \"End\" door to=C>>\n===\ntitle: GraphR\ntags: graph\n---\n<<box R \"Try again\" kind=retry>>\n<<gate t \"Text\">>\n<<exit back \"Back\" t to=B>>\n===\ntitle: GraphC\ntags: graph\n---\n<<box C \"Later\" kind=stub>>\n===\n";

#[test]
fn story_graph_has_a_node_per_box_and_an_edge_per_exit() {
    assert_eq!(tagged_titles(GRAPH, "graph").len(), 4);
    let boxes = graph_boxes(GRAPH);
    assert_eq!(boxes.len(), 4);
    assert_eq!(boxes.iter().filter(|b| has_content(b)).count(), 3);

    let dot = story_dot(&boxes, "route1", &Done::new());
    assert!(dot.contains("Route 1, story level"));
    assert!(
        dot.contains("\"A\" [label=<<b>First</b><br/><font point-size=\"10\">Goal: get in</font><br/><font point-size=\"10\">0 of 5 steps written</font>>")
    );
    assert!(dot.contains(
        "\"R\" [label=<<b>Try again</b><br/><font point-size=\"10\">0 of 2 steps written</font>>"
    ));
    // A stub has no steps to count.
    assert!(dot.contains("\"C\" [label=<<b>Later</b>>"));
    assert!(dot.contains("style=\"rounded,filled,dashed\", fillcolor=\"#f4f4f4\""));
    assert!(dot.contains("\"A\" -> \"B\" [label=\" Go on\"];"));
    // Into and out of a retry box the edges are red.
    assert!(dot.contains("\"A\" -> \"R\" [label=\" Closed\", color=\"#c0392b\""));
    assert!(dot.contains("\"R\" -> \"B\" [label=\" Back\", color=\"#c0392b\""));
    // The clue A.wine is used in B.
    assert!(
        dot.contains("\"A\" -> \"B\" [label=<&nbsp;She drinks &lt;Fox&gt; &amp; co>, style=dotted")
    );
    assert_eq!(dot.matches("style=dotted").count(), 1);
}

#[test]
fn box_graph_draws_requirements_options_and_cross_box_clues() {
    let boxes = graph_boxes(GRAPH);
    let a = box_dot(&boxes, &boxes[0], &Done::new());
    assert!(a.contains("\"entry\" -> \"n_knock\";"));
    assert!(a.contains("\"n_still\" -> \"o_still_wait\";"));
    assert!(a.contains("\"o_still_wait\" -> \"n_on\";"));
    assert!(a.contains("\"o_still_reach\" -> \"n_no\" [color=\"#c0392b\""));
    assert!(a.contains("fillcolor=\"#fdeceb\""));
    assert!(a.contains("She drinks &lt;Fox&gt; &amp; co"));
    // Nothing is written yet: every step is dashed.
    assert!(
        a.contains("\"n_knock\" [label=<<b>Knock</b>>, shape=box, style=\"rounded,filled,dashed\"")
    );
    assert!(a.contains(
        "\"o_still_wait\" [label=\"Stand still\", shape=ellipse, style=\"filled,dashed\""
    ));

    let b = box_dot(&boxes, &boxes[1], &Done::new());
    assert!(b.contains("\"n_knock\" -> \"n_door\" [style=dashed];"));
    assert!(b.contains("\"x_A_wine\" -> \"n_door\" [style=dashed, color=\"#999999\"];"));
    assert!(b.contains("\"x_A_wine\" [label=\"From First:\\nShe drinks <Fox> & co\""));
}

const PARTLY: &str = "title: GraphA\ntags: graph\n---\n<<box A \"First\">>\n<<gate knock \"Knock\">>\n<<clue wine \"Wine\" knock>>\n<<clue hat \"Hat\" knock>>\n<<choice still \"At her door\" knock>>\n<<option still wait \"Stand still\">>\n<<option still reach \"Reach\">>\n<<exit on \"Go on\" still=wait to=B>>\n===\ntitle: GraphB\ntags: graph\n---\n<<box B \"Second\">>\n<<gate door \"Door\" A.wine>>\n<<gate bell \"Bell\" A.hat|A.wine>>\n<<exit end \"End\" door bell to=A>>\n===\n";

#[test]
fn partly_written_box_counts_the_steps_that_scenes_mark_done() {
    let scene = "title: Scene\n---\n<<done A knock>>\n<<done A wait>>\n  <<done A wine>>\n<<done A on>>\n<<done B end>>\n===\n";
    let done = done_marks(scene);
    assert_eq!(done.len(), 5);
    let boxes = graph_boxes(PARTLY);

    // Steps: knock, wine, hat, still, on. The choice needs both options.
    let dot = story_dot(&boxes, "route1", &done);
    assert!(dot.contains("3 of 5 steps written"));
    assert!(dot.contains("1 of 3 steps written"));
    assert!(dot
        .contains("shape=box, style=\"rounded,filled\", fillcolor=\"#f4f4f4\", color=\"#3b5b8c\""));

    // Marking the other option too writes the choice; marking everything, the box.
    let mut done = done;
    done.insert(("A".to_string(), "reach".to_string()));
    assert!(story_dot(&boxes, "route1", &done).contains("4 of 5 steps written"));
    done.insert(("A".to_string(), "hat".to_string()));
    let dot = story_dot(&boxes, "route1", &done);
    assert!(dot.contains("fillcolor=\"#eef3fb\", color=\"#3b5b8c\""));
    assert!(!dot.contains("5 of 5"));

    let a = box_dot(&boxes, &boxes[0], &done);
    assert!(a.contains("\"n_knock\" [label=<<b>Knock</b>>, shape=box, style=\"rounded,filled\""));
    assert!(a.contains("\"n_still\" [label=<<b>At her door</b>>, shape=diamond, style=\"filled\""));
    let partly = done_marks("<<done A knock>>");
    let a = box_dot(&boxes, &boxes[0], &partly);
    assert!(a.contains("\"n_knock\" [label=<<b>Knock</b>>, shape=box, style=\"rounded,filled\""));
    assert!(a.contains("\"n_hat\" [label=<Hat>, shape=note, style=\"filled,dashed\""));
    assert!(a.contains(
        "\"n_still\" [label=<<b>At her door</b>>, shape=diamond, style=\"filled,dashed\""
    ));
}

#[test]
fn clues_between_two_boxes_share_one_edge() {
    let boxes = graph_boxes(PARTLY);
    let dot = story_dot(&boxes, "route1", &Done::new());
    // A.wine is needed twice but listed once, in file order, with A.hat.
    assert!(dot.contains("\"A\" -> \"B\" [label=<&nbsp;Wine<br/>&nbsp;Hat>, style=dotted"));
    assert_eq!(dot.matches("style=dotted").count(), 1);
}
