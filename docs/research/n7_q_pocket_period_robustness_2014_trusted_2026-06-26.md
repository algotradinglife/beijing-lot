# N=7 Q-pocket Period Robustness

Date: 2026-06-26

Scope:

- Input data: trusted-only settlement rows.
- Strategy output source:
  - `results/n7_q_pocket_whitelist_sqlite_2014_10h_trusted`
  - `results/n7_q_pocket_whitelist_sqlite_2014_1h_trusted`
- Period summary output:
  - `results/n7_q_pocket_period_robustness_2014_trusted/period_summary.csv`
  - `results/n7_q_pocket_period_robustness_2014_trusted/period_issue_profit.csv`

## Method

This does not rerun or retune the strategy per period.
It slices the same 2014+ trusted-only walk-forward tickets by test issue year.
That means each ticket is still generated using only its prior rolling training window.

Periods:

- 2014-2017
- 2018-2020
- 2021-2023
- 2024-2025

## Main 10h Arm

`q_pocket_whitelist_open__budget20_whole` by period:

| period | issues | profit | ROI | ex_top1 ROI | ex_top2 ROI | issue DD | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2014-2017 | 286 | 757.51 | 0.1324 | -0.0562 | -0.2371 | -0.1664 | jackpot_dependent |
| 2018-2020 | 151 | 219.99 | 0.0728 | -0.2666 | -0.5464 | -0.0767 | jackpot_dependent |
| 2021-2023 | 168 | 6250.92 | 1.8604 | 0.9191 | 0.0339 | -0.0609 | robust |
| 2024-2025 | 74 | 3159.27 | 2.1346 | 1.0678 | 0.2923 | -0.0299 | robust |

Interpretation:

- The open 10h arm is not uniformly robust across all periods.
- 2014-2020 has positive raw ROI but fails the ex-top stress checks.
- 2021+ is where the edge becomes robust under jackpot removal.

## Best 10h Gate By Period

| period | best raw ROI strategy | ROI | ex_top1 ROI | verdict |
| --- | --- | ---: | ---: | --- |
| 2014-2017 | keyed_pockets | 1.2100 | 0.4052 | robust |
| 2018-2020 | keyed_pockets | 0.2504 | -0.1608 | jackpot_dependent |
| 2021-2023 | whitelist_open | 1.8604 | 0.9191 | robust |
| 2024-2025 | core_issue_gate30 | 2.4112 | 1.2530 | robust |

Interpretation:

- No single 10h gate dominates every period.
- `keyed_pockets` explains much of the 2014-2017 robustness, but loses robustness later.
- `whitelist_open` and `core_issue_gate30` look materially better from 2021 onward.
- 2018-2020 remains the main stress period and should drive risk-control design.

## 1h Arm

`q_pocket_whitelist_open__budget20_whole` by period:

| period | issues | profit | ROI | ex_top1 ROI | ex_top2 ROI | issue DD | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2014-2017 | 285 | -865.14 | -0.1518 | -0.4272 | -0.5147 | -0.1655 | negative |
| 2018-2020 | 151 | -2128.28 | -0.7047 | -0.8019 | -0.8786 | -0.2128 | negative |
| 2021-2023 | 168 | 298.79 | 0.0889 | -0.6555 | -0.9301 | -0.1610 | jackpot_dependent |
| 2024-2025 | 74 | 973.43 | 0.6577 | -0.3569 | -0.6065 | -0.0658 | jackpot_dependent |

Interpretation:

- 1h still should not be a main arm.
- Positive 1h periods fail jackpot removal.
- Keep 1h as an information source or paper arm, not as production stake logic.

## Strategy Implications

The earlier global 10h result is real, but it is regime-dependent.
The current production question should not be "which global gate is best"; it should be:

1. Can we identify 2018-2020-like periods before or during betting?
2. Can issue-level risk controls reduce stake or skip periods that resemble that stress regime?
3. Can the gate adapt between `keyed_pockets`, `whitelist_open`, and `core_issue_gate30` using only prior data?

Practical next step:

- Build a rolling regime/gate selector.
- Candidate gates: `keyed_pockets`, `whitelist_open`, `core_issue_gate30`.
- Selection features should be available before settlement:
  - issue candidate count,
  - core/tail/draw-tail mix,
  - q distribution,
  - SP proxy distribution,
  - 10h market dispersion,
  - SP drift proxies from 10h to 1h as observation-only or paper comparison.
- Primary target: reduce or cap stake in 2018-2020-like regimes without overfitting to one historical slice.

Current production bias:

- Use `10h`, trusted settlement only.
- Prefer `core_issue_gate30` for conservative current-period exposure.
- Treat `whitelist_open` as higher-throughput, higher jackpot-dependence.
- Do not promote `1h` beyond paper tracking yet.
