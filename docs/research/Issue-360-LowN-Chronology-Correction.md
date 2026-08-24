# Issue #360 — Low-N selector chronology and outcome-grain correction

## Decision summary

Issue #354's probability arithmetic was useful, but its annual routing was not
causal: a whole issue was assigned the year of its latest kickoff.  Sixty-two
issues cross that artificial boundary, allowing later labels from the same
calendar year into earlier fixture predictions.  This package supersedes the
#354 chronology before #355 is allowed to select a match-selection model.

Within the corrected supported 2017–2024 panel, 55 of 435 issues have a latest
kickoff year different from their registry year.  The broader post-merge audit
count of 62/442 includes rows outside this corrected supported selector panel.

The rebuilt panel contains 132,408 fixture rows and 397,224 explicit M×3
outcome cells across authoritative registry years 2017–2024.  Every model is
trained only on labels whose conservative availability timestamp precedes the
earliest target decision timestamp.  This is a corrected data-readiness result,
not evidence that any selector improves betting performance.

## What changed

1. **Registry year is authoritative.** Earliest and latest kickoff remain
   descriptive fields and never determine the research partition.
2. **Decision time is explicit.** Each fixture uses the causal 10h snapshot
   timestamp, `fixture_kickoff_ts - 10h`.  The issue-level timestamp is the
   earliest supported fixture decision and is used only as a conservative
   model-training cutoff.
3. **Label availability is explicit.** A result is conservatively treated as
   available at `fixture_kickoff_ts + 4h`.  For every prediction row,
   `training_label_available_max_ts < fixture_decision_ts` holds.
4. **The outcome interface is truly M×3.** The new long-form cell artifact has
   the exact key `(issue, match_idx, outcome_code)` and exactly three rows per
   fixture.  The fixture-wide artifact remains the convenient selector input.
5. **Coverage is issue-weighted.** `median_fixtures_per_issue` is calculated
   from one row per issue rather than repeating large issues once per fixture.
6. **One selector role is authoritative.** The ambiguous inherited
   `temporal_role` is removed from the delivered features.  `selector_role`
   equals the frozen prediction role; 2022–2024 are exposed transfer only.

## Corrected coverage and calibration

| Registry year | Role | Issues | Settled fixtures | Mean Top-2 mass | Actual Top-2 hit | Residual |
|---:|---|---:|---:|---:|---:|---:|
| 2017 | expanding OOF | 47 | 16,775 | 74.08% | 74.86% | +0.78pp |
| 2018 | expanding OOF | 59 | 18,289 | 74.19% | 74.44% | +0.25pp |
| 2019 | expanding OOF | 55 | 17,494 | 74.12% | 74.07% | -0.06pp |
| 2020 | expanding OOF | 44 | 11,737 | 74.03% | 74.72% | +0.69pp |
| 2021 | expanding OOF | 58 | 18,557 | 73.77% | 74.10% | +0.34pp |
| 2022 | frozen transfer | 58 | 16,548 | 73.82% | 73.48% | -0.34pp |
| 2023 | frozen transfer | 55 | 15,545 | 74.17% | 74.13% | -0.04pp |
| 2024 | frozen transfer | 59 | 16,128 | 74.29% | 74.36% | +0.06pp |

The corrected annual residuals remain small.  That supports Top-2 probability
coverage as a useful baseline quantity, but it does not prove that ranking
fixtures by coverage creates an economic edge.  #355 must replay selector
selection and settlement from this corrected source.

### Historical proxy boundary

The 10h rows are **fixture-relative snapshots**, not one simultaneously visible
snapshot for an entire issue.  An issue can span days or months, so later
fixtures' 10h odds were not visible at the earliest issue anchor.  The anchor
therefore protects model-label chronology; it does not claim common issue-time
feature visibility.  #355 is authorized as retrospective proxy exploration
under this known limitation, not as a deployable live selector.  A true common
decision-epoch panel remains a forward-data task.

## Accepted-source comparison

The corrected model retains the frozen European-probability plus Beijing-line
architecture, but it is not numerically identical to the accepted #238 surface.
That difference is expected: #238 inherited the superseded issue-year routing.
Across corrected 2022–2024 support, 145,974 outcome cells are compared and the
maximum absolute probability delta is 0.05263 (0.00882 on non-zero handicap
lines).  This package therefore reports a comparison, not false “exact parity.”

## Causal and interface receipts

- Fixture feature frame:
  `2c410b7df2d512d6806055754ecd860a5fabda3ad482a8afb704cd109e57ee9c`
- M×3 cell frame:
  `a3eb717c7f4e94649fae32249b16ea9d75b57865067de1b0f01c270d2e583c30`
- Separate label frame:
  `2e92e17822a2069a2fff13432657526d5ec64080dc116cd841f4696b8e59a2dd`
- Package: `results/low_n_selector_data/`
- Build: `scripts/run_low_n_selector_data.py`
- Verify: `scripts/verify_low_n_selector_data.py`
- Executed notebook:
  `notebooks/research/low-n-selector-data/low_n_selector_data_profile.ipynb`
- Figures:
  - `docs/research/figures/issue_360_top2_calibration.png`
  - `docs/research/figures/issue_360_panel_profile.png`

The verifier rebuilds from source, checks the registry and inventory through an
independent temporal oracle, verifies exact M×3 grain and strict booleans, and
binds the source, implementation, feature, cell, label, notebook and report
receipts.

## PI disposition

- `KE-354-01`: **corrected** by registry-year routing and per-row label-time
  checks.
- `KE-354-02`: **corrected** by the explicit long-form cell artifact.
- `KE-354-03`: **corrected** by issue-unit coverage aggregation.
- `RK-354-01`: **closed** by removing the ambiguous inherited role from the
  delivered selector interface.
- `DE-354-01`: **closed** by an independent registry/inventory time oracle and
  the cross-year mutation test.

#355 remains blocked until this correction is merged.  It must then be replayed
from scratch; no pre-correction selector or ROI conclusion may be carried over.
