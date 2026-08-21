# Issue #284 — N×3 Subset-Augmented Policy Contract

Status: frozen before the first outcome-bearing pilot. The live GitHub Issue
Graph and Issue #284 body remain lifecycle authority; this document binds the
implemented method.

## Estimand and unit

The model estimates the conditional distribution of complete ticket-action
value for a pre-event `N×3` match subset sampled from an issue's full `M×3`
tensor. Subsets are data augmentation and within-issue ranking observations.
The independent unit remains the Beijing issue. Every issue receives aggregate
loss weight one, and every chronological split is grouped by issue.

## Sampler

For each eligible N from 3 through 10, each epoch requests 32 distinct subsets:
eight from each of uniform, value-weighted, divergence-weighted and causal
shape-stratified proposal families. All inputs are pre-event. Duplicate subset
identities are rejected, per-match inclusion is capped/balanced, and the seed,
epoch, family, subset identity, ordered draw probability and issue-normalized
weight are persisted. Small combination spaces are exhaustively shuffled.

The ordered draw probability describes the recorded sequential proposal. It is
not an unordered Horvitz–Thompson inclusion probability and is not used to
inflate statistical weight.

## Learned boundary

The cycle learns the N-match subset, outcome proposal, N, generator and
marginal continuation over common K prefixes. It fixes one CNY2 unit per
distinct ticket and `W=2K` or cash. Dynamic R/W and prior bankroll/path state
are explicitly not tested and require a later Stage-4 experiment.

## Time and outcome boundary

2014–2017 initializes the model; 2018–2023 are annual expanding-window OOF.
All 2024+ outcomes remain sealed. Current/future outcome, final SP, payout and
capital changes cannot enter the sampler or feature tensor. The 0.65 factor is
applied once only after a complete winning N-fold ticket is frozen.

## Thin-first rule

Run one seed and one OOF fold first. Verify subset coverage, issue-weight sums,
loss scale, nonzero gradients, prediction dispersion and genuine funded model
activity before any six-fold/five-seed execution. An all-cash pilot triggers
method diagnosis rather than an expensive repeat.

## Pilot diagnostic amendment (2026-08-21)

The first 2014–2021 fit / 2022 validation pilot exposed two method facts before
the full run:

1. Learning raw action P&L caused the risk-aware score to choose the smallest
   effective ticket support (`N=3`, only 27 distinct outcome codes at `K=128`).
   This reduced nominal losses by reducing deployed stake and was not a valid
   strategy lift. The primary learning target is therefore matched CNY100 P&L
   lift versus the same-issue frozen baseline, with stake-normalized capital
   paths. Absolute P&L remains a required secondary output.
2. Under `R=1` per distinct ticket, `WEIGHTED_WR` and `WEIGHTED_WOR` have the
   same unique ticket order and settlement. Proposal-repeat frequency is
   diagnostic evidence, not an allocation difference. The current Stage 1–3
   model may compare `TOP_VALUE` with one weighted-distinct stream; a genuine
   WR/WOR choice requires an explicit Stage-4 repeat-to-stake rule and may not
   be claimed in this cycle.

With the corrected matched-lift target, a joint-N head improved the N7/UNIFORM
control on the 2022 development slice, but selected N3 in all 62 issues. The
follow-up design therefore enumerates `D_N` for every N from 3 through 10,
trains one N-specific scoring head, selects the best subset inside each N, then
traverses the eight N-frontier candidates on the same matched-CNY100 scale.
This removes mechanical competition between heterogeneous N supports without
pretending that nested subsets are independent samples.

The first per-N pilot selected N4 in 60/62 issues and N3 in 2/62. Its matched
lift over N7/UNIFORM was only CNY86 across 62 issues and became negative after
removing the largest positive issue. It proves that the enumeration path runs,
not that dynamic N has been learned. Before expanding to five seeds, the
N-specific scores require chronological cross-N calibration, static
`N × proposal-family` controls, action entropy, and matched incremental-K
labels. The 2022 result remains a method diagnostic, not a frozen candidate.

## Bounded joint-screen amendment (2026-08-21)

The PI direction is that the eventual action must be optimized jointly. A
greedy sequence that freezes the individually best N, then K, then generator
can miss interactions and is not the intended final design. The prototype
therefore adds a bounded factorial screen before training the joint policy:

