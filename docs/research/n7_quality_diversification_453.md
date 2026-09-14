## Objective and correction to prior proposal
Owner requests a conclusive test of group selection and shared failure concentration. Live #443 already compared summed coverage/CNY with incremental joint coverage/CNY; the currently illustrated BREADTH/any_hit control is already joint-coverage greedy. Reuse these controls rather than rebrand them as new experiments. #427 covers broader atomic reallocation; do not duplicate its depth/exchange search.

## Fixed scope
Same200 exposed frozen issues, original24-candidate catalog, SP>=1.30 fixture gate, N7, CNY2 tickets, one payout-level0.65, budgets512/768/1024, seeds42501/42502/42503. Restrict this selection-only comparison to BREADTH/OPEN_FIRST: each group's existing exact25% opening prefix, qualifying within256CNY, one copy; no deepening, shortening, new groups, refill, training, cleaning or fresh periods. Preserve the existing opportunity admission/initialization if any. Budgets are ceilings; unused cash stays cash. Different chosen groups can have different fixed costs; report these spending differences, do not claim matched actual stake.

Five arms only:
1. Existing #445 SP130 BREADTH any_hit (current joint-coverage control).
2. Existing #445 SP130 BREADTH coverage_sum (standalone efficiency control).
3. NEAR95_UNION: at each step restrict affordable unopened groups to standalone coverage/CNY >=95% of its current affordable maximum, then choose largest incremental union/CNY.
4. NEAR90_UNION: same with90%.
5. NEAR95_OVERLAP: same95% efficiency eligibility, minimize maximum shared-fixture count against a selected group, then mean shared count, then maximize incremental union/CNY. With no selected groups, overlap is zero. This structural-overlap heuristic is not assumed equivalent to failure correlation.

UNION ties use estimated net/CNY, standalone efficiency, numeric group ID. OVERLAP residual ties use standalone efficiency then numeric ID. All rules and thresholds fixed before labels; no optimizing threshold/seed on target outcomes. Recompute admissible band and marginal union after every selection; no affordable candidate means cash. Keep original256 allocation worlds and separate5000 evaluation worlds/seed offset. Preserve fixed prefix identity and source/cutoff maps through shared helpers; no copied chronology logic.

## Tests and diagnostics
Reproduce both existing controls exactly from frozen inputs. Freeze all new plans/source/implementation/config receipts before actual ranks/SP. Compare actual net/ROI, spent/cash, hit/profit periods, drawdown from100000, longest losses,50-period blocks and largest1/3/5-profit-period removal across all9 budget/seed configurations per arm. Trace opportunity initialization, quality-band rejection, marginal coverage, overlap and selections. Diagnose distinct fixtures, pairwise overlap, maximum/weighted fixture concentration, model joint versus summed coverage and actual common failures. Repeated seeds/configurations are not independent samples; no causal or unseen claim. Label/after-cutoff changes must not affect selection, and malformed or missing provenance fails closed.

## Conclusive delivery
Reusable R functions, tests for every new function, independent replay/settlement/accounting and control equivalence, clean executable QMD with declared persistent inputs, diagnostic figures directly in chat, Codex review, scoped commit/push and linked PR, Project Review. Recommend a specific rule or retain current joint-coverage selection; a negative result completes scope. No extra research list in lieu of verdict, no merge/closure or live betting. #443/#445/#451/#427 are provenance/overlap references, not inferred blocking edges. Record inherited suite/data-availability limits honestly.

## Implementation and acceptance map

- `r/n7_quality_allocate.R::n7_quality_allocate`: fixed quality selection; `tests/testthat/test-n7-quality-allocate.R` tests the band, union/overlap differences, cash, empty input, cutoffs and label mutation.
- `src/n7_quality_replay.py::replay_quality`: independent NumPy selector; `tests/test_n7_quality_replay.py` tests fixed-band decisions, overlap, cash, empty input and invalid contracts.
- `r/n7_quality_settlement.R::n7_quality_settlement`: post-freeze accounting; `tests/testthat/test-n7-quality-settlement.R` tests once-only payout, rank boundary, missing/duplicate labels and stake consistency.
- `r/n7_quality_diagnostics.R::n7_quality_diagnostics`: descriptive paired reports; `tests/testthat/test-n7-quality-diagnostics.R` tests ROI, cash/equity origin, rescued/lost periods, weighted fixture concentration, longest loss streak and complete series.
- `scripts/run_n7_quality_selection.R`: prediction-only batch, old-control equivalence, source/code freeze; `scripts/check_n7_quality_selection.py`: all-new-plan independent replay; `scripts/settle_n7_quality_selection.R`: separate label admission and exact old-settlement equivalence.
- `quarto/156_n7_quality_diversification.qmd`: explicit study input, verified identities, reusable diagnostic calls, complete tables and six exported diagnostic figures.

### Transitive decision inventory

