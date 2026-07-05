# Strategy Dashboard Decision Chain Contract

Date: 2026-07-05

## Purpose

This contract defines how the strategy worktree publishes active/shadow
decision-chain artifacts for the decision dashboard.

It complements:

- `docs/ops/strategy_release_manifest_contract_2026-07-04.md`
- `schemas/strategy_release_registry_v1.schema.json`
- `docs/strategy/decision_chain_v4_semantic_contract_2026-07-04.md`

The dashboard owns display, selection state, and degraded/error reporting. The
strategy worktree owns versioned artifacts, no-leakage guarantees, replay
evidence, and the meaning of each decision field.

## Version Semantics

Decision variants use manifest ids:

```text
active_v3
shadow_vX.Y.abcd
```

Rules:

- New decision-chain artifacts use `shadow_vX.Y.abcd`: `X` is the formal or
  structural line, `Y` is the major logic branch, and `abcd` is the zero-padded
  four-digit fix counter.
- Existing `shadow_vX.Y.Z` artifacts remain readable as legacy values and sort
  equivalently to `shadow_vX.Y.000Z`.
- `decision_variants[].version_id` in `config/strategy_release.json` should
  use the same `X.Y.abcd` decision-chain version (`4.2.0000`, etc.). Release
  bundle `version_id` remains `x.y.z`.
- CSV `shadow_arm` must equal the manifest `variant_id`.
- CSV `shadow_version` is the implementation/version string for audit. It may
  be more descriptive than semver, for example
  `llm_chain_structured_v4.2.0000_layered_merge_execution_policy`.
- The API only exposes shadow artifacts whose `shadow_arm` is declared in the
  active release manifest. Undeclared shadow CSVs are suppressed.
- When at least one declared shadow artifact is available for an issue, the API
  marks the highest declared shadow version as the default option. If no shadow
  artifact is available, active fallback remains available and the response may
  be degraded.

Promotion from shadow to active requires a new release entry or an explicit
manifest update. Do not silently reinterpret a shadow CSV as active.

## Artifact Location

Dashboard-published structured shadow artifacts live under the release
artifact key:

```text
structured_shadow_dir = results/structured_decision_chain_shadow
```

Path pattern:

```text
results/structured_decision_chain_shadow/{issue}_{YYYYMMDD}_{shadow_arm}/structured_shadow_{issue}.csv
```

The API currently scans:

```text
results/structured_decision_chain_shadow/{issue}_*/structured_shadow_{issue}.csv
```

Research and backtest outputs must stay in separate directories such as
`results/backtest_*`. They are not dashboard-published artifacts unless copied
or regenerated into `structured_shadow_dir` and declared by the release
manifest.

Post-settlement replay artifacts are review-only unless their release metadata
states that they were generated from a valid pre-match snapshot before the issue
was traded.

## Minimum Dashboard CSV Schema

The dashboard currently consumes these fields. New strategy versions must keep
them populated for compatibility.

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `issue` | string | yes | Must match the file issue. |
| `match_idx` | integer | yes | Unique within issue; used as the join key. |
| `match_id` | string | recommended | Stable match id when available. |
| `league` | string | recommended | Display/audit only. |
| `home` | string | recommended | Display/audit only. |
| `away` | string | recommended | Display/audit only. |
| `handicap_line` | number/string | recommended | Beidan handicap line used by the decision chain. |
| `shadow_arm` | string | yes | Must match a manifest `decision_variants[].variant_id`, e.g. `shadow_v4.1.0`. |
| `shadow_version` | string | yes | Implementation version string for audit. |
| `shadow_judgment` | string | yes | Human-readable final summary. |
| `shadow_primary` | enum | yes if buy/display codes exist | One of `3`, `1`, `0`; first display pick. |
| `shadow_selection_codes` | string | yes | `+`-joined codes from `3`, `1`, `0`; empty means no buy/display pick. |
| `shadow_stop_flag` | boolean/int | yes | `1/true` means no executable pick now; render as stop/wait/risk, not as a buy signal. |
| `selection_type` | enum | yes | `single`, `double`, `full`, or `no-buy`. |
| `prob_top` | enum/string | recommended | Highest probability code if known. |
| `q_top` | enum/string | recommended | Highest q/EV code if known. |
| `p_3`, `p_1`, `p_0` | number | recommended | Calibrated probabilities. |
| `sp_3`, `sp_1`, `sp_0` | number | recommended | SP inputs used by q. |
| `q_3`, `q_1`, `q_0` | number | recommended | Probability times SP, before any ticket-level policy. |
| `max_q` | number | recommended | Max q among outcomes. |
| `risk_tags` | string | recommended | `;`-joined stable tags. |
| `shadow_chain_json` | JSON array | yes | Ordered decision-chain explanation steps. |
| `shadow_categories_json` | JSON array | yes | Structured category cards for dashboard display. |

