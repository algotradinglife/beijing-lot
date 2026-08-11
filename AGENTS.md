# Repository Agent Governance

## GitHub Issue Graph Is the Control-Plane Source of Truth

All planning, routing, dependency resolution, dispatch, review, and completion
decisions must be derived from the live GitHub Issue Graph.

The authoritative fields are:

- `blockedBy` / `blocking` for execution dependencies;
- `parent` / `subIssues` for work decomposition;
- `issueType` for the kind of work;
- GitHub Project `Status` for lifecycle state;
- GitHub Project membership for functional ownership. The Project determines
  the responsible role.

Issue bodies and comments may explain intent, methods, evidence, and decisions,
but they are not authoritative for dependency or lifecycle state. Text such as
`Depends on #...`, labels that imitate state, local task files, and chat history
must not be used to reconstruct or override the Issue Graph.

Before planning or dispatching work, read the relevant graph fields with
`gh issue view` or `gh issue list` JSON output. Before declaring work blocked,
ready, reviewable, or complete, read them again. When a relationship changes,
update the native GitHub relationship first and verify both directions
(`blockedBy` and `blocking`) by reading it back.

If GitHub cannot be read or updated, fail closed: report that the control-plane
state is unavailable. Do not manufacture a substitute graph from prose or local
files.

The PI owns issue contracts, graph edges, Project routing, final review, issue
closure, and PR merges. Executors may report evidence and propose graph changes,
but must not silently redefine the graph.

## Local Research OS Files

`.research/graph.yaml` and `.research/tasks/*.yaml` are derived caches or
execution notes only. They may mirror GitHub for local tooling, but they must
never lead, contradict, or replace the live GitHub Issue Graph. Any mismatch is
resolved in favor of GitHub, then the local mirror is refreshed.

## Engineering principles (owner-mandated)

1. **No backward-compat tax.** Delete obsolete code outright. No compat layers,
   no migrations, no fallbacks for old behavior — if it's outdated, remove it.
2. **Simplest implementation that satisfies the current need.** No speculative
   abstraction, no gratuitous config layers.
3. **Layered system — build thin first.** Get a minimal end-to-end version
   running, then add on top. Never rip out working code for unimplemented
   complexity.
4. **Modular components, separation of concerns.** Keep pieces decoupled and
   single-purpose.
5. **Prefer mature, maintained libraries.** No reinventing the wheel without a
   clear reason.
6. **Check existing dependencies first.** Before adding a package or writing
   your own, see what the project already has and what it can do. Don't assume
   the library is missing.
7. **Architecture decisions are made long-term.** No "ship it now, fix later"
   stopgaps — an accepted design is expected to persist.
8. **Learn from mature products.** See how established products solve the same
   problem and use proven patterns; don't invent from scratch.
