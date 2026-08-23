# Issue #358 — causal 10h European-average-odds value proxy

Contract: `BJ-UNIFIED-LOWN-EU-VALUE-DATA-001/v1`

## Decision boundary

This package provides pre-outcome, retrospective-relative 10h European-average-odds inputs for low-N research. It is **not** Beijing official SP, does not calibrate Beijing payouts, applies no raw-odds filter, and selects no fixtures or strategy. It inherits #354's frozen strictly-prior calibrated probabilities and fixed Top-2 support; it does not read #354 labels.

The provider's `10h` field is a relative snapshot label, not an observed quote timestamp. `source_observed_at_utc` therefore remains null and `source_time_status` explicitly records `RELATIVE_HORIZON_LABEL_NO_OBSERVED_TIMESTAMP` rather than fabricating a time.

## Frozen scope and evidence

- Years: 2017–2021 development lineage; 2022–2024 exposed transfer rows generated after the feature freeze.
- Cell frame SHA-256: `1f4661bef9d1511376bb932c4472fb05d24941e904133933222b9f8f3e3a2455`
- Fixture rows: 134,822; outcome cells: 404,466.
- Labels opened: `False`.
- Raw bookmaker treatment: all complete valid 3/1/0 triplets are averaged; none are filtered by price.

## Annual 10h profile

| Year | Issues | Fixtures | Mean contributing books | Mean Top-2 reliability | Mean Top-2 gross factor |
|---:|---:|---:|---:|---:|---:|
| 2017 | 48 | 16859 | 13.15 | 0.7406 | 2.4754 |
| 2018 | 59 | 19222 | 13.11 | 0.7419 | 2.4949 |
| 2019 | 53 | 16222 | 12.88 | 0.7412 | 2.5233 |
| 2020 | 38 | 9633 | 13.17 | 0.7408 | 2.4439 |
| 2021 | 63 | 20969 | 12.75 | 0.7381 | 2.3677 |
| 2022 | 62 | 19152 | 12.97 | 0.7384 | 2.3483 |
| 2023 | 53 | 14675 | 13.13 | 0.7415 | 2.3499 |
| 2024 | 66 | 18090 | 13.38 | 0.7434 | 2.3520 |

## Low-N ingredients (N=3–5)

Each cell records average European decimal odds, raw implied probability, fixture overround, de-vig probability, #354 calibrated probability and `p_times_odds`. For each fixed Top-2 fixture support, `top2_coverage_reliability` is the calibrated Top-2 mass and `top2_expected_gross_factor` is the sum of `p_times_odds` across its two supported outcomes.

For any later selected N-fixture set, the full Cartesian portfolio has `2^N` tickets and expected gross is the product of these fixture factors. The Beijing 0.65 burden is represented as a **single ticket-level factor**, never compounded across legs: `0.65 × product(odds of the winning N legs)`.

## Reproduction

```bash
python scripts/run_low_n_eu_value_data.py --data-root /absolute/path/to/data --force
python scripts/build_low_n_eu_value_notebook.py
python scripts/verify_low_n_eu_value_data.py --data-root /absolute/path/to/data
```

The semantic verifier checks package closure, implementation and source hashes, independently rebuilds every cell from the #354 pre-outcome frame and #268 raw bookmaker source, and rejects tampered values, Top-2 labels, provenance, or remanifested output.