Settlement/audit columns are optional for live artifacts and useful for replay:

```text
score
actual_code
actual_label
winning_sp
shadow_primary_hit
shadow_coverage_hit
shadow_profit_proxy
active_selection_codes
active_coverage_hit
```

They must not be used by a pre-match decision chain.

## v4+ Stable Extension Fields

v4 and later should publish stable business fields in addition to the legacy
dashboard fields above. The legacy `shadow_*` fields should be derived from
these fields so current dashboard builds can still render them.

| Field | Type | Rule |
| --- | --- | --- |
| `schema_version` | string | Example: `structured_shadow_decision_v1`. |
| `decision_action` | enum | `buy`, `stop`, `wait_late_refresh`, `full_cover_or_skip`, `review_only`. |
| `recommended_codes` | string | `+`-joined script recommendation, including full-cover candidates. |
| `buy_codes` | string | `+`-joined codes that are actually buyable now; empty unless `decision_action=buy`. |
| `primary_code` | enum/string | Primary code after script aggregation. |
| `protect_codes` | string | `+`-joined protection codes. |
| `action_reasons_json` | JSON array | Machine-readable reasons for action. |
| `candidate_pool_json` | JSON object/array | Candidate scoring details. |
| `semantic_contract_json` | JSON object | Normalized LLM semantic contract, if used. |
| `generated_at` | ISO timestamp | Artifact generation time. |
| `snapshot_cutoff_at` | ISO timestamp | Latest input snapshot timestamp allowed by no-leakage policy. |
| `artifact_mode` | enum | `live_snapshot`, `paper_shadow`, `backtest`, or `review_only`. |

Mapping rule:

- `shadow_selection_codes` should equal `buy_codes` when `decision_action=buy`.
- For `full_cover_or_skip`, `shadow_selection_codes` may show
  `recommended_codes` for audit, but `buy_codes` must be empty unless the
  budget/ticket policy approved the full cover.
- For `wait_late_refresh`, `stop`, and `review_only`, `buy_codes` must be
  empty. If display codes are retained for explanation, `shadow_stop_flag` must
  be true and `decision_action` must disambiguate that they are not buy orders.
- `stop` is a user-facing blocking signal. In live use, it means "do not place
  this bet now" even if the row still carries audit/recommended codes for
  explanation.

## v4.2.0000 Execution Artifact Fields

v4.2.0000 separates the audit recommendation from the executable betting
selection. The strategy worktree publishes execution artifacts as ordinary
structured shadow CSVs, with additional `execution_*` fields. Dashboard must
display these fields read-only and must not recompute them.

Current execution variant ids:

```text
shadow_v4.2.0000_execution_strict_fullcap2
shadow_v4.2.0000_execution_late_proxy_fullcap2
```

`strict_fullcap2` is the pre-refresh state: `wait_late_refresh` rows remain
no-buy. `late_proxy_fullcap2` represents the executable state after a valid
late SP refresh has occurred and the refreshed SP has been applied to execution
scoring. The live workflow should publish/choose `strict_fullcap2` before the
refresh window and `late_proxy_fullcap2` only after the refresh artifact exists
and per-match execution SP is available. The `fullcap2` suffix is a legacy
variant id retained for dashboard compatibility; starting with execution policy
`v4.2.0002`, this layer does not apply the final per-segment/budget cap.

