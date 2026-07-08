# active_v3.3.3 Decision-Chain Contract Handoff

Date: 2026-07-07

Owner: strategy

## Decision

`active_v3.3.3` is the formal live/default decision-chain variant exposed by
the API and dashboard.

`shadow_v3.3.3` is a legacy artifact alias only. Existing CSV artifacts that
still carry `shadow_arm=shadow_v3.3.3` remain readable through
`decision_variants[].legacy_aliases`, but API responses should display the
canonical `variant_id=active_v3.3.3`.

`active_v3` is retired. It may remain in manifests as a historical baseline,
but it is not selectable, not defaultable, and not a fallback when the formal
artifact is missing.

## Timeline

The generator is switched in this change to emit `shadow_arm=active_v3.3.3`.
Existing historical artifacts with `shadow_arm=shadow_v3.3.3` remain supported
as aliases indefinitely for replay compatibility. The next regenerated current
issue artifact should use `active_v3.3.3` directly.

## Manifest Sample

```json
{
  "variant_id": "active_v3.3.3",
  "version_id": "3.3.3",
  "kind": "shadow",
  "source": "structured_shadow_csv",
  "artifact_key": "structured_shadow_dir",
  "is_default": true,
  "selectable": true,
  "legacy_aliases": ["shadow_v3.3.3"],
  "planned_direct_shadow_arm": "active_v3.3.3",
  "readiness": {
    "artifact_required": true,
    "defaultable_when": "available",
    "missing_behavior": "artifact_missing",
    "late_refresh": "not_applicable",
    "missing_reason": "active_v3_3_3_artifact_missing_for_issue"
  }
}
```

## CSV Sample

New artifacts should emit the canonical arm:

```csv
match_idx,shadow_arm,shadow_version,shadow_selection_codes,shadow_primary,shadow_judgment,shadow_stop_flag
1,active_v3.3.3,llm_chain_bet_protect_stop_v3.3.3,3+1,3,胜为押，保平,0
```

Legacy artifacts remain accepted:

```csv
match_idx,shadow_arm,shadow_version,shadow_selection_codes,shadow_primary,shadow_judgment,shadow_stop_flag
1,shadow_v3.3.3,llm_chain_bet_protect_stop_v3.3.3_shadow,3+1,3,胜为押，保平,0
```

When read through the API, both samples should surface as `active_v3.3.3`.

## API Option Sample

```json
{
  "variant_id": "active_v3.3.3",
  "source_variant_id": "shadow_v3.3.3",
  "legacy_variant_id": "shadow_v3.3.3",
  "legacy_aliases": ["shadow_v3.3.3"],
  "kind": "shadow",
  "is_default": true,
  "selectable": true,
  "available": true,
  "readiness_status": "available"
}
```

If the user requests `decision_variant=shadow_v3.3.3`, the API should set:

```json
{
  "requested_variant_id": "shadow_v3.3.3",
  "requested_canonical_variant_id": "active_v3.3.3",
  "selected_variant_id": "active_v3.3.3",
  "selection_status": "ok"
}
```

## Missing Artifact Sample

If the formal structured CSV is missing or incomplete, do not fall back to
retired `active_v3`. The selected match variant should be an explicit no-buy
placeholder:

```json
{
  "variant_id": "active_v3.3.3",
  "available": false,
  "readiness_status": "unavailable",
  "degraded_reason": "active_v3_3_3_artifact_missing_for_issue",
  "recommendation": "正式版产物缺失",
  "selection_codes": [],
  "selection_type": "no-buy",
  "stop_flag": true,
  "execution_action": "skip_artifact_missing"
}
```

Frontend display guidance: show "正式版产物缺失" or equivalent degraded state.
Do not show `active_v3` as a substitute playable version.
