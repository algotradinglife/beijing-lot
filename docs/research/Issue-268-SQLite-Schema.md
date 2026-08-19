# Issue #268 SQLite schema

The versioned candidate database is a rebuildable normalized store over immutable external Nowscore/Titan evidence.

| Table | Grain / purpose |
|---|---|
| `inventory` | one row per frozen issue-slot; 808 issues / 213,263 fixtures |
| `acquisition_receipts` | one terminal receipt per logical HTTP source key |
| `issue_dispositions` | one terminal recovery disposition per recovered issue |
| `fixture_horizon_dispositions` | one row per recovered fixture × `initial/10h/1h` |
| `raw_quote_observations` | one parsed bookmaker quote triplet with payload identity |
| `duplicate_resolution_ledger` | one row per repeated quote key, exact or conflicting |
| `resolved_quotes` | one accepted quote per issue-slot × horizon × bookmaker |
| `matches` | outcome-free compatibility interface for #236 materialization |
| `market_snapshots` | resolved European 1X2 quote compatibility interface |
| `source_meta` / `metadata` | source role, contract and frozen input identities |

The deterministic quote key is `(issue_code, match_idx, snapshot_kind, bookmaker_id)`. Exact duplicates choose the observation tied to the lexically lowest payload SHA; conflicting quote values quarantine the entire key. Inserts are committed one issue at a time. The database is built to a temporary sibling, integrity-checked, input-stability-checked and then atomically renamed.
