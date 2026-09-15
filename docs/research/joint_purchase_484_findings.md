# Joint purchase exploration: frozen 484-issue findings

Status: version-2 numerical report generated; independent settlement PASS (31,302 groups, 21 policies), independent structure eligibility PASS (4,840 gates), and full purchase-ranking/allocation replay PASS. Final Codex review remains pending. This is retrospective diagnostic evidence, not prospective acceptance. The separately requested latest accepted-data rerun remains required.

## Scope and attribution

The purchase-level JOINT equivalence check compares two current implementation paths. An additional archived accounting comparison now passes for all 484 issues: stake, gross return, net return and winning-group counts match the earlier JOINT rows (seed 42501, SP floor 1.3, budget 1024) exactly within CNY 0.000001. The archived source is `issue459-expanded-v1/evaluation/results.csv`, SHA-256 `7ec5f907de61fc2f3571a3b0fbc333724c574058e3225058a077a011b43ba6ff`. This establishes accounting reproduction, but not identical losing tickets; the purchase-level archived-reference check remains distinct.

All 21 arms use the same frozen legacy joint probabilities, market-derived payout estimates, candidate source, and 484 issues. Budget is CNY 1,024 per issue; ticket unit CNY 2; official payout factor 0.65 is applied once per ticket. Actual stakes vary because unavailable purchases remain cash. No probability model was trained in this experiment.

The HARD control removes third-ranked outcomes from the original candidate groups; it is not a reconstruction of every earlier Top2 strategy. Results cannot establish that all Top2 strategies fail.

## Current evidence

Original JOINT stakes CNY 430,268, earns CNY 53,342.31 (ROI 12.40%), hits 204 issues, and has maximum drawdown CNY 23,852.02.

DEPTH_OPEN opens eligible groups before adding depth: stake CNY 462,546, profit CNY 57,409.31, ROI 12.41%, 216 hit issues, drawdown CNY 23,066.23. More absolute profit partly reflects more deployed capital; the ROI gain is negligible. Removing each arm's own five best issues leaves ROI 2.52%, versus JOINT 1.70%. This is a robustness diagnostic, not an independently selected validation result.

DEPTH_COMPETE hits 299 issues but loses CNY 56,013.13 (ROI -11.97%) with drawdown CNY 70,124.41. Increased hit frequency alone is not sufficient: the size of payouts and their relationship to stake matter.

U4 reduces stake to CNY 309,016, profit to CNY 38,245.65 and drawdown to CNY 18,719.86, while ROI stays near JOINT at 12.38%. This supports a lower-exposure option, not a demonstrated improvement at equal actual stake.

CONFIDENCE combines probability-dependent fixture reuse and directional money limits. The version-2 report adds matched controls (independent settlement has passed):

| Constraint | Stake CNY | Profit CNY | ROI | Hit issues | Maximum drawdown CNY |
|---|---:|---:|---:|---:|---:|
| Constant uses and money limits | 182,476 | 7,722.86 | 4.23% | 167 | 13,477.49 |
| Confidence-dependent uses only | 154,424 | 10,581.20 | 6.85% | 165 | 10,540.96 |
| Confidence-dependent money only | 181,744 | 8,454.86 | 4.65% | 167 | 13,477.49 |
| Both confidence-dependent limits | 153,460 | 11,545.20 | 7.52% | 165 | 10,540.96 |

In this frozen comparison, varying reuse supplies most of the change relative to constant limits. Adding variable money limits reduces stake by CNY 964 with unchanged aggregate gross return and hit-issue count. These are paired policy effects on this historical sample, not proof of superior probability calibration. All four still have lower ROI than JOINT; lower drawdown accompanies substantially lower investment. Confidence limits are therefore not yet an efficiency upgrade over JOINT.

SIMILAR reduces ROI to 7.10% and hit issues to 185, with drawdown CNY 23,823.59. The tested cost-to-25%-coverage similarity gate does not improve this candidate pool. It is only one definition of curve similarity and does not reject every possible curve-based selection rule.

HEAD15 is almost identical to JOINT (ROI 12.46% versus 12.40%, both 204 hit issues). The head-mass gate has little incremental effect on an already selected candidate pool.

CORE3 places only CNY 370 across the entire sample; CORE4 places no bets; STRUCTURE places CNY 94. These arms are unsupported by the existing candidate pool. Their near-flat capital curves must not be called successful risk control. In particular, their results do not test regenerating candidate groups to satisfy a core/middle/opportunity composition.

## Provisional decision

Retain original JOINT as reference. DEPTH_OPEN is the most credible modest extension here, primarily for deploying residual budget after diversification; do not claim a large efficiency improvement. U4 is an exposure-reduction alternative. Do not adopt the tested direct depth competition, hard third-outcome removal, or similarity gate as upgrades. Role-composition gates are inconclusive because almost no eligible purchases exist.

Final acceptance requires independent official-settlement verification, final code review, and the user-requested rerun on the complete currently accepted eligible dataset with parameters frozen.
