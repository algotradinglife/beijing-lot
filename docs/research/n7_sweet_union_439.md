# #439 N7 joint coverage, depth and matched-budget study

Same 200 exposed historical issues (100608–110513), 24 frozen seven-fixture candidates per issue. No retraining, new collection or cleaning. Candidate eligibility: exact prefix reaching25% or30% model cumulative probability costs at most256CNY. Unit2CNY, one ticket-level0.65 payout factor, initial capital100000CNY. Three fixed scenario seeds42501/42502/42503;256 allocation worlds and5000 independent evaluation worlds. Budgets are ceilings, not mandatory spending.

## Results and interpretation

- Joint coverage alone is not an overall improvement over the old summed-coverage optimizer: target25% BREADTH hits80–82issues versus77 for old SUM, but drawdown is16261–16574 versus14699CNY. Solver and objective both differ; this is not a pure causal isolation of the union objective.
- Group-specific deepening helps target25% coverage more than target30%. At1024, target25% DEPTH has net40871–50857, ROI21.45–26.68%, hit88–92issues and DD14532–16671. Target30% DEPTH ROI13.39–15.63%; more hit issues do not necessarily mean more profit.
- The most promising research follow-up is target25% DEPTH at512CNY: net20221–25977, ROI21.33–27.38%, hit77–83issues, profitable70–74issues, DD6718–8884, actual total spend about94800. Both same-budget original C8 controls spend about101700 and return less net in every seed. DD is usually lower, not strictly better in every paired case.
- Removing each strategy's best5issues leaves388–2975CNY net for the512sweet variant. Both same-budget original controls turn negative after removing their best3issues. Old100ROI8.4–20.1%, new100ROI29.2–40.8%; neither is an unseen test set.
- At768, target25% DEPTH has net30149–45267, ROI21.16–31.74%, DD10512–14096; it does not consistently beat1024 across seeds. Higher total net and lower drawdown remain a trade-off.
- Estimated predecision SP yields negative modeled expected net, while realized settlement net is positive. These are different price quantities; historical positive ROI does not establish positive prospective EV.

Seed42501 comparison (CNY; ROI is net/actual spend):

|Policy|Ceiling|Actual spend|Net|ROI|Max DD|Hit issues|Profitable issues|
|---|---:|---:|---:|---:|---:|---:|---:|
|25% DEPTH|512|94816|20221|21.33%|6896|80|71|
|Original C8, no opportunities|512|101728|12813|12.59%|9284|62|54|
|Original C8,60 opportunities|512|101602|13649|13.43%|7862|66|57|
|25% DEPTH|768|142626|45267|31.74%|10512|86|72|
|25% DEPTH|1024|190512|40871|21.45%|16671|88|71|
|Original C8,60 opportunities|1024|204146|43643|21.38%|12228|99|77|

Original1024 controls are historical seed42501 evidence; smaller-budget controls are newly rerun for all3seeds. No rescaling to imaginary full spending. The report includes all seeds and per-issue ledgers.

## Implementation and evidence

`r/n7_sweet_union.R` exposes prediction-only eligibility and an adapter to the original marginal-union allocator. BREADTH only opens fixed prefixes; DEPTH opens all affordable new groups first, then deepens held prefixes. No copies or U/P hard caps. Shared fixture worlds account for overlapping hit events. Exact candidate depth grids and every action/cash remainder are saved.

Controls preserve the union of legal depths contributed by ALL original policies, including C12, before filtering the evaluated C8 policies. This is essential: a reduced policy list otherwise changes legal actions as well as budget. A saved original shared-depth fixture checks exact funded group IDs/depths; the101121/768 counterexample correctly permits depth93.

`src/n7_union_inputs.py` binds the exact source catalog, rank receipt, original source freezes/seals, probability bundle hashes, source cutoff maps, and transitive Python implementation. It delegates implementation closure to `src.temporal_learning`; it introduces no fitting or temporal-learning machinery. Labels are not loaded until plans freeze. Source/code mutations fail; replay checks exact IDs/depths and allocation-world union coverage. Both runners preserve typed empty no-bet tables.

New source functions and their tests:

