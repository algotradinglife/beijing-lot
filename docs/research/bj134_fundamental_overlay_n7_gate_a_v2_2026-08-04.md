# #134 replacement Gate A — matched FULL N7 fundamental/decision overlay

> Superseded by the PI Plan-v3 freeze in
> `bj134_fundamental_overlay_n7_gate_a_v3_2026-08-04.md`. This v2 record is
> retained only as a historical, non-authoritative receipt.

## Disposition

This is the replacement outcome-unexposed Gate-A freeze for
`BJ-HIST-FUNDAMENTAL-OVERLAY-N7-001`. It supersedes the obsolete #132-based
surface in closed PR #158. Gate B remains unauthorized pending PI review.

## Exact source binding

- #167 accepted candidate/identity package:
  `bj167_gate_a_strategy_atlas_v3r1`, manifest
  `5a82422755723453638d25c90f91213da046a9e7bed87a851b2e5700faa9c724`.
- #170 accepted BEST_FULL Gate A:
  `bj170_gate_a_preoutcome_v2`, manifest
  `bb60ac5638d29674ad8c1c05f1ffe3ab9cdf12acb70ebdae6cea679743136d87`.
- #170 terminal Gate B is durability-bound only and never parsed: manifest
  `08e83353ad483e5d75911116a413186f007385f5dd37b8c4b757ac903221e512`.
- Historical SQLite SHA-256:
  `7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f`.
  Target rows use identity/rank/handicap-safe columns only. Team-state inputs
  use only matches whose kickoff is strictly earlier than the common frozen
  cutoff for that issue.
- The documented `active_v3.3.3` decision core is byte-bound at
  `50c523ae5441a3018fcc5a175b884a0d887416c99f6b34f9dc72903695adcf92`
  and copied into the immutable package.

## Frozen comparison

The common candidate universe is exact selector
`S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K_ALL`. It contains 348
complete issues, 424 candidate identities in 189 participating issues, and 159
frozen no-bet issues. Its rank-one identity exactly reproduces the accepted K1
BEST_FULL selector in all 189 participating issues and the #170 BEST_FULL
identity freeze.

Four issue-level arms select exactly one identity on that same candidate pool:

1. `MARKET_BEST_FULL`: exact frozen COLD_FIRST order;
2. `FUNDAMENTALS_ONLY`: seven-leg geometric mean of rolling Elo/form/rest
   confidence at the issue's common pre-kickoff cutoff;
3. `DECISION_CHAIN_ONLY`: seven-leg geometric mean of the exact
   `active_v3.3.3` confidence output. Each frozen role reconstructs
   `q=E_SP×q_weight` and `predicted_SP=q/p_model` before invoking the shared
   decision core; this is not a q-max proxy;
4. `FUNDAMENTALS_PLUS_DECISION`: fixed within-issue blend of 0.50 market,
   0.25 fundamental, and 0.25 decision percentiles.

Each selected identity remains `FULL_ENUMERATED`: 2,187 distinct ¥2 tickets,
¥4,374 per issue, and ¥826,686 per arm. Missing fundamentals are retained with
a neutral state and explicit missingness; no candidate is silently dropped.
Target-period home/away rank has no independent observation timestamp in the
source. It is graded `HISTORICAL_TIMING_PROXY`, excluded from all four
controlling arms, and retained only in explicitly named diagnostic fields.
The source has no historical text/intelligence payload, so the decision trace
retains those inputs explicitly unavailable rather than imputing them. The
package emits every reconstructed input, primary/protection decision, advisory
stop and confidence in `decision_chain_trace.csv.gz`.

The freeze also contains 11 exact ablation policies and their 3,828 issue-level
selection rows. They include leave-one-family-out variants for Elo strength,
form and rest in both the fundamental-only and combined views. Gate B therefore
cannot define ablations after outcomes are opened.

## Frozen evidence

- package: `results/bj134_gate_a_preoutcome_v2`;
- manifest SHA-256:
  `ed8ae73827a759ef50e3ca07309b8bf8eb13475ef0e186105b7b9c576ef5ff44`;
- content identity SHA-256:
  `c99334985c22a465a241b37f5718bcab271fe17c9c88e96d300a67f934237e86`;
- rows: 424 candidate identities, 2,968 role vectors, 1,558 target-safe match
  feature rows, 1,558 decision-chain traces, 1,392 primary issue-arm decisions,
  3,828 ablation decisions and 189 issue cutoffs;
- participation per arm: 189 selected / 159 frozen no-bet;
- tests: `pytest -q tests/scripts/test_freeze_bj134_fundamental_overlay_gate_a.py`
  (`7 passed`).

Pre-outcome identity overlap against BEST_FULL is 117/189 for fundamentals,
110/189 for decision-chain, and 168/189 for the combined overlay. These are
selection diagnostics only, not performance findings.

## Gate-B boundary

No target outcome, final/winning SP, payout, tax, ROI, or settlement field was
used or emitted. A later PI-authorized Gate B must report pre-tax ROI first,
per-ticket tax second, support/participation/calibration/hit/GM expected-SP,
threshold and ablation frontiers, stability and concentration, largest-event
and missing-data sensitivity, plus the identity-overlap diagnostics. A positive
historical result requires strict independent EV and held-out/forward evidence;
a negative result cannot demote the accepted BEST_FULL incumbent.
