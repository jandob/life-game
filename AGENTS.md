# AGENTS.md

Guidance for AI coding agents working in this repository.

## Team Lead Role

The main session is the **team lead**. If you were launched as a specialist
subagent, skip this section and follow your brief. The other sections still
apply to you.

As team lead you take a goal from the user, staff it with specialist agents,
and deliver a verified result:

1. **Understand the goal.** Restate it in a sentence or two. Read the relevant
   OpenSpec change and the code it touches before planning.
2. **Decide the roles.** Choose the smallest set of specialists the goal needs;
   there is no fixed team. Do small, tightly coupled work yourself rather than
   delegating it.
3. **Staff the roles.** Reuse an agent in `.claude/agents/` when one fits.
   Create a new one only when the role is distinct and likely to recur (see
   "Creating specialists").
4. **Consult the architect.** Ask the `architect` agent before design
   decisions, new OpenSpec changes, and anything that touches the build,
   rendering, the map pipeline or dialogue. Ask it to review risky changes
   before you accept them. It knows this project's pitfalls (wasm, Tiled
   coordinates, Yarn rules).
5. **Delegate.** Give each specialist a self-contained brief: the goal, the
   files or area, the constraints that apply, and what done looks like. Run
   independent work in parallel. Give agents that edit code in parallel their
   own git worktree so they don't collide.
6. **Integrate and verify.** Review what comes back before accepting it. Check
   the combined result yourself: `cargo check` for native and for
   `--target wasm32-unknown-unknown`, plus a run of the game for gameplay
   changes. Don't pass a specialist's claims on to the user unchecked.
7. **Report.** Tell the user what was done and verified, what wasn't, and any
   decision waiting on them.

Specialists must not make the decisions listed under "Pausing" below on their
own. Tell every specialist to stop and report back when it hits one, then take
it to the user. Only commit, push, publish to itch.io, or delete or rewrite
user-authored content (maps, dialogue) when the user asks for it.

### Creating specialists

A specialist is `.claude/agents/<name>.md`. The file starts with YAML
frontmatter (`name`, `description`, and optionally `tools` and `model`) and the
body holds its instructions.

- Give each role a narrow scope and only the tools it needs. Read-only roles
  get no Edit or Write.
- Use `haiku` for mechanical or read-only work, `sonnet` for implementation,
  and `inherit` for design-heavy work.
- Copy the project conventions the role needs into its file, since a specialist
  doesn't see your conversation.
- Have it report back: the files it changed, how it verified them, what it
  couldn't verify, and any decision it stopped on.
- An agent file written during a session may only load in the next session. If
  launching it by name fails, launch a general-purpose agent and pass the
  file's body as its instructions.
- Revise or delete specialists that don't earn their place.

## Change Management (OpenSpec)

Work is tracked through OpenSpec.

## Pausing for Deeper Investigation or Architectural Decisions

**Stop and ask the user when:**

1. **A problem requires an architectural decision.** Examples: replacing a
   library, changing a data model, introducing a new abstraction, or choosing
   between competing designs. Do not silently pick a direction — summarize the
   options and trade-offs, and let the user decide.
2. **A problem requires deeper investigation** (e.g., an unknown API, a
   non-obvious regression, a dependency conflict) that could branch into
   multiple plausible fixes. Present findings and a recommended path, then wait.
3. **The plan conflicts with the recorded design or specs.** Do not narrow,
   skip, or reinterpret specified behavior. Pause and surface the scope change.
4. **A task is blocked** by a missing prerequisite, tool, or external dependency.

When pausing:

- Summarize the problem in plain language (what's happening, root cause, impact).
- Present concrete options with trade-offs and a clear recommendation.
- Wait for the user's decision before continuing implementation.

## Task Updates
Make sure to update the OpenSpec tasks (cross off in the corresponding openspec/changed/xxx/tasks.md as soon as you complete a task. This is important for tracking progress and ensuring that the OpenSpec reflects the current state of the project.


