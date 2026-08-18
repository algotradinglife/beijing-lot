# Issue #254 — integrated data dictionary

The authoritative machine-readable dictionary is generated as
`data_dictionary.csv` in the external #254 package.  It is derived from the
actual SQLite `PRAGMA table_info` results and PyArrow schemas, rather than being
maintained as a second hand-written schema.

## Store boundaries

| Store | Purpose | Outcome availability |
|---|---|---|
| `control.sqlite` | Sources, issue-local slots, plays, 3/1/0 cells, observations, feature cells and snapshot manifests | Pre-event/control only |
| `features/m3_feature_cells.parquet` | Long analytical M×3 feature cells | Pre-event model input only |
| `labels/labels.sqlite` | Settlement result and winning SP | Post-outcome evaluation only |
| `labels/settlement_labels.parquet` | Analytical settlement labels | Post-outcome evaluation only |

## Primary analytical grain

`issue_code × match_idx × outcome_code × observation × feature_name`

`outcome_code` is restricted to `3/1/0`.  Namespace, source, causal grade,
observation semantics, availability mask, missing reason and provenance hash
travel with every feature cell.

## Identity boundary

The durable prototype key is the issue-local slot.  Provider fixture keys may
be retained as source provenance, but canonical real-world fixture, team and
competition identifiers stay null/unavailable unless a later issue establishes
a provenance-backed crosswalk.