Because live strategy artifacts may refresh automatically, dashboard must make
the selected execution policy and blocking state visible. A row that is
`skip_wait_late_refresh` should be shown as a temporary stop/wait state such as
"stop - waiting late refresh"; it is a warning not to bet that match yet, not a
final statement that the match will never be buyable.

When both strict and late-proxy artifacts are available for the same execution
version, API should default to `late_proxy_fullcap2`. This is the automated
unlock mechanism. The strict artifact remains selectable for audit, and ticket
submission remains an explicit user action.

Manifest readiness fields make this defaulting rule explicit. Each
`decision_variants[]` entry may include:

| Field | Values | Meaning |
| --- | --- | --- |
| `readiness.artifact_required` | boolean | Whether a per-issue artifact row must exist before the variant is real. |
| `readiness.defaultable_when` | `always`, `available`, `never` | Whether the API may choose this variant as the default. Execution variants use `available`. |
| `readiness.missing_behavior` | `builtin_active`, `fallback_to_active`, `diagnostic_placeholder`, `hidden_until_artifact`, `artifact_missing` | How API/frontend should treat a missing per-issue artifact. |
| `readiness.late_refresh` | `not_applicable`, `strict_wait_before_valid_live_sp_refresh`, `unlock_after_valid_live_sp_refresh` | Late-refresh timing semantics. |
| `readiness.missing_reason` | string | Stable warning code for missing artifacts. |

Runtime option fields exposed by the API:

- `available=true` means the option has real rows for the issue or is built in.
- `defaultable=true` means the option can participate in default selection.
- `readiness_status=available` means no readiness warning.
- `readiness_status=degraded` means the option is selectable only as a
  diagnostic placeholder, currently used for missing strict execution artifacts.
- `readiness_status=unavailable` means the option must not be shown as a live
  executable choice. Missing late-proxy artifacts are hidden until published.
- `degraded_reason` is a concise machine-readable reason for warnings.

For v4.2.0000 execution variants:

- missing `strict_fullcap2`: API may expose a degraded diagnostic placeholder,
  but `available=false`, `defaultable=false`, and rows are no-buy/wait.
- real `strict_fullcap2`: `available=true`, `defaultable=true`; rows held by
  late refresh stay red with `waiting_late_refresh`.
- missing `late_proxy_fullcap2`: hidden from options, not defaultable.
- real `late_proxy_fullcap2`: `available=true`, `defaultable=true`, and it
  outranks strict as the default for that issue.

Required execution extension fields:

| Field | Type | Rule |
| --- | --- | --- |
| `execution_policy_version` | string | Example: `v4.2.0002_execution_policy_2026-07-05_probability_anchor`. |
| `execution_policy_name` | enum/string | Example: `strict_fullcap2` or `late_proxy_fullcap2`. |
| `execution_action` | enum | Stable action from the execution layer. |
| `execution_reasons` | string | `;`-joined machine-readable reasons. |
| `execution_source_action` | enum/string | Original v4.2 decision action, e.g. `buy`, `wait_late_refresh`, `full_cover_or_skip`. |
| `execution_recommended_codes` | string | Audit recommendation from v4.2.0000, before execution compression. |
| `execution_double_codes` | string | Best compressed double if a full-cover row must be reduced. |
| `execution_full_score` | number/string | Per-row full-cover value score for downstream stake optimization. |
| `execution_full_candidate` | boolean/int | `1` if the row qualified as a per-row full-cover candidate. |
| `execution_full_kept` | boolean/int | `1` if this artifact leaves the row as full cover; not a final budget/cap approval in `v4.2.0002+`. |
| `execution_segment_idx` | integer/string | Rolling segment id for downstream stake optimization. |
| `execution_unlock_state` | enum/string | Late-refresh stop state for UI color and automation. |
| `source_sp_3`, `source_sp_1`, `source_sp_0` | number/string | SP values from the source structured shadow CSV before execution repricing. |
| `source_q_3`, `source_q_1`, `source_q_0` | number/string | q values from the source structured shadow CSV before execution repricing. |
| `execution_sp_3`, `execution_sp_1`, `execution_sp_0` | number/string | SP values actually used by the execution layer. |
| `execution_q_3`, `execution_q_1`, `execution_q_0` | number/string | Probability times execution SP, used for full-score and compression decisions. |
| `execution_sp_source` | string | `live_sp_snapshots`, `matches_current_sp`, `source_artifact`, or `missing_trusted_sp`. |
| `execution_sp_snapshot_ts` | string | Timestamp of the SP snapshot used by execution. |
| `execution_sp_repriced` | boolean/int | `1` when source SP and execution SP differ materially. |
| `execution_sp_reprice_ratio_max` | number/string | Largest ratio between source SP and execution SP across the three outcomes. |
| `execution_sp_missing` | boolean/int | `1` when late-proxy execution could not find trusted per-match SP and must not unlock. |

