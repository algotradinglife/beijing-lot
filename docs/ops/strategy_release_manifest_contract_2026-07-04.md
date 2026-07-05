# Strategy Release Manifest Contract

This contract is the handoff boundary between the strategy worktree and the
decision dashboard. Strategy owns model and decision-chain artifacts. The API
and frontend only load declared artifacts and render the chosen version.

Canonical files:

- Runtime registry: `config/strategy_release.json`
- Schema: `schemas/strategy_release_registry_v1.schema.json`
- Example: `tests/fixtures/strategy_release/strategy_release_manifest.example.json`
- API endpoint: `GET /api/strategy-release`

## Registry Shape

The root object uses `schema_version: strategy_release_registry_v1`,
`active_release_id`, and a `releases` map keyed by `release_id`.

Each release must include:

- `release_id`: lowercase snake-case deployment id ending in `YYYY_MM_DD`,
  for example `main_n7_384_2026_07_04`.
- `version_id`: release bundle version in `x.y.z` form.
- `status`: `active`, `shadow`, `draft`, `superseded`, or `archived`.
- `generated_at`: ISO timestamp for the artifact bundle.
- `effective_from_issue`: first issue where this release may be shown live.
- `artifact_scope`: historical range, live issue policy, and freeze policy.
- `snapshot_timestamps`: timestamps for probability, q, confidence, and
  decision-chain inputs. These make drift or late regeneration visible.
- `model_versions`: probability model, q model, active decision chain, and
  shadow decision chain ids.
- `decision_variants`: selectable active/shadow options.
- `main_strategy_arms`: dashboard labels for the supported arms.
- `artifacts`: relative paths to result files/directories.
- `required_artifacts`: health-check specs resolved through `artifacts`.
- `promotion` and `validation`: release gate metadata.

## Active And Shadow Boundary

`active` is the displayed live version. It may come from confirmed decision
snapshots or other active artifacts declared by the release.

`shadow` is provided by the strategy worktree. The dashboard must not rebuild,
reinterpret, or hard-code shadow logic. It should only consume the artifact
declared by `decision_variants[].artifact_key`.

Historical issues must only show variants that were available under the release
effective for that issue. Post-settlement artifacts are review-only unless a new
release explicitly promotes them.

## Decision-Chain Version Numbers

Decision variant ids and `decision_variants[].version_id` use `x.y.abcd` going
forward:

- `x`: formal line or structural rewrite.
- `y`: major strategy/decision-chain logic change.
- `abcd`: small fix counter within the same `x.y` line, zero-padded to four
  digits.

Example: `shadow_v3.4.0000` starts a new major logic branch after
`shadow_v3.3.0012`; `shadow_v4.0.0000` is a structural/formal version line.

Existing three-part values such as `shadow_v3.3.3` remain readable as legacy
artifacts and sort equivalently to `shadow_v3.3.0003`. New strategy artifacts
should use the four-digit fix segment.

## Required Artifacts

Current N=7 release requires:

- `main_strategy_dir/sleeve_mix_summary.csv`
- `main_strategy_dir/sleeve_mix_annual.csv`
- `main_strategy_dir/sleeve_mix_issue_profit.csv`
- `ticket_pool_csv`
- `joint_leg_rows_csv`

Optional diagnostics such as `linegap_drift_dir` can be exposed as labels or
paper sleeves, but they are not hard gates unless the strategy release promotes
them in `validation`.

## API Behavior

The API should resolve paths relative to the project root, report missing
required artifacts in `artifact_health.missing_required`, and return explicit
degraded/error state. Real mode must not silently fall back to mock data.

The frontend should treat the selected strategy version as one state variable
shared by Issue Board, Match Detail, and Settlement Review.

## Strategy Handoff Checklist

Before strategy asks the dashboard to adopt a new version:

1. Write a new release entry in `config/strategy_release.json`.
2. Use `x.y.z` for release bundle `version_id`, and `x.y.abcd` for decision
   variant `version_id` / `shadow_vx.y.abcd`.
3. Fill `generated_at`, `effective_from_issue`, `artifact_scope`, and
   `snapshot_timestamps`.
4. Point artifacts to committed or locally generated result files, without
   committing SQLite databases, Excel files, or bulky raw data.
5. Set `validation.no_future_leakage` and link the validation report.
6. Run the contract test and dashboard smoke before requesting review.
