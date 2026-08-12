# HANDOFF — Issue #207 EV round 5

[SESSION] 20260812_204736_734e74

Current branch: `analyst/bj207-active-n7-bankroll-r3` (push target: `analyst/bj207-issue`)

Current HEAD: resolve with `git rev-parse HEAD` after commit.

## Completed

- Fresh-session rework from the latest independent EV REJECT at audited SHA `ef38855194bdacfc213d751a88243a934092b50d`.
- Publication-state full sweep: successful immutable packages now replace `_STAGE_RUN_STATE.json` with frozen `COMPLETED` before manifest creation/fsync/publish; verifier rejects any other state, including a re-manifested `IN_PROGRESS` marker.
- Reason-code full sweep: every zero-funded active branch now distinguishes bankroll below ¥2 (`NO_BET_INSUFFICIENT_CAPITAL`), requested/risk budget below ¥2 (`NO_BET_REQUEST_BUDGET_BELOW_MINIMUM`), and defensive integer-projection infeasibility. Regenerated evidence has 1,665 bankroll-shortfall rows, 524 request-budget-shortfall rows, and zero causal mismatches.
- Required-metric full sweep: `capital_summary.csv` now publishes independently verified rolling 5/10/20 loss probability and deterministic worst-window return/start/end identity (12 explicit aggregate columns), while preserving primitive windows.
- Schema full sweep: audited all 242 published columns. Null units = 0; numeric columns classified as categorical/identifier = 0. Corrected the seven EV examples and added units for all new rolling aggregates.
- Scientific-conclusion full sweep: removed the superseded positive `ACTIVE_OVERLAY_EVIDENCE=true` conclusion and stale values from Research Wiki and roadmap. Current terminal decision remains `ENGINE_VALID=true`, `ACTIVE_OVERLAY_EVIDENCE=false`, `DEPLOYABLE_POLICY=false`; CV_2022 frozen learned choice `BOUNDED_NEURAL`; negative freeze `NATIVE_2_YUAN`.
- Regenerated the immutable 22-payload package and clean-executed the thin notebook.

## Evidence and receipts

- Manifest SHA-256: `07e0298bde5390cf9371fabcf28b874890f2f05b88e5525cc3e952c518dc3558`.
- Artifact counts: 68,880 active requests; 13,560 capital rows; 4,785 matched issue rows; 129,360 matched ticket/tax-lot rows.
- Focused suite: `32 passed in 813.55s (0:13:33)`.
- #206 + #207 regression: `70 passed in 936.33s (0:15:36)`.
- Notebook: `PASS cells=6 executed=6 kernel=python3`; semantic verifier PASS afterward.
- Semantic verifier: PASS with run state `COMPLETED`.
- Independent replay: semantic verifier PASS; `BYTE_IDENTICAL True PAYLOADS 22`.
- Static validation: Ruff, compileall and `git diff --check` PASS.
- Same-category probes: zero-funded reason mismatches 0; schema null units 0/242; numeric-as-identifier 0/242; required rolling aggregate columns 12/12; stale positive conclusion token scan 0.
- Mandatory tamper coverage remains in `tests/test_bj207_bankroll.py`: payout/settlement, accounting-balanced ledger mutation, rewritten manifest/run state, source trace/label/future mutation, plus schema/attribution/provenance/decision/model-choice and atomic interruption attacks.

## Known risks

Sparse N7 payouts, bounded candidate recall, overlap, predicted-SP error, integer allocation, retrospective CV_2022 selection and unresolved accepted Stage-3 baseline. No positive terminal active-overlay evidence was found.

## Next state

Next state must be `EV Review` after final regression and replay receipts are recorded. EV should independently attack publication state, inspect all zero-funded reason classes, recompute rolling loss probabilities/worst-window identities, audit schema units/domains beyond the named examples, and scan every conclusion surface. #208 remains blocked and receives no activation authority.
