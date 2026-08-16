# Issue #235 — BJ SP timeseries recovery handoff

[SESSION] 20260818_234459_2b166b

## Current HEAD

- Worktree: `/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/t_296eb0dc`
- Branch: `engineer/bj235-issue`, rebased to live `origin/main` commit `671c728`
  (accepted #234 source-schema foundation).
- Issue: #235, contract `BJ-UNIFIED-BJ-SP-TIMESERIES-001` plus PI v2 amendment
  (2026-08-17).

## Completed in this run

- Read and verified the live GitHub Issue Graph: #234 is closed and #235 is
  `In Progress`; #238 is the downstream blocked issue.
- Re-applied #235's committed v1 checkpoint onto the current accepted #234 base:
  append-only canonical SP store, strict as-of replay, source/exclusion ledgers,
  raw/probability/settlement separation, v1 executed notebook and tamper tests.
- Resolved the import conflicts by retaining all current result allow-list entries
  and adding the #235 v1 entries.

## Required v2 work before delivery

The PI amendment supersedes v1's strict-only historical disposition. Build and
verify the positive `RETROSPECTIVE_RELATIVE_PROXY` M×3 panel from the native
`beidan_xlsm` initial/10h/1h/final label buckets:

1. Retain every available bucket and emit explicit missing cells; never infer
   values from final/settlement/outcomes/later snapshots.
2. Bind each output to source, issue, canonical fixture, native line, outcome,
   snapshot bucket and availability mask, without fabricating a wall-clock.
3. Report coverage and missingness by issue and horizon (REQ-BJ09), export the
   common v2 long-form parquet for #238, and update the notebook/evidence.
4. Re-run all legacy plus panel-specific tamper tests, the build, preflight and
   notebook from clean outputs before opening/updating the evidence PR.

## Collision note

A separate legacy worktree (`/home/drwho1985/beijing-lot-235`) contains an
uncommitted v2 attempt. It is a reference only; no files there were modified.
This branch is the authoritative delivery path for the Kanban run and must
reconcile the reviewed implementation before any PR update.
