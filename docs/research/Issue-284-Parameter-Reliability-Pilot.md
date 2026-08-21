# Issue #284 — Can issue Data reliably estimate N and subset parameters?

Date: 2026-08-21
Status: exploratory method result; not a frozen candidate and not holdout evidence.

## Post-merge EV qualification

The asynchronous audit of merge `231fa13478dff880d2009e11f69471c52529f385`
identified three interpretation defects. They do not reverse this report's
NO_PROMOTION conclusion, but they narrow the numerical claims:

- the reported +9.33pp Full-HGB lift is against the internal
  `N7/WEIGHTED/K128/ENSEMBLE` diagnostic, not the live Issue-named
  `N7/TOP/K8 MARKET` control. Full-HGB is −9.24% absolute and therefore
  **−5.29pp** versus that −3.94% named control;
- the joint-policy action set is funded-action-only. Its q10 fallback is a
  funded baseline, not CASH/NO_BET, so it provides no abstention evidence;
- the CNY100,000 figures are standardized CNY100-per-issue paths, not actual
  `W=2K` bankroll paths. They cannot support cross-K drawdown or bankroll
  comparisons.

The +1.80pp Full-HGB versus fixed K512 result may remain an internal
conditional-K clue only. Unbound source inputs and unresolved missing-SP
semantics prohibit freezing any #284 number as a candidate or accepted
baseline.

## Decision summary

Enumerating `N=3,…,10` is feasible and preferable to asking one joint head to
emit N implicitly. The current pre-event value surface can produce a stable
*expected-N frontier*, but the historical data do not yet support reliable
issue-specific selection of N or a unique match subset.

The sharp distinction is:

- **feasible:** compute and rank an expected value distribution for every
  issue×N candidate before the outcome;
- **not yet reliable:** predict which N or subset will realize the best return
  in a particular issue.

No 2024+ outcome was opened.

## Data and experimental unit

- 620 Beijing issues from 2014–2023;
- 157,591 settled N×3 subsets after availability filtering;
- N from 3 through 10;
- four pre-event subset proposal families;
- up to eight distinct subsets per issue×N×family;
- fixed `CELL_VALUE / weighted-distinct / K128 / R=1` pilot semantics;
- 0.65 applied once to a complete winning N-fold ticket;
- every issue retains aggregate statistical weight one.

The 157,591 subset rows are nested augmentation observations. They do not turn
the 620 issues into 157,591 independent historical experiments.

## What the first neural pilots showed

### Joint-N head

Learning absolute P&L made the model choose N3 for all 62 validation issues.
N3 has at most 27 distinct outcome tickets at K128, so the apparent protection
mainly came from smaller effective deployment. This was a target-definition
error, not evidence that N3 was optimal.

### Per-N heads and matched lift

The target was changed to same-issue CNY100-normalized lift over an N7/UNIFORM
baseline. Eight N-specific heads were trained, each selecting inside its own N,
then the eight candidates were compared on one common scale.

Across five model seeds on the 2022 development slice:

- mean pairwise score-rank correlation: **0.920**;
- N agreement: **0.505**;
- proposal-family agreement: **0.429**;
- exact-subset agreement: **0.282**;
- all five seeds selected the same N in only **7/62 issues**.

The models learned similar smooth score surfaces, but their argmax parameters
were brittle because top candidates were close. Only 12/62 ensemble choices had
a top-vs-runner margin larger than the top candidate's across-seed score SD.

### Chronological cross-N calibration

The next pilot used 2014–2020 for model fitting, 2021 solely for cross-N score
calibration and 2022 for validation. Within each N, the 2021 calibrated score
versus realized matched lift had Spearman correlations of about −0.03 to 0.08.
In 2022, the within-issue/N mean rank correlation was −0.041.

Moreover, N alone explained **99.45%** of calibrated score variance. Only 0.55%
was left for issue-specific Data. The apparent cross-seed stability was mostly
a stable global N prior, not reliable dynamic parameter learning.

## Does averaging many subsets fix the target?

It reduces Monte Carlo noise in the pre-event expectation, but not the realized
jackpot noise enough to identify a per-issue optimum.

