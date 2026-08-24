# Issue #358 — causal 10h European-average-odds value proxy

Contract: `BJ-UNIFIED-LOWN-EU-VALUE-DATA-001/v2`

## Decision boundary

This package provides pre-outcome, retrospective-relative 10h European-average-odds inputs for low-N research. It is **not** Beijing official SP, does not calibrate Beijing payouts, applies no raw-odds filter, and selects no fixtures or strategy. It inherits the #360-corrected strictly-prior calibrated probabilities and fixed Top-2 support; it does not read settlement labels.

The provider's `10h` field is a relative snapshot label, not an observed quote timestamp. `source_observed_at_utc` therefore remains null and `source_time_status` explicitly records `RELATIVE_HORIZON_LABEL_NO_OBSERVED_TIMESTAMP` rather than fabricating a time.

## Frozen scope and evidence

- Years: 2017–2021 development lineage; 2022–2024 exposed transfer rows generated after the feature freeze.
- Cell frame SHA-256: `225d889af5b91c3c28159784d0f43ca8dcdf97a69b87154edfa8dccc92b270f8`
- Fixture rows: 132,408; outcome cells: 397,224.
- Labels opened: `False`.
- Raw bookmaker treatment: all complete valid 3/1/0 triplets are averaged; none are filtered by price.

## Annual 10h profile

| Year | Issues | Fixtures | Mean contributing books | Mean Top-2 reliability | Mean Top-2 gross factor | Mean per-stake factor |
|---:|---:|---:|---:|---:|---:|---:|
| 2017 | 47 | 16897 | 13.17 | 0.7408 | 2.4903 | 1.2452 |
| 2018 | 59 | 18490 | 13.12 | 0.7419 | 2.5004 | 1.2502 |
| 2019 | 55 | 17613 | 12.83 | 0.7412 | 2.5198 | 1.2599 |
| 2020 | 44 | 11947 | 13.13 | 0.7405 | 2.3999 | 1.2000 |
| 2021 | 58 | 18803 | 12.62 | 0.7377 | 2.3701 | 1.1850 |
| 2022 | 58 | 16740 | 13.11 | 0.7382 | 2.3343 | 1.1671 |
| 2023 | 55 | 15685 | 13.14 | 0.7418 | 2.3526 | 1.1763 |
| 2024 | 59 | 16233 | 13.39 | 0.7429 | 2.3458 | 1.1729 |

## Low-N ingredients (N=3–5)

Each cell records average European decimal odds, raw implied probability, fixture overround, de-vig probability, corrected calibrated probability and `p_times_odds`. For each fixed Top-2 fixture support, `top2_coverage_reliability` is the calibrated Top-2 mass and `top2_expected_gross_factor` is the sum of `p_times_odds` across its two supported outcomes. Because the fixed budget is spread equally over two supported outcomes per leg, `top2_expected_return_per_stake_factor = top2_expected_gross_factor / 2`.

For any later selected N-fixture set, the full Cartesian portfolio has `2^N` tickets. Its European-proxy expected gross per total stake is `0.65 × product(top2_expected_return_per_stake_factor)`. This divides by the `2^N` tickets exactly once and applies the Beijing 0.65 burden **once per complete winning ticket**, never once per leg. The equal-leg descriptive break-even floor is `(1 / 0.65) ** (1/N)`; decisions remain full-ticket calculations.

## Reproduction

```bash
python scripts/run_low_n_eu_value_data.py --data-root /absolute/path/to/data --force
python scripts/build_low_n_eu_value_notebook.py
python scripts/verify_low_n_eu_value_data.py --data-root /absolute/path/to/data
```

The semantic verifier checks package closure, implementation and source hashes, independently rebuilds every cell from the #360-corrected pre-outcome frame and #268 raw bookmaker source, and rejects tampered values, Top-2 labels, provenance, or remanifested output.
