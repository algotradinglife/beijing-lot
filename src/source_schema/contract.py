"""BJ #234 — canonical source registry / identity / temporal store contract.

BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1 (PI-user design freeze, 2026-08-16).

This module is the single source of truth for the frozen data contract:
table inventory, column semantics, domain dictionaries, admissible-use
classes and the canonical fixture identity rule.  The SQL DDL, PyArrow
schemas, domain dictionary CSV and machine-readable contract JSON are all
*rendered* from this module so they cannot drift apart.

Design rules (frozen):
- Timestamps are timezone-aware UTC, stored canonically as
  ISO-8601 ``YYYY-MM-DDTHH:MM:SS[.ffffff]Z`` in SQLite TEXT columns and as
  ``timestamp[us, tz=UTC]`` in PyArrow.
- ``outcome_code`` domain is exactly ``{"3", "1", "0"}`` after explicit
  mapping (home win / draw / away win on the *native handicap line*).
- Probability triplets stay long-form scalars keyed by match/outcome.
- The Beijing ``0.65`` coefficient appears in NO source, quote or
  probability table; it exists only in downstream ticket settlement
  metadata (out of scope here).
- Canonical fixture identity: ``fixture_id`` unique within
  ``issue_code x match_idx``; every source key arrives via an alias table,
  never by silent fuzzy match.
- Physically separate namespaces: inference (market_observation /
  market_quote / probability_estimate), proxy (recovered archives) and
  settlement (settlement table) are distinguishable by table and by
  ``admissible_use`` / ``snapshot_kind`` / partition layout.
"""

from __future__ import annotations

from enum import Enum

CONTRACT_VERSION = "BJ-UNIFIED-DATA-SOURCE-SCHEMA-001"
CONTRACT_REVISION = "v1"
FROZEN_AT_UTC = "2026-08-16T00:00:00Z"

# Outcome code domain after explicit mapping.  3=home (主胜), 1=draw (平),
# 0=away (客胜) — evaluated on the fixture's native handicap line.
OUTCOME_CODES = ("3", "1", "0")

# Timestamp storage canonical form (SQLite TEXT):
#   ISO-8601 with explicit Z suffix, microsecond precision allowed.
TS_FORMAT_SQLITE = "%Y-%m-%dT%H:%M:%SZ"
TS_FORMAT_SQLITE_US = "%Y-%m-%dT%H:%M:%S.%fZ"


class AdmissibleUse(str, Enum):
    """Causal admissibility class assigned to every registered source.

    STRICT_CAUSAL       — observation timestamp is native/proven; safe as
                          decision-epoch inference input.
    RETROSPECTIVE_PROXY — no exact decision-epoch timestamp; usable only as
                          an explicitly-labelled proxy (never strict truth).
    SETTLEMENT_ONLY     — outcome/settlement evidence only; prohibited as
                          pre-event input.
    UNUSABLE            — clock provenance or identity cannot be established.
    """

    STRICT_CAUSAL = "STRICT_CAUSAL"
    RETROSPECTIVE_PROXY = "RETROSPECTIVE_PROXY"
    SETTLEMENT_ONLY = "SETTLEMENT_ONLY"
    UNUSABLE = "UNUSABLE"


class ClockSemantics(str, Enum):
    """What the source clock actually proves."""

    NATIVE_PROVEN = "NATIVE_PROVEN"          # provider publishes a timestamp
    TRUSTED_FETCH = "TRUSTED_FETCH"          # our fetch clock, trusted NTP
    LABELED_RELATIVE = "LABELED_RELATIVE"    # initial/10h/1h/final labels only
    FILE_MTIME = "FILE_MTIME"                # file modification time (proxy)
    ABSENT = "ABSENT"                        # no clock at all


class SnapshotKind(str, Enum):
    """Kind of a market_observation row."""

    RAW_CAPTURE = "RAW_CAPTURE"              # raw payload preserved verbatim
    RECOVERED_ARCHIVE = "RECOVERED_ARCHIVE"  # recovered workbook/archive row
    PROXY_LABEL = "PROXY_LABEL"              # labelled snapshot, no exact clock
    SETTLEMENT_CROSSCHECK = "SETTLEMENT_CROSSCHECK"


class QuoteStatus(str, Enum):
    VALID = "VALID"
    SUSPENDED = "SUSPENDED"
    INVALID = "INVALID"


class BatchStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PARSED = "PARSED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class IdentityStatus(str, Enum):
    CANONICAL = "CANONICAL"
    ALIAS_RESOLVED = "ALIAS_RESOLVED"
    UNRESOLVED = "UNRESOLVED"


# ---------------------------------------------------------------------------
# Source families (contract section "Source families to register and rank")
# ---------------------------------------------------------------------------
SOURCE_FAMILIES = {
    "F1_BJ_FIRST_PARTY": {
        "name": "Beijing first-party current fixtures / native handicap / instant SP",
        "note": "Beijing Sports Lottery official interface; prospective capture with "
                "raw payload + trusted fetch clock.",
    },
    "F2_INTERNAL_ARCHIVE": {
        "name": "Existing internal historical workbooks/databases + recoverable raw archives",
        "note": "Historical causality only when source clock provenance demonstrated.",
    },
    "F3_EU_TIMESTAMPED": {
        "name": "Timestamped European bookmaker feeds",
        "note": "The Odds API historical snapshots (2020+, paid) and equivalent licensed "
                "providers; verify league/event coverage, timestamp, bookmaker, market.",
    },
    "F4_FOOTBALL_DATA_CSV": {
        "name": "Football-Data historical CSV",
        "note": "Results/open-or-close odds proxy only where timestamp semantics "
                "insufficient; never decision-epoch truth.",
    },
    "F5_RESULTS_POWER": {
        "name": "Internal match results + accepted public football data",
        "note": "Causal team/league power features; explicit competition coverage and "
                "identity mapping required.",
    },
}


# ---------------------------------------------------------------------------
# Canonical table inventory (contract "Canonical physical design" section).
# Each entry: table name, physical namespace (capture / inference / settlement),
# and ordered columns: (name, sqlite_type, pyarrow_type, nullable, constraints).
# pyarrow_type strings are parsed by pyarrow; sqlite_type is the DDL column type.
# ---------------------------------------------------------------------------
# constraint codes: PK, UNIQUE, FK:table.column, CHECK:expr, NOTNULL
def _t(name, namespace, cols, pk=None, uniques=None, fks=None, checks=None):
    return {
        "name": name,
        "namespace": namespace,
        "columns": cols,
        "pk": pk or [],
        "uniques": uniques or [],
        "fks": fks or [],
        "checks": checks or [],
    }


