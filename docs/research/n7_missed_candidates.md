# Cheapest winning candidates in missed #425 periods

Scope: unchanged exposed 100-period, 1,024-CNY experiment, baseline
`NONUNIFORM_ANY_ROI_NONE_B1024`. No new training, tickets, fitted routing or
probabilities. Reuse original 17 frozen alternatives for matched rescue/loss
comparison. Every alternative includes the same issue/seed grid; ROI uses
actual stake and cash-only policies have NA ROI.

## Findings

Seed 42501 misses35periods:20 have no cheapest candidate funded,15 fund at least
one cheapest candidate but insufficiently deeply. Seeds42502/42503 respectively
miss33/38, split19/14 and19/19. Across seeds there are106missed issue-seed records,
not106distinct historical periods. All tied minimum-cost candidates are retained;
109candidate records comprise61unfunded and48underdepth entries.

Unfunded cheapest candidate median model Top64 rank is15of24; underdepth median
is17.5. Their median actual winning ranks are75and71. Median exact additional
costs are150and98CNY; registered-grid top-ups are192and144CNY. These costs must
be funded by cutting other allocations, not by injecting extra budget. Median
maximum overlap with other funded sleeves is2; redundancy is not established
as the principal explanation. This is diagnostic association, not reconstructed
solver causality. Individual high-model-rank exclusions need joint marginal
coverage/search analysis; this report does not invent that evidence.

Seed42501 examples:

| Issue/sleeve | Model Top64 rank | Actual winning rank | Bought depth | Exact top-up | Grid top-up |
|---|---:|---:|---:|---:|---:|
|100713/21|24|13|0|26|32|
|100703/22|20|42|32|20|32|
|100908/8|13|16|8|16|16|
|100817/4|4|116|96|40|64|

On the SAME seed42501, baseline hits65periods. Fixed depth64 hits61, rescues10
and loses14; depth256 hits60, rescues9 and loses14; coverage0.1 hits58, rescues9
and loses16. Across seeds, the original alternatives' median hit counts do not
exceed the baseline's65. Reporting rescues alone would hide the tradeoff.
Seed medians of hits/rescues/losses are separate summaries, not necessarily an
arithmetic identity. The QMD includes all per-seed and median figures and ROI.

## What could select them

A hindsight forced allocation trivially identifies some inexpensive fixes, but
it uses actual winners. The tested fixed-depth/coverage alternatives select some
of them using frozen model inputs, at a cost to other periods. They do not yet
supply a demonstrated hit-rate improvement. The inexpensive-winner identity
must never become an ex-ante feature or same-period policy router.

A uniform16-ticket floor across24groups costs768CNY (75%of1024), yet the missed
periods' cheapest winning rank median is about73. An8-ticket floor already costs
384CNY. Thus blanket exploration can consume most of the budget without reaching
many of these winners. A future bounded test could compare model-only exploratory
allocation with more optimization worlds/search effort, across ALL periods with
rescues, losses, returns and drawdown; no such new policy is claimed tested here.

## Interfaces and reproduction

`r/n7_missed_candidates.R`: `n7_missed_candidates` returns all candidate funding,
tied cheapest missed candidates, exact/grid top-up costs, pre-result model ranks
and descriptive overlap. `n7_missed_comparison` returns per-policy/seed matched
hits/rescues/losses/actual spend/net/ROI. Neither function learns or selects bets.
`tests/testthat/test-n7-missed-candidates.R` tests ties, underdepth, zero funding,
replay identity, incomplete comparisons, integer sleeve IDs, string fixture-slot
contract, cash-only ROI and regression against summarise column shadowing.

```sh
quarto render quarto/142_n7_missed_candidates.qmd --execute-dir . --execute --no-cache \
  -P rank_dir:/absolute/path/to/reports/issue425-rank-v3 \
  -P output_dir:/absolute/path/to/new/report-directory
```

The rank directory's CSV and receipt hashes are verified. The portable archive
is bound to the same original freeze. All20400plans/195362allocation rows are
reconciled before diagnosis. Outputs are descriptive CSVs and a receipt;
functions reside in R, and the QMD imports them. No RDS or automatic dependency
installation. The first render failed closed when readr inferred numeric types
for comma-separated fixture slots; the explicit character schema and regression
fix preserve their identities. That failed render is not acceptance evidence.

Final acceptance:16R assertions passed; fresh QMD render v2 passed (six tables,
one visually inspected figure). Codex review found no actionable findings and
independently checked complete17×100×3comparison coverage plus20400plan replay.
No remote CI or lifecycle changes. Output is registered-root
`reports/issue425-missed-v2/142_n7_missed_candidates.html`, with all candidate,
cheapest missed, period and matched-alternative CSV ledgers and a source-bound
receipt. Reproduction consumes the prior diagnostic receipt and original portable
freeze; it never rewrites those inputs.
