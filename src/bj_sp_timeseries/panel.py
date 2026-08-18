"""Historical relative-horizon M×3 panel (REQ-BJ09, v2 amendment)."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pandas as pd

from . import OUTCOME_DOMAIN

PANEL_BUCKETS = ("initial", "10h", "1h", "final")
PRIMARY_BUCKETS = ("initial", "10h", "1h")
CONSENSUS_N_COL = {"3": "n_v1", "1": "n_v2", "0": "n_v3"}
CONSENSUS_V_COL = {"3": "v1_avg", "1": "v2_avg", "0": "v3_avg"}


def ingest_xlsm_panel(
    con: sqlite3.Connection, xlsm_db: str | Path, batch_id: str = "beidan_xlsm_panel_v1"
) -> dict:
    """Ingest the append-only relative-proxy panel from the archived buckets.

    A row is one (fixture, snapshot bucket, outcome) cell.  No exact timestamp
    is inferred: the bucket is the only temporal key, and unavailable values
    remain explicit ``missing`` cells.  Deterministic ids plus INSERT OR IGNORE
    make a repeated batch idempotent (REQ-BJ07).
    """
    xlsm_db = Path(xlsm_db)
    src = sqlite3.connect(f"file:{xlsm_db}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    counts = {"fixtures": 0, "panel_rows": 0, "present": 0, "missing": 0, "exclusions": 0}

    con.execute(
        """INSERT OR IGNORE INTO ingestion_batch
           (batch_id, source_id, requested_at_utc, received_at_utc, raw_uri,
            raw_sha256, parser_version, row_count, status)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            batch_id,
            "beidan_xlsm_archive",
            None,
            None,
            str(xlsm_db),
            _sha256_file(xlsm_db),
            "bj_sp_timeseries/v2-panel",
            None,
            "completed",
        ),
    )

    fixture_idx: dict[int, dict] = {}
    for match in src.execute(
        """SELECT match_id, issue, match_idx, kickoff_ts, league, home, away,
                  handicap_line_norm
           FROM matches WHERE issue IS NOT NULL AND match_idx IS NOT NULL
           ORDER BY issue, match_idx"""
    ):
        fixture_id = f"{match['issue']}_{int(match['match_idx']):03d}"
        fixture_idx[match["match_id"]] = {
            "fixture_id": fixture_id,
            "issue_code": match["issue"],
            "match_idx": int(match["match_idx"]),
            "line": match["handicap_line_norm"],
        }
        con.execute(
            """INSERT OR IGNORE INTO fixture
               (fixture_id, issue_code, match_idx, source_match_key, competition,
                home, away, kickoff_at_utc, native_handicap_line, identity_status)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                fixture_id,
                match["issue"],
                int(match["match_idx"]),
                str(match["match_id"]),
                match["league"],
                match["home"],
                match["away"],
                _norm_ts(match["kickoff_ts"]),
                match["handicap_line_norm"],
                "canonical",
            ),
        )
        counts["fixtures"] += 1

    for row in src.execute(
        """SELECT match_id, snapshot, n_v1, n_v2, n_v3, v1_avg, v2_avg, v3_avg
           FROM market_consensus WHERE market='euro_1x2'"""
    ):
        fixture = fixture_idx.get(row["match_id"])
        bucket = row["snapshot"]
        if fixture is None or bucket not in PANEL_BUCKETS:
            counts["exclusions"] += 1
            continue
        for code in OUTCOME_DOMAIN:
            n = row[CONSENSUS_N_COL[code]] or 0
            odds = row[CONSENSUS_V_COL[code]]
            present = n > 0 and odds is not None and odds > 0
            panel_id = f"panel_{fixture['fixture_id']}_{bucket}_{code}_beidan_xlsm_archive"
            con.execute(
                """INSERT OR IGNORE INTO relative_horizon_panel
                   (panel_id, fixture_id, issue_code, match_idx, native_handicap_line,
                    snapshot_bucket, outcome_code, decimal_odds, availability,
                    consensus_n, market_type, source_id, batch_id, provenance_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    panel_id,
                    fixture["fixture_id"],
                    fixture["issue_code"],
                    fixture["match_idx"],
                    fixture["line"],
                    bucket,
                    code,
                    odds if present else None,
                    "present" if present else "missing",
                    n,
                    "euro_1x2",
                    "beidan_xlsm_archive",
                    batch_id,
                    _provenance_hash(
                        fixture["fixture_id"], bucket, code, present, odds, n, fixture["line"], batch_id
                    ),
                ),
            )
            counts["panel_rows"] += 1
            counts["present" if present else "missing"] += 1

    from .ingest import log_exclusion

    padding_rows = src.execute(
        "SELECT COUNT(*) FROM matches WHERE issue IS NULL OR match_idx IS NULL"
    ).fetchone()[0]
    if padding_rows:
        log_exclusion(
            con,
            fixture_id=None,
            source_id="beidan_xlsm_archive",
            issue_code=None,
            season_year=None,
            native_handicap_line=None,
            reason_code="NO_OBSERVATION",
            detail=(
                f"{padding_rows} padding matches rows have NULL issue/match_idx and "
                "are excluded; no panel rows are fabricated"
            ),
            raw_count=padding_rows,
            batch_id=batch_id,
        )
        counts["exclusions"] += padding_rows
    con.commit()
    src.close()
    return counts


