# Issue #209 decision report — learned dynamic N/K/ticket policy

## Five-minute decision

Issue #209 now contains a genuine learned **per-issue** policy rather than a
fixed N7 dry-run.  A Beijing issue is the independent sample.  Its pre-event
M×3 surface is summarized into issue state, combined with an explicit action
`(N, K, generator)`, and evaluated by an action-conditioned two-part learner.
The action surface contains N={3,5,7,8}, K={8,32,128,512}, TOP_VALUE,
WEIGHTED_WR, WEIGHTED_WOR and NO_BET.  The K values are experimental anchors,
not a maximum-stake rule.

The method objective succeeded: the frozen 2023 policy selected **six distinct
actions**, so it did not collapse back to fixed N7 or hindsight grid selection.
The investment objective did not succeed: the learned active policy ended at
**CNY98,838.66**, versus **CNY99,152.00** for the matched fixed N7/K8
TOP_VALUE control, a **-0.316 percentage-point matched lift**.  The safe arm
selected NO_BET in every 2023 issue and retained CNY100,000; that is prudent
abstention, not evidence of alpha.

**PI disposition: RETAIN_FIXED_CONTROL_NO_PROMOTION.**  Gate B / 2024 remains
sealed.  #209 proves that dynamic parameter selection can be expressed as a
learning problem, but this state representation and objective do not yet
generalize well enough to replace the incumbent.

## Experimental design

- Unit: one Beijing issue, never one ticket or one M×3 cell.
- State: only pre-event issue breadth, line/book context, probability shape,
  value-distribution shape and EU-vs-line divergence summaries.
- Action: N, K and complete-ticket generator; NO_BET is explicit.
- Labels: every supported action is settled on the same realized issue state.
- Seeds: three nuisance replications are averaged *within* an issue/action row;
  seed is not a feature or a policy action.
- Economics: each ticket costs CNY2; a winning N-fold ticket pays
  `2 × 0.65 × product(SP_i)`.  The 0.65 factor is applied once per ticket,
  never per leg.
- Chronology: fit through 2021; choose model family on 2022; refit through 2022;
  freeze 2023 actions before joining outcomes.  No 2024 outcome was opened.

The learner is a maintained-library two-part model.  LogisticRegression or
MLPClassifier estimates the probability of positive issue PnL.  Two
HistGradientBoosting regressors estimate conditional positive payoff and
non-positive loss fraction; a quantile model supplies the downside term.
Selection maximizes predicted risk-adjusted log-capital increment.

## Results

| Out-of-time block / arm | Issues | Ending capital | Capital return | Turnover | Max DD | Longest loss run |
|---|---:|---:|---:|---:|---:|---:|
| 2023 learned active | 53 | CNY98,838.66 | -1.161% | CNY1,328 | 1.169% | 26 |
| 2023 fixed N7/K8 TOP_VALUE | 53 | CNY99,152.00 | -0.848% | CNY848 | 0.848% | 53 |
| 2023 safe arm | 53 | CNY100,000.00 | 0.000% | CNY0 | 0.000% | 0 |

The active arm lost CNY1,161.34 and produced four profitable issues out of 53.
It chose six actions: N7/K8/WR 32 times, N5/K8/WOR 7, N5/K8/WR 6,
N3/K8/WOR 5, N5/K128/TOP_VALUE 2 and N7/K8/WOR once.  This establishes
state-conditioned variation, not profitable variation.

Model-family selection on 2022 favored MLP_TWO_PART:

| Family | 2022 selected PnL | Mean utility (bps/issue) |
|---|---:|---:|
| LOGISTIC_TWO_PART | -CNY992.00 | -1.600 |
| MLP_TWO_PART | +CNY2,151.27 | +3.427 |

The 2022 MLP result is not solely one-hit luck: removing its largest profitable
issue still leaves +CNY1,113.19.  Nevertheless it fails the stronger test:
the frozen mapping reverses to -CNY1,161.34 in 2023, and removing 2023's
largest winner worsens it to -CNY1,197.20.  Hence the failure is temporal
generalization, not merely a reporting artefact.

## Adversarial interpretation

1. **Dynamic does not mean better.** Six actions prove the interface works;
   they do not prove the policy learned stable causal regimes.
2. **NO_BET is not Edge.** The safe arm sees uniformly negative risk scores and
   holds cash.  It is a valid fallback constraint, not a profitable model.
3. **WR versus WOR has no global winner here.** Both appear in selected actions;
   their usefulness is conditional, and the learned conditioning failed OOT.
4. **The oracle gap is not actionable.** The outcome-aware oracle earns far
   more in retrospect, but it is diagnostic only and never enters features.
5. **Capital beats raw ROI for this comparison.** The active policy's per-unit
   turnover return is less bad than the zero-hit fixed control, yet its larger K
   loses more absolute capital.  The CNY100k matched path correctly rejects it.
6. **Do not spend the 2024 holdout.** A candidate that already fails 2023 does
   not earn a terminal test merely because 2024 exists.

## What #209 taught the unified-model roadmap

The right abstraction is confirmed: learn `Q(state, action)` and choose N/K/
generator per issue, with cash as a safe fallback.  The next improvement should
not be a wider static grid.  It should improve the information and learning
target: retain richer M×3 distribution structure, expose Beijing-line versus
European-market/strength-model disagreement explicitly, use walk-forward
training with more issue blocks, and regularize toward the frozen control when
the learned advantage is uncertain.  Any future candidate must still report
absolute CNY100k capital and matched lift against the accepted baseline.

## Reproducibility and boundary

- Executable: `scripts/run_bj209_dynamic_gate_a.py`
- Core implementation: `src/issue209/dynamic_policy.py`
- Notebook: `notebooks/research/issue-209/bj209_gate_a.ipynb`
- Controlling receipt: `results/issue-209/dynamic_decision.json`
- Matched paths: `results/issue-209/dynamic_matched_capital_paths.csv`
- 2024 rows opened: **0**; Gate B authorized: **false**.
