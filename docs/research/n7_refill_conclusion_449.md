## Objective
Owner requests a conclusive answer about refilling, not another list of research directions. Complete a bounded comparison and recommend one deployable rule or explicitly reject refilling under the current evidence. #447/#445 are source provenance, not blocking dependencies. No new periods, training, cleaning or merging.

## Fixed design
Reuse the same 200 frozen historical issues, SP>=1.30 gate, market p/q, N7, CNY2 units, one ticket-level0.65 factor, budgets512/768/1024, seeds42501/42502/42503 and nine original funding policies. Preserve original reference depth grids and use the #447 v3 refill pools (v4 identical replay). These are exposed retrospective data, not unseen/causal historical-learning evidence. Do not optimize rules or seeds against outcomes.

Five arms only:
1. #445 SP130 filter-only with its existing cash (exact control).
2. #447 full-pool refill/reallocation (exact control).
3. Lock every original funded ticket; use remaining cash to open new REFILL_TOP2 groups ranked by standalone coverage per CNY.
4. Same locked original tickets and cash, but rank new groups by incremental joint coverage per CNY relative to all already funded groups.
5. Same as4, but buy only if incremental coverage per CNY is at least the locked original portfolio joint coverage per invested CNY; if original stake is zero, retain cash. This is an explicit probability-efficiency reference, not a fitted threshold or estimated-profit guarantee.

Only new groups introduced by #447 can be added. Use each group's exact25% opening prefix if within256CNY and affordable; one copy, no deepening and no displacement of original tickets. Recompute incremental coverage after every purchase on the existing frozen allocation worlds; evaluate on the separate existing evaluation worlds. Stable tie order by group ID. Insufficient cash/eligible groups or zero incremental coverage means cash. Do not expand beyond these three residual-cash variants. Report that higher coverage can still have negative expected monetary return, especially when p=q.

## Evidence and conclusion
Freeze all target candidate/selection manifests before outcomes; bind source/control receipts, cutoff maps, code/import closure and seeds. Copy198 unaffected issues exactly. Settle new groups from bound actual fixture outcomes/SP and independently check; locked tickets must be a strict preserved subset of final tickets. All budget increases prohibited. Compare all paired policy/budget/seed configurations: stake/cash/net/ROI, hit/profit periods, drawdown, longest losses,50-issue blocks, best1/3/5 removal, additional union coverage and CNY per incremental coverage, and displacement/extra-stake attribution. Distinguish the200-period portfolio denominator from only2 affected historical periods; repeated parameters are not independent observations.

Conclude whether evidence supports refilling, whether preserving original bets cures the observed harm, whether incremental coverage ranks improve actual outcomes, and which exact rule is recommended or rejected. A negative result completes the task. Do not end with further research proposals instead of a verdict.

## Delivery
Reusable R functions/Python adapters with corresponding deterministic, boundary, source-identity, receipt-mutation, cutoff/label-invariance and budget/preserved-ticket tests. Thin scripts and executed QMD with rich paired diagnostics/equity/drawdown plots. Independent replay and numerical/settlement checks; Codex review; scoped commit/push and associated PR; Project Review handoff. Inventory inherited full-suite/availability limits. No PR merge or Issue closure.

## Conclusive result

Retain FILTER_ONLY and unspent cash. Reject automatic refill under this fixed design. Across 81 paired policy/budget/seed configurations, REFILL improves/worsens/ties net return in 0/61/20; STANDALONE and INCREMENTAL each 0/27/54; EFFICIENCY_GATE 0/9/72. Largest incremental net losses are CNY3819.14, 758, 758 and 252 respectively. Locked originals eliminate displacement but do not produce any additional winning return. Added-fund estimated ROI is approximately -33.1% to -35.4%, using frozen estimated SP, not settlement SP. Higher coverage alone is insufficient to recommend spending cash.

Only 100608 and 100711 receive candidate additions; 198 issues are unchanged. These 81 configurations are sensitivity checks, not independent historical observations. This conclusion rejects the specified refill rules on current evidence; it does not establish that all possible refill rules fail.

## Implementation and function/test mapping

| Functions | Test/evidence |
|---|---|
| `n7_residual_refill` | `tests/testthat/test-n7-residual-refill.R`: locked tickets, exact budgets, rank differences, zero gain, gate rejection, cutoff and duplicate failures |
| `n7_residual_plans` | `tests/test_n7_sp_refill_bridge.py`: R/Python JSON round trip, scalar locked-ID regression, post-cutoff/label mutation invariance, full synthetic assembly |
| `n7_residual_efficiency` | `tests/testthat/test-n7-residual-efficiency.R`: paired cost ratios, empty spend versus zero evaluation gain, invalid inputs |
| `check_locked_groups` | `tests/test_n7_residual_check.py`: preserved membership/depth/stake, candidate identity, cutoff |
| `assemble_residual_predictions` | `tests/test_n7_residual_comparison.py`: exact control/unaffected rows, incomplete and duplicate grid rejection |
| `verify_refill_sources`, `verify_paired_audit` | `tests/test_n7_residual_sources.py`: member/receipt drift, relocated identical audit, revised settlement rejection |
| Thin prediction/settlement/check scripts | Two identical 486-plan prediction replays; 486 independent locked-prefix and dual-settlement checks; 81,000 rows, 405 summaries and 243 paired efficiency summaries independently reconciled |

