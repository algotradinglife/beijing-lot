# Exclude zero-handicap Top2 disagreements before group assembly

User correction: exclude a fixture from the entire candidate pool if its home
handicap is zero AND baseline/market Top2 outcome sets differ. Top1-only
disagreement does not exclude it. Nonzero handicaps stay eligible.
This supersedes the intent of QMD97, which remains an inventoried, differently
specified experiment; it must not be reported as this rule's result.

One new function: `exclude_zero_top2_disagreement(frame, *, cutoffs)` in
src/fundamentals_candidate_exclusion.py. Returns preserved-order prediction frame
and a sealed input/retained hash/count/drop-slot/cutoff ledger. No I/O or learning.
Authoritative rank_double_candidates validates native cutoffs and excludes labels.
W,D,L tie order matches existing selection. Empty retained frame fails clearly.
Tests cover identical sets with different Top1, differing sets with same Top1,
zero/positive/negative handicaps, ties, missing cutoffs, label contamination and
all-excluded failure. The existing portfolio functions are reused without changes.

Existing runner `scripts/consensus_converter.py` accepts
`--exclude-zero-top2-disagreement` at freeze; settle reads the frozen flag.
Both designs use this gate before roles/selection, and cutoffs are subset to retained
fixtures. Original results are hash-bound inventoried evidence, not recomputed
under a changed implementation. Shared transitive implementation closure is bound.
No temporal fitting, cache, recency weights or expert changes are introduced.

Run both freezes BEFORE either settlement:
```
python scripts/consensus_converter.py freeze --design paired --exclude-zero-top2-disagreement --study STUDY/paired
python scripts/consensus_converter.py freeze --design independent --exclude-zero-top2-disagreement --study STUDY/independent
python scripts/consensus_converter.py settle --study STUDY/paired
python scripts/consensus_converter.py settle --study STUDY/independent
python scripts/check_consensus_converter.py --study STUDY/paired
python scripts/check_consensus_converter.py --study STUDY/independent
quarto render quarto/98_candidate_exclusion.qmd --execute-dir . --execute --no-cache -P study:STUDY
```

Fixed exposed48issue diagnostic; all source rows, filters, cutoffs, plans and reports
are bound before label access. Existing audited settlement, one ticket-level .65,
2CNY unit,1024CNY/issue, initial capital100000. Cash held. No score protection.
Paired skeletonU3/P5, independent actualU6/P5. Same ranking/seeds/quota fractions.
Eligibility is changed, so new groups and total exposure can differ.
Historical timestamp proxies do not authorize prospective use or prove simultaneous
ticket availability. #419 remains blocked by #421; no acceptance/closure is claimed.
The independent checker recomputes excluded sets, retained hashes, ensures no
excluded fixture appears in any new role, and verifies tickets/budgets/caps/payout.
Runtime dependencies remain config/compression_breadth_runtime.json.
QMD98 uses existing R reporting functions and declares study/archive parameters.

## Observed results and validation

48issues2561fixtures ->2050 retained,511 excluded. All eight strategy variants
increase net return in this exposed sample, but drawdown does not always improve.

| Design | Before net CNY | Filtered net CNY | Filtered stake ROI % | Before DD CNY | Filtered DD CNY |
|---|---:|---:|---:|---:|---:|
| Paired PRIMARY_FILL |15235.33|19946.49|117.61|2057.14|2057.14|
| Paired MATCHED_PRIMARY |15555.33|20138.49|120.10|2057.14|2057.14|
| Paired COMPLEMENT |15819.53|19707.43|78.75|3113.14|3113.14|
| Independent C000 |16412.41|24713.37|77.70|4416.06|4416.06|
| Independent C025 |10251.36|16681.45|60.48|4865.19|4376.13|
| Independent C050 |1784.96|15592.95|64.20|6212.72|2824.57|
| Independent C075 |3243.44|10229.85|47.22|5936.57|6493.28|
| Independent C100 |-5420.47|2843.25|14.93|8357.29|5685.51|

Filtered paired COMPLEMENT earns431.05less than its MATCHED_PRIMARY control,
despite9more winning groups and2more hit issues. Filtering gains are not proof
that extra converter spend is profitable. No automatic best-policy promotion.

- `python -m pytest tests/test_fundamentals_consensus_portfolio.py tests/test_fundamentals_candidate_exclusion.py -q`:17passed using configured pinned validation Python.
- `python scripts/check_cutoff_governance.py`:PASS.
- Independent checker paired:192rows/1793groups; independent:384rows/2768newgroups.
  Original reference rows verified against bound source bytes, not reported as new model replay.
- QMD98 fresh live and archive renders succeeded, execution enabled and cache disabled.
  Rendered tables16/768/48rows and2images checked programmatically; no pixel inspection.
- Both portable fixtures supplied; CI configured for tests and archive render.
  Remote CI/full repository suite not claimed run. Existing R functions unchanged.
- First Codex review found missing CI fixtures while computation was ongoing;
  fixtures now generated and restore/render validated. Final Codex review confirms P2 resolved: both archives byte-identical and authenticated; reviewer reran17tests and both independent checkers successfully. No remaining actionable finding; it did not rerender or visually inspect HTML and did not make lifecycle decisions.

Inputs: candidate-exclusion-v1/{paired,independent}; archive:
candidate-exclusion-archive-v1/{paired,independent}, under data/derived/fundamentals_417.
Report: quarto/98_candidate_exclusion.qmd. Existing reports95/96 remain archived
historical evidence after runner changes; use their portable archive mode.
