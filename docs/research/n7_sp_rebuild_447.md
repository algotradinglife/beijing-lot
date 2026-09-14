## Objective
Follow the owner-approved first direction after #445: fix estimated SP >=1.30 and test whether rebuilding lost N7 candidate groups improves outcomes. Same exposed 200 issues, frozen market model and European-odds plus totals estimated prices. No expert training, data cleaning or new periods.

## Three paired arms
1. Original24 without SP filtering (exact #445 SP100 control).
2. Original24 with fixture-level SP1.30 filtering and no rebuilding (exact #445 SP130 control).
3. Same SP1.30 fixture filter, retain every eligible original group with its identity, and refill missing candidates to24 using eligible fixtures only. Preserve original global fixture indices and existing group order; new IDs must be distinct. Do not rebuild unaffected issues or increase pool size beyond24. Fewer than24 at a combinatorial/attempt bound is valid and explicitly reported; no invalid fixture may be reintroduced.

Gate price is 1/q for the market-model probability Top1 outcome, stable W,D,L tie order; equality1.30 is retained. Reuse the existing canonical state enumeration, fixture validation, cutoff and provenance machinery. Refill uses fixed-seed Top2-probability-weighted sampling without replacement within each group, unique unordered groups, maximum10000attempts. This isolates refilling rather than adding an extra quality/uniform mixture or tuning thresholds after results.

## Fixed allocation experiment
All three arms use the same nine #445 funding policies, budgets512/768/1024 and seeds42501/42502/42503. Refill seed is the corresponding explicit seed; scenario streams remain separate and unchanged. Keep target25%within256CNY, the original25%/30% reference-derived depth universe, N7, CNY2 physical tickets, no multiple copies and initial capital100000. Retain cash when no eligible affordable candidate exists. No outcome-based parameter choice.

## Settlement and evidence
Freeze all200-issue candidate manifests and selection plans before settlement. New groups must settle from bound fixture-level actual outcomes/SP rather than old sleeve IDs/ranks. Apply0.65 once to the ticket payout. Both legacy controls must reproduce #445; unaffected periods must be exactly unchanged by refilling. Bind raw sources, imported implementation closure, cutoff identities, seeds, eligibility and attempt ledgers, group/state identities and prediction artifacts. Independent replay and an independently coded settlement check are required. Inherited availability limits remain exposed retrospective diagnostics; no prospective or causal-admission claim.

## Outputs and acceptance
Reusable R analysis/functions in r/, Python adapters in src/, thin commands and executed QMD in quarto/. Every new/changed function requires corresponding tests (empty/insufficient pools, no-op, eligibility, uniqueness, seed determinism, index/ID preservation, cutoff mismatch, post-cutoff/label mutation invariance and settlement factor). Report all paired configurations: actual stake, cash, net return, ROI, hit/profit issues, maximum drawdown, longest losing streak,50-issue blocks, best1/3/5 removal; account for candidate/support loss and reclaimed stake. Provide equity/drawdown figures, per-issue changes and opportunity cost. No hidden reallocation of past labels into decisions.

Complete scoped tests, clean QMD render, numeric independent report checking, Codex review, scoped commit/push and PR stacked on codex/445-low-sp-filter. Record inherited full-suite gaps separately; no merge or issue closure. Project BJ Prediction & Betting In Progress -> Review. #445/#443 are provenance, not blocking graph dependencies; do not invent graph edges from narrative references.

## Implementation and replay inventory

The source catalog and #445 prediction freeze bind all 200 issues. Two affected issues are recomputed; the other 198 retain reference plans by hash. Both control arms are copied from the same bound #445 prediction/results artifacts, including all unspent cash. The comparison freeze is written before the settlement entry point reads audit outcomes or control results.

Decision-facing calls are `n7_sp_refill`, `n7_sp_refill_prepare`, `n7_sp_refill_plans`, and their existing gate, capital-option, curve-partition, world-generation and funding-allocation helpers. All receive the source cutoff map. `materialize_refill` uses shared `Cutoff.decision_epoch` and the canonical `enumerate_sleeve`; no independent chronology machinery, fitting, recency weighting, hyperparameter search or label-derived selection is added. The imported frozen baseline remains legacy retrospective evidence, not a new clean historical-learning interface. Transitive Python closure and R source identities are saved before execution and rechecked after it.

Original 25%/30% reference-derived depths remain available to every retained group. A newly introduced group's exact 25% opening depth is added only for that new group. It cannot change retained-group options. Prefix ordering is descending frozen probability, descending frozen expected contribution, then canonical state ID; the independent NumPy checker verifies this exact ordering and separately recomputes its arithmetic from fixture probabilities.

`settle_refill_plans` calls physical-ticket settlement and independently coded sleeve-state settlement. The evaluation receipt binds consumed audit snapshot, audit freeze/receipt, control results/receipt, settlement implementation closure and output bytes; inputs are hashed before use and rechecked afterward. The report verifies consumed byte identities. `check_n7_sp_refill.py` also verifies settlement implementation and independently recalculates the 243 summaries.

Function/test mapping:

| Functions | Tests |
|---|---|
| `n7_sp_refill` | `tests/testthat/test-n7-sp-refill.R` |
| `n7_sp_refill_prepare`, `n7_sp_refill_plans` | `tests/test_n7_sp_refill_bridge.py` |
| `materialize_refill` | `tests/test_n7_sp_refill.py` |
| `check_refill_prefixes` | `tests/test_n7_sp_refill_check.py` |
| `settle_refill_plans` | `tests/test_n7_sp_refill_settlement.py` |
| `n7_sp_refill_diagnostics` | `tests/testthat/test-n7-sp-refill-diagnostics.R` |
| Settlement/check command receipt boundaries | `tests/test_n7_sp_refill_receipts.py` |

The prediction command is `Rscript scripts/run_n7_sp_refill.R CONFIG.json`. Its explicit configuration and every input path are retained in `prediction-freeze.json`; use a new output directory for replay. Settlement is `python -m scripts.settle_n7_sp_refill --refill REFILL --control CONTROL --audit-study AUDIT --output OUTPUT`. Independent acceptance is `python -m scripts.check_n7_sp_refill --refill REFILL --replay REPLAY --comparison OUTPUT --repository ROOT`. Render `quarto/153_n7_sp_refill.qmd` with execution/cache refresh, repository execution directory, and the explicit `study` parameter. Restore the project R/Python environments before running; do not install dependencies during rendering.
