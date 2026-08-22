# Issue #328 — Learned S1O1 allocator mixture

## Decision

`ENDPOINT_RETAINED`; promotion is `false`. The primary comparison is exact
matched capital lift versus the frozen #319/#324 `S0O0A0` baseline.

## Risk/return summary

Paired values are `2023 / 2024`.

| Arm | capital return | two-year matched lift | max drawdown | longest losing | payout HHI | mean lambda |
|---|---:|---:|---:|---:|---:|---:|
| `L000` | +1.51% / +16.71% | CNY+16,800 | 3.34% / 3.44% | 12 / 13 | 0.361 / 0.165 | 0.000 / 0.000 |
| `L025` | +1.51% / +18.10% | CNY+18,194 | 3.34% / 3.40% | 12 / 13 | 0.361 / 0.167 | 0.250 / 0.250 |
| `L050` | +1.51% / +21.60% | CNY+21,695 | 3.34% / 3.30% | 12 / 13 | 0.361 / 0.181 | 0.500 / 0.500 |
| `L075` | +1.24% / +23.43% | CNY+23,249 | 3.35% / 3.26% | 12 / 13 | 0.373 / 0.189 | 0.750 / 0.750 |
| `L100` | +1.24% / +24.82% | CNY+24,642 | 3.35% / 3.22% | 12 / 13 | 0.373 / 0.192 | 1.000 / 1.000 |
| `DYN_RIDGE` | +1.51% / +16.71% | CNY+16,800 | 3.34% / 3.44% | 12 / 13 | 0.361 / 0.165 | 0.072 / 0.043 |
| `DYN_HGBR` | +1.51% / +16.71% | CNY+16,800 | 3.34% / 3.44% | 12 / 13 | 0.361 / 0.165 | 0.065 / 0.026 |

## Dynamic policy distribution

| issue_year | arm | count | mean | std | min | max |
|---:|---|---:|---:|---:|---:|---:|
| 2023 | `DYN_HGBR` | 53 | 0.0646 | 0.0795 | 0.0000 | 0.2888 |
| 2023 | `DYN_RIDGE` | 53 | 0.0699 | 0.0780 | 0.0000 | 0.3521 |
| 2024 | `DYN_HGBR` | 66 | 0.0266 | 0.0471 | 0.0000 | 0.2449 |
| 2024 | `DYN_RIDGE` | 66 | 0.0425 | 0.0403 | 0.0000 | 0.1272 |

The learned continuous outputs changed the integer ticket allocation on
`0` Ridge issues and `1` HGBR issues.
Consequently both learned paths are economically identical to `L000` on all
observable issues.

## Why the learner collapsed toward A0

| year | observable issues | A1-A0 total | nonzero fraction | positive fraction |
|---:|---:|---:|---:|---:|
| 2020 | 31 | CNY-997 | 21.1% | 0.0% |
| 2021 | 56 | CNY+36 | 14.3% | 1.6% |
| 2022 | 55 | CNY+2,773 | 12.9% | 1.6% |

The A1-minus-A0 response is sparse because allocator choice matters only when a
funded ticket wins and the two allocators assign it different units. The OOF
ledger has only one positive-delta issue in each of 2021 and 2022 and none in
2020. A direct PnL regressor therefore learns a conservative near-zero lambda.

The static curve is nevertheless informative: corrected two-year matched lift
versus `S0O0A0` rises from CNY+16,800
at `L000` to CNY+24,642 at `L100`.
Direct A1-minus-A0 increment is CNY+7,841,
but it is negative in 2023 and strongly positive in 2024. The per-issue static
oracle adds only CNY+1,170 over
the best fixed lambda, so this action family alone offers little dynamic ceiling.

## Adversarial interpretation

- This does **not** show that dynamic allocation is impossible. It shows that a
  memoryless issue cross-section cannot learn a very sparse allocator payoff.
- The year reversal is compatible with drift in market calibration or Beijing
  pricing. Calendar year itself is not an admissible predictor; a future model
  needs strictly lagged calibration and hit-residual state.
- Lower N may improve hit rate and path stability in a weak-edge regime, while
  higher N still amortizes the single 0.65 ticket coefficient better. That
  trade-off must be learned and cannot be inferred from allocator lambda alone.
- A next-stage MoE should use fixed, interpretable N/support/allocator experts
  and a lagged regime gate. It must beat static mixtures and issue-block shuffled
  controls; 2024 is historical transfer, not held-out confirmation.

## Interpretation boundary

- Every arm always funds CNY256; no cash/NO_BET action is available.
- `L000` and `L100` exactly represent the #324 S1O1 endpoint allocators.
- The issue is the independent unit; ticket rows are nested mechanics.
- 2024 is historical transfer, not globally unseen confirmation.
- Ex-largest, drawdown, streak and HHI qualify confidence but do not erase genuine
  matched progress versus the frozen control.
- #210 remains blocked; no result here authorizes betting or forward promotion.

## Evidence

- OOF and model receipts: `results/dynamic_allocator/oof_receipt.json`, `model_receipt.json`
- Frozen actions: `policies.parquet`, `allocations.parquet`
- Capital/risk: `performance.csv`, `matched_performance.csv`, `capital_paths.csv`, `risk_diagnostics.csv`
- Executed notebook: `notebooks/research/dynamic-allocator/dynamic_allocator.ipynb`
