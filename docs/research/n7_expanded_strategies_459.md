# #459: expanded fixed-strategy validation

This study consumes the accepted release published by the data-cleaning session.
It does not collect, clean, adjudicate, retrain experts, or choose new thresholds.
The live Issue Graph owns scope and lifecycle; this document describes the
implementation and evidence, not a replacement control plane.

## Frozen comparison

- Market publication: `markets/releases/market-cleaning-120408-121002-v1/merged.json`,
  SHA256 `629e07fcd5be77428a4344fce4ef4445cf5999b7b45f0213482270817376dda1`.
- Original 200 periods: 100608–110513. Added 295 periods: 110514–121114.
  The union is 495 explicitly enumerated periods, not the entire settlement DB.
  110915 has no eligible market observations and remains an explicit cash period.
- Fixed `market-balance-draw-1.0.0-diagnostic`, same reference training rows,
  learned cells and weights. New cutoff receipts call `src/temporal_learning`
  through `src/n7_frozen_foundation`; no fit, search or new labels are admitted.
- Numeric controls and seven policy identities: `config/n7_expanded_459.json`.
  N7, CNY2 units, CNY512/768/1024 period budgets, seeds42501/42502/42503,
  256 allocation worlds, independent 5000 evaluation worlds, CNY100000 capital.
  Coverage .25 within CNY256 to open each group; one copy; no refill.
- Six arms use estimated SP>=1.30: coverage-sum, JOINT, estimated-return,
  OPEN_FIRST depth, EXCHANGE11, EXCHANGE12. Unfiltered JOINT is the seventh arm.
  Candidate generation stays at the original24 fixture sets and original seed.
- Estimated SP uses European odds and totals. R queries actual northern-single
  settlement SP from the current registered SQLite release. Actual returns
  include exactly one ticket-level .65 factor. Original plans are retained but
  their settlement is rechecked; price revisions are reported separately.

This remains exposed historical research. Published historical quote clocks and
fixture-plus-six-hour reference-label clocks are diagnostic proxies, not observed
prospective availability. No strategy is promoted to deployment by this study.

## Entry points and data flow

All persistent paths and runtimes are explicit runtime configuration arguments.
The output root belongs under the mounted data root's `audits/` directory; HTML
belongs under `reports/`. Run the persistent-layout check before writes and at
acceptance. Runtime configurations and every consumed identity are retained in
the output receipts. Do not select inputs by directory age.

1. `scripts/prepare_n7_expanded_inputs.py CONFIG` verifies accepted releases,
   scope identities and registered archive mappings. It uses shared archive,
   published-market and roster-handicap readers and saves 25-period batches.
   Raw roster receipts are copied byte-for-byte; no outcomes are extracted.
2. `scripts/run_n7_expanded_batch.py PIPELINE BATCH_INDEX` invokes the existing
   R quote adapter and score projection. `bind_n7_expanded_foundation.py` binds
   the unchanged model to each cutoff. The existing candidate builder verifies
   model predictions and generates the same fixture/state universes.
3. `scripts/run_n7_expanded_allocation_batches.py PIPELINE TEMPLATE` dispatches
   at most three R allocation processes. It can verify/resume completed batches;
   partial outputs fail unless explicitly declared as currently running.
   `catalog_n7_expanded_batch.py` binds candidate manifests and source closures.
   `run_n7_expanded_allocations.R` calls existing allocation/exchange functions.
4. `check_n7_expanded_allocations.py` independently reconstructs state prefixes,
   the complete SP-filtered admission/depth universe, projections of shared
   fixture worlds, OPEN_FIRST selection, exchange moves,
   per-group spend and union probabilities in NumPy. Only after every batch
   passes is `all-plans-frozen.json` written. Exact configured world dimensions and
   seed-derived matrices are also replayed through the shared R sampler
   (`replay_n7_expanded_worlds.R`); supplied matrices alone cannot authorize PASS. This phase never queries settlement.
5. `prepare_n7_expanded_labels.py CONFIG` requires that complete freeze. It
   recursively revalidates plan/snapshot files, sources, catalog identities,
   replay/implementation bindings, candidate and model transitive closures,
   projection code, and the entire accepted issue grid before
   opening any outcome; receipt-byte checks alone are insufficient. It
   extracts new roster outcomes with existing parsers and loads original bound
   audit rows. `settle_n7_expanded_batches.R CONFIG` invokes the authoritative
   R five-play SQLite query/audit and candidate-rank functions. DB SHA is checked
   before and after all queries; unresolved observations are retained in status
   output, not fabricated as losses or cash. Funded unresolved groups block
   the complete comparison.
6. `combine_n7_expanded_results.R CONFIG` verifies original frozen source
   bindings and new proofs, then settles the complete31185-plan grid with the
   shared `n7_quality_settlement` function. `check_n7_expanded_settlement.py`
   independently checks native identities, scores, winning option prices,
   actual state ranks, group returns and every plan's accounting.
7. `quarto/159_n7_expanded_strategies.qmd` accepts explicit `study` and `output`
   parameters. It verifies the result receipts and calls reusable R diagnostics.
   It displays per-period tables, cohort/combined metrics, capital/drawdown,
   seed/budget sensitivity, reliability, trims and exchange attribution. No RDS.

## Hypotheses and interpretation

The pre-outcome contract asks whether SP1.30 filtering, joint coverage, depth,
estimated-return ranking and local exchanges retain their earlier advantages
in the added cohort. Compare net profit, ROI, hit/profit periods, cash and drawdown
together. Separate original, added and combined results; do not infer nine
independent replications from three budgets times three seeds.

