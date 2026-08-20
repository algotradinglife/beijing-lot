# Issue #282 — Conditional M×3 Policy Decision Report

Date: 2026-08-20  
Contract: `BJ-UNIFIED-CONDITIONAL-POLICY-001/v1`  
Primary split: fit through 2022, frozen replay on 2023  
Outcome seal: no 2024+ outcome was opened

## Five-minute decision summary

#282 proves that the variable-size issue tensor, complete-action counterfactual
engine and learned policy can run end to end. It does **not** establish a learned
betting Edge.

- The five-seed Deep Sets ensemble selected cash in all 53 primary 2023 issues.
  Ending capital was therefore exactly CNY100,000, with zero turnover and zero
  drawdown. This is an effective abstention rule, not a profitable learned policy.
- The frozen active N7/K8 market TOP control ended at CNY99,719.69. The neural
  policy exceeded that weak active control only by refusing to bet; it did not
  meet the stronger requirement of growing capital above cash.
- Linear and HGB learned policies ended at CNY97,616.17 and CNY99,289.97.
  Neither improved the frozen control.
- Annual expanding-window OOF confirms the diagnosis. Deep Sets funded only two
  model deviations over 2018–2022 and made CNY38.09 in total, while its matched
  lift versus the contemporaneously frozen active controls was CNY−2,394.25.
  HGB had three positive calendar slices but CNY−4,057.37 aggregate matched lift.
- The formal holdout gate fails: zero 2023 model-selected funded deviations,
  zero of five neural seeds above cash, and ending capital not above cash.
  Consequently #210 remains blocked and 2024+ labels stay sealed.

The useful scientific result is narrower: fixed-action diagnostics expose a
large, unstable `N8 × weighted sampling` regime. The leading row,
`ALL × CELL_VALUE × N8 × WR/WOR × K512`, returned +17.56% in 2023 and +2.82%
over 2014–2022, but its development gain is dominated by 2014 and becomes
negative after removing 2014. This is a hypothesis about observable issue
state/regime, not an accepted fixed policy.

## 1. What was built

### 1.1 Causal issue representation

Each Beijing issue is represented as a padded, masked `M × 3 × F` tensor. The
three cells of every match carry only pre-event inputs: calibrated market
probability, Beijing-line divergence, predicted SP/value, uncertainty,
mapping/source reliability and within-issue ranks. The packer rejects columns
whose names carry settlement, result, final-SP, payout or capital-outcome
semantics.

The realized outcome enters only after a complete action is frozen and needs to
be settled. The 0.65 Beijing coefficient is applied once to a complete winning
N-fold ticket, never once per leg.

### 1.2 Complete action space

The thin prototype scores 432 action identities where feasible:

- match pool: `ALL` or `TOP_HALF_VALUE`;
- outcome proposal: `CELL_VALUE`, `MARKET_PROBABILITY`, or
  `DIVERGENCE_VALUE`;
- N: 3 through 8;
- generator: `TOP_VALUE`, `WEIGHTED_WR`, or `WEIGHTED_WOR`;
- K: 8, 32, 128, or 512 distinct ticket identities;
- R: one CNY2 unit per distinct ticket;
- W: funded action turnover or cash.

K never means repeated copies of the same ticket. WR duplicate proposals are
collapsed into identity plus proposal-frequency evidence. Under the current
equal distinct-ticket stake rule, WR and WOR therefore fund identical tickets;
their proposal frequencies are reserved for a later explicit Stage-4 stake
model.

Sixteen deterministic common ticket streams are averaged inside each
issue/action. There are 267,768 action rows across 620 independent issues. The
statistical unit remains the issue, not the action row or ticket stream.

### 1.3 Models

Three maintained-library implementations were used:

1. scikit-learn linear/logistic controls;
2. scikit-learn HistGradientBoosting controls;
3. a small PyTorch Deep Sets issue encoder plus action-conditioned MLP.

The neural heads estimate positive-return probability, positive magnitude,
expected normalized P&L, and q10/q50/q90. Training combines classification,
robust magnitude/value losses, quantile pinball loss and within-issue ranking.
Every issue has equal aggregate training weight. Five initialization seeds are
aggregated by median; the best seed is never selected after outcomes.

## 2. Time design

- 2014–2017: initial development window;
- 2018–2022: annual expanding-window OOF diagnostics;
- 2023: primary frozen-2022 replay;
- 2024+: sealed.

The active fallback is selected from the declared N7/K8 controls using only
2014–2022 total P&L. That produces `FIXED_N7_K8_TOP_MARKET`. This current-tensor
control is not a replacement for legacy BEST_FULL −9.47%: BEST_FULL used a
different selected issue support, complete FULL enumeration and risk scale.
There is no honest one-to-one ticket identity mapping onto the #282 action
surface, so it remains a separately reported baseline ladder rung.

The #209 frozen dynamic artifact likewise operates with its own action schema
and dry-run funding semantics rather than a complete `(S,O,N,G,K,R,W)` ticket
identity on identical #282 support. It is not silently relabeled as a matched
Stage-3 action.

## 3. Primary 2023 capital result

All values below are pre-tax capital outcomes from CNY100,000; the one-time 0.65
payout factor is already inside ticket settlement.

| Policy | Ending capital | P&L | Turnover | Positive issues | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Cash | 100,000.00 | 0.00 | 0 | 0 | 0.00% |
| Frozen N7/K8 market TOP | 99,719.69 | −280.31 | 848 | 2 | 0.72% |
| N7/K8 cell-value WR/WOR | 100,134.21 | +134.21 | 848 | 8 | 0.36% |
| Linear learned policy | 97,616.17 | −2,383.83 | 8,192 | 0 | 2.38% |
| HGB learned policy | 99,289.97 | −710.03 | 3,072 | 4 | 0.71% |
| Deep Sets ensemble | 100,000.00 | 0.00 | 0 | 0 | 0.00% |

