# N=7 Line-Gap Guided Protection

Date: 2026-06-27

## Question

Test whether Asian handicap line gap can guide the 5单2保护 strategy.

Prior logic:

```text
line_gap = -beidan_handicap_line - asian_handicap_line

line_gap >= +0.5:
  Beidan makes the home side cover a deeper integer line than the Asian market.
  Protection should favor handicap draw/away: 1/0.

line_gap <= -0.5:
  Beidan makes the home side easier than the Asian market.
  Protection should favor home/draw: 3/1.
```

Draw as an added protection leg also requires draw odds stability:

```text
abs(log(draw_1h_odds / draw_10h_odds)) <= 0.08
```

This is a hard thesis selector: if the high-SP anchor is not on the side
supported by line_gap, it is not eligible for a protected variant.

## Implementation

Updated script:

```text
scripts/evaluate_n7_high_sp_anchor_protection.py
```

New policy:

```text
--protection-policies line_gap_guided
```

Main run:

```bash
python3 scripts/evaluate_n7_high_sp_anchor_protection.py \
  --min-year 2014 \
  --train-issues 24 \
  --max-tickets-per-issue 20 \
  --issue-budget-units 256 \
  --snapshot 1h \
  --min-proxy-odds-values 4,6,8 \
  --protection-policies line_gap_guided \
  --protect-score-floor-ratio 0.85 \
  --composition-mode target_protection \
  --target-protected-per-ticket 2 \
  --require-target-protection \
  --max-full-cover-per-ticket 1 \
  --full-cover-min-proxy-odds 12 \
  --full-protect-score-floor-ratio 0.80 \
  --line-gap-threshold 0.5 \
  --draw-stability-max-abs-log-move 0.08 \
  --output-dir results/n7_high_sp_anchor_linegap_2014_1h_5s2p_full12
```

Variants:

```text
results/n7_high_sp_anchor_linegap025_2014_1h_5s2p_full12
  same as main, but --line-gap-threshold 0.25

results/n7_high_sp_anchor_linegap_nofull_2014_1h_5s2p
  same as main, but no full-cover leg
```

## Main Results

Same-budget fractional, 256 units per issue:

| Run | Strategy | ROI | Profit | Hit Rate | Issue Win | Profitable Issues | Best Share | Verdict |
|---|---|---:|---:|---:|---:|---:|---:|---|
| gap 0.5 + full | `o6_line_gap` | 28.8% | 6478 | 1.69% | 17.1% | 15 | 98.9% | concentrated |
| gap 0.5 + full | `o4_line_gap` | 11.2% | 17570 | 1.26% | 15.8% | 97 | 75.9% | concentrated |
| gap 0.5 + full | `o8_line_gap` | 7.6% | 1174 | 1.58% | 10.0% | 6 | 484.0% | concentrated |
| gap 0.25 + full | `o6_line_gap` | 53.6% | 45377 | 1.55% | 16.9% | 56 | 70.1% | concentrated |
| gap 0.25 + full | `o4_line_gap` | 0.9% | 1418 | 1.06% | 13.8% | 89 | 772.0% | concentrated |
| gap 0.5 no full | `o4_line_gap` | 30.5% | 47870 | 1.25% | 16.0% | 98 | 27.8% | pass |

Comparison to the previous 5单2保护 arms:

| Strategy | ROI | Profit | Hit Rate | Issue Win | Profitable Issues | Verdict |
|---|---:|---:|---:|---:|---:|---|
| `o8_q_top_5s2p_full12` | 88.2% | 95498 | 0.90% | 9.5% | 40 | pass |
| `o6_q_top_5s2p_full12` | 58.4% | 91868 | 0.77% | 9.8% | 60 | pass |
| `o4_market_top_5s2p_full12` | 18.3% | 30660 | 1.11% | 14.7% | 96 | pass |
| `o4_q_top_5s2p_full12` | 12.4% | 21245 | 1.00% | 13.6% | 91 | pass |
| `o4_line_gap_5s2p_no_full` | 30.5% | 47870 | 1.25% | 16.0% | 98 | pass |

The best line-gap result is `o4_line_gap_5s2p_no_full`, but it still does not
dominate `o8_q_top` or `o6_q_top`; it is closer to a low-volatility/anti-dead
ticket arm.

## Recent 2023-2025

Recent years are the problem.

| Run | Strategy | ROI | Profit | Hit Rate |
|---|---|---:|---:|---:|
| gap 0.5 + full | `o4_line_gap` | -12.4% | -3664 | 1.04% |
| gap 0.25 + full | `o4_line_gap` | -22.9% | -7278 | 0.69% |
| gap 0.5 no full | `o4_line_gap` | -8.9% | -2616 | 1.00% |
| previous | `o8_q_top_5s2p_full12` | 56.0% | 12897 | 0.52% |
| previous | `o4_market_top_5s2p_full12` | 30.3% | 9684 | 0.72% |
| previous | `o4_q_top_5s2p_full12` | 9.4% | 3092 | 0.58% |
| baseline | `baseline_q_high_sp` | -50.2% | -16576 | 0.36% |

So hard line-gap selection fails the recent-period check.

## Diagnosis

Line-gap guidance is too restrictive as a hard selector.

Protected candidate counts:

| Run | Strategy | Candidates | Protected | Full |
|---|---|---:|---:|---:|
| gap 0.5 + full | `o4_line_gap` | 109645 | 6659 | 370 |
| gap 0.5 + full | `o6_line_gap` | 35804 | 618 | 370 |
| gap 0.5 + full | `o8_line_gap` | 16544 | 528 | 370 |
| gap 0.25 + full | `o4_line_gap` | 109645 | 11123 | 370 |
| gap 0.5 no full | `o4_line_gap` | 109645 | 6294 | 0 |

For high-SP thresholds `o6/o8`, full-cover candidates become too large a share
of protected variants. For `o4`, no-full is cleaner and less concentrated, but
recent performance is still negative.

## Conclusion

Do not use `line_gap_guided` as the primary hard protection selector.

Better interpretation:

- `line_gap` is useful as a thesis label and diagnostic.
- It may be useful as a soft depth adjustment or veto.
- It should not replace q/market-based protection selection.
- Full-cover should not be driven by line_gap alone.

Current recommended arms remain:

```text
balanced anti-dead-ticket:
  o4_market_top_5s2p_full12

high-upside tail:
  o8_q_top_5s2p_full12
```

Next integration should be soft:

```text
market/q protection selector
  + line_gap support bonus
  + line_gap opposition haircut/veto
  + draw stability filter
```

That matches the logical framework better than forcing line_gap to choose the
entire double-cover thesis.

## Outputs

- `results/n7_high_sp_anchor_linegap_2014_1h_5s2p_full12`
- `results/n7_high_sp_anchor_linegap025_2014_1h_5s2p_full12`
- `results/n7_high_sp_anchor_linegap_nofull_2014_1h_5s2p`
- `scripts/evaluate_n7_high_sp_anchor_protection.py`