Own-strategy top1/3/5 profitable-group trimming removes both group profit and
stake. Separate adverse exchange stress suppresses only the largest added
winning gross payouts, retaining foregone original payouts and costs. Neither
is a decision rule. Issue-level trims and fixed50-period blocks are descriptive.

Capital curves use the existing stop-on-insufficient-capital contract. Cohort
comparisons each start from100000; the combined path has one initial deposit.
Unfundable original plans remain available in `planned_`/shadow diagnostics.
Never interpret lower drawdown caused solely by holding more cash as independent
evidence of better selection. Never replace actual payout prices with estimates.

## Checks and function mapping

- New `replay_open_first`: `tests/test_n7_expanded_replay.py`; production
  NumPy-versus-R replay for every new plan. Uses existing exchange/surface checks.
- Independent SP/depth pool reconstruction: `tests/test_n7_expanded_pool_check.py`;
  rejects below1.30 groups, incomplete option universes and unaffordable crossings.
- Seed/count/probability and cutoff replay integration: `tests/test_n7_expanded_worlds.py`.
- New cohort summary and group trims: `tests/testthat/test-n7-expanded-diagnostics.R`.
- Input/catalog/freeze guards and immutable resume: `tests/test_n7_expanded_inputs.py`,
  `test_n7_expanded_catalog.py`, `test_n7_expanded_dispatch.py`.
- Existing shared frozen-model, publication, projection, funding, SP-filter,
  exchange, rank and settlement tests remain authoritative integration contracts.
- Seven arms reproduced the original100608 frozen selections, amounts and
  probability metrics exactly. Its44 fixtures also passed a fresh current-DB
  identity/outcome/SP integration check; no added-period labels were queried.
- Required final evidence: all31185 plans reconciled, new18585 allocations
  independently replayed, clean-session QMD render with cache/freeze bypassed,
  storage/cutoff checks, scoped Codex review, and a linked PR. Full-suite debt
  must be reported explicitly; do not imply a green entire repository or merge.

The transitive historical-learning inventory is unchanged: the shared temporal
context and reference-history/model binder supply cutoff admission, partition,
weights, cache/source/implementation identities and receipts; the fixed draw
predictor supplies probabilities. All allocation callbacks use explicit matching
fixture cutoffs. Reporting, hindsight trims and settlement do not fit/select
future decisions. New pipeline adapters contain no duplicate chronology logic.

## Acceptance command evidence

Project interpreter: Python 3.14 in the explicitly supplied project virtualenv;
R 4.6.1 and Quarto 1.10.18. Dependencies are not installed during execution.
The following scoped checks passed during this run:

```sh
$PROJECT_PYTHON -m pytest -q tests/test_n7_expanded_catalog.py tests/test_n7_expanded_dispatch.py tests/test_n7_expanded_inputs.py tests/test_n7_expanded_pool_check.py tests/test_n7_expanded_replay.py tests/test_n7_expanded_worlds.py
Rscript -e 'testthat::test_dir("tests/testthat", filter="n7-(expanded-diagnostics|market-projection|core-opportunity|funding-modes|sp-filter|group-exchange|quality-settlement|rank-diagnostic|sweet-union-summary)$", reporter="summary")'
$PROJECT_PYTHON scripts/check_cutoff_governance.py
$PROJECT_PYTHON scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json
```

Results: 23 Python tests, 185 R assertions, cutoff governance PASS and mounted
storage contract PASS. `PROJECT_PYTHON`, `R_LIBS_USER` and `RETICULATE_PYTHON`
are explicit environment setup, not inferred during QMD execution.

The requested full `Rscript tests/testthat.R` was also attempted: it failed in
existing tests with interpreter conflicts/missing interpreter paths and missing
historical fixture files (first ten failures included analysis-interfaces,
fundamentals-adjudication, double-policies, draw-signal, draw-tree, ev-returns,
and issue-report; the runner reported 28 further failures). This is not a green
whole-repository run. Those legacy tests and dependencies were not altered by
this research change; scoped test evidence does not erase that acceptance debt.
No remote CI was re-enabled and no merge is authorized by these results.

## Results and decision

All494 candidate-bearing issues settled;110915 remains cash. Independent replay
passed all31185 plans,129833 funded groups and11856 candidate actual-state ranks.
No original200 plan's settlement profit changed against the old snapshot.

At fixed1024/42501, original200 JOINT net41544.02/ROI23.72% falls to added295
net7136.36/ROI2.71%, despite issue hit rate rising41.00% to42.71%. Mean gross
per hit issue fell2642.85 to2150.29; per winning group742.17 to646.63, while
mean period stake rose875.85 to894.24. This is accounting, not causal attribution.

Keep SP1.30 JOINT as the reference. SP filtering saves810 in added-period stake
without changing gross, hits or maximum drawdown; all nine controls improve net
and ROI. SUM and EV each beat JOINT in only1/9 added-period settings. DEPTH buys
six more hit periods but costs21312 more and earns1130.24 less at the primary
setting; its original-period gain does not prove continued return advantage.
EXCHANGE12 adds only5.87 net and one hit period in added295 (ROI slightly lower).
Its combined advantage4165.10 becomes a2572.63 deficit after suppressing only
the three largest added-winning gross payouts. Added-period JOINT loses14941.55
after removing its own three best profitable periods. Thus retain the frozen
reference; do not promote exchange/extra depth or increase budget on these results.
The nine budget/seed settings are sensitivity checks, not independent replications.
