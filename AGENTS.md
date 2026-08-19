# AGENTS.md

Guidance for AI coding agents working in this repository.

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


