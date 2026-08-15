# Issue #229 R3 handoff

[SESSION] 20260815_150526_cb81c5

- Current delivery HEAD: `PR_HEAD` (resolved to the exact pushed SHA in PR #231
  and the transactional `post_handoff.py` receipt; a commit cannot embed its own
  SHA).
- Rework: `REWORK_TYPE=method`, fresh R3 against EV R2 audited SHA
  `6d198fb7f8ebd72c8904ad80d928fb045088c8ac`.

## Completed

- Closed B1 raw-presence readiness bypass: source identity, observed-at,
  decision epoch and availability masks are published and consumed by every
  divergence/profile/intersection/disposition/handoff path.
- Closed B2 fake-year parsing: development/sealed namespaces join authoritative
  #203 `cell_identity.year`; 243,462 development rows through 2023 and 60,201
  sealed 2024+ rows are independently countable.
- Completed the seven-class sweep in `R3_SWEEP_EVIDENCE.md`, including tests for
  source boundaries, remanifested semantic mutation, atomic publication and
  immediate retry.
- Published a 72-file package with 47 schema-bound tables and a package-only
  independent loader/validator.
- Executed and verified the notebook and immutable package.

## Key decisions and reasons

1. Raw list-vector presence never implies availability. Q_BJ has 353,991 raw
   rows but 228 causal rows; POWER has 4,674 raw rows but 234 causal rows.
2. Missing source observation time remains missing. The decision epoch is never
   copied into an observed-at field.
3. Issue identifiers are identifiers, not years. Label year is sourced only
   from #203 identity.
4. Empty causal intersections are committed as explicit receipts/placeholders,
   not filled or omitted.
5. `PR_HEAD` plus exact code/notebook/dependency hashes avoids the impossible
   commit-self-SHA cycle while allowing the verifier and handoff to bind the
   reviewed commit.

## Verification

- R3 tests: 31 passed.
- Full Issue #229 tests: 56 passed.
- Remanifest/tamper tests: 7 passed.
- Sequential build: 29:20 wall; 2,673,928 KiB peak RSS.
- Notebook: 13/13 cells; 0 errors; 29:16 wall; 2,670,468 KiB peak RSS.
- Final verifier: 72 files match and semantic checks PASS.

## Known limitations and risks

- Disposition is `READY_WITH_EXPLICIT_LIMITATIONS`, not unrestricted ready.
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
| D10 honest readiness | PASS; `READY_WITH_EXPLICIT_LIMITATIONS` |
| REQ-M | N/A; no `method.yaml` in contract tree |

Decision input for PI: whether #209 may proceed under the published causal
limitations, especially only 228 causal Q_BJ cells and zero causal divergence
overlap. No model/data coverage is fabricated.

Explicit review request: EV should independently rerun 87 tests, the seven
remanifest mutations, package verify, notebook 13/13, authoritative label-year
counts, and raw-versus-causal source counts before PI review.
