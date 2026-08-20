# Issue #209 — Unified Learning Gate A (divergence-aware M×3 value model)

First-cycle Gate-A delivery on 2026-08-20 (exploration mode). Data surface from
accepted #268/#238. **Gate B (2024 terminal) is sealed and NOT opened** — it
requires an independent PI authorization after Gate-A freeze review.

## What was built

A reuse-first, package-backed M×3 distributional value pipeline under
`src/issue209/`:

- **Tensor + census** (`data.py`): 808-issue M×3 development tensor (1.5M labeled
  cells), frozen chronological roles (fit ≤ 2021 / tune 2022 / calibration 2023 /
  sealed 2024+), settlement-SP label joined at ~99% dev coverage, hard 2024 seal.
- **Distributional learning** (`models.py`): multinomial outcome probability with
  categorical cross-entropy + Brier + ECE; market-only baseline, calibrated
  logistic, bounded PyTorch-MLP challenger; selection on 2022 issue-block
  log-loss only; 2023 untouched confirmation.
- **SP + cell value** (`value.py`): HistGradientBoosting quantile regression
  (q10/q50/q90) on pre-event channels; R_RAW = P(win) × SP with uncertainty;
  0.65 never applied per cell.
- **Ticket / bankroll** (`ticket.py`, `bankroll.py`): dynamic N/K policy layer;
  0.65 applied once per winning N-fold ticket (golden-tested, never 0.65^N);
  CNY100k pre-tax path, NO_BET/cash, matched lift, promotion rule.
- **Integrity** (`verify.py` + tamper tests): hash + semantic ledger-invariant
  verification; re-manifest forgery and seal forgery both rejected.

## Honest first-cycle result

On the 2022 tune block the learned challengers (logistic 1.14719, MLP 1.14619)
**did not beat** the label-free market baseline (1.14494). Per the adversarial
rule (a learner failing to beat a simpler calibrated control is not promoted),
the frozen candidate is **MARKET_ONLY_CELL**, not relabelled as learned.

2023 untouched confirmation log-loss 1.14433 (Brier 0.21569) is consistent.

## Boundary statement

Exploration `[EVIDENCE]` debt is tracked (dynamic-N sweep, per-outcome SP
sparser at official level). None alters the conclusion. No promotion, no
production claim, no 2024 opening arises from this delivery.