| Subsets in each disjoint half | Realized within-N rank correlation | Expected within-N rank correlation | Realized best-N agreement | Expected best-N agreement |
|---:|---:|---:|---:|---:|
| 1 | 0.013 | 0.079 | 20.5% | 29.8% |
| 2 | 0.028 | 0.171 | 16.1% | 30.6% |
| 4 | 0.051 | 0.293 | 17.6% | 36.8% |
| 8 | 0.035 | 0.346 | 15.0% | 41.8% |
| 16 | 0.076 | 0.484 | 18.5% | 60.8% |

Thus, more subsets make the model-defined expectation increasingly
reproducible. They do not make the realized best N reproducible: two disjoint
16-subset panels still agree on realized best N only 18.5% of the time.

## Aggregate N curve

Across all 620 issues and all sampled subsets, the descriptive pre-tax curve is:

| N | Mean ROI | Median issue ROI | Positive issue fraction | Positive years/10 | Max drawdown |
|---:|---:|---:|---:|---:|---:|
| 3 | −28.70% | −28.75% | 1.3% | 0 | 17.80% |
| 4 | −25.77% | −25.83% | 2.3% | 0 | 15.98% |
| 5 | −22.02% | −23.16% | 13.7% | 0 | 13.65% |
| 6 | −19.09% | −26.14% | 26.9% | 0 | 11.98% |
| 7 | −10.30% | −27.18% | 34.2% | 2 | 6.85% |
| 8 | −10.69% | −60.35% | 28.9% | 3 | 7.98% |
| 9 | **−6.54%** | −100.00% | 24.9% | 3 | **6.02%** |
| 10 | −14.92% | −100.00% | 11.3% | 3 | 14.18% |

N9 is the best aggregate mean in this panel, but its median issue loses the
entire CNY100 risk budget. The higher-N curve is a sparse-jackpot distribution,
not a smooth improvement in holding experience.

## Expanding-window residual-learning test

An issue×N table was built by averaging the subset distribution. Inputs contain
only pre-event issue state, N geometry and model-expected distribution. The
target is realized mean return minus model-expected mean return. Annual OOF
folds cover 2018–2023, always trained only on earlier years.

| Policy | Mean ROI | Ending capital from CNY100k | Lift vs N7 | Ex-largest lift | Positive lift years/6 |
|---|---:|---:|---:|---:|---:|
| Fixed N7 | −15.59% | 94,886 | 0 | 0 | 0 |
| Expected value only | **+0.66%** | **100,216** | +5,331 | **−4,599** | 2 |
| Expanding N prior | −16.68% | 94,530 | −356 | −3,577 | 3 |
| Ridge residual model | −27.33% | 91,036 | −3,850 | −4,654 | 3 |
| Histogram GB residual model | −23.32% | 92,351 | −2,535 | −5,756 | 1 |

The learned residual models make the result worse. The best apparent result is
the direct pre-event expectation, but it selects N10 in 271/328 OOF issues and
depends on one 2019 issue whose normalized N10 return is about +9,871. Removing
the largest positive contribution makes matched lift negative.

Issue-block bootstrap further shows the uncertainty:

- Expected-only ROI 95% interval: **−52.17% to +82.29%**;
- expected-only mean lift interval: **−37.63 to +98.13 percentage points**;
- bootstrap probability of positive mean lift: about **64.8%**.

This does not meet a candidate threshold.

## Adversarial interpretation

If challenged, the positive +0.66% result can be explained without a durable
Data-conditioned edge:

1. high N creates a lottery-like payoff and one realized jackpot dominates;
2. the expected-value model assumes leg independence and inherits probability
   and predicted-SP calibration error;
3. within-N expected value has almost no correlation with realized issue return;
4. residual learners fail out of sample;
5. choosing the visually best risk penalty after inspecting outcomes would be
   another parameter-search leak.

Therefore the positive number is a useful sweet-zone clue, not promotion
evidence.

## Joint `N × K × generator × subset` interaction screen

The next bounded screen follows the PI direction that the eventual optimum is
joint rather than a sequence of independently optimal knobs. It expands only
the high-N region (`N=7,…,10`) and covers:

- `K = 8, 16, 32, 64, 128, 256, 512`;
- deterministic `TOP_VALUE` versus probability/value-weighted distinct-ticket
  generation;
- four pre-event subset proposal families and four subsets per family;
- three fixed weighted-ticket stream seeds, treated strictly as nuisance
  replicas and averaged rather than optimized.

