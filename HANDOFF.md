# Issue #248 handoff — PI rework

[SESSION] 20260819_235658_96e389

## Current HEAD

`engineer/bj248-issue`; the commit carrying this handoff is the rework delivery
head. Resolve its exact SHA with `git rev-parse HEAD` after checkout.

## Completed rework

- Claimed #248 from `Ready` to `In Progress` after confirming its sole native
  predecessor (#234) is closed.
- Fixed **KE-248-01**: a history receipt now stores the exact fetched URL,
  rejects anything outside the HTTPS `cp.nowscore.com` fixture-specific
  TypeID=5 route before fetch, and references the raw issue-page receipt whose
  parsed row supplied that exact URL. The semantic verifier rebuilds this
  source trace from raw issue evidence.
- Fixed **KE-248-02**: an unrecognized active-page shape is recorded as
  `PARSE_ERROR`, logged, and makes the CLI non-zero. A recognized explicit
  no-sale marker is instead `EMPTY_PROVEN`, never silently `OK` with zero rows.
- Fixed **KE-248-03**: reusing a capture key succeeds only for an identical raw
  SHA and complete immutable receipt metadata. A changed payload or metadata
  now raises an explicit collision in both issue-page and history receipt paths.
- Fixed **KE-248-04**: requested, trusted-receive, kickoff, and supplied
  decision-epoch times are canonical UTC `Z` instants before persistence or
  SQLite lexical comparison. An offset epoch can no longer admit a later UTC
  receipt.
- Repaired the standalone collector CLI's import bootstrap and updated the
  executed notebook for mandatory issue-page→history trace linkage.

## Evidence

- Focused suite: `python -m pytest tests/test_bj248_forward_snapshot.py
  tests/test_bj248_rework.py tests/scripts/test_nowscore_bjdc_sp_history.py -q`
  → `21 passed`.
- Tamper-focused subset → `4 passed`: altered quote/vector, raw-source trace,
  remanifest/external-anchor path, and offset/future-receipt gate fail closed.
- Notebook: `/home/drwho1985/work/beijing-lot-206/.venv/bin/python
  scripts/execute_bj248_notebook.py` → `EXECUTED`.
- Manual read-only shadow probe of issue 26086 is documented in
  `docs/research/bj248_manual_shadow_capture.md`. It verified the live page and
  URL shape but admitted no forward vector: all 80 history outcomes were
  explicitly rejected (42 post-kickoff, 38 invalid SP domain), not zero-filled.

## Known limits / decision input

- The shadow issue's `cansale=true` rows had stale/past schedule evidence; this
  does not qualify active-sale truth, retention, cadence or successful forward
  collection. **Do not enable unattended scheduling** until a fresh issue has a
  demonstrably future source schedule and at least one complete causal vector.
- PI accepted notebook byte determinism and cross-store crash recovery as
  exploration debt; this delivery intentionally does not expand into them.
- Full repository pytest collection remains unavailable in both available
  interpreters because of unrelated missing/incomplete dependencies and a
  legacy macOS absolute input path. The focused #248 tests and notebook above
  are the applicable passing evidence.

## Next steps

1. EV: rerun the focused suite and notebook in a fresh checkout; inspect the
   allowlist/source-trace verifier and retry-collision paths.
2. PI: decide whether the negative live shadow probe is sufficient to retain
   the no-scheduler restriction or whether a later fresh-issue shadow probe is
   required before activating operations.
