# #134 Gate A — fundamental and decision-chain overlay for matched FULL N7

## Status

This is the outcome-unexposed Gate-A freeze for `BJ-HIST-FUNDAMENTAL-OVERLAY-N7-001`.
Gate B is not authorized. The package is a paper-research input, not a betting,
production, purchase or promotion artifact.

## Frozen boundary

The candidate universe is the immutable complete-issue FULL N7 identity set from
#132 (`SHA256SUMS.json` manifest
`6583503ee80fd2b40bb1c000917ff094afa0551b6a3f0af4b8d175a6432872f9`). No
candidate search, source segment, deletion rule or ticket-allocation mechanism
was reopened. There are 52,534 portfolio identities across nine #132 threshold
variants, covering 10,334 unique target matches and six target years (2020–2025).

Every arm ranks the same portfolios within the same complete `(issue, fold)` and
variant. The fixed K surface is `{1,2,4,8,16,ALL}` FULL identities. A K that
cannot be met is an explicit `NO_BET_K_UNSATISFIED` row; no borrowing, cap
relaxation or cross-issue allocation occurs. Each selected identity has 2,187
FULL tickets at ¥2 per ticket, so matched arms have identical issue-level stake.

## Pre-registered arms

1. `MARKET_E_SP_GM`: existing market-only geometric mean of per-leg E_SP;
2. `FUNDAMENTALS_ONLY`: geometric mean of past-only fundamental confidence;
3. `DECISION_CHAIN_ONLY`: geometric mean of existing `q=p×predicted_SP` q-max;
4. `FUNDAMENTALS_PLUS_DECISION`: within-issue percentile score
   `0.50 market + 0.25 fundamental + 0.25 decision`.

The fundamental state is an expanding calendar-year timing proxy. For target
year `y`, only rows with `season_year < y` update the state: fixed-K Elo with
home advantage and goal-margin cap, rolling ten-match points/goal-difference,
rank differential, rest and history depth. The target query selects only match
identity, timestamp, league, team IDs, ranks, native line and year; target
score/result/final-SP/settlement columns are not selected. Missing team IDs or
history produce neutral probabilities plus an explicit missingness field rather
than silent row removal.

## Deliverables

`results/bj134_gate_a_preoutcome_v1` contains the feature scores, portfolio
scores, complete threshold census, four-arm K frontier, ablation card, source
census, runner and manifest. The package manifest is
`51f5323f48e8851f030e022a16e62edf46622dc01b8d2b22202b7f9b23f8ddf4`.

Generation and replay both produced 52,534 portfolio rows, 59,304 frontier
rows and 10,334 target feature rows with identical manifests. The structural
counts are pre-outcome diagnostics only; no ROI, tax, payout or settlement
claim is made at Gate A. Any later positive same-window result requires strict
independent EV and held-out/forward validation.