The positive N7 WR/WOR row is a diagnostic fixed policy, not the frozen active
control and not a learned choice. Its P&L is only CNY134.21 across 53 issues and
does not establish stability.

All Deep Sets candidate expected values in 2023 were negative after downside
penalty. The guard therefore funded no neural deviation. Calling the resulting
CNY100,000 path “positive model performance” would be incorrect: the result is
`NO_BET`, and its advantage over the active control is entirely retained cash.

## 4. Expanding-window evidence

For every validation year, preprocessing, controls, the neural model and the
fallback choice use only earlier years.

| Model | 2018–2022 P&L | Funded model deviations | Positive years | Matched lift vs frozen active controls |
|---|---:|---:|---:|---:|
| Linear | −21,592.89 | 75 | 0/5 | −24,025.23 |
| HGB | −1,625.03 | 99 | 3/5 | −4,057.37 |
| Deep Sets | +38.09 | 2 | 1/5 | −2,394.25 |

This refutes the interpretation that the neural network learned a useful
dynamic action surface but happened to be cautious in 2023. Across OOF years it
almost always retreats to cash. HGB makes real choices, but those choices lose
relative to the corresponding frozen active controls in aggregate.

## 5. Static action diagnostics and the N8 signal

This analysis ranks 2023 actions only after settlement and is explicitly
post-outcome hypothesis generation. Development history is displayed beside
the 2023 row to prevent a favorable final year from being presented as frozen
evidence.

### 5.1 `CELL_VALUE × N8 × WR/WOR × K512`

- 2023: CNY9,530.88 P&L on CNY54,272 turnover; +17.56%; 23/53 positive issues;
  CNY4,387.69 remains after removing its largest winning issue.
- 2014–2022: CNY16,356.75 P&L on CNY579,584 turnover; +2.82%; 5/9 positive years.
- The development aggregate is dominated by 2014 (+32.12%). Removing 2014
  turns cumulative development P&L to CNY−28,374.67.
- 2018, 2021 and 2022 returns are −27.59%, −13.36% and −25.24%; 2023 reverses
  to +17.56%.

### 5.2 `MARKET_PROBABILITY × N8 × WR/WOR × K128`

- 2023: CNY7,760.63 P&L on CNY13,568 turnover; +57.20%; 26/53 positive issues;
  CNY6,457.14 remains after removing its largest winning issue.
- 2014–2022: CNY−8,454.96; −5.84%; only 2/9 positive years.

The first row is more interesting because both its long development aggregate
and 2023 are positive, but neither row is stable enough to promote. The shared
scientific clue is that 2023 favors broader N8 weighted ticket populations,
whereas recent training years taught the neural model to reject them. The next
question is therefore whether a causal state feature predicts this regime
transition—not whether N8 is globally superior.

## 6. Adversarial review

If challenged, the strongest objections are:

1. **Multiple-comparison selection.** The N8 rows were noticed after scanning
   hundreds of actions on 2023 outcomes. They are hypotheses, not confirmatory
   findings.
2. **Early-year concentration.** The apparent positive long-run N8/K512
   development mean depends on 2014; it is not a smooth cross-year edge.
3. **Nested evidence.** The 432 action rows per issue are highly correlated and
   cannot be treated as 432 independent observations.
4. **No learned support.** The primary network makes zero funded 2023 changes.
   A policy with no actions cannot validate dynamic parameter learning.
5. **Baseline mismatch.** Beating the weak current-tensor N7 control by holding
   cash does not beat the accepted BEST_FULL ladder on identical support.
6. **Model calibration scope.** The reported Brier score is over nested action
   rows and is diagnostic; it is not issue-level proof of investability.

## 7. Decision and next design change

Decision: **complete #282 as an informative negative prototype; do not unlock
#210 and do not open 2024+ outcomes.**

The next development hypothesis should remain within 2014–2023 and test a
causal regime-conditioned action prior focused on the N8 weighted-sampling
transition. It must be preregistered before fitting, compare against cash,
frozen N7 and the static N8/K512 candidate, and require genuine funded model
deviations. It should not add another unconstrained grid or tune against 2024+.

### Accepted prototype debt

The PI review accepts three contract deviations only because every primary
promotion gate is already negative and none can turn this result into a
candidate:

- the secondary causal-online 2023 update was not run; it is not allowed to
  replace the negative frozen-2022 primary result;
- the compact Deep Sets model was trained jointly rather than receiving a
  separately persisted cell-head pretraining phase;
- action-level summaries, overlap/HHI/ESS and requested/funded actions are
  persisted, but a separate committed ticket-identity ledger and full marginal-K
  continuation trace are not. Those would be mandatory before any candidate or
  finalize-mode handoff.

The contract also did not preregister a numeric calibration acceptance
threshold. The decision therefore marks calibration promotion as failed rather
than inventing a post-outcome cutoff. These debts explain why #282 can close as
an informative prototype but cannot authorize #210.

## 8. Artifacts

- Executed notebook: `notebooks/research/issue-282/bj282_conditional_policy.ipynb`
- Frozen method contract: `docs/research/issue_282_conditional_action_value_contract.md`
- 2023 capital-path figure: `docs/research/figures/bj282_2023_capital_paths.png`
- expanding OOF figure: `docs/research/figures/bj282_expanding_oof.png`
- N surface: `docs/research/figures/bj282_2023_n_surface.png`
- calibration: `docs/research/figures/bj282_2023_calibration.png`
- compact decision/results: `results/issue-282/`

Large counterfactual labels, model weights and row-level predictions remain
reproducible local artifacts and are intentionally not committed.
