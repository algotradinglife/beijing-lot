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

## Funding comparison implementation

`n7_funding_allocate` in `r/n7_funding_modes.R` delegates all option construction,
shared-scenario accounting and breadth-first action decisions to existing
`n7_core_option_pool`, `n7_joint_returns` and `n7_core_allocate`. Three modes,
ceilings512/768/1024, three seeds, one25% threshold:5400 plans. MULTIPLY has an
explicit four-copy maximum. Copies are recorded in funded rows and scale
settlement payouts, but not hit counts or coverage probabilities.

`tests/test_n7_funding_runner.py` exercises prediction freeze, independent
settlement checker and allocation replay on saved fixtures for ineligible,
unaffordable and multiplied cases, plus post-freeze label mutation rejection.
`n7_return_diagnostics` uses shared account curves with explicit issue order and
100000 CNY opening capital,50-issue fixed blocks and declared coverage bins.
`n7_fixture_price_diagnostic` joins exact fixture identities/handicaps with the
frozen settlement source, retaining settlement-source hashes.

QMD entry: `quarto/150_n7_return_attribution.qmd`. Inputs: attribution_dir,
output_dir. Rendering is still pending until all final verified inputs exist.

## Final calculation inputs and findings

The final calculation uses `audits/issue441-funding-v2` (5400plans), with
`audits/issue441-attribution-v3` (4800sourcegroups,66626fundedrows across old and
new studies). V1 funding removed30%-derived legal depths and is debugging only;
v2 preserves the25%/30% shared depth universe while selects only25% eligible
candidates. All3600 BREADTH/DEPTH controls reproduce #439 exactly: IDs, depths,
stake, cash, hits, settlement and model metrics. The independent checker passed
all5400funding plans; bridge checker passed all66626funded rows. Full allocation
replay is an additional required receipt, not implied by those checks.

At512, DEPTH net20221–25977, ROI21.3–27.4%, DD6718–8884, hits77–83issues.
BREADTH net11596–14331, ROI14.0–17.3%, DD6681–10446, hits65–69issues.
MULTIPLY equals BREADTH at512 because no legal copy is affordable after opening
other groups. At768 only1–3issues copy; at1024 only5issues copy. Therefore these
results do not evaluate broad arbitrary multiplicity strategies. In this study
copying reduces net versus BREADTH at768/1024 and never increases hit incidence.
DEPTH increases net/hit incidence in each seed but does not lower DD in every pair.

At512, estimated-price actual-hit net remains -24800 to-22153; settlement price
residual+45021 to+48130 produces positive net. The top5positive-price-residual
issues contribute37.5–40.2% of signed totalprice residual; top10 contribute
53.3–58.4%. Do not confuse price attribution with a predictable predecision edge.

Fixture audit includes12988 distinct frozen candidate-pool fixtures. Realized
W/D/L estimated-price ratios have medians .988/.935/1.07 respectively, with
47.0%/33.3%/63.9% settled prices exceeding estimates. These are realized-direction
descriptive distributions, not unconditional fair-SP calibrations or new policies.

Report source: QMD150. Current rendered report directory:
`reports/issue441-return-v2`; seven figures plus full per-issueROI ledger and
fixed50issue blocks. Its receipt binds sourcecatalogchronology, QMD and all
threeRdiagnostichelpers. Insufficient capital fails the bridge diagnostic;
it cannot silently mix shadow unfinanced plans with funded equity results.

Decision-path inventory remains original n7_capital_options -> n7_joint_validate
(shared Cutoff and rank_double_candidates), sleeve_tables, core_curve_features,
sweet_union_partition, core_option_pool, joint_worlds/returns, core_allocate,
capital_evaluate. The new adapter supplies explicit budgets/copies/actions and
cutoff maps; no history fit, cache, recency policy or temporal helper is added.
Attribution reads bound post-settlement audit and ranks descriptively only.

Validation:50focused Rassertions;3saved-fixture end-to-end tests including no-bet
columns, multiplied settlements, hash-consistent eval metric corruption and
auditdirection/SP contradiction;6cutoff-governancetests; broader affected R suite.
Final review, full replay and PR acceptance are recorded in the final delivery
receipt rather than inferred from this progress record.
