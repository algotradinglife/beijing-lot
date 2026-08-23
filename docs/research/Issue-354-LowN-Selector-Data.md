# Issue #354 — Strictly-prior low-N Top-2 selector data

## Decision summary

The data prerequisite for low-N match-selection research is ready. The package
contains 134,822 fixture rows at the frozen 10h horizon across 2017–2024. It
rebuilds the European-market-plus-Beijing-line probability surface without
letting the outcome-confirmed `mapping_accepted` decision lead the experiment.

This is a data-readiness result, not a strategy result. No selector has been
chosen and no 2022–2024 outcome has been used to tune a model.

## Temporal construction

- 2014–2016: initial warm-up only.
- 2017–2021: one expanding-window out-of-fold probability surface per year;
  every row's `train_year_max` is strictly smaller than its `issue_year`.
- 2022–2024: one model fitted through 2021 and applied unchanged before the
  transfer labels are opened.
- All prior-calibration summary features for 2022–2024 are likewise frozen at
  the 2017–2021 history; 2022/2023 outcomes never update later transfer rows.
- 2019–2021 are the only years eligible for later selector-family selection.
- 2022, 2023 and 2024 remain exposed historical transfer evidence.

The pre-outcome feature artifact contains no result, settlement or winning-SP
column. Labels are stored in a separate Parquet artifact.

## Coverage

| Year | Role | Issues | Fixture rows | Label rows | Mean Top-2 mass | Actual Top-2 coverage | Residual |
|---:|---|---:|---:|---:|---:|---:|---:|
| 2017 | expanding OOF | 48 | 16,859 | 16,733 | 74.05% | 74.88% | +0.83pp |
| 2018 | expanding OOF | 59 | 19,222 | 19,018 | 74.19% | 74.52% | +0.33pp |
| 2019 | expanding OOF | 53 | 16,222 | 16,098 | 74.12% | 74.05% | -0.08pp |
| 2020 | expanding OOF | 38 | 9,633 | 9,508 | 74.06% | 74.53% | +0.47pp |
| 2021 | expanding OOF | 63 | 20,969 | 20,674 | 73.80% | 74.12% | +0.32pp |
| 2022 | frozen transfer | 62 | 19,152 | 18,941 | 73.84% | 73.67% | -0.17pp |
| 2023 | frozen transfer | 53 | 14,675 | 14,548 | 74.14% | 74.27% | +0.13pp |
| 2024 | frozen transfer | 66 | 18,090 | 17,933 | 74.33% | 74.25% | -0.08pp |

The annual residuals are small, which supports using Top-2 coverage as the
primary low-N target. It does not prove that a learned ranker can improve which
fixtures are selected; #355 tests that separately.

## Feature surface

The panel includes:

- raw and mapped probability triplets;
- Top-2 support, retained mass, omitted outcome, adjacent probability gaps,
  entropy and concentration;
- native handicap structure and line-only probabilities;
- signed and absolute European-vs-line divergence;
- book count, source/temporal grades, source inventory and explicit input
  missingness count;
- strictly-prior calibration summaries;
- within-issue ranks, percentiles, dispersion and N3/N4/N5 cutoff gaps.

All feature columns are complete on the frozen supported panel. Unsupported
native-line rows are excluded explicitly rather than imputed.

## Parity and known boundary

For 2022–2024, all 155,751 structurally supported outcome cells are numerically
identical to the accepted #238 `q_eu_bjline` surface. On non-zero handicap
lines, all 62,259 cells are also identical to the #238 candidate diagnostic.
Zero-line rows intentionally use European-probability identity, matching the
accepted R0 semantics.

The equality does not inherit #238's outcome-confirmed acceptance gate. The
new lineage independently fixes the architecture and training cutoff through
2021. Because 2022–2024 have already been inspected elsewhere, their evidence
remains historical transfer evidence rather than a holdout.

## Reproducibility

- Build: `scripts/run_low_n_selector_data.py`
- Verify: `scripts/verify_low_n_selector_data.py`
- Package: `results/low_n_selector_data/`
- Frozen feature frame: `43e3b0b47a54e4eb41d6fb4103a0adea9af3b2e11d3e9992a5fb1912f5f0d98b`
- Separate label frame: `12c2746b25be824c19fbb1b618a29c5d2abef39156ab1e62107290e32801b2c8`
- Notebook: `notebooks/research/low-n-selector-data/low_n_selector_data_profile.ipynb`
- Figures:
  - `docs/research/figures/issue_354_top2_calibration.png`
  - `docs/research/figures/issue_354_panel_profile.png`

The verifier reopens the bound source projections, rebuilds every scientific
row, checks strict chronology and probability simplexes, and rejects label
leakage or semantic-frame tampering.

## Handoff to #355

#355 may now compare the predeclared S0–S3 selector families using only
2019–2021 expanding-OOF evidence for model choice. The transfer years must be
loaded only after the selected family and fitted-state receipt are frozen.
