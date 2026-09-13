# Issue 437: coverage/cost region stability

This is an explicitly retrospective study of the same 200 exposed issues,
100608–110513. It does not fit, calibrate, tune or retrain a probability model.
The candidate probability artifacts remain historical evidence, not prospective
admission. A best historical grid cell is not a deployed policy.

## Contracts and reuse

- `n7_sweet_points`: exact target crossings through `n7_capital_resolve`.
  Frozen curves carry the original probability ordering and expected gross.
- `n7_joint_validate`: shared native `Cutoff.decision_epoch` and the existing
  `rank_double_candidates` input validation boundary. No copied chronology code.
- `n7_sweet_allocate`: explicit cutoff maps, 1024 CNY ceiling, CNY2 units,
  fixed target/cost/U/P parameters. HiGHS solves a binary fixed-input problem;
  sum of sleeve coverage is a proxy objective, not joint hit probability.
  Prediction columns are whitelisted exactly; result-bearing input fails.
- `n7_coverage_summary`, `n7_sweet_diagnostics`: descriptive candidate statistics,
  chronological blocks and removal of entire high-net issues.
- `n7_sweet_overlap`: counts shared fixture identities without inventing an
  effective number of independent bets.
- `strategy_equity_curves` and `market_conditional_summary`: existing bankroll,
  cash, drawdown and best-issue accounting. No forced reinvestment or deposits.

## Historical-learning inventory

No new historical-learning function is introduced. The only optimization is
the per-issue binary purchase problem on already frozen predictions, with all
business parameters passed explicitly. No labels enter its objective, costs,
eligibility or constraints; no prior/future labels choose its parameters.
The parameter grid is a post-hoc diagnostic, not a training/validation split.

Transitive Python roots are `src.n7_rank_diagnostic` and
`src.fundamentals_n7_baseline`; the shared `implementation_closure` receipt
records their imported implementation graph. The latter imports other research
modules, but this path calls only its prediction/cutoff validation function.
The original frozen studies retain producer/model/source provenance.
R source hashes and original per-issue cutoff maps are bound in
`plans-frozen.json`. Each issue's source/evaluation bytes are verified by the
existing frozen reader. There is no newly learned artifact or learned cache.

Actual outcomes were historically exposed. The runner discards the source
reader's audit component, validates prediction-only fixtures, generates all
points and plans, seals them, and only then joins the separately hash-verified
rank labels. This sequencing is not a claim of unseen data or observed source
availability. No later labels rewrite the frozen plans. The allocator's exact
column whitelist prevents outcome columns from entering its public interface.

## Acceptance mapping

- `tests/testthat/test-n7-sweet-region.R`: exact crossings, cutoff mismatch,
  optimal feasible selection, budget, pair overlap, empty eligible pool,
  result-bearing column rejection and fixture identity failure.
- `tests/testthat/test-n7-sweet-diagnostics.R`: blocks, whole-issue removal,
  duplicate/missing scope, pair overlap and empty/single-group behavior.
- Existing depth, equity and conditional-summary tests cover imported contracts.
- `scripts/check_n7_sweet_region.py`: independent stdlib verification of all
  5,400 plan constraints and settlement totals, 81,600 prediction point keys,
  source hashes and one-time payout accounting through immutable rank labels.
- `scripts/replay_n7_sweet_allocations.R`: fresh-process replay of all 5,400
  allocations using only frozen prediction points and cutoff/fixture metadata;
  no rank or other label file is read. Every selected ID and stake must match.
- Clean QMD execution exports 12 labeled plots and tidy CSV summaries. No RDS.

The new 27 fixed-budget probes are not the existing core allocator under a new
name. They buy one target prefix per group and maximize summed group coverage
subject to U/P constraints. Controls retain the old union-coverage allocation
and original fixed seed. Differences in spending, idle cash and objective must
stay visible when comparing ROI, absolute profit and drawdown.

## Reproduction

Run from the repository root with the declared project Python and R environment:

```sh
Rscript scripts/run_n7_sweet_region.R CONFIG.json
python scripts/check_n7_sweet_region.py STUDY CHECK_JSON
Rscript scripts/replay_n7_sweet_allocations.R STUDY REPLAY_JSON
quarto render quarto/148_n7_sweet_region_stability.qmd --execute-params PARAMS.json
```

`CONFIG.json` declares three frozen input study paths, the prior rank receipt,
all 17 target probabilities and all 27 fixed budget policies. The accepted copy
is embedded in the study freeze. `PARAMS.json` supplies `study`,
`prior_rank_dir` and `output_dir`. Check the persistent layout contract before
writes. The study directory is new and cannot overwrite an existing freeze.

Plots and result tables are descriptive historical evidence. The final review
must not treat a high ROI from limited spend as dominance over a nearly fully
invested control, or treat correlated candidate groups as independent trials.