Stable `execution_action` values:

| Action | Meaning |
| --- | --- |
| `execute_single` | One executable code. |
| `execute_double` | Two executable codes. |
| `execute_full_cover` | Per-row full cover selected by execution policy; downstream stake optimization may still skip or compress it. |
| `downgrade_full_to_double` | Low-value full cover reduced to best double. |
| `downgrade_full_to_double_layer_conflict` | Layer-conflict full cover reduced to best double because full value is below threshold. |
| `downgrade_full_to_double_over_cap` | Deprecated after `v4.2.0002`; final cap is not applied in this layer. |
| `skip_wait_late_refresh` | Strict mode: row is waiting for late refresh and is not buyable. |
| `skip_stop` | Source chain stopped the row. |
| `skip_full_over_cap` | Deprecated after `v4.2.0002`; final cap is not applied in this layer. |
| `skip_no_recommendation` | No v4.2 recommended codes. |
| `skip_missing_decision` | Execution artifact could not find a v4.2 decision row. |
| `skip_missing_execution_sp` | Late-proxy mode could not find trusted per-match execution SP; row remains no-buy. |
| `skip_late_repriced_conflict_missing_prob_top` | Late-proxy row had severe SP repricing; compressed double lost the probability top, so the row remains no-buy. |
| `skip_late_q_top_drift` | Late execution q-top drifted to an uncovered outcome; row remains no-buy instead of swapping codes automatically. |

Execution mapping rules:

- `shadow_selection_codes` is the actual executable selection. It may be empty.
- `execution_recommended_codes` is the audit recommendation. It can be wider
  than `shadow_selection_codes`.
- `shadow_stop_flag=1` means no executable selection exists for this row.
- `skip_*` execution actions must be rendered as stop/no-buy states even when
  `execution_recommended_codes` is populated.
- In `v4.2.0002`, severely repriced late/full-cover rows are compressed by
  anchoring the probability top first and letting the remaining outcomes compete
  for the second slot. Dashboard should display `shadow_selection_codes` and
  `execution_double_codes` from the artifact, not re-run this compression.
- `v4.2.0002+` does not apply per-segment full-cover caps or budget decisions.
  Later ticket/stake optimization owns final match selection, N choice, and
  whether a per-row full-cover candidate is actually funded.
- `skip_wait_late_refresh` is a temporary stop. It may become executable after
  a later valid refresh, so the UI should show the policy/refresh state instead
  of silently treating the audit recommendation as actionable.
- `execution_unlock_state=waiting_late_refresh` should be rendered as a red
  stop/wait state.
- `execution_unlock_state=unlocked_after_late_refresh` should be rendered as a
  green unlocked state, because this row was previously held for late refresh,
  has been repriced with execution SP, and is now executable.
- `execution_unlock_state=not_applicable` means the row was not held by the
  late-refresh gate.
- `execution_unlock_state=blocked_after_late_refresh` means the row was still
  not executable after refresh and should remain a stop/no-buy state.
- N-ticket replay and live staking must consume `shadow_selection_codes`, not
  `execution_recommended_codes`.
- `late_proxy_fullcap2` must not score full covers from stale source `sp_*` or
  `q_*`. When `execution_sp_repriced=1`, dashboard should show that the row was
  repriced and use `execution_sp_*`/`execution_q_*` for explanation.
- If `execution_sp_missing=1`, the row is not unlocked even if a global live SP
  refresh happened.
- Match detail should show both columns when they differ.
- Dashboard must not infer that a downgraded full-cover row is a strategy miss;
  it is an execution-layer cost decision.

Reference sample:

