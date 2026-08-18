# Identity Crosswalk Contract (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1)

## Canonical identity

A fixture's canonical identity is `(issue_code, match_idx)`.  The Beijing issue (e.g. `25042`) plus the slot index inside that issue uniquely names one match.  The `fixture` table enforces:

- `PRIMARY KEY (fixture_id)`,
- `UNIQUE (issue_code, match_idx)`,
- `identity_status IN ('CANONICAL','ALIAS','AMBIGUOUS','UNIDENTIFIED')`.

## Alias tables

Source-specific keys are aliases, never primary keys.  `team_alias` and `competition_alias` map a source key to a canonical id:

- `team_alias(source_id, source_team_key, team_id, valid_from_utc, valid_to_utc)`
- `competition_alias(source_id, source_competition_key, competition_id, valid_from_utc, valid_to_utc)`

Resolution rule:

> An alias row is active when valid_from_utc <= asof <= COALESCE(valid_to_utc, '9999-12-31T23:59:59Z').  Overlapping active windows for the same (source_id, source_team_key) are forbidden by a partial unique index.

## Identity status semantics

| status | meaning |
|---|---|
| CANONICAL | the fixture row is the canonical identity |
| ALIAS | resolved from a source key through an alias row |
| AMBIGUOUS | source key maps to multiple canonical fixtures (blocked) |
| UNIDENTIFIED | source key has no alias row (never silently matched) |

## Decision epoch

`decision_epoch(decision_epoch_id, issue_code, decision_at_utc, rule_id, roster_version)` binds one frozen decision time per issue.  A market observation is causally admissible for a fixture only when `observed_at_utc <= decision_at_utc AND observed_at_utc < kickoff_at_utc` with the exact epoch looked up by issue — never inferred from `initial/10h/1h/final` labels (REQ-DS03).

## Non-interchangeability (REQ-DS03)

| column | meaning | never interchangeable with |
|---|---|---|
| observed_at_utc | when the market state was observed | received_at_utc, decision_at_utc |
| received_at_utc | when our pipeline captured it | observed_at_utc |
| decision_at_utc | frozen decision epoch | any observation label |
| kickoff_at_utc | scheduled match start | decision_at_utc |
| settled_at_utc | settlement time (after event) | any pre-event time |

## Schema-level enforcement (REQ-DS04)

```sql
-- partial unique index on active alias windows (SQLite)
CREATE UNIQUE INDEX ux_team_alias_active ON team_alias(
    source_id, source_team_key
) WHERE valid_to_utc IS NULL;

-- canonical fixture identity
CREATE UNIQUE INDEX ux_fixture_issue_idx ON fixture(issue_code, match_idx);
```
