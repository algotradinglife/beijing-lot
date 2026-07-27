# BJ-ACTIVE-V333-PROMOTION-001 — promotion card

Status: `planned_native_contract_migration`

## Invariant

`active_v3.3.3` remains the only formal default. This migration changes only
artifact and consumer vocabulary; it does not change probability, selection,
protection, stop, Exact-N, budget, concentration, or ticket rules. A fixed
snapshot must have zero match-level selection differences before and after.

## Migration matrix

| Legacy operational contract | Native active contract | Consumer action |
| --- | --- | --- |
| `kind=shadow` for `active_v3.3.3` | `kind=active` | registry/API/UI label |
| `structured_shadow_csv` | `structured_active_csv` | active resolver only |
| `structured_shadow_dir` | `structured_active_dir` | new artifact writer and resolver |
| `shadow_selection_codes` | `selection_codes` | new operational readers |
| `shadow_arm=active_v3.3.3` | `decision_variant_id=active_v3.3.3`, `arm=active` | portfolio/PDF/postmatch |
| `shadow_v3.3.3` | legacy read-only alias to `active_v3.3.3` | audit reader only; never publish |
| `active_v3` | retired, non-selectable | no fallback |
| v4.2 shadow variants | unchanged | remain shadow/manual diagnostics |

## Promotion and rollback

New operational packages require a verified native active receipt, complete
issue membership, unique `match_idx`, and canonical `selection_codes`.
Legacy artifacts remain byte-immutable and may be shown only as legacy audit
data. Rollback points to the previous verified native active schema/release;
it never re-enables `active_v3` or makes a legacy shadow artifact publishable.

## Evidence required before merge

1. fixed-snapshot row-by-row zero-difference receipt;
2. semantic ticket-package parity receipt;
3. missing/duplicate/wrong-issue/invalid-receipt fail-closed tests;
4. legacy alias read-only test and v4.2 unchanged test;
5. exact-HEAD independent Engineering Validation.
