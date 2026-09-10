# Pure baseline C1/C2 comparison (#419)

This closes the missing no-expert control in QMD75. Its BASE meant no repeated
double replacement, not no experts. QMD76 separates model from support policy.

## Fixed comparison

Use the exact accepted `new48-expanded-validation-v1/projected` snapshot:
48 issues100402–100607,2561 fixtures. The pure p distribution is the saved raw
home/away-history score grid, summed into handicap W/D/L. No expert prediction,
expert projection, model loading, or refitting enters that path. q remains the
same Euro+OU market score projection used by the expert version. Settlement is
the same accepted2561-row R/SQLite audit. No collection or SP query is repeated.

Expert comparison: frozen draw1.1.0/high0.1.0, both weights0.5. This is a matched
post-exposure retrospective diagnostic, not a new holdout. Historical clocks
remain proxies. Later source-order/clock-adjudication releases from another
session are excluded to preserve the previous comparison's exact fixture pool.
No strategy is automatically promoted from this ranking.

Pure and expert each choose their own fixtures, single positions and groups.
Thus their difference measures the full prediction-to-ticket procedure, not
an expert perturbation on identical selected groups. Within each model/case,
all nine replacement rules preserve that case's original groups/stake/cash.
Budget1024 per issue, unit2, N7, payout0.65 once per winning basic ticket;
no correct-score protection. All original seeds, candidate pools, thresholds,
disjoint-prefix policy, rankings and STRICT/FREE overlap rules remain fixed.

## Results

Budget ROI denominator:48×1024=49152. Drawdown is chronological issue-end P&L,
initial capital100000. Counts below are variants, not independent observations.

|Compression|Pure positive /36|Expert positive /36|Pure better /36|Pure positive after largest-profit issue removed|
|---|---:|---:|---:|---:|
|C1|2|0|36|0|
|C2|22|11|26|18|

|Case/rule|Pure net CNY|Pure budget ROI|Max drawdown CNY|Net excluding largest-profit issue|Expert net CNY|
|---|---:|---:|---:|---:|---:|
|D2 TOP2 FREE BASE|23809.10|48.44%|9842.01|10911.14|2993.85|
|D2 COMPRESSED FREE BASE|17703.46|36.02%|9842.01|4805.50|3660.55|
|D2 TOP2 FREE GAP02|14071.83|28.63%|12278.07|5069.99|3727.60|
|D2 COMPRESSED STRICT TV15|10196.32|20.74%|6614.54|6710.61|-3377.37|
|D2 COMPRESSED STRICT GAP05|7890.61|16.05%|3937.32|4902.55|-11825.61|
|D2 TOP2 FREE GAP10|2494.73|5.08%|9286.40|-2726.52|12036.56|

Pure D2 TOP2 FREE BASE wins50/768 groups versus40/768 for the same expert policy.
Pure is better on62/72 variants, but not universally: the expert GAP10 rule wins
that paired comparison. The two positive C1 cases are TOP2/COMPRESSED STRICT
GAP05, both net304.37, ROI0.62%; removing their largest-profit issue makes them
negative. This does not support generalizing the best observed profit to new data.

## Reuse and acceptance

- `r/fundamentals_pure_baseline.R::pure_baseline_factors` projects saved grids,
  verifies cutoffs/identities/normalization/handicap outcomes, and preserves IDs.
- `src/fundamentals_compression_variants.py::build_compression_variants` composes
  existing N7, bridge, replacement and scenario implementations; forecast-only
  inputs and explicit cutoff/money/seed/threshold parameters are required.
- `settle_compression_variants` delegates physical ticket payout to the existing
  settlement implementation; incomplete/ambiguous labels fail closed.
- Existing R `expanded_variant_comparison` provides paired risk/ROI summaries;
  BEFORE means expert and AFTER means pure in this report, not chronology.

Function tests map to `tests/testthat/test-fundamentals-pure-baseline.R` and
`tests/test_fundamentals_compression_variants.py`. The builder reproduces existing
reference plans exactly; tests cover both compression depths, money, label
rejection, cutoff failure, settlement mutation, missing SP, and identity errors.
Archive restoration is exercised by the existing N7 parametrized entry test.

`scripts/check_pure_baseline.py` independently reconstructs pure p from raw saved
grids, checks unchanged q, replays base selections, manually rebuilds all physical
tickets and replacement gates, and checks shared scenarios and SP payouts across
all3456 results. No pending result is converted to a loss or zero.

Entry sequence: `prepare_pure_baseline.R`, `pure_baseline_variants.py freeze`,
`pure_baseline_variants.py settle`, `check_pure_baseline.py`, then
`package_pure_baseline_report.py`. Source identity, fixed parameters, implementation
closures, report code and original frozen plans are receipt-bound. No RDS output.

```sh
quarto render quarto/76_pure_baseline_variants.qmd --execute-dir . --execute --no-cache
python scripts/prepare_n7_single_fixture.py --fixture tests/fixtures/pure_baseline_report.json.gz --output /path/pure-report
quarto render quarto/76_pure_baseline_variants.qmd --execute-dir . --execute --no-cache -P study:/path/pure-report -P archived_report:true
```

The report includes all72 paired strategies, cash/actual-stake and budget ROI,
drawdown/concentration sensitivity, tibble structure/head, and3456 issue rows.
Full computation requires the declared accepted source snapshot; the portable
fixture replays the report only. Local acceptance and Codex review logs are kept
in `data/derived/fundamentals_417/new48-pure-baseline-report-v2/acceptance.json`.

Codex found a P2 in the draft report: the copied freeze ID did not bind the
packaged results file. Report v2 binds its exact result bytes inside a canonical
sealed receipt, checked by `r/fundamentals_pure_report.R::read_pure_baseline_report`
in both render modes. Its mutation regression is
`tests/testthat/test-fundamentals-pure-report.R`. A consistent gross/net edit now
fails before analysis. Draft report v1 is unaccepted; all pure probabilities,
frozen plans and audited returns remain unchanged.
