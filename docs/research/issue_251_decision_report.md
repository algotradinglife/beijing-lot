# #251 identity-grain decision report — v2

## Decision summary

The data proves a stable identity for an **issue-local presentation slot**, not
for a real-world fixture across refreshes, replacements or reschedules.  The
accepted key is therefore:

`issue_slot_id = bjslot:<issue_code>:<match_idx padded to 3 digits>`

`fixture_entity_id` is a separate nullable field.  It stays null until a
source-stable event key or provenance-backed lineage is available.  Downstream
code must not reinterpret `issue_slot_id` as that entity key.

The complete deterministic identity chain for the current M×3 foundation is:

`issue_id → issue_slot_id → play_id(BJ_HANDICAP_3WAY) → outcome_cell_id(3/1/0)`

No outcome, winning-SP, payout or settlement-value field enters the mapping.

## Executed source evidence

The v2 rebuild produced:

| Identity surface | Rows |
|---|---:|
| Issues | 808 |
| Issue-local slots | 215,193 |
| Source traces | 236,666 |
| Play identities | 215,193 |
| Outcome-cell identities | 645,579 |
| Observed source-local temporal aliases | 6,785 |

The historical workbook still has 2,560 rows without a valid issue slot. They
are quarantined rather than fuzzy-matched.  Entity evidence is reported
separately across the 709,998 competition/home/away fields:

| Entity disposition | Fields |
|---|---:|
| Exact label agreement across at least two sources | 63,948 |
| Source-local only | 581,925 |
| Cross-source conflict | 61,144 |
| Missing / unidentified | 2,981 |

The 30,572 conflict-ledger records are entity-kind-specific instances. They do
not invalidate the exact issue-slot mapping, but their canonical entity IDs
remain null. Missing labels also remain null; no shared pseudo-identity such as
`team:unidentified` is created.

## Entity and alias policy

- A source-local entity key is deterministic and may support source-local
  modeling.
- A canonical cross-source entity key is populated only when at least two
  sources agree exactly on a nonblank normalized label for the same slot.
- Conflicting or missing fields are `UNRESOLVED_CONFLICT` or `UNIDENTIFIED` and
  retain source provenance.
- Observed first/last alias dates are diagnostic bounds with
  `OBSERVED_FIRST_LAST_NOT_AUTHORITATIVE`; they are not declared validity
  periods.
- Alias collision checks are keyed by
  `(alias_kind, source_id, source_alias)`, so a team and competition may share
  text without becoming the same entity.
- Fuzzy candidates remain review evidence and never become mappings.

## Exceptional cases

| Case | Disposition |
|---|---|
| Missing/invalid issue slot | Quarantine |
| Duplicate source rows for one issue slot | Quarantine all duplicates from automatic outputs |
| Rescheduled/replaced fixture | Keep slot evidence; `fixture_entity_id` remains unresolved without lineage |
| Postponed fixture | Manual review; no inferred replacement |
| Abandoned fixture | Preserve trace, exclude from inference |
| Missing entity label | Null entity ID plus `UNIDENTIFIED` ledger reason |
| Renamed entity | Provenance-backed kind-aware alias only |

## REQ-to-evidence

| Requirement | v2 evidence |
|---|---|
| REQ-ID01 | Separate `issue_slot_id` and nullable `fixture_entity_id`; report explicitly bounds refresh/reschedule claims |
| REQ-ID02 | Kind-aware observed alias table with provenance and diagnostic validity semantics |
| REQ-ID03 | Exact slot mapping and `reject_fuzzy_candidates()` manual-review boundary |
| REQ-ID04 | Explicit issue, slot, play and 3/1/0 cell tables plus formula/non-null/uniqueness validators |
| REQ-ID05 | Enforced duplicate quarantine and machine-readable exceptional-case policy/ledger |
| REQ-ID06 | Coverage separates slot, cross-source resolved, source-local, conflict, unidentified and unmatched counts by source/year/competition/causal grade |
| REQ-ID07 | Source trace retains source keys, issue slot, entity status, causal grade and rule version |
| REQ-ID08 | Adversarial tests cover null grain, duplicate quarantine, missing entities, cross-kind aliases, conflicting entities, remanifested coverage and outcome-column tampering |

## Machine-verification boundary

The full regenerable package is stored under the external data root and bound
by the committed evidence manifest. The verifier checks the complete identity
chain, formulas, non-null keys, duplicate quarantine, missing-entity routing,
kind-aware alias intervals, outcome-field exclusion, coverage/ledger counts and
manifest totals. Internal checksums establish package integrity; they are not
an external authenticity oracle for a mutable upstream SQLite source.

## Downstream permissions and limits

Allowed for #253 after EV:

- use `issue_slot_id` as the issue-local physical key;
- retain source-local entity keys for explicitly source-local features;
- preserve nullable canonical/entity fields and resolution status;
- build the M×3 play/outcome-cell foreign-key chain.

Not allowed:

- cross-refresh/reschedule joins on `issue_slot_id` as if it were a fixture
  entity;
- cross-source joins through unresolved, missing or source-local-only entities;
- silent fuzzy mapping or promotion of diagnostic alias intervals;
- use of `beidan_history_db` identity labels as inference features (it remains
  settlement-only).
