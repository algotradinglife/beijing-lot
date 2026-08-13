# HANDOFF — Issue #207 EV round 7 (REWORK_TYPE=method, fresh mode)

[SESSION] 20260813_203002_8b88b7 (analyst profile, fresh run, no resume)

Current branch: `analyst/bj207-issue` (updates PR #226)
Audited base: `6b82aa757527e8efb9398e1822d45d073dbdf4f6` (R6 delivery head, EV R6 REJECT)

## What was implemented (R7)

Fresh-session rework closes the EV R6 REJECT at `6b82aa7` with full
same-category sweeps. The three R6 blocking defects and their root causes:

1. **Defect 1 — illegal settlement values entered the evidence chain
   (验证盲区 / settlement domain).**
   - `labels_available.astype(bool)` silently coerced `NaN` and the string
     `"False"` to `True`, so historical rows with missing/malformed availability
     passed `_validate_candidates()` and `replay_path()`.
   - `realized_gross` was never domain-validated; a negative gross multiple
     produced a negative `gross_payout_yuan` that entered replay, ledger,
     drawdown, matched lift and decision artifacts and was wrapped as
     `ENGINE_VALID=true`.
   - Fix: new `_coerce_nullable_boolean()` enforces the nullable-boolean domain
     (`True/False/0/1/null` only; strings and out-of-domain values fail with
     `Stage4Error`); `_validate_settlement_domain()` requires settled rows to
     carry finite non-negative `realized_gross` and unavailable-label rows to
     carry no settlement value; `replay_path()` rejects negative payout
     (`Stage4Error("negative payout")`) after the finite check.

2. **Defect 2 — seven-cell source trace validated shape only, not per-cell
   consistency (schema/trace relationship).**
   - The trace loop checked length/field presence but never bound
     `cell.match_idx == match_indices[i]`, `cell.outcome == outcomes[i]`, or
     the `ticket_identity[i] == f"{match}:{outcome}"` encoding.
   - Fix: per-cell checks now enforce match_idx equality, outcome equality and
     the ticket-identity encoding for every cell; match identity uniqueness
     (already shape-checked) is now also confirmed per-cell; ordering is
     enforced by index alignment.

3. **Defect 3 — malformed JSON not mapped to Stage4Error (异常归一化).**
   - `json.loads(source_cells_json)` leaked `JSONDecodeError`.
   - Fix: `JSONDecodeError` → `Stage4Error("malformed source_cells_json")`; the
     same-category `decision_trace_json` parse in `_trace_frame()` is wrapped
     identically.

## Same-category sweep evidence

Committed at `docs/research/issue_207_r7_sweep_evidence.md`: category-by-category
call-point inventories (验证盲区 nullable-boolean / settlement domain /
schema-trace relationship / 异常归一化), per-call-point verdicts, and the
executable tests added. Highlights:

- All public-input `astype(bool)` uses on `labels_available` removed
  (`_validate_candidates` + `replay_path`); remaining `astype(bool)` uses are
  internal derived columns owned by the producer and semantically replayed by
  the verifier.
- Settlement domain validated once at the public boundary before
  reconstruction; replay additionally fail-fasts on negative payout.
- JSON parsers on public inputs (`source_cells_json`) and derived traces
  (`decision_trace_json`) both normalize to `Stage4Error`.

## Tests added (R7)

All in `tests/test_bj207_bankroll.py`:

- `test_candidate_validation_rejects_non_nullable_boolean_availability`
  (NaN/"False"/"True"/"false"/2/0.5/"yes")
- `test_candidate_validation_rejects_invalid_realized_gross`
  (NaN/+Inf/-Inf/-1.0/-0.001)
- `test_candidate_validation_rejects_settlement_gross_on_unavailable_labels`
- `test_candidate_validation_rejects_ev_probe_all_cv2023_unavailable_negative_gross`
  (EV R6 auditor probe regression)
- `test_candidate_validation_rejects_per_cell_source_trace_inconsistency`
  (match_idx mismatch / outcome tamper / duplicated match / identity mismatch)
- `test_candidate_validation_rejects_malformed_source_cells_json`
- `test_replay_rejects_negative_payout_from_negative_gross`
- `test_semantic_verifier_rejects_remanifested_nullable_boolean_and_negative_gross`
  (verifier mutation: NaN label + negative gross, trace tamper, malformed JSON,
  each re-manifested → semantic REJECT)

## Terminal decisions (unchanged from R5/R6)

- `ENGINE_VALID=true`, `ACTIVE_OVERLAY_EVIDENCE=false`, `DEPLOYABLE_POLICY=false`
- CV_2022 frozen learned choice: `BOUNDED_NEURAL`
- Negative freeze: `NATIVE_2_YUAN`
- SAFE NO_BET/cash: `LOWER_EXPOSURE_ONLY`

## Evidence and receipts (after regeneration)

- Regenerated immutable 22-payload package: 68,880 active requests; 13,560
  capital rows; 4,785 matched issue rows; 129,360 matched ticket/tax-lot rows.
- Semantic/hash verifier: PASS — manifest SHA-256
  `48c11d971c20cb2239cd342ade4084bea484686bd106253c77a320ba7ae78ab6`.
- Focused #207 suite: `65 passed in 934.43s (0:15:34)`.
- #206 + #207 regression: `103 passed in 1090.75s (0:18:10)`.
- Notebook clean-run: PASS (6/6 code cells; verify cell binds manifest
  `48c11d97…`).
- Fresh-dir replay: PASS — `run` + `verify` into `/tmp/bj207_replay_r7`;
  22/22 payloads byte-identical, manifest identical
  (`48c11d97…`).
- Static validation: ruff PASS, compileall PASS, `git diff --check` PASS.
- Tamper classes (mandatory + R7 additions): NaN/"False" availability,
  negative/non-finite gross, per-cell trace inconsistency, malformed JSON —
  all rejected by `_validate_candidates` with explicit `Stage4Error`;
  re-manifested verifier mutations rejected semantically.

## Known risks

Sparse N7 payouts, bounded candidate recall, overlap, predicted-SP error,
integer allocation, retrospective CV_2022 selection and unresolved accepted
Stage-3 baseline. No positive terminal active-overlay evidence. The stricter
domain validation does not change decisions on the frozen #206 source.

## Next state

Next state must be `EV Review` after the full validation matrix completes.
EV should independently rerun the R6 probe scenarios (NaN/"False" availability,
negative/non-finite gross, complete-but-inconsistent traces, malformed JSON),
attack the verifier with re-manifested settlement/trace tamper, and rerun the
mandatory tamper classes plus byte-identical replay at the new exact HEAD.
#208 remains blocked and receives no activation authority.
