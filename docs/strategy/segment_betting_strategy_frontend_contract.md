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
| `betting_strategy_version` | `segment_betting_v0.1.0000` |
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
| `seed_aggregate.summary_mode` | `single_seed` or `multi_seed_mean`. |
| `seed_aggregate.metrics.*` | `min`, `p10`, `mean`, `median`, `p90`, `max` for cost, payout, profit, ROI, bundles, selected segments, and dead segments. |
| `settings` | Concrete values used for the run. |
| `parameter_schema` | Frontend-friendly adjustable parameter metadata. |
| `segment_csv` / `bundle_csv` | Detailed executable plan artifacts. |
| `seed_summary_csv` / `segment_seed_summary_csv` | Stability artifacts. |

For live planning, the frontend should treat one deterministic primary seed as
the executable plan and show multi-seed output as stability/risk context. A
multi-seed run is not an instruction to buy every sampled plan.

## Recommended Controls

Basic controls:

| key | default | effect |
| --- | --- | --- |
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

Different decision-chain versions can therefore produce different N for the same
time segment because they expose different executable legs, widths, and coverage
probabilities.
