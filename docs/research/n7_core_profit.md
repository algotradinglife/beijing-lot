# Probability core + profitable supplement exploration

Goal: test physical CNY2 tickets under the existing CNY1,024 N7 budget, not the
non-executable half-ticket scaling from QMD132. Initial capital CNY100000, one
ticket-level payout factor 0.65. No expert retraining or actual-SP selection.

## Fixed research contract

100 previously exposed issues100608–101120, count gate5/10000, existing depth2048
candidate union and market-balance-draw-1.0.0-diagnostic probabilities. Seeds41901,
41902,41903; training20000/evaluation50000 simulated worlds. All 3300 portfolios
freeze before the runner reads its settlement snapshot. Ratios .25/.5/.75, 16
random proposals plus one PROB proposal per greedy step, 1024 two-for-two attempts,
and payout stress .8/1/1.2 are fixed in advance of this run, not selected by ROI.

- PROB/PROFIT controls preserve prior ticket identity and simulation rates.
- FIXED locks the top PROB core, supplements from PROFIT in probability order,
  then PROB if needed. This is a physical-ticket union, not an arithmetic mixture.
- GAP locks the core and greedily fills using newly profitable world count,
  capped recovery gain, expected payout, then canonical ticket id as tie-breakers.
  Final stake remains the target even when the portfolio is still being built.
- JOINT starts from GAP, exchanges two non-core tickets, and accepts profit-count
  increases or ties with increased capped recovery. Core tickets cannot move.
- Complete duplicate tickets prohibited; seven distinct fixtures within every
  ticket; reuse of fixtures across different tickets unrestricted.

Neither bounded proposal search nor joint swaps are claimed globally optimal.
Stress scenarios affect evaluation only. A common haircut is a coarse payout
sensitivity check, not a full model of SP error or team/league dependence.

## Results and interpretation

Three-seed medians, stake102400 in every policy:

| Policy | ROI | Profitable issues | Max drawdown CNY | Longest losing run | Ex-best ROI |
|---|---:|---:|---:|---:|---:|
| PROB | 52.98% | 17 | 20641 | 11 | 5.82% |
| PROFIT | 26.09% | 23 | 14311 | 10 | 5.76% |
| FIXED25 | 39.04% | 21 | 17071 | 10 | 16.57% |
| FIXED50 | 46.75% | 19 | 17059 | 17 | 10.97% |
| FIXED75 | 49.27% | 18 | 18098 | 10 | 9.81% |
| GAP25 | 28.47% | 17 | 17403 | 10 | 2.32% |
| GAP50 | 32.44% | 16 | 18884 | 19 | 2.28% |
| GAP75 | 47.55% | 16 | 20274 | 11 | 9.14% |
| JOINT25 | 36.22% | 17 | 18382 | 11 | 5.95% |
| JOINT50 | 35.44% | 16 | 19231 | 19 | 2.48% |
| JOINT75 | 44.96% | 16 | 20228 | 11 | 8.82% |

FIXED50 retains 88.2% of PROB net with 17.4% less drawdown, but its longer losing
run is a material downside. FIXED25 has stronger ex-best returns. Neither dominates
both controls. Independent simulated profitable probability rises from FIXED25
15.11% to GAP25 15.76% and JOINT25 15.90%, while actual profitable issues fall.
Optimization success under estimated p/q is not proof of improved real returns.

FIXED25 adds on average4.75 fixtures outside PROB versus GAP25 9.91. Greater breadth
did not automatically improve actual profitable frequency. PROB and PROFIT share
only16.5 complete tickets on average. Unique-ticket gross is not incremental net:
the portfolio also displaces profitable PROB tickets. Paired wins/losses are reported.

## Provenance, shared interfaces and availability gap

Current root only exposes five calibrated prediction exports, all belonging to
existing market-strength/market-balance studies; the admitted comparison is the
same100 issues, not a newly sealed unseen-period dataset. Native live graph reads
confirm #419 blockedBy #421 and #421 blocking #419. No closure or prospective
promotion is requested. Clean cross-year/new-issue acceptance remains outstanding
under #421; this exploration is complete retrospective evidence only.

Transitive decision inventory: `core_profit_plans` -> `select_probability_gate`
-> `rank_double_candidates`, shared native Cutoff validation, and shared stable
hash/implementation closure. Pool construction remains the previously frozen
`probability_gate_candidates` artifact. Old market calibration is exposed evidence;
this client adds no direct historical fit, temporal partition or source admission
machinery. It does not convert old diagnostic timestamps into observed availability.
Each plan binds native fixture cutoffs, pool and control seals, parameters and RNG;
global receipt binds all sources, plans and transitive implementation. Cache reuse
across altered source/code/cutoff fails the inherited seal/closure checks.

`src/n7_core_profit.py::core_profit_plans` is the reusable label-free search API;
`r/n7_core_profit_summary.R::n7_core_profit_summary` performs descriptive funded
accounting using the existing authoritative equity and summary functions. Tests map
to `tests/test_n7_core_profit.py` and `tests/testthat/test-n7-core-profit-summary.R`.
Inputs/outputs, money units, empty results, invalid contracts and side effects are
documented in their functions. Changing held-out sample size/stress leaves tickets
unchanged in tests. No new dependencies or imports with I/O.

## Reproduction

```
python -m scripts.replay_n7_core_profit --output <new-output-directory>
python -m scripts.check_n7_core_profit --study data/derived/fundamentals_417/n7-core-profit-v1
python -m pytest tests/test_n7_core_profit.py tests/test_n7_profit_periods.py tests/test_n7_incremental_coverage.py tests/test_n7_probability_gate.py tests/test_n7_single_ticket_sampling.py -q
Rscript -e 'testthat::test_file("tests/testthat/test-n7-core-profit-summary.R",stop_on_failure=TRUE)'
python scripts/check_cutoff_governance.py
quarto render quarto/133_n7_core_profit.qmd --execute-dir . --execute --no-cache
```

Configured runtime: project Python .venv; R4.6.1 with project `r_lib`; Quarto1.10.18.
Independent checker verifies exact3300-grid, every actual ticket payout and locked
core, unchanged controls and direct held-out union/profit/stress simulation. Native
report verifies source, implementation, checker and diagnostic bindings. The archive
fixture supports accounting-only CI rendering and is visibly labeled as such; it
cannot certify original source chronology. Full repository tests are outside this
bounded change; relevant direct dependencies are tested.

Acceptance: 22 focused Python tests and 48 relevant R assertions passed; cutoff
governance passed. All3300 independent ticket/payout/core checks and direct held-out
profit/union/stress replay passed. A rehashed report-rate tampering regression is
rejected against the sealed plan. Native and archive QMD renders execute in fresh
processes; their accounting tables match. Equity/drawdown panels are inspected.
Codex algorithm review passed; final audit found report-rate binding and aggregation
label gaps. Both were corrected, the binding regression added, and the final label
verification returned no findings. One review attempt hit model capacity and was
rerun successfully. This accepts the retrospective exploration, not #421's clean
new-issue/cross-year acceptance or closure of #419.
