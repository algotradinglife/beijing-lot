# PROTOCOL-LOG — Issue #237 (BJ-UNIFIED-POWER-FEATURE-SUPPORT-001)

Append-only protocol log for the #237 causal power feature rebuild.
Each row is a protocol decision or a debt entry; later rows may
`supersede` earlier rows.  This file is delivered with the package and
reviewed by EV/PI.

---

## 001 — FAIL-CLOSED native line semantics (C-01)

- **date**: 2026-08-16 (R2 rework, EV R1 REJECT)
- **supersedes**: none
- **rule**: A native BJ handicap line is publishable only when it is
  non-null, finite, and a member of the grid `{-3..3 step 0.5}`.
  Missing / NaN / inf / off-grid values are `line_ok=False` and NEVER
  coerced to 0.0 anywhere in the publish path.  The #180 core's internal
  `finite(value, default=0.0)` is only ever reached on publishable rows
  (after the builder's fail-closed gate).
- **same-class sweep**: all line/NaN/finite-default call points —
  `scripts/bj237_power_lib.py::line_is_publishable/line_value` (single
  predicate), `scripts/bj237_build_features.py::build_features` (line gate
  before core call), `scripts/bj237_waterfall.py::build_full_waterfall`
  (fail-closed line stage), `scripts/bj237_verify_package.py::verify`
  (C-01 checks), `tests/scripts/test_bj237_power_features.py::TestFailClosedLineSemantics`.
  #180 core `finite()` default retained (accepted freeze) but unreachable
  for non-publishable rows in this builder.

## 002 — PW06 gates rebuilt from primitives only (C-02)

- **date**: 2026-08-16 (R2 rework)
- **supersedes**: R1's terminal predicate on `P_POWER_BJLINE_available`
- **rule**: Every REQ-PW06 gate is recomputed from source primitives:
  #229 inference cell, `P_POWER_BJLINE` vector presence,
  `P_POWER_BJLINE_observed_at_utc <= feature_cutoff_ts_utc` (decision
  epoch, Asia/Shanghai→UTC), #180 freeze row + complete team_primary
  triplet, exact non-null line equality between freeze source line and
  `BJ_LINE_BOUNDARY`.  Producer-written availability flags are never a
  terminal gate; `same_line` requires BOTH sides non-null.
- **same-class sweep**: all producer-written flag/reason/summary reads in
  the package were audited — `bj237_waterfall.py` (fixed),
  `bj237_build_features.py` (no flag reads), `bj237_verify_package.py`
  (headline recomputed from artifact, not manifest).

## 003 — Aggregation keys frozen (C-03)

- **date**: 2026-08-16 (R2 rework)
- **supersedes**: R1 `(year, league, line)` and `(year, league, outcome)`
- **rule**: `support_summary` key = `(issue, year, league, line)`;
  `calibration_through_2023` key = `(issue, year, league, line, outcome)`.
  `matches` is per-issue `match_idx` nunique (issue is a key member, so
  reused match_idx across issues can never fold).  Every aggregate is
  recomputable from `power_features` (+ labels for calibration); the
  verifier recomputes and compares.
- **same-class sweep**: all window/groupby/aggregate definitions in the
  package (support_summary, calibration, headline, notebook by-year
  tables, REPORT) — key/unit/denominator frozen; cross-layer
  row/count consistency checks added in verifier + tests.

## 004 — Canonical identity consumes #234 interface (C-04)

- **date**: 2026-08-16 (R2 rework)
- **supersedes**: R1 "non-empty string" identity
- **rule**: `fixture_id = fix_{issue}_{match_idx}_{sha256(issue:match)[:16]}`
  per #234 contract; `identity_status` ∈
  {CANONICAL, ALIAS, AMBIGUOUS, UNIDENTIFIED}; team/league aliases
  resolve through temporal validity windows; future alias mutations are
  inactive; duplicate (issue, match_idx) is AMBIGUOUS and never
  publishes; unknown keys are UNIDENTIFIED, never fuzzy-matched.
- **same-class sweep**: all identity/alias joins in the package —
  builder fixture_id + identity_status, waterfall identity stage,
  verifier cross-table identity checks, tests
  `TestCanonicalIdentity` (temporal validity, unknown alias,
  duplicate fixture, future alias mutation).

## 005 — DEBT E-01: remanifested semantic tamper self-defense

- **date**: 2026-08-16 (R2 rework; debt from EV R1 DEBT-LEDGER)
- **status**: CLOSED in R2 (13/13 tamper attacks detected by production
  `verify()` after re-manifest; tests + verifier both enforce)
- **detail**: outcome permutation, legal line rewrite, team swap, league
  rewrite, epoch shift, history depth forgery, outcome domain forgery,
  whole-issue digest forgery, support zeroing, calibration forgery,
  manifest source-hash forgery, schema clearing, file deletion.
  Cross-table anchors (power_p3/p1/p0 in diagnostics, fixture fields
  duplicated), aggregate recomputation, per-issue digest map in
  manifest, file-existence closure.

## 006 — DEBT E-02: immutable publication / schema / receipt closure

- **date**: 2026-08-16 (R2 rework; debt from EV R1 DEBT-LEDGER)
- **status**: CLOSED in R2 (atomic publication via #234 publication
  module; full schema; manifest binds producer HEAD + receipts only
  participating sources; verifier validates source hashes, output
  counts, core blob)
- **detail**: fail-on-existing, same-parent staging, file+dir fsync,
  atomic rename, rollback; `feature_schema.json` covers 4 tables with
  physical/logical types, nullability, domains, FKs; manifest
  `producer_commit_sha` + `source_receipt.databases={xlsm}` only;
  SHA256SUMS covers all files.
