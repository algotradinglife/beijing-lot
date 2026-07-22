# SP-EFF-001 — SP Market Efficiency Study

> This is a market-information experiment, not a strategy backtest. No betting rule, stake rule, parameter search, or ROI objective is used.

## Dataset version

- Source: `data/beidan_live.db` (`165,486,592` bytes)
- Extracted: `2026-07-21T16:41:04+00:00`
- Reproduction cutoff (`--as-of` UTC): `2026-07-21T16:41:04Z`
- Stable settlement version SHA-256: `d6348828ede66c26abb53d69f6a5073bc12d4588d5b62395c7bac94440743a9c`
- Canonical extract SHA-256: `e0606fce3cb4e30dfcf80ba3e47787e6d750e24af3ed573336eb716c577f0b39`
- Complete-snapshot rows examined: `514,417`; valid settled matches: `2,260`
- Eligible matches after strict pre-kickoff filtering: `2,137`
- Kickoff range (UTC): `2026-05-02T03:55:00+00:00` to `2026-07-21T10:30:00+00:00`
- Included snapshot range (UTC): `2026-05-02T00:57:41+00:00` to `2026-07-21T10:21:55+00:00`
- Rejected invalid-timestamp rows: `0`; rejected post-kickoff rows: `105,156`
- Closing snapshot lead time: minimum `0.02` min; median `7.70` min

Dataset version is the canonical extract hash, not merely the mutable SQLite filename. The cutoff applies to snapshots; outcome labels are bound by the stable settlement version (match ID, result code, and result-structure hash), never mutable `settled_ts`.

## Research Question

RQ001: Does Beijing Single Match (北京单场) SP contain calibrated predictive information about the 90-minute handicap win/draw/loss result?

- H0: after a reasonable probability transformation/calibration, SP probabilities agree with realized outcome frequencies.
- H1: systematic calibration deviations remain.

## Methodology

1. Keep settled 3/1/0 matches with a complete three-way SP vector (`SP > 1` for all outcomes).
2. Interpret `snapshot_ts` as UTC and naive `kickoff_ts` as Asia/Shanghai. Select the latest complete vector strictly before kickoff; post-kickoff and invalid timestamps are excluded.
3. Transform SP jointly, not as `P = 1/SP`: `p_i = (1/SP_i) / Σ_j(1/SP_j)`. This removes the match-level overround and forces coherent three-way probabilities.
4. Preserve full issue boundaries in a fixed 70/30 chronological split. The first issues train the historical prior and one temperature parameter; the last issues are untouched holdout data.
5. Fit temperature scaling only on training log loss: `p'_i ∝ p_i^(1/T)`. No outcome-dependent rule or profitability search is performed.
6. Report fixed 0.1 probability calibration bins, fixed SP bands, and SP movement quartiles. SP movement is the mean absolute log change across the three outcomes from the earliest to the closing eligible snapshot; quartile cutoffs come from training data only.

Training issues (16, n=1,802): `26051, 26052, 26053, 26054, 26055, 26056, 26057, 26058, 26061, 26062, 26063, 26064, 26065, 26066, 26067, 26068`.

Holdout issues (8, n=335): `26069, 26071, 26072, 26073, 26074, 26075, 26076, 26077`.

## Baseline

- B0 — uniform random: `(1/3, 1/3, 1/3)`.
- B1 — SP market: normalized inverse-SP probabilities.
- B1-T — the same market probabilities with a single train-fitted temperature (`T=2.3270`). This is the calibrated H0 check.
- B2 — independent historical-win-rate model: the constant 3/1/0 frequencies estimated only from training outcomes.

## Metrics

- Multiclass Log Loss (lower is better).
- Three-class Brier Score `mean(Σ(p-y)²)`, unscaled, range 0–2 (lower is better).
- Calibration curve and ECE (cell-count-weighted absolute calibration gap).
- Per-cell standardized calibration residual tests with Holm family-wise correction across the fixed holdout cells.
- Paired proper-score differences with a 5,000-sample whole-issue cluster bootstrap.

ROI is deliberately absent.

## Results

### Holdout baseline comparison

| Baseline | Log Loss | Brier Score | ECE |
| --- | --- | --- | --- |
| B0 uniform random | 1.09861 | 0.66667 | 0.0484 |
| B1 normalized inverse SP | 1.08668 | 0.65722 | 0.0414 |
| B1-T train-fitted temperature | 1.08037 | 0.65470 | 0.0412 |
| B2 historical outcome frequency | 1.08846 | 0.66002 | 0.0246 |

Temperature calibration changes holdout Log Loss by `-0.00631` and Brier Score by `-0.00252` relative to raw normalized SP.

### Paired holdout score differences

Negative values favor the SP model. Confidence intervals resample whole holdout issues.

| Model | Comparator | Metric | Delta | 95% CI low | 95% CI high |
| --- | --- | --- | --- | --- | --- |
| B1 normalized inverse SP | B0 uniform random | Log Loss | -0.01193 | -0.06215 | +0.03087 |
| B1 normalized inverse SP | B0 uniform random | Brier Score | -0.00945 | -0.04281 | +0.01847 |
| B1 normalized inverse SP | B2 historical outcome frequency | Log Loss | -0.00178 | -0.04579 | +0.03614 |
| B1 normalized inverse SP | B2 historical outcome frequency | Brier Score | -0.00280 | -0.03190 | +0.02215 |
| B1-T train-fitted temperature | B0 uniform random | Log Loss | -0.01824 | -0.03645 | -0.00244 |
| B1-T train-fitted temperature | B0 uniform random | Brier Score | -0.01197 | -0.02499 | -0.00086 |
| B1-T train-fitted temperature | B2 historical outcome frequency | Log Loss | -0.00808 | -0.02154 | +0.00469 |
| B1-T train-fitted temperature | B2 historical outcome frequency | Brier Score | -0.00532 | -0.01482 | +0.00343 |

