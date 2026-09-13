# #441 Return attribution and breadth-first funding

Live Issue: https://github.com/algotradinglife/beijing-lot/issues/441

User-approved sequential follow-up to #439 on the same 200 exposed issues.
No new data cleaning, probability fitting, or prospective performance claim.
The reference arm is T250_DEPTH_B512. Secondary ceilings are768 and1024 CNY;
tickets cost2 CNY and contain one0.65 payout factor. Initial capital100000 CNY.

## Stage 1: exact accounting bridge

For each frozen funded prefix, let E be modeled expected gross, S stake,
H the observed indicator that the realized combination lies in the prefix,
Q its estimated predecision payout, R its settled payout, and m the copies.
The exact identity is:

`actual_net = (E-S) + (H*m*Q-E) + H*m*(R-Q)`.

The middle term is the outcome residual at fixed estimated prices, **not** an
identified probability-error estimate: sampling noise, dependence and model
error can all contribute. The final term is the realized payout-price residual.
Neither term is a permissible decision feature for the target period.
Copies scale money but never count as independent group hit events.

`r/n7_return_attribution.R::n7_return_attribution` performs this descriptive
bridge; tests cover conservation, copies, no-hit, empty data, invalid/missing
values, duplicate keys and unmatched evidence. The thin runner reads bound
#439 frozen funded plans and reconstructs estimated realized-state payout
from the original probability bundle, checking state ID and rank identity.

## Stages 2 and 3

Reuse `n7_core_option_pool` and `n7_core_allocate` with explicit cutoff maps.
Compare BREADTH, DEPTH and MULTIPLY for25% eligibility costing<=256 CNY.
Open affordable different groups first; copies are of an initial prefix, not
new independent coverage. Preserve cash when legal actions cannot be afforded.
Use three fixed original seeds, fixed scenario counts and independent evaluation
worlds. Bind and freeze decisions before settlement is loaded. No parameter
selection from observed target labels. Historical packages remain diagnostic.

Report common budget ceilings separately from actual spend; include cash-only
zero-net baseline because modeled EV is negative. Diagnose fixed time blocks,
cohorts, per-issue returns/ROI, drawdown, hit/profit periods and best1/3/5 removal.

Acceptance remains pending: full attribution, allocation comparisons and replay,
clean QMD render, diagnostic figures, Codex review, commit/push and PR. No merge
or Issue closure is included.

## Preliminary stage1 result

Explicit output: persistent `audits/issue441-attribution-v1`, covering #439 stage3
and smaller-budget controls. This is preliminary, not final acceptance; stage2
1024CNY controls and full source-binding review remain to be added.

T250_DEPTH_B512 across seeds42501/42502/42503:

|seed|model net|outcome residual|price residual|actual net|
|---:|---:|---:|---:|---:|
|42501|-29444.25|4643.96|45021.35|20221.06|
|42502|-29424.20|5814.25|46688.00|23078.06|
|42503|-29473.78|7320.96|48130.28|25977.46|

The realized-hit return at estimated prices is still negative in each seed.
Settlement-price differences dominate the bridge to positive historical net.
This does not establish that those price differences were predictable.
The next diagnostic must inspect concentration of this price residual and
fixture-level estimated-versus-settled price sources before interpreting it.
