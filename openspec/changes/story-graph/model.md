# Story graph: the model

A draft of the story graph as mathematical constraints. Decided by Janosch (2026-10-26): every subgraph has exactly one entry state, any number of edges may lead into it, and nothing is remembered outside the graph.

## Definitions

A **subgraph** is G = (N, R, s, X, σ):

- N is a finite set of nodes. A node is a **gate** (something the player does), a **choice** with options o₁…oₖ (each option is itself a node), or a **subgraph** (one level down).
- R gives each node n its requirement R(n): a formula over other nodes, built from "done" with *and* and *or*. Its edges are drawn from these formulas.
- s ∈ N is the entry: the only node with no requirement.
- X ⊆ N is the set of exits. Reaching one ends G.
- σ is the world state at s. It is the same however G was entered.

Play inside G is a sequence of done nodes. Its local state is the set D ⊆ N of nodes done so far. A node n can be done when R(n) holds on D. At most one option of each choice can be in D. A child subgraph H with exits x₁…xₘ appears in G like a choice with m options, chosen by playing H.

## Constraints

1. **Acyclic.** The edges of R form no cycle.
2. **One entry.** s is the only node without requirements, and σ is fixed.
3. **Locality.** Every story variable belongs to exactly one subgraph. Only that subgraph's nodes read or write it. Nothing outside G can tell how G was played, except by which exit it left.
4. **Exits.** X is non-empty, and an exit is required by no node of G.
5. **No dead ends.** From every reachable D, some exit can still be reached.
6. **Everything reachable.** Every node is in some reachable D.
7. **Meaningful choices.** For a choice c with options o ≠ o′, picking o and picking o′ leave different sets of nodes still reachable.
8. **Meaningful exits.** Two exits of G lead to different nodes in G's parent. Two exits that lead to the same place are one exit.
9. **Bounds.** |X| ≤ x_max and |N| ≤ n_max, with both values to be decided. A subgraph that breaks a bound is split.

## Consequences

- **Composition.** If every subgraph meets 5 and 6, so does the whole story. Each subgraph is checked once from its one entry, so the cost is the sum over subgraphs, not their product.
- **Levels are free.** Nesting changes nothing in the rules. A chapter is the level that means one day.
- **No callbacks.** A later scene can differ only because play reached a different subgraph. A line that refers back to an earlier choice needs that choice to be an exit that leads to its own subgraph.

## In Yarn (to be worked out)

- Every Yarn variable is tagged with its subgraph (3 can then be checked statically).
- Gates, choices and options set `$gate_*` and `$choice_*`. Exits start the next subgraph's entry node.
- The graph checks (1, 2, 4–9) run on the declared graph. A link check proves each scene sets a node only where R(n) is read.
