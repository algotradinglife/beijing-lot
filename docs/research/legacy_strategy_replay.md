# Old N7 strategies, independently retained probability definitions

## Fixed research contract

User requested testing the old rules without forcing a common probability
foundation. This is retrospective diagnosis, not training, unseen evaluation,
or prospective admission. No model is refitted and no best seed is selected.

Market scope: exact 784-issue catalog frozen for joint-full-v3; SHA-256
`b7406c53aec5066e8cb4d7fefcaf737f689567e1555dcb14dce786187448a2e9`.
Eight prespecified arms: RAW/CAL × C1/C2 × U3/U6, pair overlap5,
seed41902, CNY1024/issue, CNY2/ticket, one ticket-level payout factor0.65.
RAW is source q; CAL is source p (frozen calibrated market, **not strength**).
Old pure-market eligibility is retained: no strength consensus, no new minimum
favorite probability and no imported JOINT estimated-SP floor1.3.

Strength scope: the archived updated100-strategies-v1 factors, bound by the
registry migration archive hash
`36efb36bfd983f9cb79c22a1ef30d4329d3f3ef3d70c0b12f3138d419f82420f`.
Prespecified strength C1/C2×U3/U6 plus old consensus C2U3/C2U6.
The archive is historical evidence; it is not promoted to a clean current
fundamentals API. No new collection or cleaning. Missing factor periods are
recorded separately rather than inserted as cash/zero-return rows.
Consensus keeps original 2A/4D/1C roles, agreed Top1≥50% market anchors,
strength Top2 doubles and zero-handicap Top2 disagreement exclusion.

The market C1 extension uses the same purchase engine as C2. Initial groups
are consecutive seven in descending Top2 coverage; highest Top1 inside each
group is contracted. Further groups maximize log Top2 coverage under U/P.
This greedy rule does not jointly optimize which contracted portfolio is best.
No direction replacement, score protection, or extra capital.

## Provenance and chronology inventory

All prediction-only plans are frozen before the settlement phase. Existing
shared Cutoff objects, stable seals, source hashes and transitive implementation
closures are used. Imported `market_foundation_n7`, `n7_single_plan`,
`rank_double_candidates`, `next_overlap_group`, consensus constructors and
candidate exclusion all receive explicit fixture cutoffs. No new learning,
fit, window, receipt or cache machinery is copied. All outputs retain
historical_admission=false: original historical probability artifacts do not
establish source availability before the historical ticket decision epoch.
Later-label invariance is structural for these fixed plans: the freeze commands
do not read settlement. This is not a claim that historical inputs have clean
prospective chronology or that fixture-relative plans were simultaneously bettable.

The independent market checker replays source probabilities, contraction,
Cartesian support and U/P limits without production selection imports. It
does not independently prove MILP optimality. A separate independent ticket
settlement checker recalculates direction from scores/handicap, ticket hits,
SP products and monetary totals without importing production payout code.

## Entry points and function/test mapping

- `src/market_foundation_n7.py`: explicit single_count1/2;
  `tests/test_market_foundation_n7.py`, `tests/test_market_conditional_reuse.py`.
- `scripts/replay_legacy_market_grid.py`, `check_legacy_market_grid.py`,
  `settle_legacy_market_grid.py`: `tests/test_legacy_market_grid_entry.py`.
- `scripts/replay_legacy_strength_grid.py`, `check_legacy_grid_settlement.py`:
  `tests/test_legacy_strength_grid_entry.py` (archive replay, missing factors,
  independent payout and tamper rejection).
- `r/legacy_strategy_comparison.R`: `tests/testthat/test-legacy-strategy-comparison.R`;
  reuses authoritative equity and funding accounting. ROI uses actual stake;
  correlation uses period net returns. Own-best1/3/5 trimming removes both
  stake and proceeds; it does not reroute bets or reconstruct funding stops.
- `quarto/204_legacy_strategy_replay.qmd`: declared external input/proof paths;
  execution enabled, no cache/freeze, fatal errors. All-period ledger is
  continuous from CNY100000; stage ledgers initialize separately. No borrowing,
  no deposits, permanent cash after first unaffordable whole plan.

Cross-probability and cross-pool differences are whole-strategy comparisons,
not isolated causal evidence about the purchasing algorithm. Common-issue
strength comparisons do not imply identical fixture pools.

## Observed conclusion

784 issues: JOINT net CNY53188.68, ROI7.52%, drawdown35125.71. All eight
market C1/C2 arms lose. Best total net among them is RAW_C2_U3, net−69624.15,
ROI−9.06%, drawdown72693.24. It hits435 issues versus JOINT345, showing that
more hit periods do not establish better economics. Its period-net correlation
with JOINT is0.112 and198 hits are unique; low correlation alone cannot justify
allocating capital to a losing strategy. All four C1 arms run out of capital.

Additional300: JOINT−153.64; all eight compression arms remain negative.
Removing each policy's five best periods leaves JOINT+6445.59 and all market
compression arms negative. Neither RAW nor CAL is uniformly superior across
policies/cohorts. The100-issue strength/consensus subset is negative in all six
arms; consensus U3/U6 reproduces archived net−7523.285/−15729.747.
Retain JOINT as research reference; do not promote these old arms or infer that
the probability foundation alone caused their underperformance.

The older117.61% consensus-U3 result in `consensus_n6_n7.md` concerns48issues
100402–100607, outside this784-issue market snapshot. It is not contradicted
by a same-sample rerun here. The replicated archived consensus figures above
refer to the following100issues100608–101120.

Codex review identified chronology and cutoff-map verification gaps in the
independent checkers. Both are corrected with mutation regression tests;
full source-bound proof and payout replay rerun after the fixes. No purchases,
probabilities or settlement values were changed by these verifier fixes.

## Acceptance and reproduction

Published report: persistent root `reports/legacy-strategy-replay-v1/report.qmd`
and `report.html`, explicit `render-params.json`, bound CSVs/figures and evidence.
Market plans6272 / elementary tickets3164640; archived plans600 / tickets257824.
Independent monetary replay verifies all54 full-market summary rows
(9policies × ALL/original/additional × funded/shadow).

Affected Python tests:20 passed. Affected R tests:29 assertions passed.
Cutoff governance and persistent-path contracts pass. Quarto executed in a
fresh R process with cache/freeze disabled and fatal errors; tables and both
images inspected. No remote CI requested. Repository-wide unrelated tests
are not claimed: this shared worktree contains unrelated active changes.

Commands (use the configured project Python/R/Quarto runtimes):

```sh
python -m pytest tests/test_market_foundation_n7.py tests/test_market_conditional_reuse.py tests/test_legacy_market_grid_entry.py tests/test_legacy_strength_grid_entry.py -q
Rscript --vanilla -e 'testthat::test_file("tests/testthat/test-legacy-strategy-comparison.R"); testthat::test_file("tests/testthat/test-n7-purchase-accounting.R")'
python scripts/check_cutoff_governance.py
python scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json
quarto render /run/media/drwho1985/Sandisk/data/beijing-lot/reports/legacy-strategy-replay-v1/report.qmd --execute-params /run/media/drwho1985/Sandisk/data/beijing-lot/reports/legacy-strategy-replay-v1/render-params.json
```
