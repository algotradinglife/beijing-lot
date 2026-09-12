# With-replacement weighted N7 pools — EV recorded only

The owner removed the group EV gate. The final function has no EV-floor argument:
estimated SP and expected ROI cannot admit/reject tickets. Changing raw-market
proxy prices with fixed sampling probabilities leaves tickets identical (tested).

Frozen diagnostic scope: 100 exposed issues 100608–101120; five seeds41901–41905;
calibrated-market probabilities, no strength/expert routing. CNY1,024 budget per
issue, CNY2 unit and one ticket-level0.65 payout factor. Each group has two S-pool
roles and five B-pool roles, shuffled before sequential weighted sampling.

S pool: Top1≥0.5, fixture weight Top1, outcome Top1/Top2 sampled in proportion
to their probabilities. B pool: fixture weight Top2 combined mass, choose Top2
double with that mass, otherwise third-outcome single. Arbitrary precision, no
inventory or between-group reuse cap. Within-group fixtures are unique. Identical
full support groups are rejected; overlapping elementary bets are counted.
Actual cost depends on realized doubles. Unaffordable/duplicate/infeasible groups
cost nothing. At most500 attempts per issue; unspent cash is held.

Final comparison adds fixed alternative probabilities5% and10%, applied to both
pools together, alongside the original proportional policy. S alternative is
second outcome; B alternative is third-outcome single. The function exposes
`single_alternative_probability` and `double_alternative_probability` separately;
explicit None selects the proportional policy for that pool. Sampling weights
for fixture selection are unchanged. EV remains recorded only in all variants.

Expected SP=1/raw market probability (European odds+OU mapping); the calibrated
probability supplies expected outcomes. Group expected ROI is0.65 times the
product of each position's mean p/q minus1, assuming match independence.
Actual settlement uses the existing R/SQLite audit and authoritative settlement
adapter. Expected ROI is informational. These fixture-relative historical inputs
do not prove simultaneous pre-ticket availability; no prospective admission.

## Results: fixed seeds, no post-result selection

| Strategy | Stake CNY | Net CNY | ROI | Hit issues /100 | Max drawdown CNY |
|---|---:|---:|---:|---:|---:|
| CAL U3 control |94,336|12,194.19|12.93%|54|12,583.07|
| CAL U6 control |100,672|22,677.80|22.53%|56|14,449.85|
| seed41901 |97,278|-29,770.01|-30.60%|40|42,659.56|
| seed41902 |97,280|-3,417.07|-3.51%|41|19,115.74|
| seed41903 |97,280|-15,551.17|-15.99%|36|30,244.62|
| seed41904 |97,280|-3,841.43|-3.95%|43|19,838.36|
| seed41905 |97,230|-20,598.66|-21.19%|34|31,938.30|

All five proportional seeds lose. Groups increase to2,763–3,518 versus U3/U6 1,474/1,573,
but hit groups are only43–60 versus95/104. Maximum fixture reuse reaches38;
no duplicate elementary bets were observed in this run.
Average predicted group coverage is1.73%, versus original U3/U6 6.12%/6.72%.
This supports investigating how much alternative-outcome randomization reduces
coverage, though the comparison also changes selection and the eligibility gate.
It does not isolate a causal effect of reuse alone.

## Fixed alternative proportions

| Seed | Proportional ROI |5% ROI |10% ROI |
|---|---:|---:|---:|
|41901|-30.60%|-14.77%|-23.69%|
|41902|-3.51%|-7.00%|5.29%|
|41903|-15.99%|-11.38%|-18.44%|
|41904|-3.95%|7.92%|-15.92%|
|41905|-21.19%|-2.81%|-8.97%|

Median ROI: proportional−15.99%,5%−7.00%,10%−15.92%. Median maximum drawdown:
CNY30,244.62 /21,202.23 /21,287.91. Median hit issues:40 /44 /41.
Only one of five seeds profits at each fixed rate; neither is stable evidence of
improvement over the deterministic U3/U6 controls. Even each fixed rate's best
seed ROI (7.92%/5.29%) is below U3/U6 (12.93%/22.53%).
Each fixed-rate seed spends CNY97,280 over100issues; group counts are1,710–1,990
at5% and1,994–2,363 at10%. Do not select the best seed after seeing returns.

Five issues (100919,101004,101013,101107,101110) cannot fill two S-pool roles at
the fixed50% Top1 threshold. They retain all cash; this is eligibility exclusion,
not missing data. Other candidate failures/rejections remain in sealed plans.

The superseded local v2 trial with EV floors0%/10% admitted almost no bets. It is
retained only as diagnostic evidence; neither gate remains in the final API.
Final output: `data/derived/fundamentals_417/n7-weighted-sampling-rates-v4`.

## Reproduction

- `python -m scripts.replay_n7_weighted_sampling --output <new-directory>` freezes
  1,500 plans before target settlement, binding source/model files, native cutoffs,
  fixed parameters, transitive implementation closure, and plan hashes.
- `quarto/126_n7_weighted_sampling.qmd` reads/validates those receipts and displays
  period returns/ROI, independent-seed summaries, equity and drawdown curves.
- `tests/fixtures/n7_weighted_sampling.json.gz` provides1,500 result rows plus200
  controls for portable accounting/report rendering, not model replay.
- `tests/test_n7_weighted_sampling.py` covers the sampler, deterministic seeds,
  cutoff/input validation, reuse>10, role/outcome support, budget, uniqueness,
  no-eligible cases, EV algebra, price-mutation invariance and actual settlement.
- The shared R summary now represents zero-stake ROI as NA; its regression test
  also preserves best-period exclusion with matched stake. No old wrapper added.

Issue419 remains blocked by native acceptance dependency421. This fixed exposed
diagnostic does not close that requirement and does not tune on these labels.

## Validation

48 relevant Python tests passed (sampler, reusable conditional settlement and
market/legacy N7 contracts). The R summary regression has14 passing assertions,
including zero-stake NA ROI. `python scripts/check_cutoff_governance.py` passed.
Independent enumeration verified all1,500 final plans: seven unique fixtures,
Cartesian supports, no identical full groups, unit costs, estimated ticket EV,
and actual settlement. Live and archived clean Quarto renders passed and their
summary CSVs match exactly; tables and equity/drawdown images were inspected.
Codex review found no actionable defects in the final sampler/runner changes and
checked independent pool rates, original proportional mode and price-invariance.
No full-repository suite was run; unrelated working-tree changes are excluded.
