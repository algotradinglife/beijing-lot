## Objective
Conclude whether buying a shorter probability-ranked prefix within each already funded N7 group improves the current SP>=1.30 strategy. Owner requests a bounded conclusion and diagnostic figures directly in chat. No refilling, new groups, model fitting, cleaning, or additional periods.

## Fixed experiment
Use #445 SP130 funded groups and original 200 frozen issues, nine policies, seeds42501/42502/42503, budgets512/768/1024, CNY2 tickets, one ticket-level0.65 actual payout factor. Preserve original groups, probabilities, order, copies and budgets. Savings remain cash. Keep zero-investment issues in every denominator.

Eight predeclared arms: ORIGINAL; cap each group's depth at32,64,128; keep floor(50%) or floor(75%) of its original depth (at least1); stop at the first cumulative probability reaching15% or20%, never extend beyond original depth. No outcome-based threshold/seed selection. No single-ticket expected-return gate: assess whether estimated SP≈inverse probability makes that ranking degenerate.

Freeze shortened funded-prefix decisions and source/code/cutoff receipts before reading labels. Reuse exact #439 frozen full enumeration and #445 original funding manifest; bind legacy audit/rank outputs used for actual settlement. Validate each original prefix coverage/expected return against the frozen control. Independently reconstruct actual winner rank and payout, and reproduce ORIGINAL issue results before comparing cuts. Explicit cutoff maps; shared temporal closure/verification only, no copied learning machinery. Historical admission remains false: exposed research evidence, no causal or unseen claim.

## Diagnostics and verdict
For all200 issues and every paired configuration, show invested/saved cash, net/gross, ROI, hit/profit periods, max drawdown from100000, longest loss streak, 50-period blocks, best1/3/5 removal. Explain whether saved stake outweighs removed winning payouts and how much coverage is forfeited. Group-level fixed rank bands1-15,16-32,33-64,65-96,97-128,129-256,257-512: spent capital, probability mass, expected return, actual winning payout; avoid treating reused groups/configurations as independent matches. Plot capital/drawdown curves, incremental rank-band ROI/coverage, saved stake versus forfeited payout and paired sensitivity. Report all arms, not a selected seed or best historical row. Recommend a specific stopping rule or retain ORIGINAL if no robust tradeoff appears. A negative result completes the task.

## Acceptance
R functions in r/, reusable ingestion/validation in src/ if needed, thin scripts, QMD entry with declared persistent inputs and no output RDS. Every new function has deterministic normal/boundary/failure tests, source and cutoff mutation checks. Independent reproduction/accounting, fresh executed QMD, plots displayed in chat, Codex review, scoped commit/push and associated PR, Project Review; no merge/closure. Record inherited full-suite/data-availability gaps, never claim skipped checks passed. #449/#445 are provenance, not blocking dependencies.

## Implementation and input identities

`n7_prefix_stop` in `r/n7_prefix_stop.R` accepts explicit cutoff maps and fixed rules, validates original coverage/expected gross, and only shortens funded prefixes. `tests/testthat/test-n7-prefix-stop.R` covers fixed cap/fraction/coverage, preserved cash, empty funded periods, wrong cutoff, mixed issue, altered source coverage, invalid rules, and ignored future-label columns on the curve surface.

`n7_prefix_settlement` in `r/n7_prefix_settlement.R` is descriptive post-freeze accounting. `tests/testthat/test-n7-prefix-settlement.R` covers removed winning payouts, retained zero-bet periods, missing ranks and failure to reproduce original payouts. Expected and actual gross inputs already include one0.65 factor; settlement never reapplies it.

`scripts/run_n7_prefix_stop.R` binds the #445 control and all #439/#425/#435 source members, writes group-prefix and disjoint-band plans, and freezes config/cutoffs/code/input hashes before labels. `scripts/settle_n7_prefix_stop.R` checks that rank bytes equal both their own receipt and the #445 reference settlement receipt, then reproduces the original200-period result before evaluating the eight rules. `scripts/check_n7_prefix_stop.py` independently derives all candidate ranks from complete enumerations and actual payouts from bound fixture audit rows, then verifies shortened prefixes, band sums, all period accounting and report summaries. These command entry points are exercised end-to-end on the fixed200-period artifacts.

The shared `src.n7_union_inputs` and `src.temporal_learning` supply input bindings, source cutoffs and transitive Python implementation identity. No new chronology, weighting, fitting or cache implementation is added. Existing `n7_sp_refill_diagnostics`, `n7_sweet_union_summary`, `n7_selection_blocks` and `strategy_equity_curves` provide the report accounting. Legacy market-balance-draw probability packages retain `historical_admission=false`; no availability or prospective-admission upgrade is implied by this deterministic experiment.

