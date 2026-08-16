# Domain Dictionary (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v2)

## outcome_code

Exactly `3` (home win), `1` (draw), `0` (away win) after explicit mapping.  Any legacy label (e.g. `3/1/0`, `主/和/客`, `W/D/L`) must be mapped by an explicit mapping table; unmapped values are rejected by the schema CHECK constraints (REQ-DS04).

## market_type

- `euro_1x2` — European 1X2 decimal odds
- `sp_1x2` — Beijing SP 1X2
- `asian_hcap` — Asian handicap (native line)

## snapshot_kind

- `initial`, `10h`, `1h`, `final` — workbook labels.  These are **labels**, not exact observation timestamps (REQ-DS03); a registry row using them carries clock_semantics `LABEL_RELATIVE` unless independently proven.
- `live` — prospective timestamped capture from the live collector (beidan_live.db snapshots / 500_bjdc live_market_sp_snapshots).  Carries clock_semantics `TIMESTAMPED_UTC`; the exact `observed_at_utc` is the collector fetch clock and must be bound to the raw payload receipt.

## admissible_use (REQ-DS01)

| class | meaning |
|---|---|
| STRICT_CAUSAL | observed before decision epoch with trusted clock |
| RETROSPECTIVE_PROXY | timestamp semantics insufficient; proxy only |
| SETTLEMENT_ONLY | after-event truth; never inference input |
| UNUSABLE | no clock / no identity / corrupt / not owned |

v2 rule: a source with `admissible_use = STRICT_CAUSAL` must carry `clock_semantics = TIMESTAMPED_UTC` and a resolvable `raw_sha256` receipt; prose without a hash receipt is never STRICT_CAUSAL.

## clock_semantics (REQ-DS03)

| value | meaning |
|---|---|
| TIMESTAMPED_UTC | parseable UTC timestamps |
| TIMESTAMPED_LOCAL_NO_TZ | local naive timestamps |
| LABEL_RELATIVE | initial/10h/1h/final labels |
| SCHEDULE_ONLY | kickoff schedule, no observation clock |
| SETTLEMENT_AFTER_EVENT | settlement time only |
| NO_CLOCK | no usable time |

## identity_status (REQ-DS02)

CANONICAL / ALIAS / AMBIGUOUS / UNIDENTIFIED — see the identity crosswalk contract.

## coverage_grade

A = full coverage with trusted clock; B = broad coverage with clock caveats; C = partial coverage or unproven clock; D = narrow or settlement-only; F = unusable.

## Mx3 triplet completeness (REQ-DS04)

SQLite cannot express a deferred cross-row CHECK.  Triplet completeness is enforced at the canonical append boundary (the write path inserts all three `outcome_code` rows for a bookmaker in one transaction and rejects incomplete input) and is independently verifiable via the `v_incomplete_triplets` view.  A trigger rejects more than three quotes per cell.

## Payout factor

The Beijing `0.65` payout coefficient is absent from all source, quote and probability tables; it exists only in downstream ticket settlement metadata (frozen contract rule, checked by the verifier).

## Alias validity windows (REQ-DS02)

`valid_from_utc` inclusive, `valid_to_utc` exclusive; `NULL` `valid_to_utc` means still active.  Overlapping windows for the same (source, key) are rejected by triggers.
