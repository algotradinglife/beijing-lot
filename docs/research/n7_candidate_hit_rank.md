# #425 follow-up: actual winning-state rank and candidate cost diagnosis

This is post-settlement diagnosis of the unchanged 100 exposed periods and
2,400 candidate sleeves, not new selection, calibration or a betting strategy.
Raw byte bindings and frozen order are preserved. Per-sleeve ranks are counted
once, not repeated over the three allocation seeds or 68 policy arms.

## Reproduction

With the existing project R/Python dependencies installed, run from repository root:

```sh
quarto render quarto/141_n7_candidate_hit_rank.qmd --execute-dir . --execute --no-cache \
  -P study:/absolute/path/to/audits/issue425-capital-v2 \
  -P python:/absolute/path/to/project/python \
  -P output_dir:/absolute/path/to/new/report-directory
```

The explicit study is the original frozen archive, not a reconstructed or latest
snapshot. The output directory must not already exist. The default portable
allocation archive is the tracked `tests/fixtures/n7_capital_study.json.gz`.
The QMD imports the read-only Python loader with reticulate and performs all
rank/cost and aggregate analysis in R. No RDS or environment installation occurs.

- `src/n7_rank_diagnostic.py::load_rank_issue`: verify freeze/audit and raw/source
  hashes, issue and cutoff agreement; return compact JSON for one frozen issue.
- `r/n7_rank_diagnostic.R::n7_rank_diagnostic`: ordered actual-state identity,
  actual prefix rank/cost, expected rank cost, coverage target costs, actual
  payout/net and break-even depth. Prices and missing identities fail closed.
- `n7_rank_summary`: one row per issue/budget with candidate cost quartiles,
  affordable candidate counts and hindsight opportunity indicators.
- `n7_rank_allocation_check`: reconcile ranks/returns with every original plan,
  including unfunded plans, before reporting the allocation comparison.

Automated tests: `tests/test_n7_rank_diagnostic.py` and
`tests/testthat/test-n7-rank-diagnostic.R`. Checks cover input hashes, missing
identity/SP, handicap conflict, state permutation, exact costs, unsupported
inputs, duplicate rows and actual allocation accounting. An executable row-count
guard prevents an empty or partial comparison from passing rendering.

## Interpretation

An actual rank r has diagnostic prefix cost 2r CNY. This is the cost of buying a
prefix whose boundary is known after observing results; tickets cannot actually
be bought sequentially until a winner appears. The expected rank cost
`sum(p_rank * 2 * rank)` is a model statistic, not a feasible stopping policy or
a recommended budget. Actual gross uses `2 * 0.65 * product(winning SP)` once.

The cheapest actual prefix per issue costs a median 46 CNY, maximum 578 CNY.
At a 512-CNY budget, 99/100 periods have at least one affordable winning prefix;
at 1,024 CNY all 100 do. The exception at 512 is issue 101013 (minimum 578 CNY).
These are outcome-informed upper bounds, not achievable ex-ante hit rates.

At 1,024 CNY the original ANY objective hits a median 65 periods across its three
seeds: 35 missed periods nevertheless contain an affordable winning candidate.
Thus absence of any affordable candidate cannot alone explain these misses.
This does not prove an ex-ante allocator can recognize the correct candidate.

Across all candidates actual hit-cost median is 940 CNY; model expected-cost
median is approximately 1,300 CNY. QUALITY candidate median actual cost is
585 CNY, WEIGHTED 1,067 CNY, UNIFORM 1,160 CNY. These are group-weighted descriptive
comparisons of correlated candidates, not an independent-significance claim or
a policy selected on unseen data. About 95.2% of hindsight boundary prefixes
show positive net; that favorable number benefits from knowing the winning
boundary and must not be advertised as a feasible strategy profit rate.

## Acceptance

Codex review found and then verified fixes for an empty strategy filter and a
missing result-file hash check. Final review reports no remaining actionable
findings, independently reproduces all 24 candidates of one issue and reconciles
all 20,400 original plans. Final clean QMD render and its receipt supply the
execution evidence; the old v1 render is retained as superseded evidence.

Final clean render v3 passed with eight tables and two visually inspected figures.
The new rank-based reconciliation passed all 20,400 plans / 195,362 funded sleeve
rows. The selected comparison contains all 3,600 issue/seed/policy rows and 36
aggregate rows. R tests passed 21 assertions; the Python reader test passed.
The integer-to-character sleeve-key integration fix has a regression test and
final Codex follow-up review reports no actionable findings.

Registered-root output: `reports/issue425-rank-v3/141_n7_candidate_hit_rank.html`,
with `candidate-ranks.csv`, `issue-cost-distribution.csv`, `allocation-gap.csv`
and `receipt.json`. HTML SHA256:
`76876ba0108b1baaca438d3f0132edf030cb1f2625666983f6cf1b843f2c63bd`.
Current QMD/R/reader hashes match the executed receipt. Superseded v1/v2 logs
retain the empty-filter and key-type failures; neither is accepted as the final
report. No original freeze package, probability, allocation or settlement changed.

Top64 average model coverage versus realized frequency is QUALITY 22.6%/23.6%,
UNIFORM 11.2%/10.1%, WEIGHTED 11.5%/11.8%. Thus this particular coverage level does
not show gross average miscalibration, while candidate efficiency differs.
Top128 is also reported. Neither aggregate result establishes calibration of
joint multi-sleeve coverage or ability to choose winners in advance.
