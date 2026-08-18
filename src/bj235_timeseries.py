"""Historical relative-horizon adapter for Issue #235.

This adapter consumes only the sealed workbook's fixture identity, normalized
native handicap line, and the source-relative ``initial``/``10h``/``1h``
``euro_1x2`` consensus triplets.  Labels are retained as labels: no wall-clock
observation time, final snapshot, settlement column, or outcome label is read.
"""
from __future__ import annotations

import hashlib
import math
import sqlite3
from pathlib import Path

import pandas as pd


OUTCOME_CODES = ("3", "1", "0")
PROXY_HORIZONS = ("initial", "10h", "1h")
SOURCE_ID = "beidan_xlsm_workbook"
TIME_SEMANTICS = "SOURCE_RELATIVE_LABEL"
CAUSAL_GRADE = "HISTORICAL_PROXY_LABEL_ONLY"


class HistoricalProxyError(ValueError):
    """The historical workbook cannot satisfy the frozen proxy input contract."""


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _require_source_schema(connection: sqlite3.Connection) -> None:
    required = {
        "matches": {"match_id", "issue", "match_idx", "handicap_line_norm"},
        "market_consensus": {
            "match_id", "market", "snapshot", "v1_avg", "v2_avg", "v3_avg"
        },
    }
    for table, fields in required.items():
        actual = _columns(connection, table)
        missing = sorted(fields - actual)
        if missing:
            raise HistoricalProxyError(f"{table} missing required columns: {missing}")


def _finite_positive(value: object) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 0.0
    except (TypeError, ValueError):
        return False


def _line_state_id(fixture_id: str, line: object) -> str:
    try:
        valid = line is not None and not pd.isna(line) and math.isfinite(float(line))
    except (TypeError, ValueError):
        valid = False
    if not valid:
        return "NO_NATIVE_LINE"
    canonical = f"{fixture_id}|{float(line):.12g}".encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:24]


def build_historical_proxy_frame(source: str | Path) -> pd.DataFrame:
    """Return long-form source-relative 3/1/0 proxy cells.

    Exactly one consensus record must exist for each source match/horizon.  A
    malformed or incomplete vector remains a three-cell explicit unavailable
    record rather than being filled from another horizon or a terminal field.
    """
    path = Path(source)
    if not path.is_file():
        raise HistoricalProxyError(f"historical source does not exist: {path}")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        _require_source_schema(connection)
        placeholders = ", ".join("?" for _ in PROXY_HORIZONS)
        frame = pd.read_sql_query(
            f"""SELECT m.match_id, m.issue AS issue_code, m.match_idx,
                       m.handicap_line_norm AS native_handicap_line,
                       c.snapshot AS snapshot_horizon,
                       c.v1_avg AS sp_3, c.v2_avg AS sp_1, c.v3_avg AS sp_0
                  FROM matches AS m
                  JOIN market_consensus AS c ON c.match_id = m.match_id
                 WHERE c.market = ? AND c.snapshot IN ({placeholders})
                 ORDER BY m.match_id, c.snapshot""",
            connection,
            params=("euro_1x2", *PROXY_HORIZONS),
        )
    finally:
        connection.close()
    if frame.empty:
        raise HistoricalProxyError("no accepted historical proxy rows")
    required_identity = ("match_id", "issue_code", "match_idx", "snapshot_horizon")
    null_identity = frame.loc[:, required_identity].isna().any(axis=1)
    exclusion_counts = {"NULL_CANONICAL_IDENTITY": int(null_identity.sum())}
    frame = frame.loc[~null_identity].copy()
    if frame.empty:
        raise HistoricalProxyError("no rows with a canonical historical identity")
    duplicate_key = ("match_id", "snapshot_horizon")
    if frame.duplicated(list(duplicate_key)).any():
        raise HistoricalProxyError("duplicate historical consensus source cell")

    rows: list[dict[str, object]] = []
    for record in frame.to_dict(orient="records"):
        fixture_id = f"xlsm:{int(record['match_id'])}"
        prices = {code: record[f"sp_{code}"] for code in OUTCOME_CODES}
        valid_prices = {code: _finite_positive(value) for code, value in prices.items()}
        line = record["native_handicap_line"]
        try:
            line_valid = line is not None and not pd.isna(line) and math.isfinite(float(line))
        except (TypeError, ValueError):
            line_valid = False
        complete = all(valid_prices.values())
        available = complete and line_valid
        if not line_valid:
            reason = "MISSING_NATIVE_LINE"
        elif not complete and any(value is None or pd.isna(value) for value in prices.values()):
            reason = "INCOMPLETE_TRIPLET"
        elif not complete:
            reason = "INVALID_SP"
        else:
            reason = "AVAILABLE"
        inverse_sum = sum(1.0 / float(prices[code]) for code in OUTCOME_CODES) if available else 0.0
        for outcome_code in OUTCOME_CODES:
            raw_sp = prices[outcome_code]
            rows.append(
                {
                    "fixture_id": fixture_id,
                    "issue_code": str(record["issue_code"]),
                    "match_idx": int(record["match_idx"]),
                    "snapshot_horizon": str(record["snapshot_horizon"]),
                    "source_id": SOURCE_ID,
                    "time_semantics": TIME_SEMANTICS,
                    "causal_grade": CAUSAL_GRADE,
                    "native_handicap_line": float(line) if line_valid else None,
                    "native_line_state_id": _line_state_id(fixture_id, line),
                    "outcome_code": outcome_code,
                    "raw_sp": float(raw_sp) if valid_prices[outcome_code] else None,
                    "normalized_inverse_sp_probability": (
                        (1.0 / float(raw_sp)) / inverse_sum if available else 0.0
                    ),
                    "availability_mask": available,
                    "unavailable_reason": reason,
                }
            )
    result = pd.DataFrame(rows)
    result.attrs["source_exclusion_counts"] = exclusion_counts
    return result.sort_values(
        ["issue_code", "match_idx", "snapshot_horizon", "outcome_code"],
        kind="stable",
    ).reset_index(drop=True)
