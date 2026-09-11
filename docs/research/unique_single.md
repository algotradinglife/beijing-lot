# Single-role exposure cap on current non-converting D2

User contract: preserve exclusion of zero home handicap with differing baseline/
market Top2 sets. Each N7 group remains two singles and five doubles. A fixture
may be single in at most one group per issue, but may still be double elsewhere.
No conversion, no score protection. Original total fixture capU6 and pair overlapP5
remain.1024CNY per issue,64CNY/group,2CNY unit, one ticket-level.65; cash retained.

Implementation: existing `next_consensus_roles` and
`independent_consensus_portfolio` in src/fundamentals_consensus_portfolio.py accept
`anchor_max_uses`. None adds no role cap; positive integer<=max_uses counts A roles
from prior role maps. Solver zeroes ONLY exhausted A eligibility, preserving D/C.
Public portfolio permits this cap only for conversion_budget_fraction0, so its two
A roles are exactly its two singles. Invalid prior role maps/counts fail.
No function I/O, new dependency, learned threshold, cache or model version change.
Explicit native cutoffs remain validated; the cap is fixed user input and recorded.

Tests: tests/test_fundamentals_unique_single.py maps both changed functions to
role uniqueness, two singles per group, reused single becoming a double, budget,
unchanged behavior at total-use cap, bad cap and forbidden converter mode.
Existing consensus tests remain required. All raw inputs preserved.

Run:
```
python scripts/consensus_converter.py freeze --design independent --exclude-zero-top2-disagreement --anchor-max-uses 1 --study NEW_STUDY
python scripts/consensus_converter.py settle --study NEW_STUDY
python scripts/check_consensus_converter.py --study NEW_STUDY
quarto render quarto/99_unique_single.qmd --execute-dir . --execute --no-cache -P study:NEW_STUDY
```
All48plans freeze before target settlement. Source plans, original input hashes,
filter ledgers, native cutoffs, parameters and transitive implementation bind.
During freeze the uncapped current builder must reproduce every old C000 component,
stake and cash exactly from candidate-exclusion-v1/independent. Old settlement
is bound inventoried reference; no silent source or model switch.
No prospective-admission claim: exposed48issue historical proxy diagnostic.
Issue419 remains blocked by421; this is not cross-year acceptance.

QMD99 uses existing R accounting functions, reports per-issue hit/ROI,
actual invested capital, cash and equity/drawdown from100000CNY. No new R function.
Reduced drawdown can reflect lower exposure; fixed budget limit is not equal stake.
With K eligible anchors, the cap itself limits groups to floor(K/2); other roles
and overlap constraints can lower that further. Ranking and50%anchor threshold
stay unchanged. This is the existing greedy builder, not global portfolio optimality.

## Results and verification

| Metric | Original D2 | Single once |
|---|---:|---:|
| Groups |497|127|
| Winning groups |55|14|
| Group hit rate |11.07%|11.02%|
| Hit issues /48 |19|12|
| Stake CNY |31808|8128|
| Held cash CNY |17344|41024|
| Net CNY |24713.37|6745.83|
| Stake ROI |77.70%|82.99%|
| Budget ROI |50.28%|13.72%|
| Max drawdown CNY |4416.06|1789.95|
| Longest miss streak |7|9|

This is not a demonstrated superior replacement: role diversification sharply
reduces stakes and total profit; hit rate per group is nearly unchanged.
Lower absolute drawdown cannot be attributed solely to better diversification.
No equal-exposure control or unexposed validation is claimed.

- Function tests plus existing consensus and candidate exclusion regression run.
- Cutoff governance PASS.
- Independent checker:192rows/127newgroups, all single caps, role counts, total
  reuse/pair overlap, exclusion, Cartesian tickets and one-factor payout verified.
 144rows are bound prior paired references and are not new-model settlements.
- All48original C000 components/stake/cash reproduced before target settlement.
- Live QMD99 rendered successfully; archive render also required for delivery.
- New fixture uses existing authenticated archive format; CI configured.
- Raw source and settlement snapshots unchanged. Existing R functions unchanged.

Final acceptance evidence for this local comparison:
-20root tests passed (unique-single, consensus and candidate exclusion files).
- Live and archive QMD renders passed,2/96/632/48table rows and2figures verified
  programmatically. No pixel inspection.
- Codex local review: no actionable findings;17tests passed, checker passed,
  independently reproduced all48uncapped baselines AND capped plans with cutoff
  bindings, verified exclusion/D-role reuse/two singles/cash/payout/no fitting.
  Reviewer did not rerun QMD/full CI; no prospective or issue acceptance.
- Remote CI/full repository suite not claimed run. #419/#421 remain open.
- Evidence: data/derived/fundamentals_417/unique-single-review.txt;
  immutable study unique-single-v1 and portable unique-single-archive-v1.
