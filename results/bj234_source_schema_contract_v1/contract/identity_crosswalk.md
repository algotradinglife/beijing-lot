# Identity Crosswalk Contract

Canonical fixture identity is `(issue_code, match_idx)` — unique within the DDL.  Provider-specific match keys are aliases in `fixture_alias` (v2).  Legacy identity statistics are NULL-aware:

| database.table | primitive key | null_key_rows | duplicate_excess | verdict |
|---|---|---|---|---|
| beidan_xlsm.sqlite.match_features | issue|match_idx | 2560 | 0 | NULL_KEY_DEFECT |
| beidan_xlsm.sqlite.matches | issue|match_idx | 2560 | 0 | NULL_KEY_DEFECT |
| beidan_xlsm.sqlite.outcome_features | issue|match_idx|outcome_code | 7680 | 0 | NULL_KEY_DEFECT |
| beidan_features.db.matches | match_id | 0 | 3 | DUPLICATE_DEFECT |
| beidan_history.db.historical_matches | issue|match_idx | 0 | 0 | UNIQUE |
| beidan_live.db.matches | issue|match_idx | 0 | 0 | UNIQUE |
| 500_bjdc.sqlite.matches | issue|match_idx | 0 | 0 | UNIQUE |
| beidan_modeling_plus_2026.sqlite.match_features | issue|match_idx | 2560 | 0 | NULL_KEY_DEFECT |
| beidan_modeling_plus_2026.sqlite.matches | issue|match_idx | 2560 | 0 | NULL_KEY_DEFECT |
| beidan_modeling_plus_2026.sqlite.outcome_features | issue|match_idx|outcome_code | 7680 | 0 | NULL_KEY_DEFECT |
| beidan_nowscore_2026.sqlite.match_features | issue|match_idx | 0 | 0 | UNIQUE |
| beidan_nowscore_2026.sqlite.matches | issue|match_idx | 0 | 0 | UNIQUE |
| beidan_nowscore_2026.sqlite.outcome_features | issue|match_idx|outcome_code | 0 | 0 | UNIQUE |

NULL-key rows are UNIDENTIFIED, never duplicates.  A `DUPLICATE_DEFECT` verdict is only issued when `duplicate_excess > 0` over non-null keys.
