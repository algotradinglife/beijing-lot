# Issue #248 handoff

[SESSION] 20260819_015701_617a7f

## Current HEAD

`HEAD` on `engineer/bj248-issue` (the commit carrying this handoff).

## Completed

- Claimed GitHub Issue #248 and moved it from Ready to In Progress.
- Replaced an uncommitted stale 500/ZGZCW draft with a Nowscore TypeID=5-only
  prospective lane.
- Added append-only raw issue/history capture, idempotency keyed by capture,
  source + trusted-receive temporal gating, deterministic relative/common epoch
  views, an externally anchored semantic verifier, collector/materializer CLIs,
  operations/source-probe documentation and an executed notebook.
- Focused test suite: 6 passed; legacy Nowscore history suite: 5 passed.

## Key decisions

- Nowscore is the primary source; 500/ZGZCW are documented only as future
  cross-checks. No historical backfill occurs.
- Repeated raw bytes use one content-addressed file, while every distinct poll
  retains an immutable receipt and complete source table.
- A view requires `source_changed_at_utc <= decision_at_utc` and
  `trusted_received_at_utc <= decision_at_utc`, both strictly before kickoff.
- A manifest SHA must be retained in an external release/operations record;
  the verifier recomputes vectors from raw evidence and refuses a remanifested
  or source-trace/quote-tampered ledger against that trusted anchor.

## Known limits / next steps

- No live collection was started: the operator must explicitly choose and set
  `BEIJING_LOT_DATA_ROOT` before invoking the collector.
- The compact notebook is an executed offline operational-shape demonstration,
  not evidence that a live sample is sufficient for learning.
- The full `tests/decision_api/test_nowscore_status.py` could not collect in
  this interpreter because its pre-existing dependency `flask` is absent;
  focused #248 and standalone Nowscore history tests pass.
- Before delivery: complete independent staged-diff review, commit/push, open
  evidence PR, post the PI acceptance table, then self-move #248 to EV Review.
