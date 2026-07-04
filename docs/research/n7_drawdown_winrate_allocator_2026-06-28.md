# Drawdown-Stage Win-Rate Allocator

Date: 2026-06-28

## Question

When drawdown reaches certain stages, the strategy should put more weight on win rate. This is different from a hard cooldown: the system still plays, but the allocation shifts from N7 convexity toward lower-N, wider-coverage sleeves.

## Setup

- Input: `results/n7_high_win_sleeve_20260628/high_win_sleeve_issue_profit.csv`
- Output: `results/n7_drawdown_winrate_allocator_20260628/`
- Figure: `docs/research/figures/n7_drawdown_winrate_allocator_equity_2026-06-28.svg`
- Selection rule: use drawdown before each issue, so no future result leakage.
- If equity recovers, the allocator can move back toward the N7 core.

## Main Result

| Allocator | Profit | ROI | Issue win rate | Non-full-loss | MaxDD | Recent ex-best | Read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| fixed base | 306,788 | 89.6% | 14.8% | 78.3% | -29,268 | 35.5% | current high-EV reference |
| fixed 448 + 64 dynamic sleeve | 276,415 | 80.7% | 17.0% | 83.0% | -27,288 | 30.2% | light always-on sleeve |
| dd5/10/15 dynamic | 245,710 | 71.7% | 17.2% | 79.8% | -27,158 | 21.4% | staged, but profit hit is large |
| dd5/10/15/20 N5 overlap | 233,968 | 68.3% | 19.1% | 78.8% | -24,487 | 22.4% | best staged DD under 25k |
| fixed 384 + 128 N5 overlap | 241,760 | 70.6% | 20.6% | 78.8% | -24,359 | 35.8% | simpler and stronger than staged in this run |
| dd5/10/15 full safe | 185,019 | 54.0% | 18.5% | 83.0% | -23,447 | 12.2% | too much EV sacrifice |

## Interpretation

1. The idea is directionally right.

As drawdown deepens, shifting more allocation to lower-N/high-win sleeves improves maxDD and issue win rate. The staged N5-overlap allocator cuts maxDD from -29.3k to -24.5k and raises issue win rate from 14.8% to 19.1%.

2. The cost is substantial.

The best staged under-25k drawdown candidate loses about 72.8k profit versus base. The safe version improves maxDD a bit further, but profit falls to 185k. That is too expensive unless the account truly cannot tolerate a 25k drawdown.

3. Static 384+128 N5-overlap is currently a stronger baseline than the staged versions.

`fixed_384_n5ov128` has:

- profit 241.8k
- issue win rate 20.6%
- maxDD -24.4k
- recent ex-best 35.8%

The staged versions often spend long periods below the drawdown thresholds, so they remain de-risked for too many issues. That reduces EV more than expected.

4. To target maxDD below 20k, allocation alone is not enough.

Even very safe staged sleeves did not push maxDD below 20k at a 512-unit issue budget. A hard drawdown target near 20k likely requires lower base stake size, not just better allocation.

## Recommendation

Use drawdown-stage win-rate weighting as a second-layer risk control, but keep it modest:

- Normal: base N7/core allocation.
- DD > 5k: shift 64 units to high-win sleeve.
- DD > 10k: shift 128 units to high-win sleeve.
- DD > 15k: shift 128-192 units only if the current issue lacks strong convexity.
- DD > 20k: reduce total stake or require convexity override; do not rely only on sleeve switching.

Current practical candidates:

1. If target is maxDD around 25k: `fixed_384_n5ov128`.
2. If target is profit-first with better comfort: `fixed_448_dyn64`.
3. If we want explicit state-machine behavior: `dd5_10_15_20_n5ov`, but treat it as a paper arm until thresholds are tuned.

## Verification

- `python3 -m py_compile scripts/evaluate_n7_drawdown_winrate_allocator.py`
- `python3 scripts/evaluate_n7_drawdown_winrate_allocator.py --output-dir results/n7_drawdown_winrate_allocator_20260628`
