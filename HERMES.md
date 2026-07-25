# Beijing Lot — Research OS Controller Entry

This repository uses [Research OS](https://github.com/algotradinglife/research-os-template)
for structured, evidence-driven research and capability development.

**Start here, then follow the local dispatch override below.**

## Entry point

1. Read this file, including the local dispatch override
2. Read `.research/project.yaml`
3. Read `.research/graph.yaml` for roadmap and dependency context
4. Read task files referenced by roadmap nodes
5. Read the corresponding GitHub Issue execution contract and labels
6. Use the pinned template only for schema, validation, evidence, and authority guidance not overridden here

## Pinned reference

- **Repository:** https://github.com/algotradinglife/research-os-template
- **Ref:** `c4f95f423dbb4acba8c3f7acb9ced2f766c2e34d`
- **Controller:** `kernel/controller.yaml`

## Authority boundaries

| Role | Actions |
|------|---------|
| **hh1985 / PI** (research owner) | Own research intent, Issue contracts, roadmap priority, graph dependencies, `state/ready` authorization, PI review, final domain decisions, and merges |
| **Engineer** (resident Codex session) | Execute Issues routed with `owner/engineer`; perform code changes, commits, pushes, PR creation, and Engineering Validation |
| **Strategist** (resident Codex session) | Execute Issues routed with `owner/strategist`; perform strategy research and report evidence without changing production execution authority |
| **Hermes** (controller) | Poll positive GitHub routing labels, notify the named resident session, route explicit Issue/comment recipients, and avoid inferring readiness from open Issues |

## Local dispatch override

GitHub Issue labels are the operational dispatch source of truth for this repository. This local rule overrides template graph-based dispatch.

- The PI authorizes execution by adding `state/ready` plus exactly one owner label: `owner/engineer` or `owner/strategist`.
- Hermes selects only open Issues carrying both `state/ready` and the matching owner label.
- Hermes must never use a negative query such as “not completed/cancelled”. An unlabeled Issue is not dispatchable.
- On successful claim, `state/ready` must be removed before another notification can be sent for the same Issue.
- Issue number plus triggering comment ID is the idempotency key for notifications.
- Open Issues waiting for matches, external data, or prospective evidence remain non-dispatchable unless the PI explicitly restores `state/ready`.
- A mismatch between labels and the Issue contract fails closed and is reported to the PI.

Recommended positive queries:

```text
is:issue is:open label:state/ready label:owner/engineer
is:issue is:open label:state/ready label:owner/strategist
```

## Notification contract

Issue bodies and comments can route notifications without graph participation:

```text
[TO: Engineer][ACTION]
[TO: Strategist][QUESTION]
[TO: PI][REVIEW]
```

- Hermes notifies only the explicit recipient through the corresponding session.
- Hermes does not contact recipients by posting its own GitHub Issue comment.
- A notification does not itself authorize a new task claim; `state/ready` remains required.
- PR review findings belong on the PR. Execution-contract questions belong on the Issue.
- Engineer and Strategist share the GitHub identity `everything-bot-engineer`, so the explicit recipient marker and owner label are authoritative.

## Research OS graph contract

- `.research/graph.yaml` is maintained by the PI as a roadmap, dependency map, and research-history aid.
- Graph node state is coarse planning metadata, not Hermes's real-time dispatch state.
- `.research/tasks/*.yaml` preserve intent, acceptance, routing context, and durable evidence; their operational status is informational rather than a dispatch trigger.
- Hermes may read graph/task files for context but must not use them to discover or authorize the next GitHub Issue.
- Engineer, Strategist, and Hermes do not edit PI-owned roadmap or task-intent fields.

## Engineer workspace contract

- Engineer execution is fixed to worktree `.worktrees/develop` and branch `develop`.
- Engineer must not create per-Issue branches or worktrees.
- Before starting the next Engineer Issue, `develop` must be synchronized with current `main` and contain no residue from a prior merged or abandoned task.
- Engineer commits and pushes task changes on `develop` and opens the implementation PR from `develop` to `main`.

## Recovery

If chat context is lost, recover from:
- GitHub Issue labels and explicit recipient comments for current dispatch
- GitHub Issue and PR history for execution state
- Project configuration (`.research/project.yaml`)
- PI roadmap and task archive (`.research/graph.yaml`, `.research/tasks/`)
- Git revision state and validation records
