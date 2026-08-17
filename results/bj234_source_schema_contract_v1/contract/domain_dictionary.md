# Domain Dictionary (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1)

## outcome_code

Exactly `3` (home win), `1` (draw), `0` (away win) after explicit mapping.  Any legacy label (e.g. `3/1/0`, `主/和/客`, `W/D/L`) must be mapped by an explicit mapping table; unmapped values are rejected by the schema CHECK constraints (REQ-DS04).

## market_type

- `euro_1x2` — European 1X2 decimal odds
- `sp_1x2` — Beijing SP 1X2
- `asian_hcap` — Asian handicap (native line)

## snapshot_kind

- `initial`, `10h`, `1h`, `final` — workbook labels.  These are **labels**, not exact observation timestamps (REQ-DS03); a registry row using them carries clock_semantics `LABEL_RELATIVE` unless independently proven.

## admissible_use (REQ-DS01)

| class | meaning |
|---|---|
| STRICT_CAUSAL | observed before decision epoch with trusted clock |
| RETROSPECTIVE_PROXY | timestamp semantics insufficient; proxy only |
| SETTLEMENT_ONLY | after-event truth; never inference input |
| UNUSABLE | no clock / no identity / corrupt |

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

## Payout factor

The Beijing `0.65` payout coefficient is absent from all source, quote and probability tables; it exists only in downstream ticket settlement metadata (frozen contract rule, checked by the builder).