```text
docs/strategy/examples/v4_2_0000_execution_artifact_example.csv
```

## LLM And Script Boundary

The LLM may fill constrained semantic fields:

- team alias resolution;
- explicit evidence from supplied text;
- raw strength labels;
- draw semantics;
- cover-risk semantics;
- competition/team mismatch flags.

The LLM must not:

- choose final bets;
- estimate probabilities or SP;
- decide N;
- decide segment budget;
- translate ordinary strength directly into a Beidan handicap result;
- override hard stop, late refresh, or cost gates.

The script owns:

- Beidan handicap translation;
- probability/q/SP calculations;
- q stop, extreme SP, late refresh, and data-quality gates;
- final `decision_action`;
- `recommended_codes` and `buy_codes`;
- full-cover diagnostics;
- N selection, cost caps, and rolling segment policy.

## Dashboard Consumption Rules

Dashboard/API behavior:

- Load variants only from the active release manifest.
- Read shadow CSV rows only through `structured_shadow_dir`.
- Suppress undeclared `shadow_arm` artifacts and report a contract warning.
- Use one selected `decision_variant` across Issue Board, Match Detail, Main
  Strategy, and Settlement Review.
- If a requested variant is unavailable, fall back to the default variant and
  mark `selection_status=unavailable`.
- Treat missing required release artifacts as degraded state, not mock fallback.
- Render `shadow_chain_json` and `shadow_categories_json` read-only.

Dashboard must not infer or modify:

- `shadow_selection_codes`;
- `decision_action`;
- `buy_codes`;
- probabilities, q, SP, or confidence;
- active/shadow promotion status.

## Publication Flow

1. Generate research/backtest artifacts and report outside
   `results/structured_decision_chain_shadow`.
2. If the version is meant for dashboard display, generate a published CSV at:

   ```text
   results/structured_decision_chain_shadow/{issue}_{YYYYMMDD}_{shadow_arm}/structured_shadow_{issue}.csv
   ```

3. Add or update the release manifest:
   - declare `decision_variants[].variant_id`;
   - set `kind=shadow`;
   - set `source=structured_shadow_csv`;
   - set `artifact_key=structured_shadow_dir`;
   - set `version_id`;
   - fill `generated_at`, `artifact_scope`, `snapshot_timestamps`, and
     `validation.no_future_leakage`.
4. Validate release contract:

   ```bash
   python3 scripts/validate_strategy_release.py --allow-missing --json
   python3 -m py_compile src/decision_api/app.py scripts/validate_strategy_release.py
   pytest -q tests/decision_api/test_strategy_release.py tests/decision_api/test_strategy_release_contract.py
   ```

5. Smoke the dashboard/API when a live DB is available:

   ```bash
   python3 scripts/smoke_decision_dashboard_data_chain.py --issue current --json
   npm --prefix apps/decision-dashboard test -- --run
   npm --prefix apps/decision-dashboard run build
   ```

6. Request dashboard/codex review only after the artifact and manifest are both
   present.

## Promotion Gate

A shadow version can be considered for active promotion only if the strategy
report includes:

- fixed replay on 26071 and 26072, plus a wider historical/recent sample when
  available;
- action distribution: `buy`, `stop`, `wait_late_refresh`,
  `full_cover_or_skip`;
- coverage hit rate and primary hit rate;
- cost impact under the current segment cap;
- N-string ticket-level result, not only per-match hit rate;
- same-budget comparison against current active/shadow baseline;
- no-future-leakage statement for probability, q, SP, semantic inputs, and
  decision-chain snapshots;
- typical wins, typical misses, and known failure modes;
- rollback release id or explicit previous-active rollback note.

If any promotion decision needs human policy input, the Hermes card should be
blocked with the unresolved decision written in the card body/comment.

## Historical Issue Policy

Historical settled issues may be used for replay and review. They must not be
presented as live pre-match shadow decisions unless:

- the artifact was generated before the match/issue trading cutoff, or
- the release explicitly marks it as review-only/backtest-only.

Do not backfill a new shadow version into old issues to make historical display
look better. Use `artifact_mode=backtest` or `artifact_mode=review_only` for
post-settlement analysis artifacts.
