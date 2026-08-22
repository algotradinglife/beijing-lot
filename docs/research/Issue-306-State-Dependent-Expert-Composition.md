# Issue #306 — state-dependent expert composition and dynamic funding intensity

## Five-minute decision summary

The experiment returns **EXPERT_VALUE_SIGNAL / NO PROMOTION**.

The state-dependent dynamic policy (Stage A keep/skip + Stage C composition +
Stage C intensity) takes CNY100,000 to **CNY109,091.87 (+9.09%)** on the 2023
matched support, versus **CNY79,248.96 (-20.75%)** for exact `B0_BEST_FULL`.
The matched improvement is **CNY29,842.90 / +29.84 percentage points**, and the
policy also beats cash, the #299 learned residual, the train-only static
mixture, issue-block shuffle and expert-identity shuffle on identical support.

Decomposition shows where the lift lives:

- **Stage A keep/skip alone: +10,373 CNY** — the frozen expert-label-invariant
  BEST_FULL head funds 11 of 35 active 2023 issues and beats always-keep by
  +10.4k. (Stage A is a local reference fit with identical semantics until #305
  delivers its frozen output; the tag is explicit in every artifact.)
- **Composition at a fixed intensity: +0 CNY** — the fixed funding fraction
  selected on earlier expanding OOF folds collapses to 0%, exactly reproducing
  the #302 finding that a global static funding scalar has no causal value.
- **Dynamic intensity: +19,470 CNY** — the state-dependent intensity function
  deploys a positive fraction on favorable issues (46% of 2023 issues receive
  non-zero funding) and is the increment that makes the expert layer valuable.

Falsification is honest: the primary policy is at the **75th percentile** of the
exact executed-exposure null, below the 95% barrier. Random placement of the
same bundle copies slightly beats it in the tail, so the dynamic expert claim is
not yet promotable. Verdict is therefore `EXPERT_VALUE_SIGNAL` — mechanism
works and experts add positive matched lift, but cash/static/exact-null
barriers are not all cleared.

## Question and hypotheses

The focal question: can a small causal mixture-of-experts learner map pre-event
issue state to (1) expert identity scores, (2) relative expert weights, and
(3) total expert funding intensity, so that expert combination adds transferable
value over the corrected dedicated BEST_FULL keep/skip policy?

Four rival explanations were tested: true state-dependent expert value,
abstention alone (keep/skip), a static tail mix, and under-identification.
Controls: cash, exact B0_BEST_FULL, #299 learned residual, #305-stage keep/skip,
train-only static mixture, learned composition with fixed intensity, learned
intensity with fixed composition, issue-state block shuffle, expert-identity
shuffle, exact executed-exposure null, and an oracle diagnostic.

## Frozen hierarchy and support

- **Stage A** — frozen expert-label-invariant BEST_FULL keep/skip (Issue #305
  contract). The loader prefers `results/issue-305/keep_skip_predictions.csv`;
  until #305 delivers, a local reference fit with byte-invariance to expert
  labels is used and tagged `LOCAL_REFERENCE_FIT_PENDING_305`. No module
  back-propagates into Stage A decisions.
- **Stage B** — shared action-conditioned value over four realizable whole-bundle
  ledgers: SMOOTH_M512, Q_TAIL_M192, DIVERGENCE_Z100_K1, RARE_LOGIT_TOP64.
  Multi-task heads: expected pre-tax P&L, payout probability, positive-P&L
  probability, loss probability, downside, conditional payoff, tail-capture
  probabilities at 2×/5×/10× gross and +50%/+100%/+200% gain, cross-seed
  uncertainty.
- **Stage C** — composition (softmax over predicted utilities, masked by
  availability) and intensity (ridge from issue state + Stage-B risk stats,
  clipped to [0,1]). Weights become non-negative integer copies of complete
  bundles; total stake never exceeds intensity × current bankroll; remaining
  capital stays in cash. No fixed per-issue stake cap.
