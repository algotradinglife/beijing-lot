# Strategy Dashboard Artifact Contract

Date: 2026-07-04

## Purpose

This contract defines how `feature/beijing-lot-strategy` promotes validated model, decision-chain, and shadow-chain outputs into the decision dashboard without dashboard code changes.

Structured decision-chain CSV fields and active/shadow semantics are specified
in:

```text
docs/strategy/strategy_dashboard_decision_chain_contract.md
```

The dashboard consumes one active strategy release from:

```text
config/strategy_release.json
```

The live API exposes the resolved release at:

```text
GET /api/strategy-release
```

## Release Registry

`config/strategy_release.json` uses:

```text
schema_version: strategy_release_registry_v1
active_release_id: <release id to serve>
releases.<release_id>: release payload
```

To promote a new strategy build, strategy should add a new release entry and then switch `active_release_id`. Do not overwrite old release entries; they are the rollback path.

## Required Release Fields

Each release must include:

```text
release_id
status
owner
strategy_family
model_versions
decision_variants
main_strategy_arms
artifacts
required_artifacts
promotion
validation
```

`model_versions` should include:

```text
probability_model
q_model
decision_chain
shadow_decision_chain
```

`decision_variants` should include the user-selectable active and shadow views.
Active is the production snapshot view. Shadow variants are strategy-provided
artifacts and remain selectable in the UI when a current/open issue has
matching shadow CSV rows. Variants can include a `readiness` object so the API
and dashboard know whether a missing artifact should fall back, render as a
diagnostic placeholder, or stay hidden until produced.

## Artifact Keys

The dashboard currently understands these artifact keys:

```text
main_strategy_dir
ticket_pool_dir
ticket_pool_csv
linegap_drift_dir
joint_leg_rows_csv
structured_shadow_dir
```

Paths may be absolute or relative to the repo root.

Minimum required artifacts for the main strategy panel:

```text
main_strategy_dir/sleeve_mix_summary.csv
main_strategy_dir/sleeve_mix_annual.csv
main_strategy_dir/sleeve_mix_issue_profit.csv
ticket_pool_csv
joint_leg_rows_csv
```

Optional but supported:

```text
linegap_drift_dir/paper_arm_summary.csv
structured_shadow_dir/<issue>_*/structured_shadow_<issue>.csv
```

v4.2.0000 execution artifacts are published through the same
`structured_shadow_dir` mechanism. They are still structured shadow CSVs, but
their `shadow_selection_codes` represents the executable selection after the
execution policy, while `execution_recommended_codes` preserves the wider
decision-chain audit recommendation.
For `late_proxy_fullcap2`, execution scoring must use refreshed per-match SP,
not the stale source artifact SP. The artifact should retain
`source_sp_*`/`source_q_*` for audit and publish `execution_sp_*`,
`execution_q_*`, `execution_sp_snapshot_ts`, `execution_sp_repriced`, and
`execution_sp_missing` for dashboard explanation.

Current strategy-owned execution variants:

```text
shadow_v4.2.0000_execution_strict_fullcap2
shadow_v4.2.0000_execution_late_proxy_fullcap2
```

Dashboard should only display these variants when the active release manifest
declares matching `decision_variants[]` and the CSV rows contain matching
`shadow_arm` values. The `fullcap2` suffix is retained for compatibility, but
strategy execution policy `v4.2.0002+` does not apply final per-segment/budget
caps in this artifact. Dashboard must not recompute late-refresh state or N
selection from these rows; final ticket/stake optimization is a separate layer.

Readiness/defaulting contract:

- `defaultable_when=available`: the variant can be default only after real
  per-issue rows exist.
- `defaultable_when=never`: the variant is selectable for manual audit, but
  must not become the API default automatically. The current active release
  uses this for v4.2 execution variants while v3.3.3 remains the stable default.
- `missing_behavior=diagnostic_placeholder`: API may expose a degraded,
  non-defaultable placeholder for diagnosis. This is used for missing
  `strict_fullcap2`.
