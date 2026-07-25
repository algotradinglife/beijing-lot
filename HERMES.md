# Beijing Lot — Research OS Controller Entry

This repository uses [Research OS](https://github.com/algotradinglife/research-os-template)
for structured, evidence-driven research and capability development.

**Start here, then follow the machine-readable bootstrap contract.**

## Entry point

1. Read `kernel/controller.yaml` from the Research OS template
2. Read `kernel/system.yaml`
3. Read `.research/project.yaml`
4. Read `.research/graph.yaml`
5. Read task files referenced by active graph nodes
6. Read remaining kernel policies and profiles from the template

## Pinned reference

- **Repository:** https://github.com/algotradinglife/research-os-template
- **Ref:** `c4f95f423dbb4acba8c3f7acb9ced2f766c2e34d`
- **Controller:** `kernel/controller.yaml`

## Control loop

Observe persisted graph and repository state
→ Evaluate authority, data policy, risk, dependencies, and retry budget
→ Select one next action
→ Bind an executor or request a human gate
→ Collect immutable artifact references
→ Run the required validation gate
→ Apply one valid state transition
→ Persist audit and graph updates
→ Recalculate

## Authority boundaries

| Role | Actions |
|------|---------|
| **hh1985 / PI** (research owner) | Own research intent, issue contracts, task priority, dependency edges, routing profile, PI review, final domain decisions, and merges |
| **Engineer** (resident Codex session) | Execute tasks routed with `profile: engineer`; perform code changes, commits, pushes, PR creation, and Engineering Validation |
| **Strategist** (resident Codex session) | Execute tasks routed with `profile: strategist`; perform strategy research and report evidence without changing production execution authority |
| **Hermes** (controller) | Read the PI-maintained graph and task YAML, dispatch the highest-priority eligible task to the named resident session, manage operational state transitions, and trigger validation |

For full authority definitions, see `kernel/system.yaml` in the Research OS template.

## Local routing contract

- `.research/graph.yaml` and `.research/tasks/*.yaml` are the dispatch source of truth.
- The PI owns task creation, priority, dependency relationships, and `status.routing.profile`.
- Hermes may persist operational state, runtime registration, and audit history, but must not change PI-owned intent, priority, dependencies, or task owner.
- `profile: engineer` routes to the resident Engineer session; `profile: strategist` routes to the resident Strategist session.
- Both resident sessions use the shared GitHub identity `everything-bot-engineer`. GitHub `owner/engineer` and `owner/strategist` labels identify the real route; the account name does not.
- Engineer execution is fixed to worktree `.worktrees/develop` and branch `develop`.
- Engineer must not create per-Issue branches or worktrees. Before starting the next Engineer task, `develop` must be synchronized with current `main` and contain no residue from a prior merged or abandoned task.
- Engineer commits and pushes task changes on `develop` and opens the implementation PR from `develop` to `main`.
- A task is dispatchable only when it is `READY`, its `depends_on` nodes are complete, and its scheduling WIP slot is free.
- Within one WIP slot, an existing `EXECUTING` or `VALIDATING` task remains the current action. Otherwise Hermes selects the eligible `READY` task by `priority_class`, then `dispatch_rank`.
- GitHub comments do not need to mention HermesPM. Hermes derives dispatch decisions from these persisted control-plane files.

## Recovery

If chat context is lost, recover from:
- Project configuration (`.research/project.yaml`)
- Graph and task YAML (`.research/graph.yaml`, `.research/tasks/`)
- Git revision state
- Validation records and audit history
