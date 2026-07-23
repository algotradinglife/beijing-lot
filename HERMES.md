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
| **hh1985** (research owner) | Create issues, approve goals, make final domain decisions, merge PRs |
| **everything-bot-engineer** | Code modifications, commits, pushes, PR creation |
| **Hermes** (controller) | Observe graph, route work, manage state transitions, trigger validation |

For full authority definitions, see `kernel/system.yaml` in the Research OS template.

## Recovery

If chat context is lost, recover from:
- Project configuration (`.research/project.yaml`)
- Graph and task YAML (`.research/graph.yaml`, `.research/tasks/`)
- Git revision state
- Validation records and audit history
