# Archived — Research OS Workflow

> Archived on 2026-07-29. This workflow is retained for historical context
> only. It must not be used for routing or lifecycle decisions. See the
> repository-root `AGENTS.md` for the current GitHub Issue Graph governance.

## Project Status Routing

```
Inbox -> Ready -> In Progress -> Review -> Done
                  |               |
                  v               v
               Blocked        (if CHANGES_REQUESTED -> back to In Progress)
                  |
                  v
               Ready (unblocked)
```

| Drag to | Who gets notified | When |
|---------|------------------|------|
| Ready   | Your session (via owner/* label) | Task assigned to you |
| Review  | PR author if CHANGES_REQUESTED, else PI | PR needs attention |
| Blocked | PR author if linked PR needs changes, else PI | Needs unblocking |
| Done    | Your session | Task completed |

## PI Review

PI validates PR against goal alignment, scope boundary, roadmap fit, plan consistency.
PI has sole merge authority.

## Engineering Validation (EV)

Sessions dispatch their own independent subagent for EV. Read-only.
See engineering-validation skill for details.
