# Segment Betting Strategy User Explainer

Date: 2026-07-07

This document gives the frontend a compact, user-facing backtest table for the
betting strategy tab. It is explanatory copy, not a production promotion gate.

## Backtest Scope

| field | value |
| --- | --- |
| decision chain | `shadow_v3.3.3` |
| betting strategy | `segment_betting_v0.3.0000` |
| schema | `segment_betting_artifact_v1` |
| planning scope | `remaining_issue` |
| segment budget | 1000 yuan |
| ticket stake | 2 yuan per expanded ticket |
| seed sample | 20 seeds, `20260707` to `20260726` |
| issues | 26071 has 16 source rows; 26072 has 65 source rows in this artifact |

`remaining_issue` means the replay buys every remaining dynamic segment in the
issue. In live use, the default is still `next_segment`; buying the whole
remaining issue means the user accepts far-kickoff SP drift risk.

## How To Read

| term | user-facing meaning |
| --- | --- |
| base cost | Cost if each selected bundle is bought once. |
| actual stake | Cost after `stake_mode`; the default tries to scale toward the segment budget. |
| payout | Settled return from the replay. |
| profit | `payout - actual stake`. |
| ROI | `profit / actual stake`; `1.00` means +100% net ROI. |
| p10-p90 | Sampling stability range across 20 seeds; it is not a confidence guarantee. |

## Summary Table

| issue | rows | segments | stake mode | base cost | actual stake | payout mean | profit mean | profit p10-p90 | ROI mean | ROI p10-p90 | user note |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 26071 | 16 | 2 | `scale_to_budget` | 212 | 1996 | 4815.85 | 2819.85 | 2819.85 - 2819.85 | +141.28% | +141.28% - +141.28% | Default mode. Low base cost is scaled close to the 1000 yuan budget per segment. |
| 26071 | 16 | 2 | `unit_once` | 212 | 212 | 454.51 | 242.51 | 242.51 - 242.51 | +114.39% | +114.39% - +114.39% | Audit mode. Explains why the old replay spent far below budget. |
| 26072 | 65 | 4 | `scale_to_budget` | 3068 | 3924 | 14347.99 | 10423.99 | 9401.46 - 11060.43 | +265.65% | +239.59% - +281.87% | Default mode. One segment is dead; budget scaling amplifies both winning and losing segments. |
| 26072 | 65 | 4 | `unit_once` | 3068 | 3068 | 14018.92 | 10950.92 | 9928.39 - 11587.36 | +356.94% | +323.61% - +377.68% | Audit mode. Higher ROI here comes from under-spending, so it should not replace the default stake mode. |

Frontend source: this Markdown table.

## Default Segment Table

This table uses the default `scale_to_budget` stake mode.

| issue | segment | window | L | N | actual stake | profit mean | profit p10-p90 | ROI mean | dead? | user note |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 26071 | 1 | 2026-06-30 22:50 -> 2026-07-02 10:50 | 9 | 3 | 996 | 637.75 | 637.75 - 637.75 | +64.03% | no | Budget scaling raises a small base bundle set close to the segment budget. |
| 26071 | 2 | 2026-07-02 23:50 -> 2026-07-03 11:50 | 7 | 3 | 1000 | 2182.10 | 2182.10 - 2182.10 | +218.21% | no | Main profit segment for issue 26071. |
| 26072 | 1 | 2026-07-03 23:20 -> 2026-07-04 11:20 | 19 | 8 | 972 | 11497.44 | 10474.91 - 12133.88 | +1182.86% | no | A high-N single bundle hit and dominates the issue result. |
| 26072 | 2 | 2026-07-04 18:20 -> 2026-07-05 02:50 | 24 | 6 | 992 | 378.88 | 378.88 - 378.88 | +38.19% | no | Dense candidate segment downgraded to N=6 and settled with a small gain. |
| 26072 | 3 | 2026-07-05 04:50 -> 2026-07-05 22:50 | 13 | 6 | 960 | -960.00 | -960.00 - -960.00 | -100.00% | yes | Dead segment. The frontend should show this explicitly when explaining drawdown risk. |
| 26072 | 4 | 2026-07-05 23:20 -> 2026-07-07 11:20 | 9 | 3 | 1000 | -492.33 | -492.33 - -492.33 | -49.23% | no | Low base cost was scaled to budget; the result partially recovered stake but still lost money. |

Frontend source: this Markdown table.

## Frontend Display Notes

- Show `scale_to_budget` as the default stake mode and `unit_once` as an audit
  comparison, not as a better live recommendation.
- Keep `base cost` and `actual stake` side by side. This is the clearest answer
  to "why did the old replay spend so little?" and "what changed after scaling?"
- Show a visible replay label: these are settled historical examples and are not
  a guaranteed or promised return.
- Mark 26072 as a 65-row artifact sample. Do not present it as a full official
  67-row issue replay unless the artifact is regenerated with all rows.
- If the user selects `remaining_issue` in live planning, show the SP drift risk
  warning because later kickoff segments may move materially before bet time.
