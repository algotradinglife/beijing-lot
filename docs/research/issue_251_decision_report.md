# #251 canonical identity decision report

## Candidate decision

`BJ-UNIFIED-CANONICAL-IDENTITY-001-v1` proposes the stable, outcome-unexposed fixture key:

`fixture_id = bjfi:<issue_code>:<match_idx padded to 3 digits>`

Only a populated numeric `(issue_code, match_idx)` can create that key.  Team/competition labels, kickoff times and fuzzy similarity are never used to create an automatic fixture match.  `issue_code` and `match_idx` are identity fields, not presentation-only fields, pending the PI acceptance checkpoint requested in #251.

## Executed source evidence

The read-only build used only identity columns from the accepted #250 lanes:

| Source | causal grade | valid source rows | quarantined rows | automatic fixture ambiguity |
|---|---:|---:|---:|---:|
| `beidan_xlsm_workbook` | `RETROSPECTIVE_PROXY` | 192,709 | 2,560 | 0 |
| `beidan_history_db` | `SETTLEMENT_ONLY` | 38,463 | 0 | 0 |
| `beidan_live_db` | `STRICT_CAUSAL` | 5,155 | 0 | 0 |

The evidence package contains 214,854 canonical fixture IDs and 236,327 source traces.  The historical workbook’s 2,560 missing-slot records (1.311% of 195,269 input rows) are explicitly quarantined.  Its 18,349 exact-slot rows with cross-source team/competition label differences (8.5402% of canonical fixtures) are `MANUAL_REVIEW` temporal-alias cases—not fuzzy fixture matches and not discarded fixtures.

The full regenerable source trace is external to Git at the path bound in `results/bj251_canonical_identity_evidence_v1/MANIFEST.json`; committed summaries bind its `SHA256SUMS.json` hash.  No outcome/result, payout, or winning-SP field was selected; the exact selected columns are frozen in `READ_BOUNDARY.json`.

## Required exceptional-case dispositions

| Case | Disposition |
|---|---|
| Rescheduled / postponed | `MANUAL_REVIEW`; provenance-bound schedule amendment/replacement required |
| Abandoned | `EXCLUDE_FROM_INFERENCE`; preserve trace only |
| Duplicate source row | `QUARANTINED` |
| Neutral venue | `CANONICAL_NO_TEAM_REWRITE` |
| Renamed entity | `MANUAL_REVIEW`; provenance-bound temporal alias only |

## REQ-to-evidence

| Requirement | Evidence |
|---|---|
| REQ-ID01 | `src/canonical_identity/mapping.py`; deterministic-key test; full `source_trace.csv` hash bound by evidence manifest |
| REQ-ID02 | `src/canonical_identity/aliases.py`, `tables/temporal_aliases.csv` (6,785 observed bounded aliases), temporal-alias adversarial tests |
| REQ-ID03 | `reject_fuzzy_candidates()` writes `MANUAL_REVIEW`, never an accepted mapping; test proves this boundary |
| REQ-ID04 | `validate_fixture_outcome_cells()` and tests reject duplicate/missing 3/1/0 cells; #234 DDL retains `UNIQUE(issue_code, match_idx)` |
| REQ-ID05 | `tables/exceptional_case_policy.csv` and machine-readable `ambiguity_ledger.csv` |
| REQ-ID06 | `tables/coverage.csv`, stratified by source/year/competition/causal grade, including an explicit unknown bucket for quarantined rows |
| REQ-ID07 | external full `tables/source_trace.csv` records source key, slot, canonical IDs, causal grade and rule version; checksum bound in committed manifest |
| REQ-ID08 | tests cover forged source trace, fuzzy candidate, duplicate cell, missing canonical slot, cross-source alias collision, and temporal alias overlap |

## PI decision inputs / known risks

1. Accept or revise `(issue_code, match_idx)` as the fixture key; this delivery treats it as canonical following #234 but requires #251’s explicit PI/user confirmation.
2. Choose the acceptable 1.311% unmatched threshold for `beidan_xlsm_workbook`; current policy quarantines all 2,560 rows.
3. Decide owner and SLA for the 18,349 temporal team/competition alias conflicts.  They do not alter fixture IDs, but their entity aliases cannot be automatically promoted.
4. Confirm the listed reschedule/postponed/abandoned policies before an ingestion branch writes canonical fixture attributes.
5. `beidan_history_db` remains `SETTLEMENT_ONLY`; its identity labels cannot be consumed as inference features.  The proxy workbook remains `RETROSPECTIVE_PROXY`.

## Review request

EV: fresh checkout, run `python -m pytest tests/test_bj251_canonical_identity.py -q`, rebuild with an external `BEIJING_LOT_DATA_ROOT`, then independently tamper the full trace, alias interval and evidence manifest.  Verify that any duplicate/missing 3/1/0 cells fail and no outcome-bearing fields enter `READ_BOUNDARY.json`.
