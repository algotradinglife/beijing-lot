# #424: 25% cumulative probability cap and budget recycling

The original strategy buys64 tickets per seven-fixture sleeve and eight sleeves
per issue. This variant keeps the longest probability-ranked prefix whose mass
is at most .25 (maximum64 tickets), requires retained mass strictly greater than
.15, and reinvests saved budget into more distinct sleeves. Fixed CNY1024 budget,
CNY2 tickets and a single complete-ticket .65 payout factor remain unchanged.

## Frozen experiment

- Same100 exposed issues100608–101120; original nested24/240/960 candidate pools,
  calibrated market model market-balance-draw-1.0.0-diagnostic, seeds42401/2/3.
- The original900 expected-gross fixed64 controls are reused byte-for-byte.
  New900 capped plans freeze before this run reads the settlement snapshot.
- Prefix ranking is probability, expected-gross contribution, canonical state ID.
  Do not buy the first state crossing .25 and do not skip it to fill the tail.
- Draw only complete affordable qualifying sleeves, without replacement; weights
  are retained-prefix expected gross, recalculated and normalized after each draw.
  They are not ROI or per-CNY value. Cap allocation changes both depth and weights;
  the comparison evaluates this combined rule, not an isolated depth-only effect.
- At most512 physical tickets; no fixed sleeve-count limit, no extra funds, no
  partial final sleeve. Unaffordable remainder or exhausted candidates leaves cash.
- Shared50000 fixture-world outcomes preserve dependence across overlapping
  sleeves. Sampling and evaluation use independent RNG streams.
- Simulation uses frozen p; estimated ticket payout is2*.65/prod(raw-market q).
  Actual settlement uses the same frozen audit SP. No scraping, expert training,
  historical parameter tuning or target-label-dependent selection was added.

## Interfaces and validation contracts

`src/n7_sleeve_probability_cap.py::sample_capped_sleeves` accepts an explicit
native cutoff mapping, sealed expansion, pool size, lower/upper probability
limits, seed, evaluation count and money constants. It returns a sealed packed
settlement plan, per-sleeve depths/coverage/gross, draw-weight/affordability ledger,
cash reason and shared-world coverage. No I/O or import side effects.

`src/n7_sleeve_cap_check.py::check_capped_plan` independently builds prefixes
using sequential accumulation, replays affordable weighted sampling, checks
packed state identities, budget/cash/expected return and shared-world results.
Original candidate generation and full-state numerics remain bound to the
previous expansion's complete independent verification and source hashes.

`r/n7_sleeve_cap_report.R::n7_sleeve_cap_report` is descriptive funded accounting:
actual stake, cash, sleeve/ticket counts, hit/profit issues, ROI, ex-best ROI,
equity/drawdown and paired active-issue comparisons. It uses shared
`strategy_equity_curves` and `market_conditional_summary`. Initial capital100000,
permanent stop when a planned stake is unaffordable, no subsequent capital injection.

Entry points: `scripts/replay_n7_sleeve_probability_cap.py`,
`scripts/check_n7_sleeve_probability_cap.py`,
`quarto/136_n7_sleeve_probability_cap.qmd`.
Config: `config/n7_sleeve_probability_cap.json`.
Native data: `data/derived/fundamentals_417/n7-sleeve-cap25-v1`.
Report tables/plots: `data/derived/fundamentals_417/n7-sleeve-cap25-report`.

Function tests cover exact cap/floor boundaries, longest prefix, more than8
sleeves, finite-candidate exhaustion, budget remainder, duplicate-free tickets,
evaluation-length/label-free invariance, one-factor actual settlement, invalid
cutoffs and resealed depth/draw/cash/simulation/omission mutations. Runner tests
guard all-plan freezing before audit access and reject source hash/mutation failures.
R tests cover partial stake/cash, ROI, drawdown, ex-best, expanded counts and stop.

## Temporal inventory

Decision-facing `sample_capped_sleeves` takes explicit cutoffs and validates them
through imported `rank_double_candidates`; all source probability calculations
are frozen predecessor evidence. It fits nothing and never loads outcomes.
`settle_single_tickets` is called only after the new complete freeze. Cutoff,
hashes, implementation/dependency closure and verification use shared
`src/temporal_learning`; no separate chronology, fitted cache, partition, recency
weighting, or learning utilities were introduced. R/QMD perform descriptive
accounting only, with their imported implementation files bound in the report receipt.

All new plans and receipts retain `historical_admission=false`. This exposed
historical package lacks complete observed-availability and common pre-ticket
clock proof. Running the comparison does not confer prospective admissibility.
The inverse-q estimate is a price proxy and not official settlement SP.

## Initial result interpretation

Three fixed-seed medians show only a small breadth increase: approximately
8.1 sleeves per active issue, with7–10 issues per100 buying more than8 sleeves.
Many sleeves already have C64 below25%, so their depth is unchanged; small
savings often cannot fund another complete sleeve above the15% floor.

| Pool | Fixed64 ROI | Cap25 ROI | Fixed64 hit issues | Cap25 hit issues |
|---:|---:|---:|---:|---:|
|24|23.03%|14.72%|42|42|
|240|14.00%|10.25%|45|44|
|960|5.99%|7.37%|40|41|

The960 pool improves slightly in this exposed history, while24/240 weaken.
Modeled any-hit coverage slightly declines in all three, so more sleeves alone
does not establish improved combined coverage. Stake and unused cash differ;
the QMD exposes those differences and paired actual investments. No universal
improvement or production replacement is established.

## Required checks

```
python -m pytest tests/test_n7_sleeve_probability_cap.py tests/test_n7_sleeve_cap_runner.py tests/test_n7_sleeve_expansion.py tests/test_n7_sleeve_expansion_runner.py tests/test_n7_sleeve_states.py tests/test_n7_probability_gate.py tests/test_n7_single_ticket_sampling.py -q
python -m scripts.check_n7_sleeve_probability_cap --study data/derived/fundamentals_417/n7-sleeve-cap25-v1
python scripts/check_cutoff_governance.py
Rscript tests/testthat.R
quarto render quarto/136_n7_sleeve_probability_cap.qmd --execute-dir . --execute --no-cache
```

Use the declared project Python/R setup and existing offline R pipeline/next-issue
fixtures. CI runs the new contracts and renders the bound archive fixture, which
is explicitly accounting-only. Native source-bound render and independent Codex
review are separate acceptance requirements.

## Acceptance (2026-09-12)

- Scoped Python contracts:23 passed. R report:10 assertions passed. Full
  `Rscript tests/testthat.R` passed with no failures, warnings or skips.
- Independent full check passed1800 plans (900 new capped,900 immutable controls),
  bound to the preceding96000-candidate verification. Check includes exact prefix,
  affordable draw sequence, ticket identities, expected/actual returns and shared
  fixture-world coverage. Cutoff governance:PASS.
- Clean native and archive QMD executions passed. Five accounting CSVs are
  byte-identical. Native HTML has4 tables and2 figures, no execution errors;
  both equity and drawdown figures inspected.
- Independent Codex review found **“No actionable correctness findings.”** It
  independently reran23 Python tests and10 R assertions, verified306 source
  hashes,1800 plan hashes, implementation closures and native/archive result
  binding. Verdict: historical diagnostic evidence only, no prospective approval.

Evidence prefix: `data/derived/fundamentals_417/n7-sleeve-cap25-` with
`py-tests.log`, `r-suite.log`, `check.log`, `cutoff.log`, `render-native.log`,
`render-archive.log`, `review-result.txt`. Machine-readable acceptance hashes
are in the native study's `acceptance-receipt.json`.
