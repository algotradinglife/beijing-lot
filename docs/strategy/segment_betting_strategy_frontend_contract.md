# Segment Betting Strategy Frontend Contract

Date: 2026-07-07

This contract describes the rolling segment N-string betting planner produced by
`scripts/estimate_segment_betting_plan.py`.

The planner is downstream of the decision-chain artifact. It does not decide the
per-match 3/1/0 selections. It groups executable selections into kickoff-time
segments, chooses N from segment size and expected coverage, samples affordable
small-combo bundles, and settles or estimates return.

## Versioning

The betting strategy has its own version independent from the decision-chain
version.

Current default:

| field | value |
| --- | --- |
| `strategy_family` | `segment_betting_plan` |
| `betting_strategy_version` | `segment_betting_v0.3.0000` |
| `artifact_schema_version` | `segment_betting_artifact_v1` |

Version semantics:

| part | when to change |
| --- | --- |
| family | A different betting planner family, not just a parameter change. |
| major | Incompatible payout/cost semantics or artifact contract changes. |
| minor | Material strategy logic changes: segmentation, N selection, bundle scoring, budget allocation, or stability method. |
| four-digit patch | Bug fixes, diagnostics, report fields, or conservative tuning that preserves the strategy contract. |

The frontend should display the decision-chain version and betting strategy
version separately. Two artifacts can share the same decision-chain version but
use different betting strategy versions, and vice versa.

## Output Files

Each run writes:

| file | purpose |
| --- | --- |
| `segment_betting_plan_summary.json` | Main frontend/API payload. |
| `segment_betting_plan_segments.csv` | Per-seed, per-segment selected cost/payout/profit and N diagnostics. |
| `segment_betting_plan_bundles.csv` | Per-seed selected N-string bundles. |
| `segment_betting_plan_seed_summary.csv` | One summary row per sampled seed. |
| `segment_betting_plan_segment_seed_summary.csv` | Per-segment stability summary across seeds. |

## JSON Contract

The summary JSON includes:

| key | meaning |
| --- | --- |
| `summary` | Main displayed estimate. For multi-seed runs this is the mean summary. |
| `strategy_family` | Betting planner family id. |
| `betting_strategy_version` | Version of segmentation/N/bundle/budget logic. |
| `artifact_schema_version` | JSON/CSV schema version for frontend compatibility. |
| `planning_scope` | `next_segment` or `remaining_issue`. |
| `settings.stake_mode` | `scale_to_budget` or `unit_once`. |
| `decision_time` | Optional planning timestamp used to filter already-started matches. |
| `available_segments` | Number of dynamic segments available after decision-time filtering. |
| `segments` | Number of segments actually included in this plan. |
| `sp_drift_risk` | Risk marker. `accepted=true` means the user chose to buy remaining future segments now. |
| `seed_aggregate.summary_mode` | `single_seed` or `multi_seed_mean`. |
| `seed_aggregate.metrics.*` | `min`, `p10`, `mean`, `median`, `p90`, `max` for cost, payout, profit, ROI, bundles, selected segments, and dead segments. |
| `settings` | Concrete values used for the run. |
| `parameter_schema` | Frontend-friendly adjustable parameter metadata. |
| `segment_csv` / `bundle_csv` | Detailed executable plan artifacts. |
| `seed_summary_csv` / `segment_seed_summary_csv` | Stability artifacts. |

For live planning, the frontend should treat one deterministic primary seed as
the executable plan and show multi-seed output as stability/risk context. A
multi-seed run is not an instruction to buy every sampled plan.

## Planning Scope

The live betting workflow is dynamic. One issue can be split into several
rolling kickoff segments, but the user chooses how much of the remaining issue
to buy now.

| `planning_scope` | meaning | SP drift posture |
| --- | --- | --- |
| `next_segment` | Build and buy only the next dynamic segment after `decision_time`. | Default. Limits far-kickoff SP drift. |
| `remaining_issue` | Build and buy every remaining dynamic segment in the issue. | User explicitly accepts SP drift risk for later segments. |

When `decision_time` is present, matches with `kickoff <= decision_time` are
excluded before segment construction. The frontend should show `available_segments`
and `segments` together so the user can see whether they are buying one segment
or the whole remaining issue.

## Stake Mode

The segment budget is now a target by default, not only a hard cap.