def table_specs() -> list[dict]:
    """Canonical table specifications (frozen)."""
    return [
        _t(
            "source_registry", "capture",
            [
                ("source_id", "TEXT", "string", False, ["PK"]),
                ("provider", "TEXT", "string", False, []),
                ("endpoint", "TEXT", "string", True, []),
                ("acquisition_method", "TEXT", "string", False, []),
                ("terms_status", "TEXT", "string", False, []),
                ("timezone", "TEXT", "string", False, []),
                ("clock_semantics", "TEXT", "string", False, []),
                ("cadence_seconds", "INTEGER", "int64", True, []),
                ("parser_version", "TEXT", "string", False, []),
                ("admissible_use", "TEXT", "string", False, []),
                ("first_usable_at_utc", "TEXT", "timestamp[us, tz=UTC]", True, []),
                ("last_usable_at_utc", "TEXT", "timestamp[us, tz=UTC]", True, []),
                ("raw_content_sha256", "TEXT", "string", True, []),
                ("coverage_grade", "TEXT", "string", False, []),
                ("notes", "TEXT", "string", True, []),
            ],
            pk=["source_id"],
            checks=["admissible_use IN ('STRICT_CAUSAL','RETROSPECTIVE_PROXY','SETTLEMENT_ONLY','UNUSABLE')",
                    "clock_semantics IN ('NATIVE_PROVEN','TRUSTED_FETCH','LABELED_RELATIVE','FILE_MTIME','ABSENT')"],
        ),
        _t(
            "ingestion_batch", "capture",
            [
                ("batch_id", "TEXT", "string", False, ["PK"]),
                ("source_id", "TEXT", "string", False, []),
                ("requested_at_utc", "TEXT", "timestamp[us, tz=UTC]", False, []),
                ("received_at_utc", "TEXT", "timestamp[us, tz=UTC]", False, []),
                ("raw_uri", "TEXT", "string", True, []),
                ("raw_sha256", "TEXT", "string", False, []),
                ("parser_version", "TEXT", "string", False, []),
                ("row_count", "INTEGER", "int64", False, []),
                ("status", "TEXT", "string", False, []),
            ],
            pk=["batch_id"],
            fks=[("source_id", "source_registry", "source_id")],
            checks=["status IN ('RECEIVED','PARSED','FAILED','REJECTED')"],
        ),
        _t(
            "bookmaker", "capture",
            [
                ("bookmaker_id", "TEXT", "string", False, ["PK"]),
                ("canonical_name", "TEXT", "string", False, []),
                ("source_id", "TEXT", "string", False, []),
            ],
            pk=["bookmaker_id"],
            fks=[("source_id", "source_registry", "source_id")],
        ),
        _t(
            "team", "capture",
            [
                ("team_id", "TEXT", "string", False, ["PK"]),
                ("canonical_name", "TEXT", "string", False, []),
            ],
            pk=["team_id"],
        ),
        _t(
            "team_alias", "capture",
            [
                ("alias_id", "TEXT", "string", False, ["PK"]),
                ("source_id", "TEXT", "string", False, []),
                ("source_team_key", "TEXT", "string", False, []),
                ("team_id", "TEXT", "string", False, []),
                ("valid_from_utc", "TEXT", "timestamp[us, tz=UTC]", False, []),
                ("valid_to_utc", "TEXT", "timestamp[us, tz=UTC]", True, []),
            ],
            pk=["alias_id"],
            fks=[("source_id", "source_registry", "source_id"),
                 ("team_id", "team", "team_id")],
            uniques=[("source_id", "source_team_key", "valid_from_utc")],
        ),
        _t(
            "competition", "capture",
            [
                ("competition_id", "TEXT", "string", False, ["PK"]),
                ("canonical_name", "TEXT", "string", False, []),
            ],
            pk=["competition_id"],
        ),
        _t(
            "competition_alias", "capture",
            [
                ("alias_id", "TEXT", "string", False, ["PK"]),
                ("source_id", "TEXT", "string", False, []),
                ("source_competition_key", "TEXT", "string", False, []),
                ("competition_id", "TEXT", "string", False, []),
                ("valid_from_utc", "TEXT", "timestamp[us, tz=UTC]", False, []),
                ("valid_to_utc", "TEXT", "timestamp[us, tz=UTC]", True, []),
            ],
            pk=["alias_id"],
            fks=[("source_id", "source_registry", "source_id"),
                 ("competition_id", "competition", "competition_id")],
            uniques=[("source_id", "source_competition_key", "valid_from_utc")],
        ),
        _t(
            "fixture", "capture",
            [
                ("fixture_id", "TEXT", "string", False, ["PK"]),
                ("issue_code", "TEXT", "string", False, []),
                ("match_idx", "INTEGER", "int64", False, []),
                ("source_match_key", "TEXT", "string", True, []),
                ("competition_id", "TEXT", "string", True, []),
                ("home_team_id", "TEXT", "string", True, []),
                ("away_team_id", "TEXT", "string", True, []),
                ("kickoff_at_utc", "TEXT", "timestamp[us, tz=UTC]", False, []),
                ("native_handicap_line", "REAL", "float64", True, []),
                ("sale_cutoff_at_utc", "TEXT", "timestamp[us, tz=UTC]", True, []),
                ("identity_status", "TEXT", "string", False, []),
            ],
            pk=["fixture_id"],
            uniques=[("issue_code", "match_idx")],
            fks=[("competition_id", "competition", "competition_id"),
                 ("home_team_id", "team", "team_id"),
                 ("away_team_id", "team", "team_id")],
            checks=["match_idx >= 1",
                    "identity_status IN ('CANONICAL','ALIAS_RESOLVED','UNRESOLVED')"],
        ),
        _t(
            "decision_epoch", "capture",
            [
                ("decision_epoch_id", "TEXT", "string", False, ["PK"]),
                ("issue_code", "TEXT", "string", False, []),
                ("decision_at_utc", "TEXT", "timestamp[us, tz=UTC]", False, []),
                ("rule_id", "TEXT", "string", False, []),
                ("roster_version", "TEXT", "string", True, []),
            ],
            pk=["decision_epoch_id"],
        ),
        _t(
            "market_observation", "inference",
            [
                ("observation_id", "TEXT", "string", False, ["PK"]),
                ("fixture_id", "TEXT", "string", False, []),
                ("source_id", "TEXT", "string", False, []),
                ("market_type", "TEXT", "string", False, []),
                ("handicap_line", "REAL", "float64", True, []),
                ("observed_at_utc", "TEXT", "timestamp[us, tz=UTC]", False, []),
                ("received_at_utc", "TEXT", "timestamp[us, tz=UTC]", False, []),
                ("snapshot_kind", "TEXT", "string", False, []),
                ("batch_id", "TEXT", "string", True, []),
            ],
            pk=["observation_id"],
            fks=[("fixture_id", "fixture", "fixture_id"),
                 ("source_id", "source_registry", "source_id"),
                 ("batch_id", "ingestion_batch", "batch_id")],
            checks=["snapshot_kind IN ('RAW_CAPTURE','RECOVERED_ARCHIVE','PROXY_LABEL','SETTLEMENT_CROSSCHECK')"],
        ),
        _t(
            "market_quote", "inference",
            [
                ("quote_id", "TEXT", "string", False, ["PK"]),
                ("observation_id", "TEXT", "string", False, []),
                ("bookmaker_id", "TEXT", "string", True, []),
                ("outcome_code", "TEXT", "string", False, []),
                ("decimal_odds", "REAL", "float64", False, []),
                ("quote_status", "TEXT", "string", False, []),
            ],
            pk=["quote_id"],
            fks=[("observation_id", "market_observation", "observation_id"),
                 ("bookmaker_id", "bookmaker", "bookmaker_id")],
            uniques=[("observation_id", "outcome_code")],
            checks=["outcome_code IN ('3','1','0')",
                    "decimal_odds > 1.0",
                    "quote_status IN ('VALID','SUSPENDED','INVALID')"],
        ),
        _t(
            "probability_estimate", "inference",
            [
                ("estimate_id", "TEXT", "string", False, ["PK"]),
                ("fixture_id", "TEXT", "string", False, []),
                ("decision_epoch_id", "TEXT", "string", False, []),
                ("estimator_id", "TEXT", "string", False, []),
                ("target_market", "TEXT", "string", False, []),
                ("handicap_line", "REAL", "float64", True, []),
                ("outcome_code", "TEXT", "string", False, []),
                ("probability", "REAL", "float64", False, []),
                ("uncertainty", "REAL", "float64", True, []),
                ("observed_at_utc", "TEXT", "timestamp[us, tz=UTC]", False, []),
                ("calibration_version", "TEXT", "string", False, []),
                ("provenance_hash", "TEXT", "string", False, []),
            ],
            pk=["estimate_id"],
            fks=[("fixture_id", "fixture", "fixture_id"),
                 ("decision_epoch_id", "decision_epoch", "decision_epoch_id")],
            uniques=[("fixture_id", "decision_epoch_id", "estimator_id",
                      "target_market", "handicap_line", "outcome_code")],
            checks=["outcome_code IN ('3','1','0')",
                    "probability >= 0.0 AND probability <= 1.0",
                    "uncertainty IS NULL OR uncertainty >= 0.0"],
        ),
        # Physically separate settlement namespace (REQ-DS05).
        _t(
            "settlement", "settlement",
            [
                ("settlement_id", "TEXT", "string", False, ["PK"]),
                ("fixture_id", "TEXT", "string", False, []),
                ("result_code", "TEXT", "string", False, []),
                ("winning_sp", "REAL", "float64", True, []),
                ("settled_at_utc", "TEXT", "timestamp[us, tz=UTC]", False, []),
                ("source_id", "TEXT", "string", False, []),
            ],
            pk=["settlement_id"],
            fks=[("fixture_id", "fixture", "fixture_id"),
                 ("source_id", "source_registry", "source_id")],
            uniques=[("fixture_id", "source_id")],
            checks=["result_code IN ('3','1','0')"],
        ),
    ]


def namespace_of(table: str) -> str:
    for spec in table_specs():
        if spec["name"] == table:
            return spec["namespace"]
    raise KeyError(table)


# Canonical fixture_id derivation: deterministic, collision-free within
# (issue_code, match_idx).  Human-readable prefix + SHA-256 tail keeps it
# debuggable and unique without a global sequence dependency.
def fixture_id(issue_code: str, match_idx: int) -> str:
    import hashlib

    if not isinstance(match_idx, int) or match_idx < 1:
        raise ValueError(f"match_idx must be int >= 1, got {match_idx!r}")
    raw = f"{issue_code}:{match_idx}".encode("utf-8")
    return f"fix_{issue_code}_{match_idx}_{hashlib.sha256(raw).hexdigest()[:16]}"