The result contains 1,106,532 action rows over all 620 development issues. No
2024+ outcome was opened. The leading descriptive fixed actions are:

| N | Generator | K | Mean ROI | Ex-largest ROI | Issue bootstrap 95% interval | Positive years/10 | Median issue |
|---:|---|---:|---:|---:|---:|---:|---:|
| 9 | WEIGHTED | 8 | +13.91% | −6.98% | [−39.81%, +81.48%] | 6 | −100% |
| 10 | WEIGHTED | 128 | +5.43% | **+0.70%** | [−20.18%, +36.57%] | 3 | −100% |
| 9 | TOP_VALUE | 8 | +4.66% | −1.93% | [−30.09%, +43.36%] | 7 | −100% |
| 7 | TOP_VALUE | 8 | −2.03% | −3.85% | [−17.03%, +14.45%] | 5 | −100% |
| 8 | TOP_VALUE | 512 | −8.90% | −10.31% | [−14.30%, −3.24%] | 2 | −18.24% |

These rows are hypotheses, not accepted baselines. Even after nuisance
averaging, no fixed action has a bootstrap interval wholly above zero. The
ranking of the 56 fixed actions is also unstable across years: mean pairwise
year-rank Spearman is only **0.055** (median **0.041**).

The interaction is nevertheless real enough to retain in the learning design:

- there is no global `WR/WOR`-style generator winner; matched generator lift
  changes sign with N and K;
- small K helps some TOP_VALUE high-N actions, while larger K helps other
  weighted actions;
- `N7 × TOP_VALUE × K8` improves the matched mean over
  `N7 × WEIGHTED × K128` by +15.40 percentage points, but its paired bootstrap
  interval still touches zero and its median issue lift is negative;
- the model-expected TOP_VALUE surface is severely optimistic at high N
  (for example +173% expected versus −2.03% realized for N7/K8), showing that
  per-cell value calibration and leg-independence error compound across a
  ticket;
- the first one-subset screen produced much larger apparent winners than this
  denser screen. Stream seed and subset identity must therefore be integrated
  out, never offered to the optimizer as actions.

The new executed notebook
`notebooks/Issue-284-Joint-Parameter-Screen.ipynb` contains the complete heatmap,
matched generator comparison, yearly table, issue-level capital diagnostics and
the expected-versus-realized plot.

## Expanding-window joint-policy learning

The final prototype treats selector family as an action parameter rather than
averaging it away. The action space is therefore:

`N(7…10) × K(8…512) × generator(2) × selector-family(4 + ENSEMBLE)`

Specific subset identity and weighted-stream seed remain nested nuisance
replicas. The matched baseline is the previously specified
`N7/WEIGHTED/K128/ENSEMBLE`; it was not selected after seeing this OOF result.
Annual expanding-window folds cover 2018–2023. The models are deliberately
small maintained-library implementations: Ridge, histogram gradient boosting
and a two-layer sklearn MLP.

| Policy | OOF ROI | Lift vs matched baseline | Lift bootstrap 95% interval | Positive lift years/6 | Ending CNY100k capital |
|---|---:|---:|---:|---:|---:|
| Fixed N7/weighted/K128 | −18.57% | 0 | fixed | 0 | 93,909 |
| Fixed N7/TOP/K512 | −11.04% | +7.53pp | [−1.34, +16.16] | 5 | 96,379 |
| Action-only HGB | −10.58% | +7.99pp | [−0.66, +16.34] | 5 | 96,528 |
| State + action HGB | −10.73% | +7.84pp | [−0.81, +16.35] | 5 | 96,481 |
| Full HGB | **−9.24%** | **+9.33pp** | **[+0.07, +19.33]** | 5 | **96,970** |
| MLP | −10.95% | +7.62pp | [−0.89, +16.86] | 5 | 96,407 |
| Expected-only | −68.39% | −49.82pp | [−84.57, +0.68] | 1 | 77,567 |

These figures use equal aggregate training weight for every issue in every
estimator. The weights are rescaled to mean one before fitting so estimator
regularization does not change merely because the action table contains many
nested rows.

The adversarial control still changes the interpretation. MLP selects the fixed
`N7/TOP/K512/ENSEMBLE` action in 323/328 issues; its actual lift over that fixed
action is only +0.086pp, with paired bootstrap interval [−0.33pp, +0.56pp]. It
has mostly learned a global action prior.

