# Segment Betting Strategy User Explainer

Date: 2026-07-07

This document is a frontend-facing historical example for the rolling segment
N-string betting planner. It is settled replay only and is not a return promise.

The 26072 rows below are based on the `active_v3.3.3` structured artifact with
65 rows. They should not be displayed as the complete official 67-match issue.

## Summary Examples

| field | value |
| --- | --- |
| decision chain | `active_v3.3.3` (`shadow_v3.3.3` legacy alias for these replay artifacts) |
| betting strategy | `segment_betting_v0.3.0000` historical replay example |
| schema | `segment_betting_artifact_v1` |
| planning scope | `remaining_issue` legacy name |
| segment budget | 1000 yuan |
| ticket stake | 2 yuan per expanded ticket |
| seed sample | 20 seeds, `20260707` to `20260726` |
| issues | 26071 has 16 source rows; 26072 has 65 source rows in this artifact |

Current frontend scope names are `by_segment` and `entire_issue`. Legacy
`next_segment` inputs normalize to `by_segment`; legacy `remaining_issue` inputs
normalize to `entire_issue`. Live generation with an explicit decision time must
exclude matches that have already kicked off; the settled replay rows below keep
legacy names because they are historical artifacts.

| issue | decision_chain | betting_strategy | planning_scope | stake_mode | sample_rows | seed_count | selected_segments | base_cost_yuan | actual_stake_yuan | profit_yuan_mean | profit_yuan_p10 | profit_yuan_p90 | roi_mean | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26072 | active_v3.3.3 | segment_betting_v0.3.0000 | next_segment | scale_to_budget | 65 | 10 | 1 | 972 | 972 | 12120.38 | 10853.47 | 12966.20 | 12.4695 | Default stake mode; no extra budget room in this segment. |
| 26072 | active_v3.3.3 | segment_betting_v0.3.0000 | remaining_issue | scale_to_budget | 65 | 10 | 4 | 3068 | 3924 | 11046.93 | 9780.02 | 11892.75 | 2.8152 | Default stake mode; buys all remaining segments and accepts SP drift risk. |
| 26072 | active_v3.3.3 | segment_betting_v0.3.0000 | next_segment | unit_once | 65 | 10 | 1 | 972 | 972 | 12120.38 | 10853.47 | 12966.20 | 12.4695 | Audit comparison only. |
| 26072 | active_v3.3.3 | segment_betting_v0.3.0000 | remaining_issue | unit_once | 65 | 10 | 4 | 3068 | 3068 | 11573.86 | 10306.95 | 12419.68 | 3.7724 | Audit comparison only; under-spends versus the segment budget. |

## Default Scale-To-Budget Segment Example

| issue | planning_scope | stake_mode | segment_idx | eligible_matches | recommended_n | base_cost_yuan_mean | actual_stake_yuan_mean | profit_yuan_mean | dead_segment_rate | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26072 | remaining_issue | scale_to_budget | 1 | 19 | 8 | 972 | 972 | 12120.38 | 0.0 | First executable dynamic segment. |
| 26072 | remaining_issue | scale_to_budget | 2 | 24 | 6 | 992 | 992 | 378.88 | 0.0 | Dense second segment. |
| 26072 | remaining_issue | scale_to_budget | 3 | 13 | 6 | 960 | 960 | -960.00 | 1.0 | Dead segment in this settled replay. |
| 26072 | remaining_issue | scale_to_budget | 4 | 9 | 3 | 144 | 1000 | -492.33 | 0.0 | Stake scaling fills budget and can reduce replay ROI. |

## Display Rules

- Always label these rows as historical settled replay examples.
- Highlight `scale_to_budget` as the default mode.
- Keep `unit_once` as audit comparison only.
- Show base cost and actual stake side by side.
- When `seed_count > 1`, show p10/mean/p90 or a p10-p90 interval.
- Do not infer complete-issue performance from the 26072 65-row artifact sample.

## Issue-Level Replay Table

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
- If the user selects `entire_issue` in live planning, show the SP drift risk
  warning because later kickoff segments may move materially before bet time.
