# N5/N6 repeated-single swaps at 10%

Same exposed 48 issues100402–100607. Keep the original uncapped N5 and N6
groups, group order and stakes exactly. Two singles; N5 has three doubles,
N6 four doubles. CNY1,024 budget, CNY2 units, group prices16/32, at most64/32
groups, no effective U cap. Existing P4/P5 limits remain. No reassembly, expert,
score protection or increased investment.

First fixture appearance stays unchanged regardless of role. Each subsequent
appearance that is a single independently switches market Top1 to market Top2
with probability .1; doubles never switch. The original direction ranking is
always used, with no cascading flips. All100 seeds0–99 are fixed before this
run opens settlement. Same random keys as the prior25% N5 study make the10%
swap positions a subset of its25% positions for every seed. No best-seed choice.

## Results

All arms spend CNY46,080: 45 active issues at1,024 plus3 no-bet issues.
N5 uses2,880 groups and N6 uses1,440. Random rows below are100-seed means;
their drawdown statistic is the median across seeds.

|Strategy|Net CNY|ROI|Hit issues /48|Winning groups|Max drawdown CNY|
|---|---:|---:|---:|---:|---:|
|N5 no swap|22,401.47|48.61%|22|505|7,433.45|
|N5 single10%|16,828.83|36.52%|28.56|435.95|7,539.87 median|
|N6 no swap|37,636.65|81.68%|20|223|7,563.98|
|N6 single10%|27,335.95|59.32%|22.15|189.81|7,648.13 median|

N5 ROI5th–95th percentiles30.14%–44.18%; N6 45.46%–71.11%.
All100 seeds of each remain profitable, but none outperforms its no-swap
control. N5 rescues6.57 issues and loses0.01 on average; N6 rescues2.37 and
loses0.22. More hit issues do not offset fewer total winning groups/payouts.

Compared with prior N5 single25%, mean ROI improves21.47% to36.52%, while
mean hit issues fall30.87 to28.56. Lowering the rate reduces the return penalty,
but still does not improve returns or median drawdown versus no swap. This
comparison does not estimate an optimal rate or claim future performance.

## Implementation and evidence

- No source model or portfolio functions changed. Reuse
  `src/fundamentals_reuse_random.py::random_reuse_plan` with explicit
  `single_probability=.1,double_probability=0,group_size=5|6` and native Cutoffs.
- Thin entry point `scripts/n5_n6_single10.py freeze|settle --study NEW` binds
  existing plan/source hashes, implementation closure, all seeds/parameters,
  and native cutoffs. All new plans freeze before reading actual settlement.
  Cache is issue-local and keyed by exact sealed component within this run.
  Existing source plans are historical artifacts, not clean model interfaces.
- Settlement uses authoritative functions with one ticket-level .65 factor.
  Both newly settled no-swap controls must reproduce prior group/hit/stake/
  gross/net values exactly within1e-7. No label influences selection or swapping.
- R entry point `quarto/117_n5_n6_single10.qmd` imports existing reporting and
  equity functions, presents paired controls, all-seed return/hit/drawdown
  distributions, per-issue net/ROI/hits and predesignated seed0 example curves.
- Python tests passed33 cases across N5/N6/N7 coverage, including new10% cases;
  cutoff governance scan passed. No new functions or dependencies were added.
- Independent `scripts/check_n5_n6_single10.py --study STUDY` checks unchanged
  original groups, all physical support/ticket payouts, every deterministic
  draw, no double swaps, nested10%/25% N5 changes and every R policy metric.
  Audit passed436,320 physical groups and all9,696 rows/202 policy metrics.
  N5 swapped55,570 of555,800 eligible singles; N6 swapped26,587 of269,200.
  All no-swap controls matched prior results and all double swaps remained zero.
- R tests passed31 assertions. Fresh live and archive renders passed with
  execution enabled, cache disabled and fatal errors. All five CSVs matched
  byte-for-byte. Both HTML reports have2/2/2/2/96 table rows and two visually
  inspected equity/drawdown plots, without execution errors. Portable fixture
  `tests/fixtures/n5_n6_single10.json.gz` is included in the new CI step.
  Full-suite and remote-CI execution are not claimed.
- Final independent Codex review passed without actionable defects. Reviewer
  reran the full physical checker and10 scoped tests, verified96 no-swap control
  rows exactly, receipt/source bindings, portable fixture, CSV equality and
  rendered interpretation. Log: `n5-n6-single10-review.txt` in the derived
  `fundamentals_417` directory. Root ran the broader33-case test selection.

This is exposed-history retrospective diagnosis, not prospective acceptance.
Seed percentiles describe randomization here, not future confidence intervals
or probability of profit. Hit issues are not necessarily profitable issues.
GitHub #419 remains OPEN and blocked by OPEN #421; no lifecycle change.