def panel_support(con: sqlite3.Connection) -> dict:
    """Return REQ-BJ09 coverage and missingness by issue and horizon."""
    rows = con.execute(
        """SELECT issue_code, snapshot_bucket, COUNT(DISTINCT fixture_id) AS fixtures,
                  COUNT(*) AS cells,
                  SUM(CASE WHEN availability='present' THEN 1 ELSE 0 END) AS cells_present,
                  SUM(CASE WHEN availability='missing' THEN 1 ELSE 0 END) AS cells_missing
           FROM relative_horizon_panel
           GROUP BY issue_code, snapshot_bucket
           ORDER BY issue_code, snapshot_bucket"""
    ).fetchall()
    per_issue = [dict(row) for row in rows]
    by_bucket: dict[str, dict] = {}
    for row in rows:
        bucket = by_bucket.setdefault(
            row["snapshot_bucket"],
            {"issues": 0, "fixtures": 0, "cells": 0, "cells_present": 0, "cells_missing": 0},
        )
        bucket["issues"] += 1
        bucket["fixtures"] += row["fixtures"]
        bucket["cells"] += row["cells"]
        bucket["cells_present"] += row["cells_present"]
        bucket["cells_missing"] += row["cells_missing"]
    total_fixtures = con.execute("SELECT COUNT(DISTINCT fixture_id) FROM relative_horizon_panel").fetchone()[0]
    return {"per_issue": per_issue, "by_bucket": by_bucket, "total_fixtures": total_fixtures}


def build_panel_evidence(con: sqlite3.Connection) -> dict:
    """Produce the positive v2 disposition with explicit proxy limitations."""
    support = panel_support(con)
    total_cells = con.execute("SELECT COUNT(*) FROM relative_horizon_panel").fetchone()[0]
    total_present = con.execute(
        "SELECT COUNT(*) FROM relative_horizon_panel WHERE availability='present'"
    ).fetchone()[0]
    return {
        "disposition": "HISTORICAL_RELATIVE_PROXY_PANEL",
        "status": "POSITIVE_DELIVERY",
        "scope": "historical Beijing line and 3/1/0 SP at initial/10h/1h/final label buckets",
        "cells_total": total_cells,
        "cells_present": total_present,
        "cells_missing": total_cells - total_present,
        "missing_ratio": round((total_cells - total_present) / total_cells, 4) if total_cells else None,
        "issues_covered": len({row["issue_code"] for row in support["per_issue"]}),
        "fixtures_covered": support["total_fixtures"],
        "buckets_profiled": list(support["by_bucket"]),
        "bucket_primary_scope": list(PRIMARY_BUCKETS),
        "by_bucket": support["by_bucket"],
        "strict_historical_causal_support": 0,
        "limitations": [
            "no exact wall-clock timestamps; snapshot bucket is the temporal key",
            "missing cells are explicit and are not inferred from settlement, outcomes or later snapshots",
            "decimal odds are archived euro_1x2 consensus averages",
        ],
    }


def verify_panel_provenance(con: sqlite3.Connection, batch_id: str = "beidan_xlsm_panel_v1") -> dict:
    """Recompute every panel cell's binding hash; mismatch means tampering."""
    bad: list[str] = []
    rows = con.execute(
        """SELECT panel_id, fixture_id, snapshot_bucket, outcome_code, availability,
                  decimal_odds, consensus_n, native_handicap_line, provenance_hash
           FROM relative_horizon_panel"""
    ).fetchall()
    for row in rows:
        actual = _provenance_hash(
            row["fixture_id"],
            row["snapshot_bucket"],
            row["outcome_code"],
            row["availability"] == "present",
            row["decimal_odds"],
            row["consensus_n"],
            row["native_handicap_line"],
            batch_id,
        )
        if actual != row["provenance_hash"]:
            bad.append(row["panel_id"])
    return {"checked": len(rows), "mismatches": len(bad), "sample": bad[:5]}


def relative_horizon_view_df(con: sqlite3.Connection) -> pd.DataFrame:
    """Return the settlement-free long M×3 view required by #238."""
    return pd.read_sql_query(
        """SELECT issue_code, match_idx, fixture_id, native_handicap_line,
                  snapshot_bucket, outcome_code, decimal_odds, availability,
                  market_type, source_id
           FROM relative_horizon_panel
           ORDER BY issue_code, match_idx, snapshot_bucket, outcome_code""",
        con,
    )


def _provenance_hash(fixture_id, bucket, code, present, odds, count, line, batch_id) -> str:
    payload = "|".join(
        [
            str(fixture_id), str(bucket), str(code), "present" if present else "missing",
            "" if odds is None else f"{odds:.8f}", str(count),
            "" if line is None else f"{line:.4f}", str(batch_id),
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _norm_ts(ts):
    from .ingest import _norm_ts as normalize

    return normalize(ts)


def _sha256_file(path: Path) -> str:
    from .ingest import _sha256_file as sha256_file

    return sha256_file(path)
