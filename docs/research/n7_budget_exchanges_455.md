## Objective
Test whether budget-aware local group exchanges improve the current JOINT greedy N7 allocation, and conclude adopt a named rule or retain JOINT. The user authorized autonomous research and a conclusive delivery after #453. #424 already used portfolio optimization on a different 8x64 universe; reuse existing infrastructure rather than claim a new optimizer. #443/#453 compared sequential selection/quality gates, not these fixed-prefix local exchanges.

## Frozen scope
Same200 exposed issues, same frozen candidate catalog/market model, SP>=1.30, N7, original25% opening prefixes capped at256CNY per group, one copy, no new candidates/refill/depth changes/retraining. Budgets512/768/1024, seeds42501/42502/42503, allocation256 shared worlds and independent5000 evaluation worlds. Reuse #453 source-bound snapshots, cutoffs and JOINT control; independently reproduce controls before settlement. Preserve original opportunity initialization and never remove mandatory opportunity groups. CNY2 units, initialcapital100000, actual Beidan payout factor0.65 once. Estimated SP remains the European-odds/totals mapped lane.

## Exactly three prespecified allocation arms
1. JOINT: original marginal union/CNY greedy selection.
2. EXCHANGE11: start from JOINT; consider removing zero or one nonmandatory selected group and adding one unselected group, under the original budget.
3. EXCHANGE12: same, but allow adding one or two distinct unselected groups. A removed group cannot be immediately re-added in the same move.

At each step enumerate all legal moves, choose the plan with the greatest total covered allocation-world count. Accept only a strict increase in covered-world count; equal-coverage reshuffles are not accepted. Ties: greater total estimated net, lower total stake, then lexicographically smallest sorted numeric group IDs. No outcome/rank/actualSP input. Recompute after every accepted move; stop when no strictly improving legal move remains. Strict integer coverage gains bound accepted moves by256. Retain cash. Log removed/added IDs, original/final spend, world gain, estimated net and stop reason; compare independent5000-world coverage to detect simulation-specific gains. No tuning of neighborhoods, seeds or thresholds on settlement.

Existing solver n7_capital_solve may be used only for a clearly separate diagnostic optimality bound on the same option pool (no effect on funded tickets), with explicit resource/status reporting. It is not a fourth allocation arm or a requirement to expand the research if local exchanges are unhelpful. Local optimality is not global optimality; fixed256-world improvements are not guaranteed probability improvements.

## Provenance, tests, evaluation
Verify complete #453 manifests and shared src/n7_union_inputs source/cutoff/transitive bindings. Keep all decision-facing calls explicit in cutoff, bind new code/config/source identities, freeze every new plan before opening settlement. Reuse shared temporal contracts, do not implement chronology helpers. historical_admission=false; prior exposure limits claims but does not prevent a completed diagnostic study.

Tests cover constructed greedy failures, 1-to-2 opportunity, exact budget/cash, mandatory groups, empty pools, stable ties, strict monotonicity/termination, labels/post-cutoff mutation invariance and malformed provenance. Independently replay selected identities/prefixes/stakes and actual settlement. Report all5400 plans (3arms x3budgets x3seeds x200), actual spend/cash, net/ROI, hit/profitable issues, drawdown/losing streak, paired rescued/lost periods, model gain versus independent-world gain, overlap/concentration,50-issue blocks and own-best1/3/5 removal. Repeated seeds are sensitivity configurations, not independent samples. Distinguish exposure changes from selection quality.

## Delivery
Reusable tested R functions, authoritative implementation reuse, thin entry scripts, independent replay, executed QMD and inline diagnostic figures, explicit conclusive recommendation, Codex review, scoped commit/push, associated open non-draft PR and verified Project Review. Preserve inherited full-suite gaps honestly. No merge, Issue closure or actual betting. #453/#443/#424 are provenance, not inferred blockedBy dependencies; live native graph governs routing and lifecycle.

## Implemented decision and evidence

Adopt EXCHANGE12 as the preferred version for this exposed retrospective research, retain JOINT as the reference. Net improves in7/9 fixed configurations, median +CNY2008.62 and median ROI +2.16 percentage points. Hit periods improve5/9, drawdown4/9. Own-best1/3 removal retains7/9 gains; own-best5 retains6/9. It is not a uniformly lower-drawdown rule: worst net delta -2705.31, worst drawdown delta +759.93. All512 and1024 configurations improve net, while768 improves only1/3. No additional neighborhood/seed search or prospective release is authorized by this conclusion.

EXCHANGE11 improves net6/9, hit periods5/9, drawdown3/9. EXCHANGE12 changes439/1800 plans, with mean independent-scenario coverage gain .001921 (0.1921 percentage points).110 plans lose independent-scenario coverage despite strict allocation-scenario gains. Mean gains include unchanged plans and do not establish calibration or true-probability guarantees.

