# Group-level attribution of N7 exchange gains (#457)

## Scope and conclusion

Describe existing #455 frozen 200 issues only. Three budgets512/768/1024, three seeds42501/42502/42503, JOINT and EXCHANGE11/12. No training, selection, threshold search or new strategy. Source outcomes were already exposed; this is retrospective attribution, not prospective admission. Retain EXCHANGE12 as research preference and JOINT reference; no new feature-based gate is justified.

Fair own-strategy removal of largest1/3/5 positive winning-group net contributions preserves improvement in7/9 EXCHANGE12 configurations (6/9 EXCHANGE11). However, suppressing only the largest added-group payout leaves4/9 positive EXCHANGE12 deltas; suppressing3/5 leaves0/9. The largest three added payouts contribute31.9%–66.7% of added gross. These are different hindsight sensitivities, not deployable rules or independent evidence.

The top five positive winning groups are mostly shared: four common groups in two configurations and five in seven configurations. Symmetric trimming largely removes common profit, so its stability alone cannot establish robustness of incremental gains.

Budget1024/seed42501: added gross15280.114641, forgone gross11054.889530, additional cost66, delta4159.225111. One rescued period contributes2076.448482;82 both-hit periods contribute2104.776629;117 both-miss periods lose22 additional cost. All retained groups have identical stake, coverage, depth and payoff, so zero differential contribution.

Coverage is constrained around25.1% by fixed opening prefixes. Added groups have lower average estimated return per CNY in8/9 configs, and higher average overlap with OTHER original groups in7/9. Neither a high single-group return gate nor lower raw overlap is a consistent explanation. Optimization targets union coverage, not these marginal group features. Do not infer causal feature utility from descriptive averages or nine repeated-history configurations.

## Data and accounting contract

Explicit source manifest: `audits/issue455-exchange-v1/plans-frozen.json`, SHA256 `72f94b727221ad9cb4f09c5e86046b62e273067fe759ad1f6c2f009567708756`. Inputs include separately hashed evaluation receipt, plans/results, settled groups and action log; source memberships are checked against #453 frozen snapshots. Output: `audits/issue457-attribution-v1` and rendered report in `reports/issue457-attribution-v1` on declared persistent root.

Group unit is issue/arm/seed/sleeve, matched across variants within budget. Complete5400 plan grid includes empty plans. Pair3600 exchange plans with JOINT. Join cardinalities and full plan sums must reconcile; retained groups cannot change payoff, cost, prefixes or probabilities. Final-set attribution avoids double-counting temporary intermediate additions. Independent Python replays each logged group-set operation, checks all final sets, overlap arithmetic, delta contributions and both trim definitions.

Fair trim removes positive group net and that group's cost from each scheme separately; it does not recompute bankroll allocation or imply hindsight betting. Adverse trim removes added winning payouts only and preserves all costs. Report each seed separately; overlap makes winning groups dependent. One ticket-level0.65 is already included in source settled gross; do not apply again.

## Functions, chronology and review inventory

- `r/n7_exchange_attribution.R::n7_exchange_attribution`: explicit settled tables, chronology order and trim counts; no IO, learning, ranking for decisions or mutable global state. Tests in `tests/testthat/test-n7-exchange-attribution.R` cover accounting, additions/removals/retention, empty plans, group trimming, adverse payout suppression, duplicate/missing/broken contracts and unchanged retained features.
- `n7_verify_attribution_groups`: reconstructs each group through existing authoritative `n7_quality_settlement` using hashed frozen funded rows and settlement ranks, then checks all group fields. Regression tests reject payout redistribution that preserves issue totals, missing groups/labels and changed ranks; normal and empty cases pass. Added in response to the first Codex review finding that plan-level source replay did not validate individual group payouts.
- `scripts/check_n7_exchange_attribution.py`: thin independent accounting CLI; full-data integration run checks3600 paired plans, source/output/implementation hashes and memberships. No reusable project function is hidden inside the script.
- `quarto/158_n7_exchange_attribution.qmd`: explicit input/output/source replay receipt, calls R function, presents diagnostic tables and five figures, writes machine-readable provenance receipt with code/source/cutoff hashes and parameters. No embedded fitting functions.
- Transitive decision-facing sources remain #455 `n7_group_exchange`, shared `n7_capital_evaluate`, source `n7_core_allocate`, `src/n7_union_inputs` and `src/temporal_learning`. No chronology implementation is copied or new learning introduced. Reuse full #455 source/implementation/cutoff validation and5400 plan/settlement replay before this analysis; descriptive sorting of realized returns is labelled hindsight-only.

## Acceptance commands

Select project Python, R4.6.1/R_LIBS_USER and Quarto1.10.18 explicitly; no environment installation while rendering.

```sh
"$python" scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json
"$python" scripts/check_n7_group_exchanges.py "$source" --settlement > "$source_replay"
Rscript -e 'testthat::test_file("tests/testthat/test-n7-exchange-attribution.R",stop_on_failure=TRUE)'
"$python" scripts/check_cutoff_governance.py
quarto render quarto/158_n7_exchange_attribution.qmd --execute --cache-refresh --execute-dir "$repository_root" -P study:"$source" -P output:"$output" -P replay_receipt:"$source_replay"
"$python" scripts/check_n7_exchange_attribution.py "$source" "$output"
```

Acceptance:23 scoped R assertions PASS; source5400 plan/settlement replay PASS;3600 paired-plan and15356 group-ledger independent replay PASS (including reconstructed per-group settlement, overlap and logged actions); storage/cutoff checks PASS; clean executable QMD render and five inspected figures PASS. Final Codex review has no actionable findings after fixing the group-settlement gap. Review SHA256 `f912b22169d17f5781cb9431ae72b3b1ea69243d66793035f627f6e4da557f1e`. Inherited full-R-suite6 failures/errors and2 integration skips documented since #451 remain out of scope; no claim of all-repository green or merge approval.