| `stake_mode` | meaning |
| --- | --- |
| `scale_to_budget` | Default. Select bundles, then repeat selected bundles by score until the segment budget is nearly exhausted. |
| `unit_once` | Audit mode. Buy each selected bundle once; this reproduces the old conservative under-spend behavior. |

Segment CSV fields:

| field | meaning |
| --- | --- |
| `base_cost_yuan` | Cost before stake scaling. |
| `selected_cost_yuan` | Final cost after stake scaling. |
| `stake_multiplier_units` | Sum of bundle repeat multipliers in the segment. |

Bundle CSV fields:

| field | meaning |
| --- | --- |
| `stake_multiplier` | Number of times this bundle is bought. |
| `scaled_cost_yuan` | Bundle cost after multiplier. |
| `scaled_payout_yuan` | Settled bundle payout after multiplier. |
| `scaled_profit_yuan` | Settled bundle profit after multiplier. |

## Recommended Controls

Basic controls:

| key | default | effect |
| --- | --- | --- |
| `stake_mode` | `scale_to_budget` | Scale selected bundles toward segment budget, or use `unit_once` for audit. |
| `planning_scope` | `next_segment` | Choose next dynamic segment or all remaining issue segments. |
| `decision_time` | empty | Filters out matches already started at planning time. |
| `segment_budget_yuan` | `1000` | Caps total cost per rolling segment. |
| `window_hours` | `12` | Base kickoff window. Smaller is closer to kickoff but can starve segments. |
| `extend_hours` | `18,24,36` | Fallback windows when the base segment is too small. |
| `min_matches` | `6` | Minimum segment size before extension. |
| `max_matches` | `24` | Maximum segment size before N selection. |
| `max_n` | `8` | Upper bound for N. |
| `seed_count` | `1` | Stability runs. Use `20+` for comparison reports. |

Advanced controls:

| key | default | effect |
| --- | --- | --- |
| `stake_yuan_per_ticket` | `2` | Current BJDC cost assumption. Usually fixed. |
| `min_n` | `3` | Lower bound after budget or coverage downgrades. |
| `sample_attempts` | `12000` | Higher values reduce missed candidate noise but cost more CPU. |
| `max_overlap` | `null` | Bundle overlap guard. `null` means `N-2`. |
| `allow_negative_ev` | `false` | Diagnostic only; live planning should normally keep it off. |

Debug controls:

| key | default | effect |
| --- | --- | --- |
| `sample_seed` | `20260707` | Reproducible primary sampled plan. |
| `sample_seeds` | empty | Explicit comma-separated replay seed list; overrides `seed_count`. |

## Display Diagnostics

The frontend should display these per-segment fields when explaining why N
changed between strategy versions:

| field | reason |
| --- | --- |
| `eligible_matches` | N starts from segment size, roughly half the available matches. |
| `expected_coverage_hit_rate` | Lower expected coverage can downgrade N. |
| `actual_coverage_hit_rate` | Settled replay diagnostic only. |
| `width_counts` | Different single/double/full-cover shapes change cost and coverage. |
| `recommended_n` / `initial_recommended_n` | Shows final N after budget fallback versus initial recommendation. |
| `reasons` | Includes N downgrade and no-bundle explanations. |
| `planning_scope` / `sp_drift_risk_level` | Explains whether the segment is part of a bounded next-segment buy or remaining-issue buy. |
| `stake_mode` / `base_cost_yuan` / `selected_cost_yuan` | Explains whether cost was scaled toward budget or kept as one unit per bundle. |

Different decision-chain versions can therefore produce different N for the same
time segment because they expose different executable legs, widths, and coverage
probabilities.

## User-Facing Backtest Explanation

The betting strategy page should include a compact explanatory table using the
checked-in replay examples:

| file | frontend use |
| --- | --- |
| `docs/strategy/segment_betting_strategy_user_explainer_2026-07-07.md` | Human-readable wording, summary table, and default `scale_to_budget` per-segment explanation table for the tab. |

Display constraints:

- Treat these rows as settled replay examples, not live return promises.
- Label 26072 as a 65-row artifact sample unless a full-row artifact replaces it.
- Show `scale_to_budget` as the default stake mode and `unit_once` as audit mode.
- Keep `base_cost_yuan` and `selected_cost_yuan` visible together so users can
  understand budget scaling.
- Show p10/mean/p90 or p10-p90 ranges when `seed_count > 1`; do not display a
  single seed result as deterministic strategy quality.