![Out-of-sample calibration](../figures/sp_eff_001_calibration.png)

### Calibrated market probability bins (holdout)

| Outcome | Probability bin | n | Mean p | Actual rate | Gap | Holm p | Significant |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 0.1-0.2 | 1 | 0.185 | 0.000 | -0.185 | 1.0000 | False |
| 3 | 0.2-0.3 | 40 | 0.280 | 0.350 | +0.070 | 1.0000 | False |
| 3 | 0.3-0.4 | 242 | 0.351 | 0.388 | +0.038 | 1.0000 | False |
| 3 | 0.4-0.5 | 50 | 0.418 | 0.540 | +0.122 | 0.9620 | False |
| 3 | 0.5-0.6 | 2 | 0.523 | 0.500 | -0.023 | 1.0000 | False |
| 1 | 0.1-0.2 | 5 | 0.163 | 0.400 | +0.237 | 1.0000 | False |
| 1 | 0.2-0.3 | 87 | 0.286 | 0.241 | -0.045 | 1.0000 | False |
| 1 | 0.3-0.4 | 243 | 0.320 | 0.280 | -0.040 | 1.0000 | False |
| 0 | 0.2-0.3 | 81 | 0.277 | 0.210 | -0.067 | 1.0000 | False |
| 0 | 0.3-0.4 | 224 | 0.346 | 0.353 | +0.007 | 1.0000 | False |
| 0 | 0.4-0.5 | 24 | 0.415 | 0.417 | +0.002 | 1.0000 | False |
| 0 | 0.5-0.6 | 4 | 0.563 | 0.500 | -0.063 | 1.0000 | False |
| 0 | 0.6-0.7 | 2 | 0.641 | 0.000 | -0.641 | 0.7619 | False |

### Closing SP bands (calibrated market, holdout)

| outcome | SP band | n | mean p | hit rate | gap |
| --- | --- | --- | --- | --- | --- |
| 3 | 1-1.5 | 2 | 0.523 | 0.500 | -0.023 |
| 3 | 1.5-2 | 39 | 0.423 | 0.436 | +0.013 |
| 3 | 2-3 | 177 | 0.368 | 0.441 | +0.072 |
| 3 | 3-5 | 103 | 0.310 | 0.330 | +0.020 |
| 3 | 5-8 | 11 | 0.265 | 0.455 | +0.190 |
| 3 | 8+ | 3 | 0.217 | 0.333 | +0.117 |
| 1 | 2-3 | 28 | 0.344 | 0.393 | +0.049 |
| 1 | 3-5 | 290 | 0.310 | 0.266 | -0.044 |
| 1 | 5-8 | 9 | 0.263 | 0.111 | -0.152 |
| 1 | 8+ | 8 | 0.185 | 0.250 | +0.065 |
| 0 | 1-1.5 | 6 | 0.589 | 0.333 | -0.256 |
| 0 | 1.5-2 | 21 | 0.417 | 0.381 | -0.036 |
| 0 | 2-3 | 142 | 0.364 | 0.373 | +0.010 |
| 0 | 3-5 | 132 | 0.308 | 0.295 | -0.012 |
| 0 | 5-8 | 34 | 0.261 | 0.176 | -0.085 |

### SP change magnitude (calibrated market, holdout)

Training cutoffs for mean absolute log-SP change: `0.25576, 0.56732, 1.03787`.

| change quartile | n | mean change | log loss | Brier |
| --- | --- | --- | --- | --- |
| Q1 | 63 | 0.15833 | 1.09350 | 0.66317 |
| Q2 | 81 | 0.38917 | 1.08109 | 0.65567 |
| Q3 | 109 | 0.76659 | 1.06649 | 0.64514 |
| Q4 | 82 | 1.53893 | 1.08803 | 0.65994 |

## Limitations

- The live collector covers only a short 2026 window; issue sizes and league mix vary, and early issues are much larger than later issues.
- The last observed collector snapshot is a closing proxy, not an exchange-grade official closing timestamp. Lead time varies by match.
- `result_code` is taken from the settlement table as the 90-minute handicap 3/1/0 label; this experiment does not independently reconstruct every settlement from raw scores and handicap history.
- The historical-frequency baseline is intentionally simple. It establishes an outcome-frequency comparator, not a best possible team-strength model such as a mature Elo system.
- Calibration cells in the tail can be small. Holm correction controls the declared family of fixed-bin tests, but the short holdout still has limited power.
- SP movement is descriptive and may reflect unequal observation windows. It is not interpreted as a tradable signal.

## Conclusion

The calibrated SP model has lower holdout Log Loss than at least one non-market baseline, but at least one issue-block-bootstrap interval crosses zero. This is directional, not conclusive, evidence of incremental predictive information.

Fail to reject H0 on this holdout: no pre-specified probability/outcome cell retains a calibration deviation after Holm correction.

The market-information conclusion should also consider whether B1/B1-T improve proper scoring rules over B0 and B2. A detected statistical bias is only a research starting point; it does not establish a realizable trading edge after payout rules, timing, limits, or costs.

## Reproduction

```bash
python scripts/run_sp_eff_001.py --db data/beidan_live.db --as-of 2026-07-21T16:41:04Z
```
