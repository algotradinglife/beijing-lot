# Segment Betting Strategy Frontend Contract

Date: 2026-07-07

This contract describes the rolling segment N-string betting planner produced by
`scripts/estimate_segment_betting_plan.py`.

The planner is downstream of the decision-chain artifact. It does not decide the
per-match 3/1/0 selections. It groups executable selections into kickoff-time
segments, chooses N from segment size and expected coverage, samples affordable
small-combo bundles, and settles or estimates return.

Ownership boundary:

- Strategy owns the generation method: script logic, parameter semantics,
  versioning, and this frontend/API contract.
- Backend/frontend ops owns running the generator for live issues and placing
  the resulting artifacts under the active strategy release's
  `artifacts.segment_betting_plan_dir`.
- API and frontend only read those generated artifacts.
- Missing live artifacts should be displayed as an explicit strategy gap; the
  dashboard must not synthesize or recompute a fallback plan.

## Versioning

The betting strategy has its own version independent from the decision-chain
version.

Current default:

| field | value |
| --- | --- |
| `strategy_family` | `segment_betting_plan` |
| `betting_strategy_version` | `segment_betting_v0.4.0000` |
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

The directory is selected by `config/strategy_release.json`:

```text
artifacts.segment_betting_plan_dir
```

## JSON Contract

The summary JSON includes:

| key | meaning |
| --- | --- |
| `summary` | Main displayed estimate. For multi-seed runs this is the mean summary. |
| `strategy_family` | Betting planner family id. |
| `betting_strategy_version` | Version of segmentation/N/bundle/budget logic. |
| `artifact_schema_version` | JSON/CSV schema version for frontend compatibility. |
| `planning_scope` | `by_segment` or `entire_issue`. Legacy query values `next_segment` and `remaining_issue` are normalized to `by_segment` and `entire_issue`. |
| `settings.stake_mode` | `scale_to_budget` or `unit_once`. |
| `decision_time` | Optional planning timestamp used to annotate segment timing/refresh context; issue-wide scopes still include ended matches. |
| `available_segments` | Number of concrete plan segments in the selected scope. |
| `segments` | Number of segments actually included in this plan. |
| `dynamic_segments_available` | Number of rolling time segments in the full issue. For `entire_issue`, this can be greater than `segments`. |
| `sp_drift_risk` | Risk marker. `accepted=true` means the user chose the all-issue view despite far-kickoff SP drift risk. |
| `summary.expected_profit_yuan` / `summary.expected_roi` | Live/open-issue display metrics. |
| `summary.settlement_status` | `unsettled`, `partially_settled`, or `settled`. |
| `summary.primary_metric_mode` | `expected` before settlement, `realized` after all included rows settle. |
| `summary.payout_yuan` / `summary.profit_yuan` / `summary.roi` | Realized replay metrics; blank until all included segments are settled. |
| `seed_aggregate.summary_mode` | `single_seed` or `multi_seed_mean`. |
| `seed_aggregate.metrics.*` | `min`, `p10`, `mean`, `median`, `p90`, `max` for cost, payout, profit, ROI, bundles, selected segments, and dead segments. |
| `settings` | Concrete values used for the run. |
| `parameter_schema` | Frontend-friendly adjustable parameter metadata. |
| `segment_csv` / `bundle_csv` | Detailed executable plan artifacts. |
| `seed_summary_csv` / `segment_seed_summary_csv` | Stability artifacts. |

For live planning, the frontend should treat one deterministic primary seed as
the executable plan and show multi-seed output as stability/risk context. A
multi-seed run is not an instruction to buy every sampled plan.

For open issues, display expected profit/ROI as the estimate and label realized
profit/ROI as pending. Realized fields are populated only after all included
matches are settled.

## API Contract

The decision API exposes the plan through a read-only endpoint:

```text
GET /api/issues/<issue>/segment-betting-plan
```

Default filters:

| filter | default |
| --- | --- |
| `decision_variant` / `variant` / `version` | Active release default decision variant. |
| `planning_scope` | `by_segment` |
| `stake_mode` | `scale_to_budget` |
| `betting_strategy_version` | empty, meaning latest matching artifact by mtime. |
| `label` | empty. |

When an artifact is found, the response is the summary JSON plus:

| key | meaning |
| --- | --- |
| `_artifact_path` | Resolved summary JSON path. |
| `artifact_status.status` | `available`. |
| `strategy_release` | Active release metadata and artifact health. |

When no artifact is found, the API returns HTTP 200 with:

```text
status=missing
artifact_status.status=missing
artifact_status.artifact_dir=<resolved segment_betting_plan_dir>
artifact_status.filters=<effective filters>
plan=null
```

Frontend should render the missing state directly and route it to the live
artifact generation job/operator; it should not call the generator itself from
the browser. Strategy action is only needed when the method, parameters, or
contract need to change.

## Planning Scope

The live betting workflow is dynamic. One issue can be split into several
rolling kickoff segments, but the user chooses how much of the remaining issue
to buy now.

| `planning_scope` | meaning | SP drift posture |
| --- | --- | --- |
| `by_segment` | Build every rolling time segment for the whole issue; ended matches remain included. Future segment rows can be regenerated as selections/SP refresh. | Default. Shows operational segment boundaries. |
| `entire_issue` | Build one all-issue segment containing every eligible match in the issue; ended matches remain included. | User explicitly accepts SP drift risk for later kickoffs. |

When `decision_time` is present, it does not exclude already-started matches.
It only annotates segment timing (`hours_from_decision_start/end`) and helps the
frontend distinguish settled/past rows from future rows that may be regenerated.
The frontend should show `available_segments`, `segments`, and
`dynamic_segments_available` together so the user can see whether the artifact
is a by-segment issue view or one all-issue segment.

## Stake Mode

The segment budget is now a target by default, not only a hard cap.

| `stake_mode` | meaning |
| --- | --- |
| `scale_to_budget` | Default. Select bundles, then repeat selected bundles by score until the segment budget is nearly exhausted, subject to `max_bundle_spend_pct`. |
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
| `planning_scope` | `by_segment` | Choose rolling issue segments or one all-issue segment. |
| `decision_time` | empty | Annotates segment timing relative to the planning snapshot; does not filter rows. |
| `segment_budget_yuan` | `1000` | Caps total cost per rolling segment. |
| `max_bundle_spend_pct` | `0.4` | Caps one selected N-string bundle's scaled spend as a share of the segment budget. |
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
| `settlement_status` / `settled_matches` | Separates live planning from settled replay. |
| `expected_profit_yuan` / `expected_roi` | Primary live estimate. |
| `actual_coverage_hit_rate` | Settled replay diagnostic only. |
| `width_counts` | Different single/double/full-cover shapes change cost and coverage. |
| `recommended_n` / `initial_recommended_n` | Shows final N after budget fallback versus initial recommendation. |
| `reasons` | Includes N downgrade and no-bundle explanations. |
| `planning_scope` / `sp_drift_risk_level` | Explains whether the artifact is by-segment or one all-issue segment. |
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
