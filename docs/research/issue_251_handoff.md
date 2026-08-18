# Issue #251 v3 handoff

- Direct PI R3 keeps the deterministic physical key at `issue_slot_id`; every
  refresh/reschedule-stable fixture and cross-source canonical entity ID stays
  null.
- The external v3 package snapshots 239,226 source rows and emits 808 issues,
  215,193 issue slots, 236,666 source traces, 215,193 plays, and 645,579 cells.
- The 63,948 exact same-slot label agreements are diagnostic, not canonical.
  Reliable-source local identity covers 561,056 fields; 84,817 settlement-only
  fields expose no entity key; 61,144 fields conflict and 2,981 are missing.
- Blank/reused source keys, invalid slots, duplicate source slots, and observed
  non-open statuses are quarantined. Diagnostic alias intervals have no
  operational resolver.
- The exact source-input snapshot is included externally. Full verification
  reconstructs every decision-facing table and rejects schema, identity,
  coverage, status, alias, or prohibited-outcome tampering.
- #253 may use the issue-local slot and M×3 identity surfaces after EV, but may
  not manufacture real-world fixture or cross-source entity joins.