Fixed seed42501/budget1024: JOINT stake175170, net41544.02, ROI23.72%,82 hits, drawdown16368.79; both exchange rules stake175236, net45703.24, ROI26.08%,83 hits, drawdown16192.49. Extra stake66CNY does not explain the main gain in this example.

## Function/test and transitive inventory

- `r/n7_group_exchange.R::n7_group_exchange`:18 assertions in `tests/testthat/test-n7-group-exchange.R`, including an actual shared-JOINT greedy trap escaped by1-to-2,1-to-1 improvement, equal-coverage no-churn, ties, cash, mandatory options, empty pools and cutoff/label invariance.
- `r/n7_frozen_scenarios.R::n7_frozen_scenarios`:5 assertions in `tests/testthat/test-n7-frozen-scenarios.R` for empty/singleton matrices, shape, identifiers and cutoff mismatch.
- `src/n7_exchange_replay.py::replay_group_exchange` and `verify_exchange_provenance`:3 tests in `tests/test_n7_exchange_replay.py`, covering neighborhood replay, mandatory options, ties and code/cutoff/source-verifier mutations. Shared `tests/test_n7_union_inputs.py`:5 tests. Combined8 Python tests PASS.
- `scripts/run_n7_group_exchanges.R`:prediction-only batch; source snapshots decoded into existing shared `n7_core_allocate` and `n7_capital_evaluate` contracts. New selector calls have explicit original cutoffs, budget and maximum additions. No new learning or chronology machinery.
- `scripts/check_n7_group_exchanges.py`:complete artifact checks, frozen implementation hashes, shared `verify_union_binding`, exact cutoff agreement, independent group/prefix/amount replay, and optional independently reconciled actual settlement.
- `scripts/settle_n7_group_exchanges.R`:reuse authoritative `n7_quality_settlement`; exact1800 old-control settlement matches. QMD reuses `n7_quality_diagnostics`, `n7_selection_overlap`, `n7_selection_blocks`, `n7_sweet_union_summary` and `strategy_equity_curves`; no copied accounting or chronology functions.

The source closure is inherited from #453 through `src/n7_union_inputs` and shared `src/temporal_learning`: source hashes, source cutoffs, rank receipt metadata and transitive Python/model imports. This study additionally binds its R implementation/decoder/runner and exact source freeze. Existing scenarios are immutable issue/seed-specific evidence, not caches eligible for other targets. The independent checker verifies these bindings again; its first Codex review finding about missing replay-time checks was fixed with mutation regressions.

## Reproduction and acceptance boundary

Study directory: `audits/issue455-exchange-v1`; source: `audits/issue453-quality-v1`.5400 predictions frozen;1800 JOINT controls exactly reproduced; independent5400 plan and settlement replay PASS. Freeze SHA256 `72f94b727221ad9cb4f09c5e86046b62e273067fe759ad1f6c2f009567708756`. Explicit configuration is `config` below; project Python and R library environment must be selected before execution.

```sh
"$python" scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json
Rscript -e 'for(f in c("group-exchange","frozen-scenarios")) testthat::test_file(paste0("tests/testthat/test-n7-",f,".R"),stop_on_failure=TRUE)'
"$python" -m pytest tests/test_n7_exchange_replay.py tests/test_n7_union_inputs.py -q
"$python" scripts/check_cutoff_governance.py
Rscript scripts/run_n7_group_exchanges.R "$config"
"$python" scripts/check_n7_group_exchanges.py "$study" > "$study/selection-replay.json"
Rscript scripts/settle_n7_group_exchanges.R "$study"
"$python" scripts/check_n7_group_exchanges.py "$study" --settlement > "$study/settlement-replay.json"
quarto render quarto/157_n7_group_exchanges.qmd --execute --cache-refresh --execute-dir "$repository_root" -P study:"$study"
```

Prediction outputs require a new directory; settlement repeated execution rejects differing previous rows. Scope tests and cutoff governance pass. No all-repository green claim: inherited full-R-suite6 failures/errors and2 integration skips from #451 (interpreter, threshold-fixture and retraining-context debt) remain recorded in #453 and outside this change. This delivery does not authorize merge. Final Codex review found no actionable defects or narrowed scope, independently reconciling5400 plans/settlements, numerical claims,23 R assertions and8 Python tests. Review SHA256 `741363ff02aa258b768e72ec56834ed9e27acf2fc956375d0e4f97928abe9244`; results SHA256 `76ced155262d14eeefff5c9a723eb71a6e558459ce7c4816efa8d63feffcbfe3`. QMD records the commands and resolved review finding. PR stacks on `codex/453-quality-diversification` solely to isolate this diff from earlier unmerged studies, not to assert an Issue dependency.
