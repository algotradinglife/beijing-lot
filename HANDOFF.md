# Issue #229 R4 PI takeover handoff

[SESSION] 20260815_150526_cb81c5

- Current delivery HEAD is bound externally by the independent EV
  `AUDITED_SHA`; a Git commit cannot embed its own SHA.
- R4 is a PI-owned candidate-mode correction against R3 audited SHA
  `6c5cdf36ea77d94be1ed69eca50f9d0f6b6accda`.

## Conclusion correction

- Readiness no longer accepts anchor-only support. It requires a causal
  pre-event SP plus at least one independent EU/POWER divergence pair.
- POWER materialization now fails closed when its source handicap line differs
  from the target BJ line.
- Empty chart sources are explicit unavailable receipts, not `BOUND` tables.
- The present package therefore concludes `BLOCKED_DATA_DEFECT`.

## Key decisions and reasons

1. Raw list-vector presence never implies availability. Q_BJ has 353,991 raw
   rows but 228 causal rows; POWER has 4,674 raw rows but 234 causal rows.
2. Missing source observation time remains missing. The decision epoch is never
   copied into an observed-at field.
3. Issue identifiers are identifiers, not years. Label year is sourced only
   from #203 identity.
4. Empty causal intersections are committed as explicit receipts/placeholders,
   not filled, omitted or called ready.
5. Exact review binding is external through `AUDITED_SHA`; package content
   remains bound by code/notebook/dependency/source hashes.

## Verification

- R4 focused/full tests: 92 passed.
- Ruff and `git diff --check`: PASS.
- Sequential build: 29:01 wall; 2,827,008 KiB peak RSS.
- Notebook: 13/13 cells; 0 errors; 29:29 wall; 2,852,356 KiB peak RSS.
- Final verifier: 74 files match and semantic checks PASS.

## Known limitations and risks

- Disposition is `BLOCKED_DATA_DEFECT`.
- Q_BJ causally available: 228 cells.
- Q_EU_BJLINE causally available: 0; P_POWER causally available: 234, but no
  causal overlap with Q_BJ; no causal divergence rows are published.
- Q_BJ_SP_DEVIG causally available: 0.
- REQ-D01 remains False due to 15 post-decision cells, 68,298 missing timestamp
  entries, 37,614 observed-after-epoch feature rows, and 677,394 raw-present/
  no-causal-epoch rows. Available-set violations are zero.
- 2024+ labels remain sealed with zero handoff rows.

## PI acceptance block

| Acceptance criterion | Evidence/result |
|---|---|
| D01 causal provenance | Honest FAIL; masks fail closed; 0 available-set violations |
| D02 identity | PASS; unique package-local `cell_key` and FK closure |
| D03 probability validity | PASS; invalid triplets 0 |
| D04 outcome/line mapping | PASS; float half-goal mapping and explicit failures |
| D05 divergence semantics | PASS; per-cell recomputation; no raw-only support |
| D06 settlement isolation | PASS; authoritative development/sealed split |
| D07 payout boundary | PASS; no payout/tax/0.65 construction in payloads |
| D08 complete profiling | PASS; source×outcome×cohort plus empty receipts |
| D09 schema/provenance | PASS; 47 tables; package-only semantic validator |
| D10 honest readiness | PASS; `BLOCKED_DATA_DEFECT` because required causal intersections are zero |
| REQ-M | N/A; no `method.yaml` in contract tree |

Decision: #209 may not proceed from this handoff. A separate native
data-remediation predecessor must create causal SP-backed divergence support.

Explicit review request: EV should independently rerun 87 tests, the seven
remanifest mutations, package verify, notebook 13/13, authoritative label-year
counts, and raw-versus-causal source counts before PI review.
