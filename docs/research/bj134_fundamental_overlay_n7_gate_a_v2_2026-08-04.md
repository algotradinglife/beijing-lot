# #134 replacement Gate A — matched FULL N7 fundamental/decision overlay

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
  use results from calendar years strictly earlier than each target year.

## Frozen comparison

The common candidate universe is exact selector
`S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K_ALL`. It contains 348
complete issues, 424 candidate identities in 189 participating issues, and 159
frozen no-bet issues. Its rank-one identity exactly reproduces the accepted K1
BEST_FULL selector in all 189 participating issues and the #170 BEST_FULL
identity freeze.

Four issue-level arms select exactly one identity on that same candidate pool:

1. `MARKET_BEST_FULL`: exact frozen COLD_FIRST order;
2. `FUNDAMENTALS_ONLY`: seven-leg geometric mean of strictly-prior-year
   Elo/form/rank/rest fundamental confidence;
3. `DECISION_CHAIN_ONLY`: seven-leg geometric mean of the existing maximum
   `q_weight` outcome score;
4. `FUNDAMENTALS_PLUS_DECISION`: fixed within-issue blend of 0.50 market,
   0.25 fundamental, and 0.25 decision percentiles.

Each selected identity remains `FULL_ENUMERATED`: 2,187 distinct ¥2 tickets,
¥4,374 per issue, and ¥826,686 per arm. Missing fundamentals are retained with
a neutral state and explicit missingness; no candidate is silently dropped.

## Frozen evidence

- package: `results/bj134_gate_a_preoutcome_v2`;
- manifest SHA-256:
  `1001ab87115302480306f6b4e44b0d409fc5078b630eab09662b979238eef38a`;
- content identity SHA-256:
  `6ee0ef358ca6230621a8972dd52dbd92eaeaa210218fa6bd7c22859758f3d285`;
- rows: 424 candidate identities, 2,968 role vectors, 1,558 target-safe match
  feature rows, and 1,392 issue-arm decisions;
- participation per arm: 189 selected / 159 frozen no-bet;
- tests: `pytest -q tests/scripts/test_freeze_bj134_fundamental_overlay_gate_a.py`.

Pre-outcome identity overlap against BEST_FULL is 116/189 for fundamentals,
125/189 for decision-chain, and 169/189 for the combined overlay. These are
selection diagnostics only, not performance findings.

## Gate-B boundary

No target outcome, final/winning SP, payout, tax, ROI, or settlement field was
used or emitted. A later PI-authorized Gate B must report pre-tax ROI first,
per-ticket tax second, support/participation/calibration/hit/GM expected-SP,
threshold and ablation frontiers, stability and concentration, largest-event
and missing-data sensitivity, plus the identity-overlap diagnostics. A positive
historical result requires strict independent EV and held-out/forward evidence;
a negative result cannot demote the accepted BEST_FULL incumbent.
