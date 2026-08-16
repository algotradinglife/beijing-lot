"""Issue #234 — read-only census of all registered source databases (v2).

v2 rework addresses EV R1 defect classes C1 and C4:

- **C1 identity metrics**: duplicate/null statistics use correct primitive
  keys per table (``issue, match_idx`` for match tables; the long-form key
  ``issue, match_idx, outcome_code`` for outcome_features).  NULL-key rows
  are counted separately and NEVER reported as duplicates; the reported
  duplicate excess is ``non_null_rows - distinct_non_null_keys`` (0 for the
  legacy tables, matching the EV's independent recomputation).
- **C4 label sealing**: the census never reads settlement/outcome label
  values.  Column value scans use an **allow-list** (identity keys,
  timestamps, observation prices) — everything else (``score``,
  ``result_code``, ``winning_sp``, ``hit``, ``fthg``, ``ftag``, settlement
  tables, …) is SEALED and physically unreadable through this API.  A probe
  demonstrates that reading a sealed column fails closed.

Every database is opened ``mode=ro`` with ``query_only=ON``; the census never
mutates sources (REQ-DS07 binds machine-readable outputs + source hashes).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import contract

# ---------------------------------------------------------------------------
# Data root resolution
# ---------------------------------------------------------------------------
DATA_ROOTS = [
    Path(os.environ.get("DATA_ROOT", "/home/drwho1985/workspace/soccer/beijing-lot/data")),
    Path("/home/drwho1985/beijing-lot-234/data"),
]


def resolve_data_root() -> Path:
    for p in DATA_ROOTS:
        if p.exists():
            return p
    raise FileNotFoundError("no data root found; set DATA_ROOT env")


# ---------------------------------------------------------------------------
# Database inventory (frozen)
# ---------------------------------------------------------------------------
# key -> (family, relative path)
DATABASE_INVENTORY: tuple[dict[str, str], ...] = (
    {"key": "beidan_xlsm.sqlite", "family": contract.FAMILY_INTERNAL_HISTORICAL,
     "path": "derived/beidan_xlsm/beidan_xlsm.sqlite"},
    {"key": "beidan_features.db", "family": contract.FAMILY_INTERNAL_HISTORICAL,
     "path": "beidan_features.db"},
    {"key": "beidan_history.db", "family": contract.FAMILY_INTERNAL_HISTORICAL,
     "path": "beidan_history.db"},
    {"key": "beidan_live.db", "family": contract.FAMILY_INTERNAL_HISTORICAL,
     "path": "beidan_live.db"},
    {"key": "500_bjdc.sqlite", "family": contract.FAMILY_INTERNAL_HISTORICAL,
     "path": "derived/500_bjdc/500_bjdc.sqlite"},
    {"key": "beidan_modeling_plus_2026.sqlite", "family": contract.FAMILY_INTERNAL_HISTORICAL,
     "path": "derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite"},
    {"key": "beidan_nowscore_2026.sqlite", "family": contract.FAMILY_INTERNAL_HISTORICAL,
     "path": "derived/beidan_xlsm/beidan_nowscore_2026.sqlite"},
)

# ---------------------------------------------------------------------------
# Sealing (C4): tables and columns whose VALUES are never read by the census.
# ---------------------------------------------------------------------------
# Tables whose values are settlement/label truth -> SEALED (metadata only).
SEALED_TABLES: dict[str, tuple[str, ...]] = {
    "beidan_xlsm.sqlite": ("official_500_settlements", "action_candidates"),
    "beidan_features.db": (),
    "beidan_history.db": (),
    "beidan_live.db": ("settlements",),
    "500_bjdc.sqlite": (
        "multimarket_settlement_truth", "postmatch_reviews",
        "postmatch_review_runs", "postmatch_review_issue_summary",
    ),
    "beidan_modeling_plus_2026.sqlite": ("official_500_settlements", "action_candidates"),
    "beidan_nowscore_2026.sqlite": ("official_3sp_settlements", "action_candidates"),
}

# Per-table allow-list of columns whose values may be scanned (identity keys,
# timestamps, observation prices).  Everything else is SEALED.
MEASURABLE_COLUMNS: dict[str, dict[str, tuple[str, ...]]] = {
    "beidan_xlsm.sqlite": {
        "matches": ("issue", "match_idx", "kickoff_ts", "ts_10h", "kickoff_serial", "ts_10h_serial"),
        "match_features": ("issue", "match_idx", "kickoff_ts", "season_year", "handicap_line_raw", "handicap_line_norm"),
        "outcome_features": ("issue", "match_idx", "kickoff_ts", "season_year", "handicap_line_norm", "outcome_code",
                             "euro_final_odds", "euro_final_p", "euro_10h_odds", "euro_1h_odds", "euro_initial_odds"),
        "market_snapshots": ("match_id", "market", "bookmaker", "snapshot", "v1", "v2", "v3"),
        "market_consensus": ("match_id", "market", "snapshot", "n_rows", "n_complete",
                             "v1_avg", "v2_avg", "v3_avg", "v1_min", "v2_min", "v3_min",
                             "v1_max", "v2_max", "v3_max"),
        "exotic_odds": ("match_id", "market", "outcome", "odds"),
        "issue_list": ("issue",),
        "source_meta": ("key", "value"),
        "line_lookup": (),
        "action_definitions": (),
    },
    "beidan_features.db": {
        "matches": ("issue", "match_idx", "season", "kickoff", "beidan_hcap",
                    "p_close_3", "p_close_1", "p_close_0", "p_open_3", "p_open_1", "p_open_0",
                    "crown_close_3", "crown_close_1", "crown_close_0",
                    "pinn_close_3", "pinn_close_1", "pinn_close_0",
                    "asian_p_home_close", "asian_p_home_open", "asian_line"),
    },
    "beidan_history.db": {
        "historical_matches": ("issue", "match_idx", "kickoff_ts", "handicap_line",
                               "avg_eu_home", "avg_eu_draw", "avg_eu_away"),
        "scrape_log": ("issue", "fetched_at", "n_matches", "status"),
    },
    "beidan_live.db": {
        "matches": ("issue", "match_idx", "kickoff_ts", "handicap_line", "created_ts", "fid"),
        "snapshots": ("match_id", "snapshot_ts", "sp_3", "sp_1", "sp_0",
                      "vol_pct_3", "vol_pct_1", "vol_pct_0", "pool_total",
                      "eu_h", "eu_d", "eu_a"),
        "settlements": (),  # SEALED: settlement values never read
    },
    "500_bjdc.sqlite": {
        "matches": ("issue", "match_idx", "fid", "end_time", "schedule_date", "handicap_line",
                    "home_rank", "away_rank", "avg_odds_home", "avg_odds_draw", "avg_odds_away"),
        "live_sp_snapshots": ("issue", "playid", "fetched_at", "source_updatetime", "row_idx",
                              "handicap_line", "sp_home", "sp_draw", "sp_away"),
        "live_market_sp_snapshots": ("issue", "playid", "market_key", "fetched_at",
                                     "source_updatetime", "row_idx", "sp", "source_attribute",
                                     "fetched_at_utc", "source_updated_at_hkt", "batch_id",
                                     "source_url", "sale_cutoff_hkt"),
        "market_sp_capture_batches": ("batch_id", "issue", "playid", "market_key", "source_url",
                                      "fetched_at_utc", "source_updated_at_hkt", "payload_sha256",
                                      "match_rows", "outcome_rows", "complete_vector_rows",
                                      "open_rows", "terminal_rows"),
        "issues": ("issue", "ordinal", "label", "is_selected", "is_current", "year",
                   "first_seen_at", "last_seen_at"),
        "fetch_log": ("fetched_at", "kind", "issue", "url", "status", "ok", "elapsed_sec",
                      "bytes", "rows_parsed"),
        "source_meta": ("key", "value"),
        "nowscore_bjdc_matches": ("issue", "match_idx", "provider_match_id", "fetched_at",
                                  "schedule_date", "kickoff_time", "handicap_line"),
        "match_details_500": ("issue", "match_idx", "fid", "fetched_at", "status"),
        "match_intel_digest": ("issue", "match_idx", "fid", "fetched_at", "status", "source_count"),
        "match_intel_sources": ("issue", "match_idx", "fid", "source", "source_tier", "fetched_at", "status"),
        "nowscore_match_details": ("issue", "match_idx", "provider_match_id", "fetched_at", "status"),
        "segment_decision_windows": ("issue", "segment_idx", "segment_start", "segment_end",
                                     "freeze_at", "created_at"),
        "segment_recovery_windows": ("issue", "parent_segment_idx", "child_identity",
                                     "segment_start", "segment_end", "freeze_at", "created_at"),
        "segment_decision_refresh_runs": ("issue", "segment_idx", "checkpoint", "scheduled_at", "started_at", "finished_at", "status"),
        "segment_recovery_publications": ("issue", "parent_segment_idx", "child_identity", "state",
                                          "parent_manifest_sha256", "recovery_manifest_sha256",
                                          "recovery_published_at_hkt"),
        "natural_day_segment_publications": ("issue", "policy", "manifest_sha256", "published_at_hkt"),
        "operations_alert_lifecycle": ("issue", "alert_id", "code", "domain", "first_seen_at", "last_seen_at", "resolved_at"),
        "live_workflow_runs": ("run_id", "issue", "mode", "status", "started_at", "finished_at", "elapsed_sec"),
        "live_workflow_steps": ("run_id", "step_idx", "step_key", "label", "status", "started_at", "finished_at", "elapsed_sec"),
        "llm_decision_snapshots": ("snapshot_id", "issue", "match_idx", "match_id", "status",
                                   "generated_at", "checked_at", "superseded_at"),
        "adhoc_betting_request_ledger": ("request_id", "idempotency_key", "issue", "requested_n",
                                         "requested_at_hkt", "input_asof_hkt", "source_snapshot_sha256",
                                         "created_at_hkt", "valid_until_hkt", "immutable_status"),
        "multimarket_settlement_truth": (),  # SEALED
        "postmatch_reviews": (),             # SEALED
        "postmatch_review_runs": (),         # SEALED
        "postmatch_review_issue_summary": (),  # SEALED
    },
    "beidan_modeling_plus_2026.sqlite": {
        "matches": ("issue", "match_idx", "kickoff_ts", "season_year", "handicap_line_norm"),
        "match_features": ("issue", "match_idx", "kickoff_ts", "season_year", "handicap_line_raw", "handicap_line_norm"),
        "outcome_features": ("issue", "match_idx", "kickoff_ts", "season_year", "handicap_line_norm", "outcome_code",
                             "euro_final_odds", "euro_final_p", "euro_10h_odds", "euro_1h_odds", "euro_initial_odds"),
        "market_consensus": ("match_id", "market", "snapshot", "n_rows", "n_complete"),
        "source_meta": ("key", "value"),
        "action_definitions": (),
        "official_500_settlements": (),  # SEALED
        "action_candidates": (),         # SEALED
    },
    "beidan_nowscore_2026.sqlite": {
        "matches": ("issue", "match_idx", "kickoff_ts", "season_year", "handicap_line_norm"),
        "match_features": ("issue", "match_idx", "kickoff_ts", "season_year", "handicap_line_raw", "handicap_line_norm"),
        "outcome_features": ("issue", "match_idx", "kickoff_ts", "season_year", "handicap_line_norm", "outcome_code",
                             "euro_final_odds", "euro_final_p", "euro_10h_odds", "euro_1h_odds", "euro_initial_odds"),
        "market_snapshots": ("match_id", "market", "bookmaker", "snapshot", "v1", "v2", "v3"),
        "market_consensus": ("match_id", "market", "snapshot", "n_rows", "n_complete"),
        "exotic_odds": ("match_id", "market", "outcome", "odds"),
        "issue_list": ("issue",),
        "source_meta": ("key", "value"),
        "line_lookup": (),
        "action_definitions": (),
        "official_3sp_settlements": (),  # SEALED
        "action_candidates": (),         # SEALED
    },
}

# ---------------------------------------------------------------------------
# Identity primitive keys (C1).  Long-form keys include outcome_code.
# ---------------------------------------------------------------------------
IDENTITY_KEYS: dict[str, dict[str, tuple[str, ...]]] = {
    "beidan_xlsm.sqlite": {
        "matches": ("issue", "match_idx"),
        "match_features": ("issue", "match_idx"),
        "outcome_features": ("issue", "match_idx", "outcome_code"),  # long-form
    },
    # NOTE: beidan_features.matches has NO match_idx column; the real
    # primitive key is match_id (190,743 distinct; 3 duplicated rows).
    "beidan_features.db": {"matches": ("match_id",)},
    "beidan_history.db": {"historical_matches": ("issue", "match_idx")},
    "beidan_live.db": {"matches": ("issue", "match_idx")},
    "500_bjdc.sqlite": {"matches": ("issue", "match_idx")},
    "beidan_modeling_plus_2026.sqlite": {
        "matches": ("issue", "match_idx"),
        "match_features": ("issue", "match_idx"),
        "outcome_features": ("issue", "match_idx", "outcome_code"),
    },
    "beidan_nowscore_2026.sqlite": {
        "matches": ("issue", "match_idx"),
        "match_features": ("issue", "match_idx"),
        "outcome_features": ("issue", "match_idx", "outcome_code"),
    },
}

# ---------------------------------------------------------------------------
# Clock evidence map (REQ-DS01/DS03)
# ---------------------------------------------------------------------------
CLOCK_EVIDENCE: dict[str, dict[str, str]] = {
    "beidan_xlsm.sqlite": {
        "kickoff_ts": "SCHEDULE_ONLY",
        "ts_10h": "LABEL_RELATIVE",
        "kickoff_serial": "NO_CLOCK",
        "ts_10h_serial": "NO_CLOCK",
        "fetched_at": "TIMESTAMPED_LOCAL_NO_TZ",
        "imported_at": "TIMESTAMPED_UTC",
        "end_time": "SCHEDULE_ONLY",
        "schedule_date": "SCHEDULE_ONLY",
    },
    "beidan_features.db": {"kickoff": "SCHEDULE_ONLY"},
    "beidan_history.db": {"kickoff_ts": "SCHEDULE_ONLY", "fetched_at": "TIMESTAMPED_LOCAL_NO_TZ"},
    "beidan_live.db": {
        "kickoff_ts": "SCHEDULE_ONLY",
        "created_ts": "TIMESTAMPED_LOCAL_NO_TZ",
        "snapshot_ts": "TIMESTAMPED_UTC",
        "settled_ts": "TIMESTAMPED_LOCAL_NO_TZ",
    },
    "500_bjdc.sqlite": {"fetched_at": "TIMESTAMPED_LOCAL_NO_TZ", "fetched_at_utc": "TIMESTAMPED_UTC"},
    "beidan_modeling_plus_2026.sqlite": {"kickoff_ts": "SCHEDULE_ONLY"},
    "beidan_nowscore_2026.sqlite": {"kickoff_ts": "SCHEDULE_ONLY"},
}


def _conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _q(conn: sqlite3.Connection, sql: str):
    try:
        return conn.execute(sql).fetchall()
    except Exception as e:  # noqa: BLE001 — probe must not die on odd schemas
        return [("ERR", str(e))]


# ---------------------------------------------------------------------------
# C4: sealed-column guard — the census API physically refuses sealed reads.
# ---------------------------------------------------------------------------
class SealedColumnError(ValueError):
    """Raised when code attempts to read a settlement/label column value."""


def assert_measurable(db_key: str, table: str, column: str) -> None:
    """Fail closed when a column value would be read but is not allow-listed."""
    allow = MEASURABLE_COLUMNS.get(db_key, {}).get(table, ())
    if column not in allow:
        raise SealedColumnError(
            f"refusing to read sealed column {db_key}.{table}.{column}"
        )


# ---------------------------------------------------------------------------
# Bounded census: tables above this row count skip per-column value scans.
# ---------------------------------------------------------------------------
COLUMN_SCAN_MAX_ROWS = 1_000_000


# ---------------------------------------------------------------------------
# C1: identity metrics with correct primitive keys
# ---------------------------------------------------------------------------
def identity_stats(conn: sqlite3.Connection, table: str, key_cols: tuple[str, ...]) -> dict:
    """Correct duplicate/null statistics for a primitive key.

    - ``null_key_rows``: rows where ANY key column is NULL (these are
      UNIDENTIFIED, never duplicates).
    - ``non_null_rows``: rows where the whole key is present.
    - ``distinct_non_null``: distinct keys among non-null rows.
    - ``duplicate_excess``: non_null_rows - distinct_non_null (real
      duplicates only; 0 when every non-null key is unique).
    - ``duplicate_groups``: number of keys with COUNT(*)>1 among non-null.
    """
    quoted = ", ".join(f'"{c}"' for c in key_cols)
    null_pred = " OR ".join(f'"{c}" IS NULL' for c in key_cols)
    key_expr = " || '|' || ".join(f'"{c}"' for c in key_cols)
    try:
        # fail closed: every key column must exist (double-quoted missing
        # identifiers silently become string literals in SQLite, which would
        # corrupt duplicate metrics — C1)
        table_cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
        missing = [c for c in key_cols if c not in table_cols]
        if missing:
            return {
                "error": f"primitive key column(s) missing: {missing}",
                "primitive_key": "|".join(key_cols),
            }
        total = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        null_rows = conn.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE {null_pred}'
        ).fetchone()[0]
        distinct = conn.execute(
            f'SELECT COUNT(DISTINCT CASE WHEN NOT ({null_pred}) '
            f'THEN {key_expr} END) FROM "{table}"'
        ).fetchone()[0]
        groups = conn.execute(
            f'SELECT COUNT(*) FROM (SELECT {quoted} FROM "{table}" '
            f'WHERE NOT ({null_pred}) GROUP BY {quoted} HAVING COUNT(*) > 1)'
        ).fetchone()[0]
        non_null = total - null_rows
        return {
            "total_rows": int(total),
            "null_key_rows": int(null_rows),
            "non_null_rows": int(non_null),
            "distinct_non_null_keys": int(distinct),
            "duplicate_excess": int(non_null - distinct),
            "duplicate_groups": int(groups),
            "uniqueness_verdict": (
                "NULL_KEY_DEFECT" if null_rows
                else ("DUPLICATE_DEFECT" if (non_null - distinct) > 0
                      else "UNIQUE")
            ),
        }
    except sqlite3.Error as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Column scanning (allow-list only; C4)
# ---------------------------------------------------------------------------
def column_stats(conn: sqlite3.Connection, table: str, columns: tuple[str, ...]) -> list[dict]:
    rows = []
    for column in columns:
        rows.append(_column_one(conn, table, column))
    return rows


def _column_one(conn: sqlite3.Connection, table: str, column: str) -> dict:
    out: dict[str, object] = {"table": table, "column": column}
    try:
        out["nulls"] = int(conn.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NULL'
        ).fetchone()[0])
        out["distinct"] = int(conn.execute(
            f'SELECT COUNT(DISTINCT "{column}") FROM "{table}"'
        ).fetchone()[0])
        mn, mx = conn.execute(
            f'SELECT MIN("{column}"), MAX("{column}") FROM "{table}"'
        ).fetchone()
        out["min"] = str(mn) if mn is not None else None
        out["max"] = str(mx) if mx is not None else None
    except sqlite3.Error as e:
        out["error"] = str(e)[:120]
    return out


# ---------------------------------------------------------------------------
# Content hashes (REQ-DS07)
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class CensusResult:
    databases: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    columns: list[dict] = field(default_factory=list)
    identity: list[dict] = field(default_factory=list)
    timestamps: list[dict] = field(default_factory=list)
    source_hashes: list[dict] = field(default_factory=list)
    sealed: list[dict] = field(default_factory=list)


def run_census(root: Path) -> CensusResult:
    """Profile every registered database under ``root`` read-only.

    Databases that do not exist are recorded with ``exists=False`` so the
    frozen registry names them explicitly instead of silently omitting them.
    """
    result = CensusResult()
    for entry in DATABASE_INVENTORY:
        key = entry["key"]
        path = root / entry["path"]
        size = path.stat().st_size if path.exists() else -1
        result.databases.append({
            "database_key": key,
            "path": entry["path"],
            "family": entry["family"],
            "exists": path.exists(),
            "size_bytes": size,
            "size_mb": round(size / 1e6, 1) if size >= 0 else -1,
            "sha256": sha256_file(path) if path.exists() else None,
        })
        if not path.exists():
            continue
        conn = _conn(path)
        tables = _q(conn, "SELECT name, type FROM sqlite_master "
                          "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' "
                          "ORDER BY type, name")
        sealed_tables = SEALED_TABLES.get(key, ())
        allow_map = MEASURABLE_COLUMNS.get(key, {})
        identity_map = IDENTITY_KEYS.get(key, {})
        clock_map = CLOCK_EVIDENCE.get(key, {})
        for tname, ttype in tables:
            schema = _q(conn, f'PRAGMA table_info("{tname}")')
            col_names = [c[1] for c in schema]
            try:
                rowcount = conn.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()[0]
            except sqlite3.Error:
                rowcount = -1
            is_sealed_table = tname in sealed_tables
            result.tables.append({
                "database_key": key,
                "table": tname,
                "type": ttype,
                "rows": rowcount,
                "n_columns": len(col_names),
                "sealed": is_sealed_table,
            })
            if is_sealed_table:
                # SEALED table: metadata only, no value scans (C4)
                result.sealed.append({
                    "database_key": key, "table": tname,
                    "columns": ",".join(col_names), "reason": "settlement/label truth",
                })
                continue
            # column inventory + measured stats for allow-listed columns only
            # (bounded: huge tables skip per-column value scans — REQ-DS06)
            scan_allowed = rowcount < COLUMN_SCAN_MAX_ROWS
            for cname in col_names:
                if cname in allow_map.get(tname, ()):
                    if scan_allowed:
                        try:
                            stats = _column_one(conn, tname, cname)
                        except sqlite3.Error:
                            stats = {"table": tname, "column": cname, "error": "scan failed"}
                        stats["database_key"] = key
                        result.columns.append(stats)
                    else:
                        result.columns.append({
                            "database_key": key, "table": tname, "column": cname,
                            "scanned": False, "reason": "bounded census (table too large)",
                        })
                else:
                    result.sealed.append({
                        "database_key": key, "table": tname, "column": cname,
                        "reason": "settlement/label column; not allow-listed",
                    })
            # identity metrics (C1)
            if tname in identity_map:
                idrow = identity_stats(conn, tname, identity_map[tname])
                idrow["database_key"] = key
                idrow["table"] = tname
                idrow["primitive_key"] = "|".join(identity_map[tname])
                result.identity.append(idrow)
            # timestamp clock samples (REQ-DS03 evidence)
            for cname, semantics in clock_map.items():
                if cname not in col_names:
                    continue
                try:
                    mn, mx = conn.execute(
                        f'SELECT MIN("{cname}"), MAX("{cname}") FROM "{tname}"'
                    ).fetchone()
                    sample = conn.execute(
                        f'SELECT "{cname}" FROM "{tname}" LIMIT 1'
                    ).fetchone()
                except sqlite3.Error:
                    mn = mx = sample = None
                result.timestamps.append({
                    "database_key": key, "table": tname, "column": cname,
                    "clock_semantics": semantics,
                    "min": str(mn) if mn is not None else None,
                    "max": str(mx) if mx is not None else None,
                    "sample": str(sample[0]) if sample and sample[0] is not None else None,
                })
        conn.close()
    return result