Full HGB is more interesting: it selects K512 in 295/328 issues and K256 in the
other 33. Its matched lift over fixed K512 is +1.80pp and remains +0.80pp after
removing the largest incremental issue. However, the direct paired bootstrap
interval is approximately [−0.34pp, +4.58pp]. State + action alone adds only
+0.31pp over fixed K512; the extra expected-surface features account for most
of the conditional switch but add +1.49pp over state HGB with an interval that
also crosses zero. This is a genuine conditional-K sweet-zone clue, not a
reliable learned policy or accepted baseline. The q10 head still falls back in
every issue, so current uncertainty estimates cannot fund it safely.

The descriptive fixed `N7/TOP/K8` path is −3.94% in these six OOF years, but
that action was highlighted after examining the full development surface. It is
an optimistic exploratory comparator, not a clean accepted baseline.

## Outcome-value surface is a regime parameter, not a fixed winner

The #282 counterfactual label panel already contains the complementary action
dimension that was missing from the first #284 joint screen:

- `MARKET_PROBABILITY`: construct/rank tickets from the market probability
  surface;
- `CELL_VALUE`: use the current per-cell value surface;
- `DIVERGENCE_VALUE`: combine value, market probability and the pre-event
  model–market divergence surface.

Reusing those frozen labels avoids a second expensive ticket simulation. It
also gives a direct adversarial test of whether one value definition can be
fixed globally. For the matched `ALL / N7 / TOP / K8` action:

| Outcome surface | 2014–2022 ROI | 2023 ROI | Full-period ROI | Ex-largest ROI | Issue bootstrap 95% interval | Positive years/10 |
|---|---:|---:|---:|---:|---:|---:|
| MARKET_PROBABILITY | **+38.54%** | **−33.06%** | +32.42% | +14.72% | [−18.79%, +95.85%] | 3 |
| CELL_VALUE | −42.37% | −100.00% | −47.30% | −63.65% | [−83.08%, +1.62%] | 1 |
| DIVERGENCE_VALUE | −74.95% | **+25.80%** | −66.33% | −77.05% | [−89.29%, −36.22%] | 1 |

The result does not mean that the divergence mode became a durable winner in
2023: that positive year contains only one positive issue and is itself highly
tail-concentrated. Conversely, the large full-period market-probability mean is
mainly a 2019–2021 cluster; its median issue is −100%, and its issue bootstrap
interval crosses zero.

Across all 432 fixed actions, development-period versus 2023 action-rank
Spearman is only **0.305**. The best development action was the market N7/TOP/K8
row above, and it failed in 2023. This makes outcome-value mode a scientifically
important *dynamic* action parameter, but rejects the shortcut of fixing the
historically best mode. The next model must learn a pre-event regime → value
surface relationship and still beat same-regime static controls.

The executed notebook includes the annual curves and the full 432-action
development-to-2023 transfer plot. No 2024+ outcome was opened.

### Subset-level joint confirmation

The outcome modes were then put into the same subset action vector as N, K,
generator and selector family. This exposed an algebraic alias that should be
removed from later models. Within one fixed N-match subset,
`CELL_VALUE = market_probability × match_specific_predicted_SP`; the SP scalar
is common to all three outcomes of that match. Every complete ticket therefore
receives the same product of match scalars, so CELL and MARKET rank tickets in
exactly the same order. All 138,614 matched pilot actions were identical. The
two modes can affect *match-subset selection*, but they are not separate
outcome-ranking parameters after the subset is fixed.

`DIVERGENCE_VALUE` does change the within-match ordering. A thin one-subset,
one-stream screen produced several spectacular rows, but nuisance confirmation
showed why those rows cannot be read literally:

| Candidate | Thin mean ROI | Denser mean ROI | Denser ex-largest ROI | Denser 2023 ROI | Interpretation |
|---|---:|---:|---:|---:|---|
| N8 / shape / divergence / weighted / K16 | +134.05% | **−12.66%** | −18.06% | +38.08% | 8-subset × 5-seed confirmation rejects the apparent Edge |
| N9 / divergence-selector / divergence / weighted / K64 | +800.83% | **+5.27%** | −13.41% | −19.17% | retains a sweet-zone clue, not robust absolute Edge |

