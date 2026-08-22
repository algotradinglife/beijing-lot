# Issue #330 — Causal lagged regime state ledger

## Decision

`SPARSE_RESPONSE_REDESIGN`; promotion is `false`, and #210 remains blocked.

The state panel is useful, but the direct allocator target is not a viable gate:
only 5 of 252
observable issues have positive A1-minus-A0 PnL, and only
9 are nonzero. The next MoE interface is
`MULTITASK_LAGGED_CALIBRATION_STATE`: use lagged calibration/coverage state as a
shared auxiliary representation and keep expert PnL as the terminal evaluation,
not the only supervised label.

## Data completeness and annual state

| issue_year | issues | mean_trusted_fixture_fraction | eu_brier | line_brier | eu_top2_residual | line_top2_residual | allocator_observable | allocator_delta_sum | allocator_nonzero | allocator_positive |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 38 | 97.97% | 0.6477 | 0.6573 | +0.0087 | +0.0001 | 31 | -997 | 1 | 0 |
| 2021 | 63 | 98.51% | 0.6467 | 0.6598 | +0.0002 | -0.0048 | 56 | +36 | 2 | 1 |
| 2022 | 62 | 98.47% | 0.6478 | 0.6601 | -0.0024 | -0.0058 | 55 | +2773 | 1 | 1 |
| 2023 | 53 | 98.91% | 0.6470 | 0.6587 | +0.0016 | -0.0015 | 50 | -273 | 1 | 0 |
| 2024 | 66 | 99.17% | 0.6462 | 0.6585 | -0.0009 | -0.0016 | 60 | +8114 | 4 | 3 |

`Top2 residual = realized Top2 coverage - predicted Top2 probability mass`.
Positive values mean the model covered realized outcomes more often than its
assigned mass implied; this is a calibration diagnostic, not betting profit.

The broad probability layer is much more stable than the allocator payout:
European Brier varies by only 0.0016 across five years and beats
the Beijing-line control by 0.0096 to
0.0131 each year. Absolute annual Top2 calibration bias is
at most 0.0087. The large 2023/2024 allocator reversal therefore
does not look like a broad failure of the market probability center; sparse
winning-ticket allocation is the more direct explanation.

## Chronological predictive diagnostics

| target | issue_year | condition | issues | mse | mse_lift_vs_prior | spearman |
|---:|---:|---:|---:|---:|---:|---:|
| allocator_delta | 2023 | COMBINED_HGBR | 50 | 5906.752592 | -4114.251150 | -0.203 |
| allocator_delta | 2023 | COMBINED_HGBR_STATE_SHIFT | 50 | 4345.340677 | -2552.839235 | -0.015 |
| allocator_delta | 2023 | CURRENT_RIDGE | 50 | 10662.743203 | -8870.241761 | -0.064 |
| allocator_delta | 2024 | COMBINED_HGBR | 60 | 579798.143321 | -10421.177975 | -0.007 |
| allocator_delta | 2024 | COMBINED_HGBR_STATE_SHIFT | 60 | 580474.529229 | -11097.563884 | -0.057 |
| allocator_delta | 2024 | CURRENT_RIDGE | 60 | 549573.061651 | +19803.903695 | +0.241 |
| eu_brier | 2023 | COMBINED_HGBR | 53 | 0.000153 | -0.000003 | +0.007 |
| eu_brier | 2023 | COMBINED_HGBR_STATE_SHIFT | 53 | 0.000152 | -0.000002 | +0.140 |
| eu_brier | 2023 | CURRENT_RIDGE | 53 | 0.000185 | -0.000035 | +0.033 |
| eu_brier | 2024 | COMBINED_HGBR | 66 | 0.000248 | -0.000067 | -0.000 |
| eu_brier | 2024 | COMBINED_HGBR_STATE_SHIFT | 66 | 0.000271 | -0.000090 | -0.166 |
| eu_brier | 2024 | CURRENT_RIDGE | 66 | 0.000176 | +0.000004 | +0.132 |
| eu_top2_residual | 2023 | COMBINED_HGBR | 53 | 0.001067 | -0.000212 | +0.028 |
| eu_top2_residual | 2023 | COMBINED_HGBR_STATE_SHIFT | 53 | 0.001194 | -0.000339 | -0.060 |
| eu_top2_residual | 2023 | CURRENT_RIDGE | 53 | 0.000888 | -0.000033 | -0.075 |
| eu_top2_residual | 2024 | COMBINED_HGBR | 66 | 0.001335 | -0.000123 | +0.077 |
| eu_top2_residual | 2024 | COMBINED_HGBR_STATE_SHIFT | 66 | 0.001537 | -0.000325 | -0.087 |
| eu_top2_residual | 2024 | CURRENT_RIDGE | 66 | 0.001218 | -0.000007 | +0.064 |
| line_brier | 2023 | COMBINED_HGBR | 53 | 0.000093 | -0.000004 | +0.169 |
| line_brier | 2023 | COMBINED_HGBR_STATE_SHIFT | 53 | 0.000101 | -0.000013 | +0.006 |
| line_brier | 2023 | CURRENT_RIDGE | 53 | 0.000095 | -0.000007 | +0.107 |
| line_brier | 2024 | COMBINED_HGBR | 66 | 0.000145 | -0.000019 | -0.010 |
| line_brier | 2024 | COMBINED_HGBR_STATE_SHIFT | 66 | 0.000170 | -0.000044 | -0.268 |
| line_brier | 2024 | CURRENT_RIDGE | 66 | 0.000128 | -0.000002 | -0.048 |
| line_top2_residual | 2023 | COMBINED_HGBR | 53 | 0.001277 | -0.000228 | -0.017 |
| line_top2_residual | 2023 | COMBINED_HGBR_STATE_SHIFT | 53 | 0.001500 | -0.000451 | -0.047 |
| line_top2_residual | 2023 | CURRENT_RIDGE | 53 | 0.001205 | -0.000156 | +0.020 |
| line_top2_residual | 2024 | COMBINED_HGBR | 66 | 0.001919 | -0.000460 | -0.029 |
| line_top2_residual | 2024 | COMBINED_HGBR_STATE_SHIFT | 66 | 0.002450 | -0.000991 | -0.288 |
| line_top2_residual | 2024 | CURRENT_RIDGE | 66 | 0.001643 | -0.000184 | -0.035 |