- first screen: all `N=3,…,10`, both allowed Stage 1–3 generators and common
  `K=8,…,512` prefixes on one subset per proposal family;
- nuisance confirmation: `N=7,…,10`, four subsets per family and three fixed
  weighted-stream seeds;
- learned ablation space: the complete `N7…N10 × K × generator × four
  selector-families` factorial plus the cross-family ENSEMBLE, the frozen
  matched control and `CASH/ABSTAIN`. Keeping the complete bounded factorial
  avoids selecting neighborhoods with future validation outcomes.

Subset identity and stream seed are **not** action parameters. They are nested
nuisance replicas and must be averaged inside the issue/action label. Neither
the highest-return subset nor the highest-return seed may be selected using
realized outcomes. The model target is the conditional distribution of matched
lift over the frozen control, with lower-bound utility and baseline fallback;
the realized historical argmax is diagnostic only.

The selector family is an explicit action; only subset identity within that
family is nuisance. The later full action vector may add finer selector
thresholds, outcome-value surface, repeat/stake (`R/W`) and capital fraction.
Each addition must preserve the same issue-grouped chronological split and
report whether it adds matched lift after conditioning on the existing action
vector.

## Joint-policy diagnostic amendment (2026-08-21)

Annual OOF compares action-only, issue-state + action, and full expected-surface
models. This ablation is controlling: a learned policy is Data-conditioned only
if it improves over the action-only model and the best available fixed action.
All estimators enforce equal aggregate issue weight, rescaled to mean one before
fitting so regularization is invariant to nested action-row count. Under that
required weighting, MLP selects `N7/TOP_VALUE/K512/ENSEMBLE` in 323/328 issues
and adds only +0.086pp to the fixed action. Full HGB selects K512 in 295 issues
and K256 in 33; it adds +1.80pp over fixed K512, but its paired bootstrap interval
crosses zero. The dynamic-learning result is therefore a conditional-K
sweet-zone clue, not a reliable learned policy. The next iteration should test
that interaction with richer action semantics rather than merely add capacity.

Reuse of the #282 frozen outcome-surface labels confirms that value mode must be
part of that action semantics. The development winner
`MARKET_PROBABILITY/N7/TOP/K8` reverses from +38.54% in 2014–2022 to −33.06%
in 2023, while development-to-2023 rank Spearman across all 432 fixed actions is
only 0.305. Consequently, the next learned model may choose among
`MARKET_PROBABILITY`, `CELL_VALUE` and `DIVERGENCE_VALUE`, but may not fix a
mode from the full-history leaderboard. It must learn a pre-event regime → mode
relationship and compare it with same-regime static controls.

The thin subset interaction screen also identifies a removable alias:
`CELL_VALUE` and `MARKET_PROBABILITY` generate identical within-subset ticket
order because the predicted-SP multiplier is constant across the three outcomes
of each fixed match. They remain distinct only at the match-selection layer.
`DIVERGENCE_VALUE` is the genuine alternative outcome-ranking mode.

Two high apparent divergence rows were nuisance-confirmed with eight subsets
and five stream seeds. N8/shape/K16 collapsed from +134.05% to −12.66%. N9/
divergence-selector/K64 retained +5.27% but was −13.41% ex-largest and −19.17%
in 2023. An isolated 2018–2023 mode-switch OOF also failed: Ridge, HGB and MLP
all underperformed fixed divergence. This fixes the next method boundary: add
pre-event M×3 divergence-shape features before reintegrating mode into the full
joint policy; increasing network capacity alone is not authorized.

## Joint selective-protection amendment (2026-08-21)

Issue #285 showed that protection cannot remain an external sleeve added after
freezing the base action. The unified action vector is extended to:

`(N, selector, outcome_mode, generator, K, protection_policy)`.

`protection_policy` jointly determines no-protection/protection, protected base
ticket, protected leg, alternative outcome, confidence threshold and maximum
protection share. These choices compete with cash and additional unprotected
tickets under the same issue budget. The no-protection action and frozen base
portfolio remain explicit fallbacks.

The model must not first select the historically best N/K/base action and then
fit protection greedily. Base and protection choices are evaluated jointly on
matched incremental P&L. Specific subset identities and stream seeds remain
nuisance replicas and cannot enter the optimized action vector.
