# Uncapped N6 versus original N7 (no replacements)

Same 48 issues, 100402–100607; retrospective exposed-data diagnosis only.
N6 uses two singles and four baseline Top2 doubles, CNY32 per group and
CNY1,024 issue budget. Existing consensus assembly is reused without changes:
two A anchors, three D agreed doubles, one C disagreement double. Exclude
zero-handicap Top2 disagreements. First build disjoint groups, then expand with
pair overlap at most five. No experts, replacements or score protection.

The integer reuse bound passed to the existing interface is 32, the maximum
number of affordable groups. It cannot restrict any funded placement; unlike
the earlier U3/U6 N6 experiment, this has no effective fixture reuse cap.
Original N7 U3/U6 controls remain unchanged. Thus this measures the requested
complete strategies, not an isolated effect of changing N alone.

|N7 reference|Net-return Pearson|Spearman|Hit phi|Both hit|N6 only|N7 only|Neither|
|---|---:|---:|---:|---:|---:|---:|---:|
|U3|0.862263|0.528262|0.612081|15|5|4|24|
|U6|0.817134|0.701088|0.784904|17|3|2|26|

Correlations use per-issue net CNY, including zero-stake issues, not cumulative
equity. Unequal actual investments mean these correlations alone do not prove
diversification or bankroll efficiency.

|Strategy|Groups|Hit issues|Stake CNY|Net CNY|Stake ROI|Max drawdown CNY|
|---|---:|---:|---:|---:|---:|---:|
|N6 uncapped|1,440|20/48|46,080|37,636.65|81.68%|7,563.98|
|N7 U3|265|19/48|16,960|19,946.49|117.61%|2,057.14|
|N7 U6|497|19/48|31,808|24,713.37|77.70%|4,416.06|

No effective low-correlation complement emerged. N6 buys all 32 groups in 45
active issues, with three no-bet issues; its greater net profit comes with more
capital deployed and greater drawdown. A hit means a winning group, not positive
issue net profit. Initial equity CNY100,000; no adaptive bankroll gate.

## Reproduction and checks

- `scripts/n6_uncapped.py freeze --study NEW` seals all 48 plans; `settle`
  separately reads final SP. Reuses native cutoff objects and source bindings;
  no fitting or new chronology implementation. Historical admission stays false.
- `quarto/113_n6_uncapped_correlation.qmd` is the R reporting entry point,
  importing existing report/equity/summary functions. Live snapshot:
  `data/derived/fundamentals_417/n6-uncapped-v1`.
- `python -m pytest tests/test_fundamentals_n6_uncapped.py tests/test_fundamentals_consensus_portfolio.py -q`:
  15 passed. New test proves 32 funded groups can reuse both anchors 32 times
  while maintaining P5, two singles, four doubles and the fixed budget.
- `python scripts/check_n6_uncapped.py --study data/derived/fundamentals_417/n6-uncapped-v1`:
  all 1,440 physical groups checked for roles, no swaps, supports, P5, budget,
  Cartesian tickets and one ticket-level 0.65 settlement factor; all 144 rows
  reconciled, original controls unchanged. NumPy/SciPy independently reproduce
  R correlations and drawdown. Observed maximum fixture reuse: 32.
- Portable fixture `tests/fixtures/n6_uncapped.json.gz` preserves the sealed
  results for clean archive rendering; CI runs the regression test and QMD.
- Fresh live and archive renders both passed with execution enabled and cache
  disabled; all three CSV outputs matched byte-for-byte. Both HTML reports had
  2/3/144 table rows and no execution errors. Existing equity/report R tests
  passed 31 assertions; `python scripts/check_cutoff_governance.py` passed.
  Full repository tests and remote CI have not been claimed as executed.
- Independent Codex review passed with no actionable defects. Reviewer reran
  all 15 tests and the ticket checker, verified receipts/cutoffs, correlations,
  live/archive equality and rendered content. Review log:
  `data/derived/fundamentals_417/n6-uncapped-review.txt`.

GitHub #419 remains OPEN, blocked by OPEN #421. This comparison does not satisfy
the outstanding cutoff-safe acceptance requirement or authorize issue closure.
