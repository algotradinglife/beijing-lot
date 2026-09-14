## Objective
Compare low estimated-SP fixture filtering against #443 on the same exposed 200 issues. Owner requests autonomous goal, reusable R/QMD, tests, Codex review and PR. No expert retraining or data cleaning.

## Price and filter contract
Use frozen predecision European-odds plus totals mapped q only. For each fixture choose its probability-top1 outcome (stable W,D,L tie order); estimated SP is 1/q for that outcome, with no leg-level 0.65. Remove the entire fixture when SP < threshold. Thresholds fixed before label evaluation: no filter (1.00), 1.10, 1.20, 1.30, 1.50. Actual Beidan SP is settlement-only; apply 0.65 once per ticket.

## Paired experiment
First retain the identical original 24 candidate groups and remove any group containing a filtered fixture. Preserve fixture indices, scenario RNG and canonical outcome ranking. This isolates filtering; do not silently rebuild missing groups. Record eligible fixtures/groups, high-probability mass lost, no-eligible-group issues and retained cash. Separately assess prediction-only feasibility of rebuilding groups, and report that a fixed-pool filter is not evidence for reconstructed candidates.
Cross all five filter levels with #443 nine policies, budgets512/768/1024 and seeds42501/42502/42503. Fixed N7, unit2CNY, starting capital100000, no copies; preserve complete depth universe and original25%within256CNY gate. No-filter control must exactly reproduce #443. Report all variants, never choose per-issue thresholds from outcomes.

## Evaluation and governance
Report actual stake/net/ROI/max drawdown, hit and profit issues, capital/drawdown curves, threshold sensitivity,50issue blocks and best1/3/5 removal. Include common-issue comparisons and cash accounting so lower exposure cannot masquerade as improved selection. Freeze all selection plans before opening labels; independent prediction replay and settlement checking. Reuse shared src/temporal_learning cutoffs/bindings, no historical fitting. Explicit retrospective-only evidence with inherited chronology limitations.

## Acceptance
Automated tests for each changed function, no-filter equivalence, boundaries/ties/invalid SP/empty admissible pool and post-cutoff mutation invariance. Clean executed QMD with reproducible explicit paths and receipts, Codex review, scoped commits/push and PR, Project Review handoff; no merge or closure. #443 provides frozen evidence and is not an execution blocker; no new dependency edge inferred merely from provenance.

## Implementation and run inputs
The shared runner requires `minimum_sp` on every policy row. Unfiltered means explicit1.00; no hidden default. `n7_sp_filter()` returns fixture and group ledgers plus a filtered admission partition. It never rebuilds candidates, alters fixture indices or reads settlement. Original core depth grid is constructed before filtering.
Input: the explicit #439 catalog and #435 rank receipts used by #443. Completed calculation outputs are in the immutable issue445-low-sp-v2 audit directory on the declared mounted data root; v1 preserves the deliberately aborted pre-settlement attempt. Run/check/replay commands are the same shared entry points as #443, with the new45-policy configuration stored inside plans-frozen.json.
All5 gates ×9 policies ×3 budgets ×3 seeds ×200 issues =81000 plans.

`n7_sp_diagnostics()` exposes the descriptive table contract (summary, curves,
50-issue blocks, per-issue ROI, admission losses, paired differences, common-staked
issues). It does not learn/select anything from results. Gate and diagnostics
functions are covered by tests/testthat/test-n7-sp-filter.R and
tests/testthat/test-n7-sp-diagnostics.R. Checker integration tests deliberately
rehash incorrect admission, forbidden funded groups and changed controls to prove
semantic checks go beyond file-hash equality.

Current validation commands (project environment must already be configured):

```sh
Rscript -e 'testthat::test_file("tests/testthat/test-n7-sp-filter.R"); testthat::test_file("tests/testthat/test-n7-sp-diagnostics.R")'
RSCRIPT=/absolute/path/Rscript /project/python -m pytest tests/test_n7_funding_runner.py tests/test_n7_sp_filter_checker.py tests/scripts/test_cutoff_governance.py
/project/python scripts/check_n7_sp_filter.py /absolute/study /absolute/issue443-control /absolute/new-check-receipt.json
```

## Exact within-issue computation equivalence
For each issue, cutoff and seed, policies with identical admitted partition,
mode, objective and allocation order share one deterministic computation.
Every original policy row still expands into its own plan, diagnostic threshold,
funded rows and actions. This is exact equality, not approximate grouping or a
cross-cutoff cache. n7_sp_policy_groups tests preserve row identities, reject
cutoff mismatch and distinguish changed candidate sets/objectives. The model
replay checks every expanded plan; the Python checker separately reconstructs
all gates and binds each arm to its frozen threshold.
The initial unoptimized run was deliberately stopped after10issues before
any settlement evaluation; its aborted receipt is preserved in v1. Complete
research outputs use issue445-low-sp-v2.
