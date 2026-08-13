# HANDOFF — Issue #207 EV round 6 (REWORK_TYPE=method)

[SESSION] 20260813_134000_r6  (engineer kanban t_6ac59904; fresh-session run, no resume)

Current branch: `wt/t_6ac59904` (push target: `analyst/bj207-issue` updates PR #226)
Audited base: `120022c8d7bf484e039822f01a3dcf39f9463cf3` (R5 delivery head, EV R5 REJECT)

## Completed

- **Defect 1 — `minimum_fundable_capital_yuan` metric semantics (EV R5 §1)**:
  `src/bankroll_policy/fixed_n7.py` no longer hardcodes `TICKET_STAKE` for every
  row. New helper `_minimum_fundable_capital_yuan(fraction, exogenous_schedule)`
  returns `TICKET_STAKE / risk_fraction` for self-funded risk-fraction controllers
  (1%→200.0, 5%→40.0, 25%→8.0, 100%→2.0), `TICKET_STAKE` for native/no-fraction
  and for exogenous matched-schedule replay (the schedule fixes the request).
  Regenerated ledger: 10,170 previously-wrong risk-fraction rows corrected;
  13,560-row ledger fully matches the golden table.
- **Defect 2 — `log_joint_probability` schema unit (EV R5 §2)**:
  `_schema_catalog()` now declares explicit unit
  `natural_log_dimensionless_probability` and domain `(-inf, 0]` for
  `log_joint_probability` instead of the fallback `fraction`. The frozen #206
  source (`src/ticket_policy/fixed_n7.py`) and `results/issue-206/` are
  untouched. Regenerated `schema.json` reflects the fix.
- **Sweep A — fundability/metric semantics**: call-point inventory =
  producer (`replay_path` requested/budget/min-fundable), reason-code
  (`_zero_funding_reason`), projection (`_project_counts`), summary
  (`_path_metrics`), schema catalog, verifier (re-derives via `replay_path`).
  Golden tests for risk fractions {1%,5%,25%,100%}, native/no-fraction, and
  zero/below/exact threshold boundary added to `tests/test_bj207_bankroll.py`.
- **Sweep B — schema/verification blind spot**: independent 242-column audit
  matrix committed at `tests/fixtures/bj207_schema_audit_matrix.json` (unit/domain/
  nullability/dtype/PK/FK/relationships for every published column), with a
  golden test that compares `schema.json` to the matrix WITHOUT reusing
  `_schema_catalog()`, plus a probability/log/odds/return/rank/count/economic
  field-level spot-check across all tables.
- Regenerated the immutable 22-payload package with the R5-lineage Python
  3.11.15 venv (provenance environment consistent with audited lineage).

## Evidence and receipts (to fill after validation)

- Manifest SHA-256: `ce93583f768bbffdc9167e3d0d037916fec7c69d8eea95ddea8a5eb65f6694ba`.
- Artifact counts: 68,880 active requests; 13,560 capital rows; 4,785 matched
  issue rows; 129,360 matched ticket/tax-lot rows.
- Focused suite: PASS 44/44 (run 314) and re-confirmed within 82/82 regression (run 315).
- #206 + #207 regression: PASS 82/82 in 962.42s (run 315, final state incl.
  relocated matrix fixture).
- Notebook clean-run: PASS (6/6 code cells; verify cell binds manifest
  `ce93583f…`, timestamps 2026-08-13T06:34Z, unchanged by R6 relocation).
- Semantic verifier: PASS (in-place, after regeneration).
- Independent fresh-dir replay: PASS — `run` + `verify` into
  `/tmp/bj207_replay_r315`; SHA256SUMS.json byte-identical and all 22 payloads
  byte-identical to committed package; verify status PASS manifest
  `ce93583f…` (68,880 requests / 13,560 capital rows / 4,785 matched issues /
  129,360 matched tickets).
- Static validation: ruff PASS, compileall PASS, `git diff --check` PASS.
- Same-category probes: 30/30 PASS on final relocated fixture — min-fundable
  golden 13,560/13,560; schema audit matrix 242/242 (11 tables);
  log_joint_probability unit/domain/data ≤ 0 verified; zero-funded reason
  partition complete with 0 causal mismatches; 87/87 matched groups; 13,560-row
  conservation; no top-up; integer ¥2 tickets.
- R6 relocation fix: audit matrix moved `tests/data/…` (gitignored, never
  committed) → `tests/fixtures/bj207_schema_audit_matrix.json`; all references
  updated so a clean checkout passes the golden schema audit test.

## Terminal decisions (unchanged from R5)

- `ENGINE_VALID=true`, `ACTIVE_OVERLAY_EVIDENCE=false`, `DEPLOYABLE_POLICY=false`
- CV_2022 frozen learned choice: `BOUNDED_NEURAL`
- Negative freeze: `NATIVE_2_YUAN`
- SAFE NO_BET/cash: `LOWER_EXPOSURE_ONLY`

## Known risks

Sparse N7 payouts, bounded candidate recall, overlap, predicted-SP error,
integer allocation, retrospective CV_2022 selection and unresolved accepted
Stage-3 baseline. No positive terminal active-overlay evidence.

## Next state

Next state must be `EV Review` after the full validation matrix completes
(downstream cards: test-engineer validation, then PR/EV-review delivery).
EV should independently recompute min-fundable per risk fraction, audit the
242-column matrix and `log_joint_probability` semantics, rerun the mandatory
tamper classes and byte-identical replay at the new exact HEAD. #208 remains
blocked and receives no activation authority.