No functions are defined inside the QMD. The report reuses existing #447 accounting and plot functions. The command scripts perform orchestration without new temporal utilities.

## Cutoff and inherited implementation inventory

New allocation functions accept explicit fixture-relative cutoff maps and require exact identity matching with source scenarios. They do not fit, tune, learn thresholds or select seeds. Prefix identities, original funded stakes and separate allocation/evaluation world streams are fixed before settlement. `src.temporal_learning` provides implementation closure, seals and verification; no copied temporal machinery was added.

Inherited R helpers are `n7_sleeve_tables`, `n7_joint_sleeves`, `n7_capital_depth`, `n7_capital_portfolio`; frozen Python closure roots include `src.fundamentals_n7_baseline` and `src.temporal_learning`. Source binding uses `src.n7_union_inputs`; prefix checking and settlement reuse `src.n7_sp_refill_check`, `src.n7_sp_refill_settlement`, and `src.n7_rank_diagnostic`. The source market-balance-draw model and #425/#435/#439/#445/#447 packages are legacy exposed diagnostic evidence. Their historical availability gaps prevent prospective admission; `historical_admission=false` is preserved. Passing label-mutation checks does not repair those inherited gaps.

Frozen manifests contain full config, cutoff maps, transitive implementation hashes and source hashes. Prediction members and control inputs are checked before use and again before finalization. Settlement additionally requires the exact same audit bytes as the reference control; a different internally valid audit fails closed. These safeguards address all three first-review findings, including paired incremental-coverage cost reporting.

## Reproduction and acceptance evidence

The data root is resolved from `config/persistent_data_layout.json`; current explicit artifacts are under its `audits/` directory:

- Original prediction controls: `issue445-low-sp-v2`.
- Refill prediction source: `issue447-refill-predictions-v3`; paired comparison: `issue447-refill-comparison-v4`.
- Residual freeze: `issue449-residual-predictions-v2`; independent replay: `issue449-residual-predictions-v3`.
- Final comparison: `issue449-residual-comparison-v2`; actual audit: `issue425-capital-v2`.

For a new reproduction, extract `config` from the residual `prediction-freeze.json`, supply the current repository/interpreter explicitly, and change only `output_dir` to a fresh directory. Run `Rscript scripts/run_n7_residual_refill.R CONFIG.json` twice with distinct output directories. The scripts refuse output reuse. Then run:

```sh
"$project_python" scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json
PYTHONPATH=. "$project_python" scripts/settle_n7_residual_refill.py --residual "$prediction_dir" --reference "$reference_dir" --audit-study "$audit_dir" --output "$study_dir"
quarto render quarto/154_n7_residual_refill.qmd --execute --cache-refresh -P study:"$study_dir"
PYTHONPATH=. "$project_python" scripts/check_n7_residual.py --study "$study_dir" --predictions "$prediction_dir" --replay "$replay_dir" --reference "$reference_dir" --repository "$repository_root"
"$project_python" -m pytest -q tests/test_n7_residual_check.py tests/test_n7_residual_comparison.py tests/test_n7_residual_sources.py tests/test_n7_sp_refill_bridge.py
Rscript -e 'testthat::test_file("tests/testthat/test-n7-residual-refill.R", stop_on_failure=TRUE); testthat::test_file("tests/testthat/test-n7-residual-efficiency.R", stop_on_failure=TRUE)'
Rscript tests/testthat.R
```

Use configured R libraries and set `RSCRIPT`, `FUNDAMENTALS_PYTHON`, `RETICULATE_PYTHON` consistently with the explicit project interpreter. Actual acceptance used Rscript `/usr/local/bin/Rscript`, Python in the primary repository `.venv`, and Quarto1.10.18. The report was copied to the persistent reports directory and rendered with `--execute-dir` pointing at the repository, execution enabled and cache refreshed.

Scoped checks pass: Python5 tests; R17 assertions; independent check PASS (81000 rows,405 summaries,486 allocation replays,243 efficiency configurations). Result SHA256: `b3a0be38e64270a14fb4fe878f63636756fe71566166c457c5eab8cea9e593d0`; summary SHA256: `599e670c17460eea2b6cc66943e785243efd332679298722d7979976147840a4`. Six equity/drawdown figures and nonempty paired tables are rendered with CNY/probability units.

Full `Rscript tests/testthat.R` does **not** pass: six failures and two skips in inherited tests. Two failures are explicit-interpreter conflicts in analysis-interfaces/mapping-regression; two are missing draw-threshold fixtures; two are missing retraining context/inventory fixtures. The two pipeline integration skips require a materialized integration bundle. These are recorded gaps, not passes; this PR does not modify those components or claim merge readiness for the repository-wide suite. No full Python-suite or remote CI pass is claimed. Review handoff records these gaps in #449 for PI disposition without merging or closing the issue.
