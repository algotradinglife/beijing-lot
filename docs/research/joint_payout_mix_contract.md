# JOINT mixed payout coverage contract

Frozen 784-issue exposed historical diagnostic. No model fitting, new group
formation, chronological availability claim, or prospective deployment.

Compare original JOINT, payout floors 128 and 256, and MIX10/MIX15/MIX20.
Keep original groups and their maximum ticket counts. Budget ceiling CNY1024,
ticket CNY2, initial capital CNY100000, payout factor .65 exactly once.

Reserve floor(original total ticket count * share) tickets for supplement.
First buy probability-ranked payout >=256 tickets, within group quotas, up to
original total minus reserve. Then buy ranked payout [128,256) tickets only in
groups opened by the main stage, using their remaining quotas. Each combination
is purchased once. Unused reserve stays cash; original idle budget is not filled.
This is redistribution of existing planned investment, not extra funding.

R decision interface: `joint_payout_mix` in `r/joint_payout_mix.R`, with explicit
cutoffs, budgets, floors and share. Shared `n7_joint_validate` owns cutoff checks.
Python `replay_payout_mix` independently reconstructs the ordered ticket list.
Existing freeze and metric-verification interfaces bind sources and implementation
and seal all plans before settlement. Existing authoritative settlement applies
actual Beidan SP; estimated prices remain euro/totals-derived throughout selection.

Tests: `tests/testthat/test-joint-payout-mix.R` tests reservation, price bands,
cash, unopened groups, no duplicates and invalid parameters/cutoffs.
`tests/test_joint_payout_study.py` parametrizes full freeze/replay/settlement,
tamper rejection, immutable plans and no-allocation issues for both study types.
QMD entry: `quarto/208_joint_payout_mix.qmd`, explicit verified input parameters.

Acceptance: complete 784 x 6 plans and replay; original JOINT exact accounting;
overall and fixed phase return, ROI, drawdown and hit counts; added/removed ticket
attribution, spending versus cash; direct conversation charts; clean render;
Codex review and scoped commit/push. No final verdict before evidence exists.

## Completed research result

784 issues x6 arms independently replayed and settled in
`audits/joint-payout-mix-v1`; report published at `reports/joint-payout-mix-v1`
under the persistent data root. Original three controls reproduce prior totals.

| Policy | Stake CNY | Net CNY | ROI | Maximum drawdown CNY | Hit issues |
|---|---:|---:|---:|---:|---:|
| Original |706950|53188.68|7.52%|35125.71|345|
| Floor128 |706950|56683.54|8.02%|34784.04|346|
| Floor256 |706950|45987.15|6.51%|35772.46|351|
| MIX10 |669408|32753.47|4.89%|50620.21|340|
| MIX15 |643674|28346.06|4.40%|49131.66|329|
| MIX20 |615282|35445.60|5.76%|46159.51|321|

Reject this fixed-reserve implementation as an upgrade. Compared with Floor256,
mixes rescue 4/4/5 issues but lose 15/26/35. Supplement reserves fill only
46.4/39.9/34.9 percent: original group quotas and already-opened eligibility
constrain availability. Lower investment does not explain away lower ROI and
higher drawdown. The original drawdown segment also deteriorates. This verdict
does not establish that all lower-band tickets or other allocation designs fail.
