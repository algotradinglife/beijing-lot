# Exclusive N7 pools and conditional alternatives

Fixed retrospective comparison on 100 exposed issues100608–101120, using the
existing calibrated market foundation and five fixed seeds41901–41905. No fitting
or post-result seed selection. Issue419 remains blocked by acceptance issue421;
this fixture-relative diagnostic does not establish simultaneous ticket availability.

## Contract

S pool contains market Top1>=50%; B pool is its complement. Each group draws two
S and five B fixtures. Weights are Top1 for S and Top2 mass for B, renormalized
inside the eligible pool after each draw. Pools cannot borrow fixtures. Groups
have seven unique fixtures; between groups reuse is unlimited. Full identical
support groups are rejected. Budget1024, unit2, actual Cartesian cost, and one
ticket-level0.65 settlement factor. EV uses calibrated p/raw q ratios and is
recorded only, never gates selection or funding. At most500 attempts per issue.

Defaults are first outcome for S and Top2 double for B. Conditional alternatives
are second outcome single for S, third outcome single for B. Only permitted
positions use5%/10% alternative probability. These are proposal probabilities;
affordability selection can change proportions in accepted groups.

The updated `weighted_n7_plan` accepts explicit single/double gap limits and B
condition, plus separate alternative probabilities. Strength columns are required
and validated, but only affect B disagreement eligibility. Native cutoffs and all
parameters/input identities are sealed; no actual outcome enters the planner.

| Rule | S gate | B gate |
|---|---|---|
| BASE | no alternatives | no alternatives |
| ANY05/10 | unrestricted | unrestricted |
| G10_05/10 | first-second<=.10 | first-third<=.10 |
| G20_05/10 | first-second<=.20 | first-third<=.20 |
| SIGNAL05/10 | first-second<=.10 | market third in strength Top2 |
| JOINT05/10 | first-second<=.10 | first-third<=.20 AND strength signal |

## Results across five seeds

| Rule | Median ROI | Profitable seeds | Median maximum drawdown CNY |
|---|---:|---:|---:|
| BASE |-8.29%|1/5|16,313|
| ANY05 |-7.65%|2/5|13,498|
| ANY10 |-11.47%|2/5|20,086|
| G10_05 |-8.26%|1/5|16,313|
| G10_10 |-8.29%|1/5|16,313|
| G20_05 |-0.83%|2/5|13,422|
| G20_10 |-8.86%|2/5|14,002|
| SIGNAL05 |-0.19%|2/5|13,983|
| SIGNAL10 |-1.40%|2/5|12,513|
| JOINT05 |-4.30%|2/5|12,992|
| JOINT10 |-3.02%|2/5|12,690|

SIGNAL05 has mean ROI+0.35%, but median−0.19% and only2/5 profitable seeds. Removing
each seed's highest-net issue yields median ROI−5.55%. Thus it remains a diagnostic
candidate, not a replacement for deterministic CAL_U3/U6 (12.93%/22.53%).
Paired old overlapping-pool RATE05/10 results are shown in QMD from their archived
fixture; their models are not imported into current decisions.

**The S gap gates do not trigger:** there are1070 S candidates and their minimum
first-second gap is21.00798 percentage points. Neither10 nor20 points changes S
outcomes. This experiment therefore measures B changes for conditional policies;
it does not show that S gap gating is ineffective. Gaps25/30 would admit374/774
candidate fixtures, respectively; returns at those thresholds have not been tested.

In SIGNAL05,1190 accepted B alternative holdings hit360 times (30.25%); ANY05's
3040 alternative holdings hit825 times (27.14%). These are repeated holdings,
not independent matches, and do not establish a causal precision gain. Rules also
change budget fit and subsequent group construction. G10 B alternatives occur
only11/15 times across5seeds, both with zero hits: sparse evidence.

## Reproduction and checks

`python -m scripts.replay_n7_weighted_sampling --output <new-directory>` freezes
5500 plans before reading the bound authoritative R/SQLite audit. Current output:
`data/derived/fundamentals_417/n7-exclusive-conditional-v5`.

`quarto/127_n7_exclusive_conditional.qmd` validates source/implementation/plan
hashes, displays every period's ROI and cash, all seed equity/drawdown curves,
and position-level alternative eligibility/hits. Its archive fixture is
`tests/fixtures/n7_exclusive_conditional.json.gz`; old pool comparison uses the
separately declared `tests/fixtures/n7_weighted_sampling.json.gz`.

Every changed project function is covered in `tests/test_n7_weighted_sampling.py`:
exclusive membership, no-borrow/no-bet, normalization through sampling, exact gap
boundaries, strength gates, disallowed alternatives, budget, duplicate groups,
price mutation invariance and settlement contracts. 48 relevant Python tests and
cutoff governance pass. Codex review found no actionable defects and independently
passed144 extra boundary/rank/gate/allocation cases. Full-repository checks were
not run; unrelated working-tree changes are outside this comparison.

After the review, independent replay verified all5500 completed plans for pool
membership, gate eligibility, actual support, unique groups, Cartesian costs and
settlement proceeds. Clean live and archived QMD renders passed; summary CSVs
are byte-identical. All plotted panels and key tables were visually inspected.