The batch calls `n7_capital_options` -> `n7_joint_validate` / `n7_sleeve_tables`, `n7_core_curve_features`, `n7_sweet_union_partition`, `n7_sp_filter`, `n7_core_option_pool`, `n7_joint_worlds`, `n7_joint_returns`, then the existing `n7_core_allocate` or new `n7_quality_allocate`, both checked by `n7_capital_evaluate`. All receive the original explicit cutoff map. No fitting or policy tuning occurs here; the incoming probability model remains frozen diagnostic evidence.

`src.n7_union_inputs.bind_union_inputs` and `verify_union_binding` own source/cutoff/implementation binding, including imported `fundamentals_n7_baseline`, `temporal_learning`, NumPy and pandas. The R source closure is frozen before labels. No local chronology, weighting, partition learning or cross-cutoff cache is introduced. Replay matrices are issue/seed-specific and bound in the freeze; they cannot be silently borrowed from another target. Reporting and settlement are downstream descriptive operations, never callbacks into selection.

## Research verdict

Retain original JOINT marginal-union-per-CNY selection. NEAR95_UNION and NEAR90_UNION improve net in only 2/9 and 1/9 fixed budget/seed configurations, respectively, and neither increases hit periods in any configuration. NEAR95_OVERLAP improves net in 5/9 (median +CNY805.22), but drawdown in only 2/9 and hit periods in 1/9. All three CNY1024 configurations lose net relative to JOINT; CNY512 improves in all three. Removing each strategy's own best three periods leaves 6/9 gains, so this is not simply one-jackpot dependence, but still does not establish a consistent risk/hit improvement.

The quality gate narrows the pool before diversification. Average bought-group overlap across the nine configurations is 4.947 fixtures for JOINT, 5.438 for NEAR95_OVERLAP and 5.491 for NEAR95_UNION. Thus overlap preference helps within the 95% band but does not beat the original unconstrained marginal-union selector. Mean modeled funded-period union is .40317 versus .37887; corresponding observed hit proportions are .40345 versus .38978. These repeated configurations are sensitivity summaries, not independent evidence.

Fixed example seed42501/budget1024: JOINT net41544.02, ROI23.72%,82 hit periods, maximum drawdown16368.79; NEAR95_OVERLAP net38049.98, ROI21.86%,76 hit periods, drawdown16579.60. Actual invested amounts175170 and174058 differ because different fixed-cost groups were selected. SUM improves drawdown in7/9 but net in3/9, with no increase in hit periods; it also does not replace JOINT.

## Execution evidence

Persistent study: `audits/issue453-quality-v1`. Prediction freeze SHA256 `b888c649fb8e4081e8b2fe20556ae59c8cf133a392a2d80b3ec22cbc90994157` binds9000 plans and600 replay snapshots. Exact old-control reproduction3600, independent new selections5400, independent settlement9000 all PASS. No candidate pool, fixed prefix or probability model was changed. Report figures include equity, drawdown, common failures, union calibration,50-period blocks and stake attribution.

Run from repository root with the explicit project Python, R4.6.1 and Quarto1.10.18 environment used in the frozen config:

```sh
"$python" scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json
Rscript -e 'for(f in c("allocate","settlement","diagnostics")) testthat::test_file(paste0("tests/testthat/test-n7-quality-",f,".R"),stop_on_failure=TRUE)'
"$python" -m pytest tests/test_n7_quality_replay.py -q
"$python" scripts/check_cutoff_governance.py
Rscript scripts/run_n7_quality_selection.R "$config"
"$python" scripts/check_n7_quality_selection.py "$study" > "$study/selection-replay.json"
Rscript scripts/settle_n7_quality_selection.R "$study"
"$python" scripts/check_n7_quality_settlement.py "$study" > "$study/settlement-replay.json"
quarto render quarto/156_n7_quality_diversification.qmd --execute --cache-refresh --execute-dir "$repository_root" -P study:"$study"
```

The prediction runner requires a fresh output directory. Settlement can replay identical existing results but rejects changed results. Initial Codex review's three findings were fixed and regression tested: every funded prefix/copy/amount is compared to its option, all604 artifact hashes are required, and post-exhaustion risk/blocks/paired tables now use the actual funded ledger. Targeted tests35 R assertions and4 Python tests pass; cutoff governance passes. Final Codex review found no actionable defects and independently checked the data/claims. Review log SHA256 `9ef1582b9116a5dd3bb1e22906221afc94315aad80f2d46f1836359af3770143`; result SHA256 `3df0117ddbaaf844bd444edf3b1ce50de552c7cd8cfb10a2bf084b247a5930c1`. The delivery QMD records exact commands, outcomes and findings resolved. PR is stacked on `codex/451-prefix-stop` to isolate this research from preceding unmerged studies; this is code provenance, not a newly asserted Issue dependency.

Inherited full-R-suite debt from the immediately preceding #451 check remains outside this change:6 failures/errors (interpreter/reticulate conflicts, missing draw-threshold fixtures, missing retraining context/inventory) and2 integration skips. This is not an all-repository green claim or merge authorization; scope tests and independent study checks are the acceptance evidence for this research delivery. The inherited log is `/home/drwho1985/.codex/review-artifacts/n7-low-sp/prefix-full-r.log`.