For the N9 row, matched divergence-minus-CELL lift is +33.36pp and remains
+14.57pp after removing its largest lift issue, but its issue-bootstrap interval
is [−5.55pp, +85.97pp] and only four of ten calendar years are positive in
absolute ROI. It is a high-variance, post-selected hypothesis.

### Can current Data learn when to switch value mode?

The N9/K64 matched pair was used for an isolated annual expanding-window OOF
test over 2018–2023. The target was continuous issue-level
`DIVERGENCE_VALUE − CELL_VALUE` lift, not a hindsight winner class. Inputs were
the 18 accepted pre-event aggregate issue-state features.

| Policy | OOF ROI | Lift vs CELL | Ex-largest ROI | Lift bootstrap 95% interval | Divergence use | Ending CNY100k capital |
|---|---:|---:|---:|---:|---:|---:|
| Fixed divergence | **+0.015%** | +31.50pp | −8.23% | [−4.48pp, +68.20pp] | 100.0% | **100,004.82** |
| HGB dynamic mode | −17.94% | +13.55pp | −26.24% | [−19.38pp, +48.40pp] | 60.2% | 94,135.25 |
| MLP dynamic mode | −19.88% | +11.61pp | −24.67% | [−19.97pp, +41.06pp] | 74.3% | 93,498.89 |
| Ridge dynamic mode | −21.59% | +9.90pp | −26.39% | [−20.97pp, +39.88pp] | 82.3% | 92,939.65 |
| Fixed CELL | −31.49% | 0 | −37.27% | fixed | 0% | 89,703.34 |

The fixed divergence row was discovered after inspecting the development
surface, so even its near-flat path is not clean candidate evidence. More
importantly, every learned switcher underperforms the fixed divergence action.
Current aggregate Data have not learned the parameter as a function of issue
state; they mostly add switching error.

The next feature layer should therefore encode the *shape* of the M×3
divergence surface: counts/mass above signed thresholds, positive-versus-negative
tail asymmetry, divergence × probability/value ranks, line buckets, source
reliability and within-issue concentration. Only after a mode model beats the
same fixed divergence control should outcome mode be restored to the full joint
`N × selector × mode × generator × K` policy.

## Next design decision

1. Keep explicit enumeration of N=3,…,10.
2. Treat the expected-N frontier as a deterministic optimizer input, not as a
   learned realized-return truth.
3. Retain action-only, state+action and full-feature model ablations. A dynamic
   contribution exists only if it beats the best contemporaneously available
   static action, not merely the inherited weak baseline.
4. Add an uncertainty/abstention boundary: if top N is not separated from the
   runner-up, retain the frozen baseline rather than forcing an argmax.
5. Preserve a bounded joint action space rather than optimizing each parameter
   separately, but do not claim that the current MLP has learned it dynamically.
6. Learn a return distribution (and matched lift) conditional on pre-event Data,
   not a realized winner label. Require an abstention/fallback action whenever
   the lower uncertainty bound does not beat the frozen control.
7. Selector family is now an explicit action. The outcome-value surface is also
   an action parameter, but its severe cross-year reversal means it should be
   conditioned on richer pre-event matrix/distribution features; keep random
   subset/stream seeds as nuisance replicas.
8. Remove the CELL-versus-MARKET outcome-ranking alias after a subset is fixed;
   retain their distinction only where it changes match selection. Treat
   DIVERGENCE as the genuine outcome-ranking mode and require richer matrix
   shape features before another dynamic switching attempt.
9. Preserve the accepted baseline ladder separately. The pilot N7 values here
   are matched controls for this sampled-subset experiment, not a replacement
   for the accepted −9.47% BEST_FULL baseline.

The current feasibility verdict is:

> **JOINT PARAMETER INTERACTIONS EXIST, BUT CURRENT MODELS MOSTLY RECOVER A
> STATIC N7/TOP/K512 ACTION. DYNAMIC DATA-CONDITIONED SELECTION IS NOT YET
> DEMONSTRATED. OUTCOME-VALUE MODES ALSO REVERSE ACROSS REGIMES, SO THE NEXT
> GAIN MUST COME FROM LEARNING MARKET STATE, NOT FROM FIXING ANOTHER GLOBAL
> WINNER.**
