"""Identity crosswalk contract (REQ-DS02).

Maps every existing database's identity semantics onto the canonical
``fixture(issue_code, match_idx)`` identity.  The crosswalk is a *contract*
stating how source keys bind to canonical fixtures — never a silent fuzzy
match.  It is data-driven where the source DBs are reachable (read-only) and
declarative for the identity rule itself.

Canonical rule (frozen):
  fixture_id = deterministic hash of (issue_code, match_idx), unique within
  that pair (see contract.fixture_id).  Source keys arrive via team_alias /
  competition_alias / fixture.source_match_key; identity_status =
  CANONICAL | ALIAS_RESOLVED | UNRESOLVED.

Crosswalk rows per existing database:
  db, table, source_key_columns, canonical_binding, resolvable, note
"""
from __future__ import annotations

from . import contract
from .profiler import db_paths, resolve_data_root

CROSSWALK: list[dict] = [
    {
        "db": "beidan_live.db",
        "table": "matches",
        "source_key_columns": ["issue", "match_idx"],
        "canonical_binding": "issue_code=issue, match_idx=match_idx → fixture_id",
        "resolvable": "YES",
        "note": "issue x match_idx UNIQUE verified (dup=0); match_id kept as "
                "source_match_key; kickoff_ts is Beijing local, bind tz Asia/Shanghai "
                "then convert to UTC.",
    },
    {
        "db": "beidan_live.db",
        "table": "settlements",
        "source_key_columns": ["issue", "match_idx"],
        "canonical_binding": "settlement.fixture_id = canonical fixture",
        "resolvable": "YES",
        "note": "settled_ts present; settlement namespace only.",
    },
    {
        "db": "beidan_history.db",
        "table": "historical_matches",
        "source_key_columns": ["issue", "match_idx"],
        "canonical_binding": "issue_code=issue, match_idx=match_idx → fixture_id",
        "resolvable": "YES",
        "note": "UNIQUE verified (dup=0); no settled timestamp — SETTLEMENT_ONLY.",
    },
    {
        "db": "beidan_features.db",
        "table": "matches",
        "source_key_columns": ["issue", "match_idx"],
        "canonical_binding": "issue_code=issue, match_idx=match_idx → fixture_id",
        "resolvable": "PARTIAL",
        "note": "table has NO match_idx column — identity must come via "
                "kickoff/home/away join into canonical fixtures; rows without "
                "resolution are UNRESOLVED. kickoff format is mixed.",
    },
    {
        "db": "beidan_xlsm.sqlite",
        "table": "matches",
        "source_key_columns": ["issue", "match_idx"],
        "canonical_binding": "issue_code=issue, match_idx=match_idx → fixture_id",
        "resolvable": "PARTIAL",
        "note": "2560 rows with NULL issue/match_idx excluded by canonical "
                "NOT NULL + UNIQUE constraints; 1 duplicate pair found in raw "
                "probe (issue NULL group). kickoff has 6 '1899-12-30' garbage rows.",
    },
    {
        "db": "beidan_xlsm.sqlite",
        "table": "official_500_settlements",
        "source_key_columns": ["issue", "match_idx"],
        "canonical_binding": "settlement.fixture_id = canonical fixture",
        "resolvable": "YES",
        "note": "settlement namespace; fetched 2026-06-26, end_time 2013-2017 — "
                "SETTLEMENT_ONLY evidence.",
    },
]


def identity_crosswalk_rows() -> list[dict]:
    return CROSSWALK


def canonical_identity_rule() -> dict:
    return {
        "rule": "fixture_id = fix_{issue_code}_{match_idx}_{sha256(issue:match)[:16]}",
        "unique_within": "issue_code x match_idx",
        "alias_requirement": "every source key binds via alias tables; "
                             "silent fuzzy matching prohibited",
        "identity_status": ["CANONICAL", "ALIAS_RESOLVED", "UNRESOLVED"],
        "example": contract.fixture_id("25041", 1),
    }
