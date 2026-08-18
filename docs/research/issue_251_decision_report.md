# #251 identity-grain decision report — v3

## Decision summary

The data proves a stable identity for an **issue-local presentation slot**, not
for a real-world fixture or a cross-source team/competition entity. The accepted
physical key is:

`issue_slot_id = bjslot:<issue_code>:<match_idx padded to 3 digits>`

`fixture_entity_id`, `canonical_competition_id`, `canonical_home_team_id`, and
`canonical_away_team_id` therefore remain null in every automatic output. Exact
same-slot label agreement is diagnostic evidence only; it is not identity.

The deterministic M×3 chain is:

`issue_id → issue_slot_id → play_id(BJ_HANDICAP_3WAY) → outcome_cell_id(3/1/0)`

No outcome, winning-SP, payout, or settlement-value field enters the mapping.

## Executed source evidence

The v3 rebuild snapshots 239,226 source rows and emits:

| Identity surface | Rows |
|---|---:|
| Issues | 808 |
| Issue-local slots | 215,193 |
| Source traces | 236,666 |
| Play identities | 215,193 |
| Outcome-cell identities | 645,579 |
| Observed source-local alias intervals | 1,532 |

The historical workbook has 2,560 rows without a valid issue slot. They are
quarantined rather than parsed permissively or fuzzy-matched. Entity evidence is
reported across the 709,998 competition/home/away fields:

| Entity disposition | Fields |
|---|---:|
| Diagnostic same-slot exact label agreement | 63,948 |
| Reliable-source local identity | 561,056 |
| Settlement-label-only evidence | 84,817 |
| Cross-source conflict | 61,144 |
| Missing / unidentified | 2,981 |

The agreement count is almost unchanged from v2, but its interpretation is
corrected: it is not a promoted canonical entity. All 84,817 labels from
`beidan_history_db` remain `SETTLEMENT_LABEL_ONLY` and cannot become model
features or source-local entity keys. The 30,572 conflict-ledger rows are
entity-kind-specific instances; missing labels and conflicts keep canonical IDs
null.

## Entity, status, and alias policy

- Reliable sources may expose deterministic **source-local** entity keys.
- Settlement-only rows preserve raw labels and provenance but expose no
  source-local entity ID.
- Every trace carries `source_record_status`, `case_disposition`, entity role,
  causal grade, and rule version. Non-open statuses are quarantined where a
  source actually supplies status; status is not invented for sources that do
  not.
- Blank or reused `(source_id, source_key)` values are quarantined.
- Observed first/last alias dates are diagnostic bounds with
  `OBSERVED_FIRST_LAST_NOT_AUTHORITATIVE`; no operational alias resolver consumes
  them.
- Alias collision validation is keyed by
  `(alias_kind, source_id, source_alias)`, so a team and competition may share
  text without becoming the same entity.
- Fuzzy candidates remain manual-review evidence and never become mappings.

## Exceptional cases

| Case | Disposition |
|---|---|
| Missing/invalid issue slot | Quarantine |
| Blank/reused source key | Quarantine |
| Duplicate source rows for one issue slot | Quarantine all duplicates from automatic outputs |
| Rescheduled/replaced fixture | Keep slot evidence; real-world entity remains unresolved without lineage |
| Postponed fixture | Manual review; no inferred replacement |
| Abandoned fixture | Preserve trace, exclude from inference |
| Missing entity label | Null entity ID plus `UNIDENTIFIED` ledger reason |
| Renamed entity | Diagnostic, provenance-backed, kind-aware alias only |

## Machine-verification boundary

The full external package contains the exact `source_input_snapshot.csv` used by
the mapper. Its digest and the external checksum-set digest are anchored by the
committed evidence manifest. Verification reconstructs the issue, slot, play,
cell, trace, exception, alias, and coverage tables from that snapshot and
compares them exactly. It also enforces schema allowlists and prohibits outcome,
payout, result, or winning-SP fields outside the outcome-code cell identity.

Internal checksums establish package integrity; they are not an external
authenticity oracle for mutable upstream SQLite sources.

## Downstream permissions and limits

Allowed for #253 after EV:

- use `issue_slot_id` as the issue-local physical key;
- retain source-local entity keys only for explicitly reliable, source-local
  features;
- preserve nullable canonical/entity fields and resolution status;
- build the M×3 play/outcome-cell foreign-key chain.

Not allowed:

- cross-refresh/reschedule joins on `issue_slot_id` as if it were a fixture
  entity;
- cross-source joins through exact-label agreement, diagnostic alias windows,
  settlement labels, or source-local-only identities;
- fuzzy mapping or implicit homonym collapse;
- use of `beidan_history_db` identity labels as inference features.
