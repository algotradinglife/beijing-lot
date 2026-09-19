# Weak handicap gaps and third-outcome purchase compression

This is a fixed post-hoc comparison on the previous 23 paired worst JOINT issues
from the frozen 939-issue ledger; 100105/101001 lack score-grid evidence. It is
not unseen validation, a fitted probability model, or prospective admission.

`r/line_gap_third.R::line_gap_third` keeps native p/q and shared worlds. It changes
purchase ranking only: multiply each combination score by 0.5 for each treated
fixture's third-ranked outcome, or exclude that outcome with weight zero.
Third rank uses the original JOINT p, with W/D/L tie-breaking. Conditional
half-grid line gap >=0.5 includes weak and strong fixtures; >=1 is strong only.
The all-fixture exclusion arm tests whether any gain requires the gap signal.

Existing candidate groups, original per-group ticket depths, SP gate 1.3,
1024 CNY period cap, 2 CNY tickets and one ticket-level 0.65 factor remain fixed.
There is no group eligibility gate from the preceding experiment. JOINT reselects
among changed ticket sets using the original model worlds. Original coverage and
expected gross are recomputed on the new support, never using compressed scores
as calibrated probabilities. This is not the mechanical full-128-ticket Top2
strategy. Changing candidate generation or purchasing depths is outside scope.

| Arm | Stake CNY | Gross CNY | Net CNY | ROI | Hit / profitable issues |
|---|---:|---:|---:|---:|---:|
| Original |23514|0|-23514|-100%|0 / 0|
| Strong only, half weight |23382|0|-23382|-100%|0 / 0|
| Strong only, exclude third |23384|0|-23384|-100%|0 / 0|
| Weak+strong, half weight |23056|6664.05|-16391.95|-71.10%|4 / 1|
| Weak+strong, exclude third |22838|23874.43|1036.43|4.54%|5 / 3|
| All fixtures, exclude third |22840|27203.94|4363.94|19.11%|5 / 3|

All 23 issues remain funded. The positive arms recover the same five issues:
110910, 120407, 121010, 121014, 140707. The all-fixture arm's extra payout comes
from 120407. Removing each arm's largest profitable issue, including its stake,
leaves net -13691.62 (weak+strong exclusion) and -13693.62 (all exclusion).
Thus profitable totals are concentrated, not evidence of stable profitability.

Among 2035 distinct fixtures, third-ranked outcomes occur in 309/1121 weak-gap
fixtures (27.56%) versus 247/898 no-gap fixtures (27.51%). Strong-gap evidence is
only 16 fixtures, four thirds (25%). Estimated original third mass is 25.13%,
25.41%, and 18.07%, respectively. These failure-selected observations do not
support claiming third outcomes are unusually rare when the line gap is weak.

Conclusion: the controlled sample supports investigating purchase-support
compression, but supplies no incremental evidence for a line-gap gate. It does
not justify calibrating genuine third-outcome probability to zero. Preserve both
winning and failed configurations instead of selecting a deployment rule here.

Entry: quarto/246_worst_line_third.qmd, config/worst_line_third.json.
External output: audits/worst-line-third-v2; rendered reports/worst-line-third-v2.
Tests: line-gap-third, n7-core-opportunity, n7-joint-sleeves. Initial broader test
invocation lacked FUNDAMENTALS_PYTHON and failed; rerunning with the declared
project Python passed. QMD executes cleanly; original BASE exactly reproduces
sealed group/state choices. Independent checker replays 69507 tickets and 887
selected-group score/support rankings, without using the new ranking function.