Explicit artifacts under the configured persistent data root: control `audits/issue445-low-sp-v2`, catalog `audits/issue439-union-v1/catalog.json`, rank provenance `audits/issue435-rank-return-v1`. The initial prediction attempt v1 failed the source-reproduction assertion before writing a freeze: the batch selected all issues due to an R data-mask variable collision. It was corrected to `.env$issue` and a mixed-issue function regression was added. Only the fully sealed replacement run is admissible for this comparison.

## Reproduction

Use the project interpreter and R libraries explicitly. A config includes `output_dir`, `control_dir`, `catalog`, `rank_dir`, `repository_root`, `python`, `unit_cny=2`, `payout_factor=0.65`, `band_ends=[15,32,64,96,128,256,512]` and the eight rules above. Config is embedded in each prediction freeze; output directories must be fresh. Run from the repository root with matching `RETICULATE_PYTHON` and `PYTHONPATH=.`:

```sh
"$project_python" scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json
Rscript scripts/run_n7_prefix_stop.R CONFIG.json
Rscript scripts/settle_n7_prefix_stop.R "$prediction_dir" "$study_dir"
quarto render quarto/155_n7_prefix_stop.qmd --execute --cache-refresh -P study:"$study_dir"
"$project_python" scripts/check_n7_prefix_stop.py --predictions "$prediction_dir" --study "$study_dir" --repository "$repository_root"
Rscript -e 'testthat::test_file("tests/testthat/test-n7-prefix-stop.R",stop_on_failure=TRUE); testthat::test_file("tests/testthat/test-n7-prefix-settlement.R",stop_on_failure=TRUE)'
Rscript tests/testthat.R
```

## Conclusive result

Retain the original funded depth. Do not introduce a universal prefix-stopping rule from this experiment. All seven shortening rules fail to improve net return in a majority of the81 paired configurations. Lower absolute drawdown generally accompanies less stake and fewer hit periods, rather than demonstrating that the removed tickets were inefficient.

| Rule | Better / worse / same net configurations | Median net change CNY | Median hit-period change |
|---|---|---:|---:|
| CAP32 | 3 / 78 / 0 | -23142.15 | -36 |
| CAP64 | 13 / 68 / 0 | -7932.90 | -15 |
| CAP128 | 27 / 27 / 27 | 0 | -1 |
| HALF | 5 / 76 / 0 | -17000.79 | -26 |
| THREE_QUARTERS | 14 / 67 / 0 | -7938.00 | -12 |
| COVER15 | 6 / 75 / 0 | -17873.45 | -29 |
| COVER20 | 8 / 73 / 0 | -16582.96 | -19 |

CAP128 leaves all BREADTH configurations unchanged because those groups already fit within128 tickets. Benefits concentrate in some DEPTH/COMPETE configurations; other depth policies lose return. It is not a cross-policy improvement. Removing each strategy's own largest1/3/5 profitable periods does not produce a majority-improving rule either. This trimming diagnostic removes different dates for different strategies, not a matched subset of periods.

For the predeclared illustrative configuration (42501,1024,BREADTH/OPEN_FIRST/any_hit), original net is41544.02CNY, ROI23.72%,82 hit periods and maximum drawdown16368.79CNY. CAP64 yields24658.57CNY, ROI18.15%,73 hit periods and11810.59CNY drawdown. The original rank bands33–64,65–96 and97–128 retain positive realized ROI; a lower ticket probability is not evidence of negative actual contribution. Sparse high-return tail bands are descriptive and were not used to create new rules.

## Acceptance evidence and limits

Authoritative prediction directory: `audits/issue451-prefix-predictions-v2`; comparison: `audits/issue451-prefix-comparison-v2`; report: `reports/issue451-prefix-v2/155_n7_prefix_stop.html`. Comparison v1 and v2 have identical result bytes; v2 adds rejection of incomplete variant group sets. Result SHA256: `54c1ff9551955e49cc381bbd7c59e7ccc55a8e044595981f5804b968d6774a9f`.

Independent replay PASS:4800 candidate winner states/payouts,478600 funded prefixes,129600 period results and648 complete summaries. Disjoint band probability, estimated return, actual payout and stake reconcile back to each original group. Source audits are restricted to each source freeze's owned issue list; their snapshots may include other issues, which must not be admitted as duplicate source owners.

Scope tests:15 R assertions and1 Python test pass. Added `verify_summary_grid` (`src/n7_prefix_validation.py`) rejects empty, truncated, duplicate or null-key reports, with `tests/test_n7_prefix_validation.py` regression coverage. First Codex review found missing-variant rows could become fictitious cash-only rows and truncated summaries could pass; both were corrected and tested. The full R suite was rerun and still has6 inherited failures/errors and2 skips: explicit interpreter conflicts in analysis-interfaces/mapping-regression, missing draw-threshold fixtures, missing retraining context/inventory, and unmaterialized pipeline integration bundles. These are not passes, and this scope does not claim repository-wide merge acceptance or full Python-suite/remote CI success.