- Independent unit is the issue; experts, tickets, seeds are nested. Expanding
  predictions: 2021 ← 2019-20, 2022 ← 2019-21, 2023 ← 2019-22. 2024+ sealed.
  Objective selection (mean-P&L vs log-wealth vs downside-aware) is performed
  only on earlier expanding OOF folds; 2023 realized outcomes never select the
  funding rule.

## Twelve mandated controls

| # | Control | 2023 terminal | 2023 growth | Funded issues | Interpretation |
| --- | --- | --- | --- | --- | --- |
| 1 | cash | 100,000.00 | 0.00% | 0 | no-bet reference |
| 2 | exact B0_BEST_FULL | 79,248.96 | -20.75% | 35 | always-keep baseline |
| 3 | #299 learned residual | 90,895.64 | -9.10% | 10 | prior residual path |
| 4 | Stage A keep/skip | 89,622.24 | -10.38% | 11 | frozen dedicated keep/skip |
| 5 | train-only static mixture | 32.00 | -99.97% | 3 | full-bankroll static mix (ruined) |
| 6 | composition, fixed intensity | 89,622.24 | -10.38% | 11 | fixed intensity selected on OOF = 0 |
| 7 | intensity, fixed composition | 7,830.24 | -92.17% | 32 | dynamic intensity on static mix (ruined) |
| 8 | **fully dynamic (primary)** | **109,091.87** | **+9.09%** | **24** | composition + intensity |
| 9 | issue-state block shuffle | 87,549.08 | -12.45% | 23 | state signal destroyed |
| 10 | expert-identity shuffle | 56,221.26 | -43.78% | 26 | expert identity destroyed |
| 11 | exact executed-exposure null | p75 = 105,851 | — | — | primary percentile 0.75 < 0.95 |
| 12 | oracle diagnostic | 137,198.79 | +37.20% | 11 | upper bound only |

Controls 5 and 7 are full-bankroll expert placements by construction (#302's
static control behaved the same, ending 2023 at CNY84.88); they are destroyed
because one 2023 issue can nearly wipe a 100k bankroll when all experts are
funded at high intensity. The gap between them and the primary is therefore the
value of learned state-dependent intensity, not an artifact.

## Long-tail capture

- primary 2023: 35.4% payout issue rate, 6.25% issues with gross ≥ 2× stake,
  rolling-5/10/20 capture probabilities positive.
- Stage A keep/skip funds only issues where the expected utility head is above
  zero, which also prunes the worst losing streaks (max drawdown 27.2% vs 28.5%
  for B0).
- The tail-capture heads are trained per issue, but the exact-null percentile
  (0.75) shows placement of tail-funding across issues is not yet separable
  from random.

## Seed and calibration

- Stage A receipts: mean/downside MLPs converged for all seeds/years;
  `expert_label_inputs=0` in every receipt.
- Stage B 2023 per-seed mean predicted P&L: all four experts negative
  (Q_TAIL_M192 -558 to -604 per bundle, RARE_LOGIT_TOP64 -66 to -400); the
  composition softmax therefore selects the least-negative available experts,
  and intensity concentrates funding on the least risky issues.
- Cross-seed disagreement is carried as `predicted_pnl_std_cny` and adds a
  risk penalty to the intensity design.

## Deliberate limits and decision input for PI

1. **Stage A is NOT #305's frozen output yet.** `stage_a_source =
   LOCAL_REFERENCE_FIT_PENDING_305`; the loader will switch to
   `results/issue-305/keep_skip_predictions.csv` when #305 delivers. Re-running
   this experiment after #305 merges is cheap (≈40 s) and will replace the
   reference with the frozen head.
2. Composition at the fixed-intensity margin adds zero separately from
   keep/skip; dynamic intensity is where the expert layer adds value. This
   isolates the promising lever for a follow-up: learn intensity with better
   OOF signal (the current ridge collapses most issues to zero).
3. The exact executed-exposure null (75th percentile) fails the 95% barrier;
   no promotion, no #210 access, and 2024+ remains sealed. Any candidate
   follow-up must clear the null plus a separately approved held-out gate.
4. Controls 5/7 ruin under full-bankroll expert placement; this is a real
   feature of the whole-bundle integer execution contract, not a bug, and it is
   precisely why state-dependent intensity is necessary.