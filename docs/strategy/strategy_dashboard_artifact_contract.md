# Strategy Dashboard Artifact Contract

Date: 2026-07-04

## Purpose

This contract defines how `feature/beijing-lot-strategy` promotes validated model, decision-chain, and shadow-chain outputs into the decision dashboard without dashboard code changes.

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

`decision_variants` should include the user-selectable active and shadow views. Active is the production snapshot view. Shadow variants are strategy-provided artifacts and remain selectable in the UI when a current/open issue has matching shadow CSV rows.

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
