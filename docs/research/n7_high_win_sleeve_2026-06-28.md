# N7 Core With High Win-Rate Sleeve

Date: 2026-06-28

## Question

N=7 is naturally a high payoff-ratio strategy. Since the result predictor is not weak, can we pair it with a higher win-rate strategy to improve issue-level experience and reduce drawdown?

## Setup

- Base: `reference::draw_tail_to_n3::w5::dd2::ls4`
- Output: `results/n7_high_win_sleeve_20260628/`
- Figure: `docs/research/figures/n7_high_win_sleeve_equity_2026-06-28.svg`
- Budget rule: same 512 units per issue. Core units + sleeve units = 512.
- Win rate means issue-level positive PnL rate, not ticket hit rate.

Sleeves tested:

- `n5_static`: fixed N5x90, high issue win rate, lower EV.
- `n5_static_overlap50`: N5x90 overlap-50 variant, better recent performance, lower non-full-loss.
- `n3_n5_dynamic`: dynamic N3/N5/N7 shape, good non-full-loss, moderate win-rate lift.
- `n3_static_high_win`: highest non-full-loss, but too much EV loss.

## Main Result

| Model | Profit | ROI | Issue win rate | Non-full-loss | MaxDD | Recent ex-best | Read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| base 512 | 306,788 | 89.6% | 14.8% | 78.3% | -29,268 | 35.5% | high EV baseline |
| 448 core + 64 N3/N5 dynamic | 276,415 | 80.7% | 17.0% | 83.0% | -27,288 | 30.2% | best light sleeve |
| 384 core + 128 N3/N5 dynamic | 246,041 | 71.8% | 18.5% | 83.0% | -25,825 | 24.8% | balanced smoothing |
| 384 core + 128 N5 overlap | 241,760 | 70.6% | 20.6% | 78.8% | -24,359 | 35.8% | visible win-rate lift |
| 256 core + 256 N5 static | 172,032 | 50.2% | 25.3% | 81.9% | -24,353 | 12.7% | too much EV sacrifice |

## Interpretation

1. A high win-rate sleeve is feasible, but it is not free.

Moving from pure N7 core to lower-N coverage raises issue win rate, but profit falls quickly. A 50/50 split can raise issue win rate to about 25%, but profit drops from 306.8k to 172.0k. That is too expensive for the main strategy.

2. The practical range is 12.5%-25% sleeve.

The best light version is `448 core + 64 N3/N5 dynamic`:

- profit remains 276.4k
- issue win rate improves 14.8% -> 17.0%
- non-full-loss improves 78.3% -> 83.0%
- maxDD improves -29.3k -> -27.3k

If the goal is a more visible win-rate lift, `384 core + 128 N5 overlap` gets issue win rate to 20.6%, keeps recent ex-best roughly equal to base, and improves maxDD. But it gives up about 65k profit.

3. N3-static is not a good primary sleeve.

It raises non-full-loss above 91%, but the EV drag is too large. It is a possible last-resort smoothing or psychological sleeve, not a production main allocation.

## Recommendation

Use a barbell portfolio rather than replacing N7:

- Core: N7 high payoff-ratio strategy remains the main EV engine.
- Sleeve: 12.5%-25% lower-N high win-rate allocation to improve issue-level experience.
- Candidate production arm: `448 core + 64 N3/N5 dynamic`.
- Candidate paper arm: `384 core + 128 N5 overlap` if we want issue win rate above 20%.

This combines with the convexity framework: on high-convexity issues, preserve or increase N7/core exposure; on normal or low-convexity issues, the high-win sleeve can carry more of the experience-smoothing role.

## Verification

- `python3 -m py_compile scripts/evaluate_n7_high_win_sleeve.py`
- `python3 scripts/evaluate_n7_high_win_sleeve.py --output-dir results/n7_high_win_sleeve_20260628`
