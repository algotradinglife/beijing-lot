# Issue #251 v2 handoff

- Direct PI R2 corrects the identity grain on PR #258: the deterministic key is
  `issue_slot_id`, while the refresh/reschedule-stable `fixture_entity_id`
  remains nullable.
- The external v2 package contains 808 issues, 215,193 issue slots, 236,666
  source traces, 215,193 plays and 645,579 outcome cells.
- Entity coverage is explicit: 63,948 exact cross-source fields; 581,925
  source-local-only fields; 61,144 conflicting fields; 2,981 unidentified
  fields. The ledger contains 30,572 entity-kind conflicts, 2,981 missing
  entity labels and 2,560 quarantined missing slots.
- Duplicate source slots are excluded from automatic outputs. Missing entities
  stay null. Alias validation is kind-aware and its observed intervals are
  diagnostic, not authoritative.
- Full package and evidence verification cover the identity chain, formulas,
  coverage reconciliation, alias semantics and outcome-field exclusion.
- Downstream #253 may use the issue-local slot and M×3 identity surfaces after
  EV, but may not manufacture real-world fixture or cross-source entity joins.