- `missing_behavior=hidden_until_artifact`: API hides the option until the
  artifact exists. This is used for missing `late_proxy_fullcap2`.
- Runtime API options expose `available`, `defaultable`, `readiness_status`,
  and `degraded_reason`; dashboard should display these directly.
- Structured shadow artifacts are complete only when their CSV `match_idx` set
  matches the issue `matches` table. Strategy publish scripts must skip
  incomplete artifacts; API exposes any legacy suppressed artifacts through
  `strategy_version_context.contract_warnings[].type=structured_shadow_artifacts_incomplete`.

Reference sample CSV:

```text
docs/strategy/examples/v4_2_0000_execution_artifact_example.csv
```

## Dashboard Consumption

The decision API uses the active release for:

- Main strategy A/B candidates in `/api/issues/:issue/main-strategy`
- Annual and issue-level replay rows
- Historical EV ticket pool
- Joint leg q/probability/confidence metadata
- Structured shadow decision variants
- Strategy lab source data
- Health checks and artifact diagnostics

The frontend still lets users choose active or shadow versions. The dashboard only changes where those variants come from: strategy release metadata and strategy-provided CSV artifacts.

For v4.2.0000 execution artifacts:

- Issue Board and Match Detail should show both the audit recommendation
  (`execution_recommended_codes`) and executable selection
  (`shadow_selection_codes`).
- Execution badges should come from `execution_action` and
  `execution_reasons`.
- `value_only_sp_drift` inside `execution_reasons` is an audit/risk marker for
  payout-driven q movement; it is not a no-buy state unless `execution_action`
  itself is `skip_*`.
- `late_refresh_pending_draw_rescue` inside `execution_reasons` means a
  previously skipped pending draw was restored after severe late SP refresh.
  It is executable when `execution_action=execute_double`.
- Full-cover display should use `execution_full_score`,
  `execution_full_candidate`, and `execution_full_kept`.
  `execution_full_kept=1` means the row remains full cover in this per-row
  artifact, not that budget optimization has funded it.
- Late-refresh stop color should come from `execution_unlock_state`:
  `waiting_late_refresh` renders red and `unlocked_after_late_refresh` renders
  green.
- `skip_*` actions should be rendered as stop/no-buy states. In particular,
  `skip_wait_late_refresh` is a temporary warning to not bet the match until a
  valid late SP refresh artifact exists.
- v4.2 execution variants are manual diagnostic/experimental views in the
  current release. If a future release makes them defaultable, live data
  auto-refresh must keep the selected policy visible instead of silently turning
  a stop/wait row into an actionable pick.
- Rolling/N views and any stake preview must use `shadow_selection_codes`.
- Dashboard/API must treat `execution_*` as read-only artifact data.

## Validation

Before handing off a new release:

```bash
python3 scripts/validate_strategy_release.py --release <release_id>
```

For a machine that has not pulled/generated ignored `results/` artifacts yet:

```bash
python3 scripts/validate_strategy_release.py --release <release_id> --allow-missing
```

API smoke after promotion:

```bash
curl http://127.0.0.1:8790/healthz
curl http://127.0.0.1:8790/api/strategy-release
curl http://127.0.0.1:8790/api/issues/current/main-strategy
```

Code smoke:

```bash
python3 -m py_compile src/decision_api/app.py scripts/validate_strategy_release.py
pytest -q tests/decision_api/test_strategy_release.py
```

## Promotion Rules

Strategy should not promote a release unless it provides:

- Reproducible artifact paths
- Same-budget comparison against the current active release when changing portfolio logic
- No-future-leakage statement for probability, q, decision-chain, and shadow-chain artifacts
- Historical and recent-period performance summary
- Clear rollback release id or explicit note that the previous active release is the rollback

`line-gap` and `SP drift` remain diagnostics unless a strategy release explicitly validates and documents them as production selectors.

## Rollback

Rollback is a one-line config change:

```text
active_release_id: <previous release id>
```

Then restart or reload the decision API process so the release cache is refreshed.