The combined lagged model improves the current-only model consistently in
0 of four calibration targets across
both 2023 and 2024. Block-bootstrap lower bounds are positive in
0 calibration year-target
slices. This rejects a deployable fast-regime gate from the present summaries.

The state-shift rows rotate complete lag blocks across issues while leaving the
current pre-event cross-section unchanged. If shifted performance is similar or
better, the apparent lagged signal is not accepted as issue-specific state skill.

## Block-bootstrap MSE increment: combined HGBR minus current Ridge

Positive values favor adding lagged state.

| target | issue_year | issues | mean_mse_improvement | ci95_low | ci95_high | block_size | draws |
|---:|---:|---:|---:|---:|---:|---:|---:|
| allocator_delta | 2023 | 50 | +4755.990611 | -2153.654732 | +11227.954019 | 5 | 2000 |
| allocator_delta | 2024 | 60 | -30225.081670 | -66848.858118 | -2928.978019 | 5 | 2000 |
| eu_brier | 2023 | 53 | +0.000032 | -0.000010 | +0.000074 | 5 | 2000 |
| eu_brier | 2024 | 66 | -0.000071 | -0.000181 | +0.000007 | 5 | 2000 |
| eu_top2_residual | 2023 | 53 | -0.000179 | -0.000513 | +0.000111 | 5 | 2000 |
| eu_top2_residual | 2024 | 66 | -0.000117 | -0.000319 | +0.000050 | 5 | 2000 |
| line_brier | 2023 | 53 | +0.000003 | -0.000019 | +0.000025 | 5 | 2000 |
| line_brier | 2024 | 66 | -0.000017 | -0.000055 | +0.000013 | 5 | 2000 |
| line_top2_residual | 2023 | 53 | -0.000072 | -0.000378 | +0.000248 | 5 | 2000 |
| line_top2_residual | 2024 | 66 | -0.000276 | -0.000742 | +0.000132 | 5 | 2000 |

## Information carried forward

- Admissible current inputs: market probability entropy/concentration, Top1/Top2
  mass, European-vs-Beijing-line divergence, line mix and bookmaker coverage.
- Experimental auxiliary state inputs: strictly shifted rolling/EWMA Brier,
  log loss and Top1/Top2 coverage residuals with observation counts and last
  timestamps. They are causally admissible but **not** established predictors;
  the next issue must retain a no-lag ablation and state-shift falsification.
- Diagnostic-only until more support: lagged A1-A0 PnL, fixed-strategy PnL,
  near-miss and payout concentration. Their labels are too sparse/partial to be
  the sole MoE gating target.
- Rejected inputs: calendar year, issue-code prefix, same-issue outcome, future
  settlement, final SP and any outcome-ranked expert choice.

## Adversarial interpretation

- Smooth year-to-year movement can reflect bookmaker adaptation, source changes
  or sample composition; it is not by itself a tradable regime.
- A small next-issue MSE gain does not establish capital Edge. The following MoE
  must beat static expert weights and issue-block state-shuffled controls on
  matched exposure.
- The 2023/2024 slices are historical diagnostics already opened elsewhere.
  They do not substitute for #210 prospective evidence.
- The sparse allocator response explains why #328 collapsed to A0 and motivates
  multitask learning, but it does not prove that a neural gate will succeed.

## Evidence

- Executed notebook: `notebooks/research/regime-state/regime_state.ipynb`
- State ledger: `results/regime_state/state_ledger.parquet`
- OOF predictions and diagnostics: `oof_predictions.parquet`,
  `prediction_metrics.csv`, `bootstrap_increment.csv`, `persistence.csv`
- Exact source/chronology receipt and package hashes under `results/regime_state/`
