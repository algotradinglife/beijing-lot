# Segment Betting Strategy User Explainer

Date: 2026-07-07

This document is a frontend-facing historical example for the rolling segment
N-string betting planner. It is settled replay only and is not a return promise.

The 26072 rows below are based on the `active_v3.3.3` structured artifact with
65 rows. They should not be displayed as the complete official 67-match issue.

## Summary Examples

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
