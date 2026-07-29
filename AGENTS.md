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