- `n7_sweet_union_partition`, `n7_sweet_union_allocate`: `tests/testthat/test-n7-sweet-union.R`.
- `n7_sweet_union_summary`: `tests/testthat/test-n7-sweet-union-summary.R`; shared equity accounting, best1/3/5 sensitivity.
- `bind_union_inputs`, `verify_union_binding`: `tests/test_n7_union_inputs.py`.
- Thin runner/checker integration: `tests/test_n7_sweet_union_replay.py`, `tests/test_n7_union_empty_runner.py` (ineligible batch, unaffordable batch, original cash-only control, saved shared-depth equivalence).

No historical fit is added. Decision path: native `n7_joint_validate` -> shared Cutoff + `rank_double_candidates`; existing `n7_sleeve_tables`, `n7_capital_options`, `n7_core_curve_features`, `n7_core_partition`, `n7_core_option_pool`, `n7_joint_worlds/returns`, `n7_core_allocate/evaluate`. All controls are declared retrospective probes; upstream historical probability packages remain evidence only, historical_admission=false.

## Reproduce / acceptance

Authoritative outputs: persistent `audits/issue439-union-v3/{stage1,stage2,stage3,controls}`. Each includes input binding, exact config/cutoffs/code hashes, frozen predictions/funded/actions CSVs, settlement receipt and independent replay receipts. Source catalog is explicitly `audits/issue439-union-v1/catalog.json`; no directory-age discovery. Earlier v1 is preliminary evidence, v2 interrupted runs are debugging evidence only. Stage1/2 v3 predictions, funding, actions and results are byte-identical to v1 after source-binding hardening.

Run from repository root with configured R library and project Python:

```sh
Rscript scripts/run_n7_sweet_union.R CONFIG_JSON
Rscript scripts/run_n7_union_budget_controls.R CONTROL_CONFIG_JSON
PROJECT_PYTHON scripts/check_n7_sweet_union.py STUDY NEW_RECEIPT_JSON
Rscript scripts/replay_n7_sweet_union.R STUDY NEW_RECEIPT_JSON
```

Every config explicitly supplies source catalog, rank directory, repository root, Python, new output directory, seeds and budgets. Reuse the frozen config with a new output path. For Quarto entry `quarto/149_n7_sweet_joint_coverage.qmd`, supply `stages` (all4v3dirs), `prior_study` (issue437-sweet-region-v1), `rank_dir` (issue435-rank-return-v1), `output_dir` (new report directory). Clean rendering executes analysis with cache/freeze disabled and errors fatal; final report location `reports/issue439-union-v3`.

Validation:17Python regression tests,6cutoff-governance tests,215affected/shared R assertions passed. Commands:

```sh
RSCRIPT=R_SCRIPT_PATH R_LIBS_USER=PROJECT_R_LIBRARY PROJECT_PYTHON -m pytest tests/test_n7_union_inputs.py tests/test_n7_sweet_union_replay.py tests/test_n7_union_empty_runner.py -q
PROJECT_PYTHON -m pytest tests/scripts/test_cutoff_governance.py -q
PYTHONPATH=REPOSITORY_ROOT FUNDAMENTALS_PYTHON=PROJECT_PYTHON R_LIBS_USER=PROJECT_R_LIBRARY Rscript -e "testthat::test_dir('tests/testthat',filter='n7-(sweet-union|core-opportunity|capital-portfolio|capital-depth|joint-sleeves)|fundamentals-equity',reporter='summary',stop_on_failure=TRUE)"
```

The first two broad R attempts lacked the declared interpreter/import environment and failed; configured reruns passed. The unrelated full worktree test suite is not represented as passing. Codex reviews found and drove the depth-universe, provenance and empty-stage corrections; final delivery receipt records final replay/render/review acceptance. No actual betting, issue closure or PR merge is performed.

Final acceptance: all13200 plans passed independent source/budget/settlement checks and full label-free allocation replay. Clean QMD rendering passed with11diagnostic figures; table values matched direct R summaries. Final Codex review returned scoped PASS, independently checking all13200plans and the512-budget/tail claims. Persistent `audits/issue439-union-v3/delivery-acceptance.json` binds final review, tests, report and stage receipts to the delivered commit and PR.
