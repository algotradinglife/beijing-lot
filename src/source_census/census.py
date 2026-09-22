"""Read-only source-role assessment for BJ-UNIFIED-SOURCE-CENSUS-001.

The module profiles only declared logical source families.  It never writes an
external source, crawls, normalizes, imputes, trains, or uses labels to decide
feature availability/admissibility.  All SQLite opens are URI read-only.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ISSUE = 250
PACKAGE_NAME = "bj250_source_census_v3"
OUTCOME_CODES = ("3", "1", "0")
PROXY_POLICY_ID = "ISSUE_250_PI_USER_V2_RELATIVE_PROXY"
PROXY_SNAPSHOTS = ("initial", "10h", "1h")
PROXY_SURFACES = {
    "euro_1x2": {
        "vector_semantics": "THREE_OUTCOME_EURO_1X2",
        "admissible_use": "HISTORICAL_PROXY_CANDIDATE",
        "role_gate_eligible": True,
        "downstream_requirement": "TRANSLATE_TO_NATIVE_BEIJING_LINE_IN_236",
    },
    "kelly_1x2": {
        "vector_semantics": "DERIVED_THREE_OUTCOME_KELLY",
        "admissible_use": "HISTORICAL_PROXY_DESCRIPTIVE",
        "role_gate_eligible": False,
        "downstream_requirement": "DO_NOT_TREAT_AS_INDEPENDENT_PRICE",
    },
    "asian_handicap": {
        "vector_semantics": "TWO_PRICE_PLUS_LINE_NOT_OUTCOME_TRIPLET",
        "admissible_use": "AUXILIARY_RELATIVE_PROXY",
        "role_gate_eligible": False,
        "downstream_requirement": "EXPLICIT_LAYOUT_REQUIRED_IN_236",
    },
    "over_under": {
        "vector_semantics": "TWO_PRICE_PLUS_LINE_NOT_P34_OUTCOME_TRIPLET",
        "admissible_use": "AUXILIARY_RELATIVE_PROXY",
        "role_gate_eligible": False,
        "downstream_requirement": "OPTIONAL_GOAL_DISTRIBUTION_INPUT_ONLY",
    },
}
HIST40_RELEASE = {
    "tag": "hist-data-census-001-r8",
    "commit": "97a9c0a78d2fce0004cb1240113a070b980403b9",
    "manifest_sha256": "ed16b29626b4af70e80cdfee3130d6d5e89cd79d09e06110d4d55570e217cdc8",
    "archive_sha256": "7de5e20d0a3b2185bcaf8e4229544c28100cd2d29c9cc315adbc6afe48f4a38d",
}
LABEL_TOKENS = (
    "result",
    "score",
    "winning",
    "settle",
    "payout",
    "hit",
    "profit",
    "roi",
    "fthg",
    "ftag",
    "official_sp",
    "final",
    "halftime",
    "half_",
    "total_goals",
    "winner",
    "return",
)
TERMINAL_TABLES = {"official_500_settlements", "action_candidates"}
HIST40_CROSSWALK = Path(__file__).with_name("resources") / "hist40_field_crosswalk.csv"
_HIST40_BASELINE: dict[tuple[str, str, str], dict[str, str]] | None = None

# R8's two market-scoped prohibitions cannot be represented by the generic
# (source, table, column) schema dictionary.  Keep their finer grain intact.
HIST40_SCOPE_OVERRIDES = (
    {
        "source_id": "beidan_xlsm",
        "scope_level": "field_market",
        "table": "exotic_odds",
        "column": "odds",
        "market": "correct_score",
        "admissible_use": "PROHIBITED",
        "integration_decision": "PROHIBITED",
        "destination_layer": "none",
        "provenance_grade": "UNVERIFIED_MARKET_AND_TIME",
        "reason": "R8_SCORE_PRICE_PROVIDER_MARKET_TIME_UNRESOLVED_AND_26_VS_25_SCHEMA",
    },
    {
        "source_id": "beidan_xlsm",
        "scope_level": "field_market",
        "table": "exotic_odds",
        "column": "odds",
        "market": "total_goals",
        "admissible_use": "PROHIBITED",
        "integration_decision": "PROHIBITED",
        "destination_layer": "none",
        "provenance_grade": "HISTORICAL_P40_SCHEMA_INCOMPATIBLE",
        "reason": "R8_HISTORICAL_FOUR_WAY_TOTAL_GOALS_NOT_CURRENT_EIGHT_WAY_P40",
    },
)

SOURCE_ROUTING = {
    "historical_relative_time_proxy": {
        "advance_to_251": True,
        "advance_to_252": True,
        "decision": "ASSESS_IDENTITY_IN_251_AND_TEMPORAL_PROXY_IN_252",
    },
    "identity_schedule_support": {
        "advance_to_251": True,
        "advance_to_252": False,
        "decision": "ASSESS_IDENTITY_SUPPORT_IN_251",
    },
    "settlement_label_truth": {
        "advance_to_251": False,
        "advance_to_252": False,
        "decision": "SETTLEMENT_ONLY_NO_FEATURE_ROUTING",
    },
    "strict_forward_candidate": {
        "advance_to_251": True,
        "advance_to_252": True,
        "decision": "ASSESS_IDENTITY_IN_251_AND_SEAL_CLOCKS_IN_252",
    },
    "derived_copy": {
        "advance_to_251": False,
        "advance_to_252": False,
        "decision": "EXCLUDE_DERIVED_COPY",
    },
}


def _hist40_baseline_records() -> dict[tuple[str, str, str], dict[str, str]]:
    global _HIST40_BASELINE
    if _HIST40_BASELINE is None:
        with HIST40_CROSSWALK.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        _HIST40_BASELINE = {}
        for row in rows:
            key = (row["source_id"], row["table"].lower(), row["column"].lower())
            if key in _HIST40_BASELINE:
                raise RuntimeError(f"duplicate R8 field crosswalk key: {key}")
            _HIST40_BASELINE[key] = row
    return _HIST40_BASELINE


def hist40_baseline_record(
    source_id: str, table: str, column: str
) -> dict[str, str] | None:
    """Read the committed, R8-derived per-field admissibility crosswalk."""
    return _hist40_baseline_records().get((source_id, table.lower(), column.lower()))


def hist40_baseline_applies(source_id: str, content_sha256: str) -> bool:
    """True only if a declared source still has the exact R8 asset identity."""
    row = next(
        (
            value
            for (mapped_source, _, _), value in _hist40_baseline_records().items()
            if mapped_source == source_id
        ),
        None,
    )
    return row is not None and row["r8_content_sha256"] == content_sha256


def hist40_field_baseline_applies(
    baseline: dict[str, str] | None, content_sha256: str
) -> bool:
    """Bind a lane to the exact R8 asset identity recorded for that field."""
    return (
        baseline is not None and baseline.get("r8_content_sha256", "") == content_sha256
    )


def field_admissible_use(
    table: str,
    column: str,
    *,
    source_role: str | None = None,
    baseline: dict[str, str] | None = None,
) -> str:
    """Return a field lane, fail-closed against the R8 admissibility record.

    A historical-source container never authorizes fields by itself.  A field
    needs an explicit R8 row that is non-terminal and pre-match eligible before
    it becomes a historical-proxy candidate.  New/changed/unmapped fields stay
    raw-only pending a future policy decision.
    """
    table_name, field = table.lower(), column.lower()
    if source_role in {"EXCLUDE", "RECOVER"}:
        return source_role
    if (
        source_role == "SETTLEMENT_ONLY"
        or table_name in TERMINAL_TABLES
        or any(token in table_name for token in ("settle", "result"))
        or any(token in field for token in LABEL_TOKENS)
        or baseline is not None
        and baseline.get("terminal_value", "").lower() == "true"
    ):
        return "SETTLEMENT_ONLY"
    if source_role in {"RAW_ONLY", "MUTABLE_UNFROZEN"}:
        return "RAW_ONLY"
    if source_role == "HISTORICAL_PROXY":
        if baseline is None:
            return "RAW_ONLY"
        if baseline.get("pre_match_feature_eligible", "").lower() != "true":
            return "RAW_ONLY"
        if "historical_proxy" not in baseline.get("admissible_use", "").lower():
            return "RAW_ONLY"
        return "HISTORICAL_PROXY_CANDIDATE"
    return "RAW_ONLY"


def profile_field_lane(
    source_id: str,
    table: str,
    column: str,
    source_role: str,
    content_sha256: str,
) -> str:
    """Resolve one observed field against R8 only when the asset is unchanged."""
    baseline = hist40_baseline_record(source_id, table, column)
    if not hist40_field_baseline_applies(baseline, content_sha256):
        baseline = None
    return field_admissible_use(
        table, column, source_role=source_role, baseline=baseline
    )


def capture_match_key_columns(columns: set[str]) -> tuple[str, ...]:
    """p34 snapshot match identity; playid is a play type, never a match key."""
    required = ("issue", "fetched_at", "row_idx")
    return required if all(column in columns for column in required) else ()


def _capture_logical_match_key_columns(columns: set[str]) -> tuple[str, ...]:
    required = ("issue", "row_idx")
    return required if all(column in columns for column in required) else ()


def _key_expr(columns: tuple[str, ...]) -> str:
    return " || '|' || ".join(f"CAST({_q(column)} AS TEXT)" for column in columns)


class DataRootError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    relative_path: str
    lineage_root: str
    layer: str
    lane: str
    intended_role: str
    mutable: bool
    coverage_table: str
    issue_column: str | None
    match_column: str | None
    date_column: str | None
    source_clock_column: str | None
    capture_clock_column: str | None
    decision_fields: tuple[str, ...]
    notes: str


SOURCES = (
    SourceSpec(
        "beidan_xlsm",
        "derived/beidan_xlsm/beidan_xlsm.sqlite",
        "beidan_xlsm",
        "raw_canonical",
        "historical_relative_time_proxy",
        "HISTORICAL_PROXY",
        False,
        "matches",
        "issue",
        "match_idx",
        "kickoff_ts",
        None,
        None,
        (
            "issue",
            "match_idx",
            "kickoff_ts",
            "league",
            "home",
            "away",
            "handicap_line",
            "ts_10h",
            "home_team_id",
            "away_team_id",
            "result_label",
        ),
        "Historical initial/10h/1h labels are proxy buckets, never strict observation timestamps.",
    ),
    SourceSpec(
        "beidan_features",
        "beidan_features.db",
        "beidan_features",
        "derived",
        "identity_schedule_support",
        "RAW_ONLY",
        False,
        "matches",
        "issue",
        "match_id",
        "kickoff",
        None,
        None,
        (
            "issue",
            "match_id",
            "kickoff",
            "league",
            "home",
            "away",
            "home_id",
            "away_id",
            "beidan_hcap",
            "p_open_3",
            "p_open_1",
            "p_open_0",
            "p_close_3",
            "p_close_1",
            "p_close_0",
            "result_code",
        ),
        "Identity/schedule support with no accepted source or capture observation clock.",
    ),
    SourceSpec(
        "beidan_history",
        "beidan_history.db",
        "beidan_history",
        "derived",
        "settlement_label_truth",
        "SETTLEMENT_ONLY",
        False,
        "historical_matches",
        "issue",
        "match_idx",
        "kickoff_ts",
        None,
        None,
        (
            "issue",
            "match_idx",
            "kickoff_ts",
            "league",
            "home",
            "away",
            "handicap_line",
            "avg_eu_home",
            "avg_eu_draw",
            "avg_eu_away",
            "result_code",
            "winning_sp",
        ),
        "Settlement/label truth must remain separate from inference.",
    ),
    SourceSpec(
        "beidan_live",
        "beidan_live.db",
        "beidan_live",
        "raw_capture",
        "strict_forward_candidate",
        "STRICT_FORWARD_CANDIDATE",
        True,
        "matches",
        "issue",
        "match_idx",
        "kickoff_ts",
        None,
        "created_ts",
        (
            "match_id",
            "issue",
            "match_idx",
            "kickoff_ts",
            "league",
            "home",
            "away",
            "handicap_line",
            "created_ts",
        ),
        "Mutable live collector; its existing clock is capture-only.",
    ),
    SourceSpec(
        "beidan_modeling_plus",
        "derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite",
        "beidan_xlsm",
        "derived",
        "derived_copy",
        "EXCLUDE",
        False,
        "matches",
        "issue",
        "match_idx",
        "kickoff_ts",
        None,
        None,
        ("issue", "match_idx", "kickoff_ts"),
        "Derived copy; not independent source evidence.",
    ),
    SourceSpec(
        "beidan_nowscore",
        "derived/beidan_xlsm/beidan_nowscore_2026.sqlite",
        "beidan_xlsm",
        "derived",
        "derived_copy",
        "EXCLUDE",
        False,
        "matches",
        "issue",
        "match_idx",
        "kickoff_ts",
        None,
        None,
        ("issue", "match_idx", "kickoff_ts"),
        "Derived copy; not independent source evidence.",
    ),
)


def resolve_data_root(value: str | Path | None = None) -> Path:
    raw = (
        str(value) if value is not None else os.environ.get("BEIJING_LOT_DATA_ROOT", "")
    )
    if not raw:
        raise DataRootError(
            "BEIJING_LOT_DATA_ROOT is required; repository fallback is prohibited"
        )
    root = Path(raw).resolve()
    if not root.is_dir():
        raise DataRootError(
            f"BEIJING_LOT_DATA_ROOT is not a readable directory: {root}"
        )
    return root


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    """Public, deterministic digest used by independent anchor construction."""
    return _sha256(path)


def package_anchor(package: Path) -> dict[str, object]:
    """Create an anchor from actual payload bytes, never manifest assertions."""
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    payload_hashes = {
        path.relative_to(package).as_posix(): _sha256(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name not in {"MANIFEST.json", "SHA256SUMS.json"}
    }
    return {
        "issue": manifest.get("issue"),
        "semantic_hashes": payload_hashes,
        "package": manifest.get("package", ""),
        "implementation_sha256": manifest.get("implementation_sha256", ""),
        "crosswalk_sha256": _sha256(HIST40_CROSSWALK),
        "manifest_sha256": _sha256(package / "MANIFEST.json"),
    }


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _tables(c: sqlite3.Connection) -> list[str]:
    return [
        str(r[0])
        for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def _columns(c: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    return [
        (str(r[1]), str(r[2])) for r in c.execute(f"PRAGMA table_info({_q(table)})")
    ]


def _is_label(name: str) -> bool:
    return any(token in name.lower() for token in LABEL_TOKENS)


def _field_family(table: str, column: str, admissible_use: str | None = None) -> str:
    if (
        admissible_use == "SETTLEMENT_ONLY"
        or field_admissible_use(table, column) == "SETTLEMENT_ONLY"
    ):
        return "label_settlement"
    x = column.lower()
    if x in {
        "issue",
        "match_idx",
        "playid",
        "row_idx",
        "match_id",
        "home",
        "away",
        "home_id",
        "away_id",
        "league",
    }:
        return "identity_schedule"
    if (
        "clock" in x
        or "time" in x
        or "date" in x
        or x
        in {
            "kickoff",
            "kickoff_ts",
            "fetched_at",
            "fetched_at_utc",
            "created_ts",
            "source_updatetime",
            "source_updated_at_hkt",
        }
    ):
        return "timestamp"
    if (
        "sp" in x
        or "odds" in x
        or x.startswith("p_")
        or x in {"v1", "v2", "v3", "handicap_line", "beidan_hcap"}
    ):
        return "market_feature"
    return "other"


def _scope(spec: SourceSpec) -> str:
    return (
        " WHERE market_key = 'handicap_3way'"
        if spec.source_id == "bjdc_500_capture"
        else ""
    )


def _join_scope(scope: str, condition: str) -> str:
    return f"{scope}{' AND ' if scope else ' WHERE '}{condition}"


def profiling_periods() -> tuple[str, ...]:
    return (
        "EARLIER_YEAR",
        "CALENDAR_2024",
        "GAP_2025_01_TO_03",
        "2025_04_TO_2026_04",
        "PROSPECTIVE_2026_05_ONWARD",
        "NULL_OR_UNPARSEABLE_DATE",
    )


def strict_forward_role(
    *, source_clock_complete: bool, capture_clock_complete: bool, mutable: bool
) -> str:
    if not source_clock_complete or not capture_clock_complete:
        return "RAW_ONLY"
    return "MUTABLE_UNFROZEN" if mutable else "STRICT_FORWARD_CANDIDATE"


def role_from_profile(
    spec: SourceSpec,
    *,
    coverage_status: str,
    proxy_gate_valid_matches: int,
    proxy_gate_bucket_count: int,
    source_clock_complete: bool,
    capture_clock_complete: bool,
) -> str:
    """Return a disposition only when one coherent support surface qualifies.

    In particular, a source cannot be promoted by adding a triplet count from
    one table to an admissible field count from another.  The historical lane
    is controlled only by the explicit Issue-250 proxy-surface profile.
    """
    if coverage_status != "PROFILED":
        return "RECOVER"
    if spec.layer == "derived" and spec.lineage_root != spec.source_id:
        return "EXCLUDE"
    if spec.lane == "historical_relative_time_proxy":
        if proxy_gate_bucket_count != len(PROXY_SNAPSHOTS):
            return "RAW_ONLY"
        if proxy_gate_valid_matches <= 0:
            return "RAW_ONLY"
        return "HISTORICAL_PROXY"
    if spec.lane == "strict_forward_candidate":
        return strict_forward_role(
            source_clock_complete=source_clock_complete,
            capture_clock_complete=capture_clock_complete,
            mutable=spec.mutable,
        )
    return spec.intended_role


def canonical_causal_intersection() -> str:
    return "NOT_YET_EVALUATED"


def native_key_intersection(
    left: Iterable[tuple[str, int]], right: Iterable[tuple[str, int]]
) -> int:
    return len(set(left).intersection(set(right)))


def lineage_decisions(records: list[dict[str, object]]) -> list[dict[str, object]]:
    roots: set[str] = set()
    out: list[dict[str, object]] = []
    for item in records:
        row = dict(item)
        root = str(row["lineage_root"])
        row["independent_evidence"] = root not in roots
        row["dedup_reason"] = (
            "" if row["independent_evidence"] else f"DERIVED_FROM_{root}"
        )
        roots.add(root)
        out.append(row)
    return out


def _null_expr(column: str) -> str:
    q = _q(column)
    return f"({q} IS NULL OR TRIM(CAST({q} AS TEXT)) = '')"


def _invalid_expr(column: str) -> str:
    lower = column.lower()
    q = _q(column)
    if lower == "sp" or "odds" in lower or lower in {"v1", "v2", "v3", "winning_sp"}:
        return f"({q} IS NOT NULL AND CAST({q} AS REAL) <= 0)"
    if lower.startswith("p_") or lower.endswith("_prob"):
        return f"({q} IS NOT NULL AND (CAST({q} AS REAL) < 0 OR CAST({q} AS REAL) > 1))"
    return "0"


def _source_aggregate(
    c: sqlite3.Connection, spec: SourceSpec, columns: set[str]
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if spec.coverage_table not in _tables(c):
        return (
            {
                "coverage_status": "TABLE_MISSING",
                "rows": -1,
                "issue_count": -1,
                "match_count": -1,
            },
            [],
        )
    fields = [x for x in spec.decision_fields if x in columns]
    scope = _scope(spec)
    select = ["COUNT(*) AS rows"]
    if spec.issue_column in columns:
        select.append(f"COUNT(DISTINCT {_q(spec.issue_column)}) AS issue_count")
    else:
        select.append("-1 AS issue_count")
    match_keys = (
        _capture_logical_match_key_columns(columns)
        if spec.source_id == "bjdc_500_capture"
        else tuple(
            key
            for key in (spec.issue_column, spec.match_column)
            if key and key in columns
        )
    )
    if len(match_keys) >= 2:
        select.append(f"COUNT(DISTINCT {_key_expr(match_keys)}) AS match_count")
    else:
        select.append("-1 AS match_count")
    for i, field in enumerate(fields):
        select.append(f"SUM(CASE WHEN {_null_expr(field)} THEN 1 ELSE 0 END) AS n{i}")
        select.append(
            f"SUM(CASE WHEN {_invalid_expr(field)} THEN 1 ELSE 0 END) AS i{i}"
        )
    values = c.execute(
        f"SELECT {', '.join(select)} FROM {_q(spec.coverage_table)}{scope}"
    ).fetchone()
    row = {
        "coverage_status": "PROFILED",
        "rows": int(values[0]),
        "issue_count": int(values[1]),
        "match_count": int(values[2]),
    }
    profiles = []
    for i, field in enumerate(fields):
        profiles.append(
            {
                "source_id": spec.source_id,
                "table": spec.coverage_table,
                "field": field,
                "field_family": _field_family(spec.coverage_table, field),
                "is_label_or_settlement": _is_label(field),
                "denominator_rows": int(values[0]),
                "null_or_blank_count": int(values[3 + 2 * i] or 0),
                "non_null_count": int(values[0]) - int(values[3 + 2 * i] or 0),
                "impossible_value_count": int(values[4 + 2 * i] or 0),
                "availability_used_for_role": not _is_label(field),
            }
        )
    return row, profiles


def _coverage_strata(
    c: sqlite3.Connection, spec: SourceSpec, columns: set[str]
) -> list[dict[str, object]]:
    if spec.coverage_table not in _tables(c) or spec.date_column not in columns:
        return [
            {
                "source_id": spec.source_id,
                "period": p,
                "year_or_range": "",
                "source_rows": -1,
                "coverage_record_count": -1,
                "record_grain": "UNAVAILABLE",
                "issue_count": -1,
                "match_count": -1,
                "date_missing_or_unparseable": -1,
                "reason": "NO_SAFE_DATE_COLUMN",
            }
            for p in profiling_periods()
        ]
    date = _q(spec.date_column)
    scope = _scope(spec)
    base = int(
        c.execute(f"SELECT COUNT(*) FROM {_q(spec.coverage_table)}{scope}").fetchone()[
            0
        ]
    )
    count_expr = _coverage_count_expr(spec, columns)
    rows: list[dict[str, object]] = []
    predicates = [
        ("CALENDAR_2024", "2024", f"{date} >= '2024-01-01' AND {date} < '2025-01-01'"),
        (
            "GAP_2025_01_TO_03",
            "2025-01..03",
            f"{date} >= '2025-01-01' AND {date} < '2025-04-01'",
        ),
        (
            "2025_04_TO_2026_04",
            "2025-04..2026-04",
            f"{date} >= '2025-04-01' AND {date} < '2026-05-01'",
        ),
        ("PROSPECTIVE_2026_05_ONWARD", "2026-05+", f"{date} >= '2026-05-01'"),
        (
            "NULL_OR_UNPARSEABLE_DATE",
            "null/unparseable",
            f"{date} IS NULL OR TRIM(CAST({date} AS TEXT)) = '' OR {date} < '1900-01-01'",
        ),
    ]
    for period, label, predicate in predicates:
        rows.append(
            _coverage_row(
                c, spec, columns, period, label, predicate, scope, base, count_expr
            )
        )
    earlier_scope = _join_scope(
        scope, f"{date} >= '1900-01-01' AND {date} < '2024-01-01'"
    )
    year_rows = c.execute(
        f"SELECT substr(CAST({date} AS TEXT), 1, 4), COUNT(*) FROM {_q(spec.coverage_table)}{earlier_scope} GROUP BY 1 ORDER BY 1"
    ).fetchall()
    for year, _ in year_rows:
        predicate = f"{date} >= '{year}-01-01' AND {date} < '{int(year) + 1}-01-01'"
        rows.append(
            _coverage_row(
                c,
                spec,
                columns,
                "EARLIER_YEAR",
                str(year),
                predicate,
                scope,
                base,
                count_expr,
            )
        )
    return rows


def _coverage_count_expr(spec: SourceSpec, columns: set[str]) -> tuple[str, str]:
    issue = (
        f"COUNT(DISTINCT {_q(spec.issue_column)})"
        if spec.issue_column in columns
        else "-1"
    )
    match_keys = (
        _capture_logical_match_key_columns(columns)
        if spec.source_id == "bjdc_500_capture"
        else tuple(
            key
            for key in (spec.issue_column, spec.match_column)
            if key and key in columns
        )
    )
    match = f"COUNT(DISTINCT {_key_expr(match_keys)})" if len(match_keys) >= 2 else "-1"
    return issue, match


def _coverage_row(
    c: sqlite3.Connection,
    spec: SourceSpec,
    columns: set[str],
    period: str,
    label: str,
    predicate: str,
    scope: str,
    base: int,
    expr: tuple[str, str],
) -> dict[str, object]:
    query_scope = _join_scope(scope, predicate)
    value = c.execute(
        f"SELECT COUNT(*), {expr[0]}, {expr[1]} FROM {_q(spec.coverage_table)}{query_scope}"
    ).fetchone()
    grain = (
        "P34_OUTCOME_CELL"
        if spec.source_id == "bjdc_500_capture"
        else "SOURCE_COVERAGE_RECORD"
    )
    return {
        "source_id": spec.source_id,
        "period": period,
        "year_or_range": label,
        "source_rows": base,
        "coverage_record_count": int(value[0]),
        "record_grain": grain,
        "issue_count": int(value[1]),
        "match_count": int(value[2]),
        "date_missing_or_unparseable": int(value[0])
        if period == "NULL_OR_UNPARSEABLE_DATE"
        else 0,
        "reason": "PROFILE_STRATUM_NOT_SPLIT_ASSIGNMENT",
    }


def _period_sql(date_expression: str) -> tuple[str, str]:
    period = f"""
        CASE
          WHEN {date_expression} IS NULL OR TRIM(CAST({date_expression} AS TEXT)) = '' OR {date_expression} < '1900-01-01'
            THEN 'NULL_OR_UNPARSEABLE_DATE'
          WHEN {date_expression} < '2024-01-01' THEN 'EARLIER_YEAR'
          WHEN {date_expression} < '2025-01-01' THEN 'CALENDAR_2024'
          WHEN {date_expression} < '2025-04-01' THEN 'GAP_2025_01_TO_03'
          WHEN {date_expression} < '2026-05-01' THEN '2025_04_TO_2026_04'
          ELSE 'PROSPECTIVE_2026_05_ONWARD'
        END
    """
    label = f"""
        CASE
          WHEN {date_expression} IS NULL OR TRIM(CAST({date_expression} AS TEXT)) = '' OR {date_expression} < '1900-01-01'
            THEN 'null/unparseable'
          WHEN {date_expression} < '2024-01-01' THEN substr(CAST({date_expression} AS TEXT), 1, 4)
          WHEN {date_expression} < '2025-01-01' THEN '2024'
          WHEN {date_expression} < '2025-04-01' THEN '2025-01..03'
          WHEN {date_expression} < '2026-05-01' THEN '2025-04..2026-04'
          ELSE '2026-05+'
        END
    """
    return period, label


def _proxy_coverage_by_period(c: sqlite3.Connection) -> list[dict[str, object]]:
    """Report true match/vector/physical-cell denominators for proxy surfaces."""
    if not {"market_snapshots", "matches"}.issubset(set(_tables(c))):
        return []
    period_sql, label_sql = _period_sql("kickoff_ts")
    match_rows = c.execute(
        f"""
        WITH mp AS (
          SELECT match_id, issue, {period_sql} AS period, {label_sql} AS year_or_range
          FROM matches
        )
        SELECT period, year_or_range, COUNT(DISTINCT match_id), COUNT(DISTINCT issue)
        FROM mp
        GROUP BY period, year_or_range
        """
    ).fetchall()
    denominators = {
        (str(period), str(label)): (int(matches), int(issues))
        for period, label, matches, issues in match_rows
    }
    markets = ",".join("?" for _ in PROXY_SURFACES)
    vector_rows = c.execute(
        f"""
        WITH mp AS (
          SELECT match_id,
                 issue,
                 {period_sql} AS period,
                 {label_sql} AS year_or_range,
                 CASE WHEN issue IS NOT NULL AND match_idx IS NOT NULL
                            AND home IS NOT NULL AND away IS NOT NULL
                            AND handicap_line IS NOT NULL
                      THEN 1 ELSE 0 END AS identity_ok
          FROM matches
        )
        SELECT mp.period,
               mp.year_or_range,
               ms.snapshot,
               ms.market,
               COUNT(*) AS vector_rows,
               COUNT(DISTINCT ms.match_id) AS vector_matches,
               3 * COUNT(*) AS physical_cells,
               SUM((ms.v1 IS NOT NULL) + (ms.v2 IS NOT NULL) + (ms.v3 IS NOT NULL)) AS non_null_cells,
               SUM(CASE WHEN ms.v1 IS NOT NULL AND ms.v2 IS NOT NULL AND ms.v3 IS NOT NULL THEN 1 ELSE 0 END) AS complete_vectors,
               SUM(CASE WHEN ms.v1 IS NOT NULL AND ms.v2 IS NOT NULL AND ms.v3 IS NOT NULL
                              AND (ms.market <> 'euro_1x2'
                                   OR (CAST(ms.v1 AS REAL) > 0 AND CAST(ms.v2 AS REAL) > 0 AND CAST(ms.v3 AS REAL) > 0))
                        THEN 1 ELSE 0 END) AS valid_vectors,
               COUNT(DISTINCT CASE
                   WHEN ms.v1 IS NOT NULL AND ms.v2 IS NOT NULL AND ms.v3 IS NOT NULL
                        AND (ms.market <> 'euro_1x2'
                             OR (CAST(ms.v1 AS REAL) > 0 AND CAST(ms.v2 AS REAL) > 0 AND CAST(ms.v3 AS REAL) > 0))
                   THEN ms.match_id END) AS valid_matches,
               COUNT(DISTINCT CASE
                   WHEN mp.identity_ok = 1
                        AND ms.v1 IS NOT NULL AND ms.v2 IS NOT NULL AND ms.v3 IS NOT NULL
                        AND (ms.market <> 'euro_1x2'
                             OR (CAST(ms.v1 AS REAL) > 0 AND CAST(ms.v2 AS REAL) > 0 AND CAST(ms.v3 AS REAL) > 0))
                   THEN ms.match_id END) AS native_identity_valid_matches
        FROM market_snapshots ms
        JOIN mp ON mp.match_id = ms.match_id
        WHERE ms.snapshot IN ('initial', '10h', '1h')
          AND ms.market IN ({markets})
        GROUP BY mp.period, mp.year_or_range, ms.snapshot, ms.market
        ORDER BY mp.period, mp.year_or_range, ms.snapshot, ms.market
        """,
        tuple(PROXY_SURFACES),
    ).fetchall()
    out: list[dict[str, object]] = []
    for row in vector_rows:
        period, label, snapshot, market = map(str, row[:4])
        match_denominator, issue_denominator = denominators[(period, label)]
        policy = PROXY_SURFACES[market]
        out.append(
            {
                "source_id": "beidan_xlsm",
                "period": period,
                "year_or_range": label,
                "snapshot_horizon": snapshot,
                "market": market,
                "proxy_policy_id": PROXY_POLICY_ID,
                "vector_semantics": policy["vector_semantics"],
                "admissible_use": policy["admissible_use"],
                "role_gate_eligible": policy["role_gate_eligible"],
                "match_denominator": match_denominator,
                "issue_denominator": issue_denominator,
                "vector_row_count": int(row[4]),
                "distinct_matches_with_vector": int(row[5]),
                "physical_cell_count": int(row[6]),
                "non_null_physical_cell_count": int(row[7] or 0),
                "complete_vector_row_count": int(row[8] or 0),
                "valid_vector_row_count": int(row[9] or 0),
                "distinct_matches_with_valid_vector": int(row[10] or 0),
                "native_identity_valid_match_count": int(row[11] or 0),
                "missing_match_count": max(0, match_denominator - int(row[5])),
            }
        )
    return out


def _duplicate_profile(
    c: sqlite3.Connection, spec: SourceSpec, columns: set[str]
) -> dict[str, object]:
    if spec.source_id == "bjdc_500_capture":
        keys = [
            key
            for key in ("issue", "playid", "fetched_at", "row_idx", "outcome_code")
            if key in columns
        ]
    else:
        keys = [
            key
            for key in (spec.issue_column, spec.match_column)
            if key and key in columns
        ]
    if len(keys) < 2:
        return {
            "source_id": spec.source_id,
            "table": spec.coverage_table,
            "key_definition": "UNAVAILABLE",
            "duplicate_key_groups": -1,
            "duplicate_rows_beyond_first": -1,
            "reason": "NO_TWO_COMPONENT_NATIVE_KEY",
        }
    scope = _scope(spec)
    where = _join_scope(scope, " AND ".join(f"{_q(key)} IS NOT NULL" for key in keys))
    group = ", ".join(_q(key) for key in keys)
    result = c.execute(
        f"SELECT COUNT(*), COALESCE(SUM(n - 1), 0) FROM (SELECT COUNT(*) n FROM {_q(spec.coverage_table)}{where} GROUP BY {group} HAVING COUNT(*) > 1)"
    ).fetchone()
    return {
        "source_id": spec.source_id,
        "table": spec.coverage_table,
        "key_definition": "+".join(keys),
        "duplicate_key_groups": int(result[0]),
        "duplicate_rows_beyond_first": int(result[1]),
        "reason": "NATIVE_KEY_DUPLICATE_PROFILE",
    }


def _m_per_issue(
    c: sqlite3.Connection, spec: SourceSpec, columns: set[str]
) -> list[dict[str, object]]:
    if spec.source_id == "bjdc_500_capture":
        logical_keys = _capture_logical_match_key_columns(columns)
        if not logical_keys:
            return []
        scope = _join_scope(
            _scope(spec), " AND ".join(f"{_q(key)} IS NOT NULL" for key in logical_keys)
        )
        rows = c.execute(
            f"SELECT {_q('issue')}, COUNT(DISTINCT {_q('row_idx')}) FROM {_q(spec.coverage_table)}{scope} GROUP BY {_q('issue')} ORDER BY {_q('issue')}"
        ).fetchall()
        return [
            {
                "source_id": spec.source_id,
                "issue": str(issue),
                "m_matches": int(matches),
                "semantics": "P34_LOGICAL_MATCHES_BY_ISSUE_AND_ROW_IDX",
            }
            for issue, matches in rows
        ]
    if spec.issue_column not in columns or spec.match_column not in columns:
        return []
    scope = _join_scope(
        _scope(spec),
        f"{_q(spec.issue_column)} IS NOT NULL AND {_q(spec.match_column)} IS NOT NULL",
    )
    rows = c.execute(
        f"SELECT {_q(spec.issue_column)}, COUNT(DISTINCT {_q(spec.match_column)}) FROM {_q(spec.coverage_table)}{scope} GROUP BY {_q(spec.issue_column)} ORDER BY {_q(spec.issue_column)}"
    ).fetchall()
    return [
        {
            "source_id": spec.source_id,
            "issue": str(issue),
            "m_matches": int(matches),
            "semantics": "NATIVE_MATCH_COUNT",
        }
        for issue, matches in rows
    ]


def _snapshot_completeness(
    c: sqlite3.Connection, spec: SourceSpec
) -> list[dict[str, object]]:
    """Profile vector rows without calling every three-column layout an Mx3 triplet."""
    tables = set(_tables(c))
    out: list[dict[str, object]] = []
    if spec.source_id == "beidan_xlsm" and {"market_snapshots", "matches"}.issubset(
        tables
    ):
        rows = c.execute(
            """
            SELECT ms.snapshot,
                   ms.market,
                   COUNT(*) AS vector_rows,
                   COUNT(DISTINCT ms.match_id) AS vector_matches,
                   SUM((ms.v1 IS NOT NULL) + (ms.v2 IS NOT NULL) + (ms.v3 IS NOT NULL)) AS non_null_cells,
                   SUM(CASE WHEN ms.v1 IS NOT NULL AND ms.v2 IS NOT NULL AND ms.v3 IS NOT NULL
                            THEN 1 ELSE 0 END) AS complete_vectors,
                   SUM(CASE WHEN ms.v1 IS NOT NULL AND ms.v2 IS NOT NULL AND ms.v3 IS NOT NULL
                                  AND (ms.market <> 'euro_1x2'
                                       OR (CAST(ms.v1 AS REAL) > 0 AND CAST(ms.v2 AS REAL) > 0 AND CAST(ms.v3 AS REAL) > 0))
                            THEN 1 ELSE 0 END) AS valid_vectors,
                   COUNT(DISTINCT CASE
                       WHEN ms.v1 IS NOT NULL AND ms.v2 IS NOT NULL AND ms.v3 IS NOT NULL
                            AND (ms.market <> 'euro_1x2'
                                 OR (CAST(ms.v1 AS REAL) > 0 AND CAST(ms.v2 AS REAL) > 0 AND CAST(ms.v3 AS REAL) > 0))
                       THEN ms.match_id END) AS valid_vector_matches,
                   COUNT(DISTINCT CASE
                       WHEN ms.v1 IS NOT NULL AND ms.v2 IS NOT NULL AND ms.v3 IS NOT NULL
                            AND (ms.market <> 'euro_1x2'
                                 OR (CAST(ms.v1 AS REAL) > 0 AND CAST(ms.v2 AS REAL) > 0 AND CAST(ms.v3 AS REAL) > 0))
                            AND m.issue IS NOT NULL AND m.match_idx IS NOT NULL
                            AND m.home IS NOT NULL AND m.away IS NOT NULL
                            AND m.handicap_line IS NOT NULL
                       THEN ms.match_id END) AS native_identity_valid_matches
            FROM market_snapshots ms
            LEFT JOIN matches m ON m.match_id = ms.match_id
            WHERE ms.snapshot IN ('initial', '10h', '1h')
            GROUP BY ms.snapshot, ms.market
            ORDER BY ms.snapshot, ms.market
            """
        ).fetchall()
        for row in rows:
            market = str(row[1])
            policy = PROXY_SURFACES.get(
                market,
                {
                    "vector_semantics": "UNCLASSIFIED_THREE_COLUMN_LAYOUT",
                    "admissible_use": "RAW_ONLY",
                    "role_gate_eligible": False,
                    "downstream_requirement": "SOURCE_SPECIFIC_REVIEW_REQUIRED",
                },
            )
            out.append(
                {
                    "source_id": spec.source_id,
                    "market": market,
                    "snapshot_horizon": str(row[0]),
                    "time_semantics": "RETROSPECTIVE_RELATIVE_PROXY",
                    "proxy_policy_id": PROXY_POLICY_ID,
                    "vector_semantics": policy["vector_semantics"],
                    "admissible_use": policy["admissible_use"],
                    "role_gate_eligible": policy["role_gate_eligible"],
                    "downstream_requirement": policy["downstream_requirement"],
                    "vector_row_count": int(row[2]),
                    "physical_cell_count": int(row[2]) * 3,
                    "non_null_physical_cell_count": int(row[4] or 0),
                    "distinct_matches_with_vector": int(row[3]),
                    "complete_vector_row_count": int(row[5] or 0),
                    "valid_vector_row_count": int(row[6] or 0),
                    "distinct_matches_with_valid_vector": int(row[7] or 0),
                    "native_identity_valid_match_count": int(row[8] or 0),
                    "missing_or_invalid_vector_rows": int(row[2]) - int(row[6] or 0),
                }
            )
    if spec.source_id == "bjdc_500_capture" and "live_market_sp_snapshots" in tables:
        rows = c.execute(
            """
            SELECT COUNT(*) AS cells,
                   COUNT(DISTINCT issue || '|' || fetched_at || '|' || row_idx) AS snapshot_matches,
                   SUM(CASE WHEN sp IS NOT NULL THEN 1 ELSE 0 END) AS non_null_cells,
                   SUM(CASE WHEN sp IS NULL OR sp <= 0 THEN 1 ELSE 0 END) AS bad_sp
            FROM live_market_sp_snapshots
            WHERE market_key='handicap_3way'
            """
        ).fetchone()
        triples = c.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT issue, fetched_at, row_idx
                FROM live_market_sp_snapshots
                WHERE market_key='handicap_3way'
                GROUP BY issue, fetched_at, row_idx
                HAVING COUNT(DISTINCT outcome_code)=3
                   AND SUM(CASE WHEN sp IS NOT NULL AND sp > 0 THEN 1 ELSE 0 END)=3
            )
            """
        ).fetchone()[0]
        out.append(
            {
                "source_id": spec.source_id,
                "market": "handicap_3way",
                "snapshot_horizon": "observed_capture",
                "time_semantics": "MUTABLE_UNFROZEN",
                "proxy_policy_id": "NOT_APPLICABLE_FORWARD_CAPTURE",
                "vector_semantics": "P34_OUTCOME_CELL_TRIPLET",
                "admissible_use": "RAW_ONLY_PENDING_CLOCK_AND_SEAL",
                "role_gate_eligible": False,
                "downstream_requirement": "SEAL_AND_DEFINE_CLOCK_POLICY_IN_252",
                "vector_row_count": int(rows[1]),
                "physical_cell_count": int(rows[0]),
                "non_null_physical_cell_count": int(rows[2] or 0),
                "distinct_matches_with_vector": int(rows[1]),
                "complete_vector_row_count": int(triples),
                "valid_vector_row_count": int(triples),
                "distinct_matches_with_valid_vector": int(triples),
                "native_identity_valid_match_count": int(triples),
                "missing_or_invalid_vector_rows": int(rows[1]) - int(triples),
            }
        )
    return out


def _historical_proxy_gate(c: sqlite3.Connection) -> tuple[int, int]:
    """Return common valid Euro-proxy matches and qualifying bucket count.

    Each qualifying match must have at least one positive three-way Euro vector
    at every accepted relative horizon and a same-source native identity plus
    Beijing handicap line.  No other table/field count can satisfy this gate.
    """
    if not {"market_snapshots", "matches"}.issubset(set(_tables(c))):
        return 0, 0
    row = c.execute(
        """
        SELECT COUNT(*), COALESCE(MIN(bucket_count), 0)
        FROM (
            SELECT ms.match_id,
                   COUNT(DISTINCT CASE
                       WHEN ms.v1 IS NOT NULL AND ms.v2 IS NOT NULL AND ms.v3 IS NOT NULL
                            AND CAST(ms.v1 AS REAL) > 0
                            AND CAST(ms.v2 AS REAL) > 0
                            AND CAST(ms.v3 AS REAL) > 0
                       THEN ms.snapshot END) AS bucket_count
            FROM market_snapshots ms
            JOIN matches m ON m.match_id = ms.match_id
            WHERE ms.market = 'euro_1x2'
              AND ms.snapshot IN ('initial', '10h', '1h')
              AND m.issue IS NOT NULL AND m.match_idx IS NOT NULL
              AND m.home IS NOT NULL AND m.away IS NOT NULL
              AND m.handicap_line IS NOT NULL
            GROUP BY ms.match_id
            HAVING bucket_count = 3
        )
        """
    ).fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def _candidate_mapping(
    c_xlsm: sqlite3.Connection, c_features: sqlite3.Connection
) -> list[dict[str, object]]:
    # Candidate evidence only: no identity policy is accepted here.  Lower requires
    # same issue + normalized home/away + calendar date; upper relaxes date.
    x = c_xlsm.execute(
        "SELECT issue, lower(trim(home)), lower(trim(away)), substr(kickoff_ts,1,10) FROM matches WHERE issue IS NOT NULL AND home IS NOT NULL AND away IS NOT NULL AND kickoff_ts >= '1900-01-01'"
    ).fetchall()
    f = c_features.execute(
        "SELECT issue, lower(trim(home)), lower(trim(away)), substr(kickoff,1,10) FROM matches WHERE issue IS NOT NULL AND home IS NOT NULL AND away IS NOT NULL AND kickoff >= '1900-01-01'"
    ).fetchall()
    x_lower = [(str(a), str(b), str(d), str(e)) for a, b, d, e in x]
    f_lower = {(str(a), str(b), str(d), str(e)) for a, b, d, e in f}
    x_upper = [(str(a), str(b), str(d)) for a, b, d, _ in x]
    f_upper = {(str(a), str(b), str(d)) for a, b, d, _ in f}
    # Both bounds are counts of xlsm rows that have at least one candidate;
    # relaxation can only enlarge the eligible xlsm row set.
    lower = sum(key in f_lower for key in x_lower)
    upper = sum(key in f_upper for key in x_upper)
    return [
        {
            "level": "CANDIDATE_MAPPED_RANGE",
            "left_source": "beidan_xlsm.matches",
            "right_source": "beidan_features.matches",
            "mapping_assumption": "lower=issue+normalized_home+normalized_away+calendar_date; upper=issue+normalized_home+normalized_away",
            "lower_bound": lower,
            "upper_bound": upper,
            "authoritative": False,
            "decision": "NON_AUTHORITATIVE_PROPOSED_MAPPING_PENDING_251",
        }
    ]


# The intersection levels a package must contain. One definition, used by the verifier and by the
# fixture builder: when these were written out twice they drifted, and the fixture agreeing with
# itself hid a verifier that rejected every package production actually emitted.
INTERSECTION_LEVELS = (
    "RAW_PRESENT",
    "CANDIDATE_MAPPED_RANGE",
    "CANONICAL_CAUSAL_INTERSECTION",
)


def _intersections(data_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "level": "RAW_PRESENT",
            "left_source": "beidan_xlsm.market_snapshots",
            "right_source": "beidan_xlsm.matches",
            "mapping_assumption": "native fields only",
            "lower_bound": "initial/10h/1h field families profiled",
            "upper_bound": "initial/10h/1h field families profiled",
            "authoritative": True,
            "decision": "HISTORICAL_PROXY_ONLY",
        }
    ]
    xp, fp = (
        data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite",
        data_root / "beidan_features.db",
    )
    if xp.exists() and fp.exists():
        a, b = _connect(xp), _connect(fp)
        try:
            rows.extend(_candidate_mapping(a, b))
        finally:
            a.close()
            b.close()
    else:
        rows.append(
            {
                "level": "CANDIDATE_MAPPED_RANGE",
                "left_source": "beidan_xlsm.matches",
                "right_source": "beidan_features.matches",
                "mapping_assumption": "unavailable",
                "lower_bound": "NOT_EVALUATED_MISSING_SOURCE",
                "upper_bound": "NOT_EVALUATED_MISSING_SOURCE",
                "authoritative": False,
                "decision": "MISSING_SOURCE",
            }
        )
    rows.append(
        {
            "level": "CANONICAL_CAUSAL_INTERSECTION",
            "left_source": "all",
            "right_source": "all",
            "mapping_assumption": "frozen identity+temporal policy required",
            "lower_bound": canonical_causal_intersection(),
            "upper_bound": canonical_causal_intersection(),
            "authoritative": False,
            "decision": "DEFERRED_TO_251_AND_252",
        }
    )
    return rows


def profile(data_root: Path) -> dict[str, list[dict[str, object]]]:
    inventory: list[dict[str, object]] = []
    fields: list[dict[str, object]] = []
    coverage: list[dict[str, object]] = []
    periods: list[dict[str, object]] = []
    duplicates: list[dict[str, object]] = []
    triplets: list[dict[str, object]] = []
    proxy_periods: list[dict[str, object]] = []
    m_distribution: list[dict[str, object]] = []
    schemas: list[dict[str, object]] = []
    for spec in SOURCES:
        path = data_root / spec.relative_path
        record = asdict(spec)
        record.pop("decision_fields")
        record.update(
            {
                "hist40_binding": HIST40_RELEASE["tag"],
                "assessment_basis": "RECOMPUTED_CHANGED_OR_MUTABLE"
                if spec.mutable
                else "INHERITED_R8_AND_REPROFILED",
                "relative_path": spec.relative_path,
            }
        )
        if not path.exists():
            record.update(
                {
                    "exists": False,
                    "content_sha256": "",
                    "consistency": "MISSING_UNREADABLE",
                    "role": "RECOVER",
                    "source_clock_complete": False,
                    "capture_clock_complete": False,
                }
            )
            inventory.append(record)
            continue
        before = path.stat()
        content_sha256 = "MUTABLE_UNFROZEN_NO_HASH" if spec.mutable else _sha256(path)
        baseline_asset_bound = hist40_baseline_applies(spec.source_id, content_sha256)
        connection = _connect(path)
        try:
            tables = _tables(connection)
            columns = (
                {name for name, _ in _columns(connection, spec.coverage_table)}
                if spec.coverage_table in tables
                else set()
            )
            aggregate, source_fields = _source_aggregate(connection, spec, columns)
            source_triplets = _snapshot_completeness(connection, spec)
            source_clock_complete = bool(
                spec.source_clock_column
                and spec.source_clock_column in columns
                and next(
                    (
                        row["null_or_blank_count"]
                        for row in source_fields
                        if row["field"] == spec.source_clock_column
                    ),
                    1,
                )
                == 0
            )
            capture_clock_complete = bool(
                spec.capture_clock_column
                and spec.capture_clock_column in columns
                and next(
                    (
                        row["null_or_blank_count"]
                        for row in source_fields
                        if row["field"] == spec.capture_clock_column
                    ),
                    1,
                )
                == 0
            )
            proxy_gate_valid_matches, proxy_gate_bucket_count = (
                _historical_proxy_gate(connection)
                if spec.source_id == "beidan_xlsm"
                else (0, 0)
            )
            role = role_from_profile(
                spec,
                coverage_status=str(aggregate["coverage_status"]),
                proxy_gate_valid_matches=proxy_gate_valid_matches,
                proxy_gate_bucket_count=proxy_gate_bucket_count,
                source_clock_complete=source_clock_complete,
                capture_clock_complete=capture_clock_complete,
            )
            schema_drafts: list[dict[str, object]] = []
            for table in tables:
                for ordinal, (name, typ) in enumerate(_columns(connection, table), 1):
                    baseline = hist40_baseline_record(spec.source_id, table, name)
                    lane = profile_field_lane(
                        spec.source_id, table, name, role, content_sha256
                    )
                    schema_drafts.append(
                        {
                            "source_id": spec.source_id,
                            "table": table,
                            "ordinal": ordinal,
                            "column": name,
                            "sqlite_type": typ,
                            "baseline_r8_record": baseline is not None,
                            "baseline_binding": "R8_EXACT_ASSET_BOUND"
                            if baseline_asset_bound and baseline
                            else (
                                "R8_ASSET_CHANGED" if baseline else "NO_R8_FIELD_RECORD"
                            ),
                            "baseline_pre_match_feature_eligible": baseline.get(
                                "pre_match_feature_eligible", ""
                            )
                            if baseline
                            else "",
                            "baseline_admissible_use": baseline.get(
                                "admissible_use", ""
                            )
                            if baseline
                            else "",
                            "baseline_timestamp_grade": baseline.get(
                                "timestamp_grade", ""
                            )
                            if baseline
                            else "",
                            "admissible_use": lane,
                            "terminal_denylisted": lane == "SETTLEMENT_ONLY",
                        }
                    )
            r8_generic_admissible_field_count = sum(
                row["admissible_use"] == "HISTORICAL_PROXY_CANDIDATE"
                for row in schema_drafts
            )
            for row in schema_drafts:
                lane = profile_field_lane(
                    spec.source_id,
                    str(row["table"]),
                    str(row["column"]),
                    role,
                    content_sha256,
                )
                row["admissible_use"] = lane
                row["terminal_denylisted"] = lane == "SETTLEMENT_ONLY"
                row["field_family"] = _field_family(
                    str(row["table"]), str(row["column"]), lane
                )
                row["label_or_settlement_field"] = lane == "SETTLEMENT_ONLY"
            annotate_decision_field_profiles(source_fields, schema_drafts)
            fields.extend(source_fields)
            coverage.append(dict(aggregate, source_id=spec.source_id, lane=spec.lane))
            periods.extend(_coverage_strata(connection, spec, columns))
            duplicates.append(_duplicate_profile(connection, spec, columns))
            m_distribution.extend(_m_per_issue(connection, spec, columns))
            triplets.extend(source_triplets)
            if spec.source_id == "beidan_xlsm":
                proxy_periods.extend(_proxy_coverage_by_period(connection))
            schemas.extend(schema_drafts)
        finally:
            connection.close()
        after = path.stat()
        stable = (before.st_size, before.st_mtime_ns) == (
            after.st_size,
            after.st_mtime_ns,
        )
        record.update(
            {
                "exists": True,
                "size_bytes": before.st_size,
                "mtime_ns": before.st_mtime_ns,
                "content_sha256": content_sha256,
                "consistency": "MUTABLE_UNFROZEN"
                if spec.mutable
                else ("CONSISTENT_READ" if stable else "MUTATED_DURING_READ"),
                "hist40_asset_bound": baseline_asset_bound,
                "role": role,
                "source_clock_complete": source_clock_complete,
                "capture_clock_complete": capture_clock_complete,
                "proxy_policy_id": PROXY_POLICY_ID
                if spec.source_id == "beidan_xlsm"
                else "",
                "proxy_gate_valid_matches": proxy_gate_valid_matches,
                "proxy_gate_bucket_count": proxy_gate_bucket_count,
                "r8_generic_admissible_field_count": r8_generic_admissible_field_count,
            }
        )
        inventory.append(record)
    return {
        "source_inventory": lineage_decisions(inventory),
        "field_inventory": schemas,
        "hist40_scope_overrides": [dict(row) for row in HIST40_SCOPE_OVERRIDES],
        "field_profile": fields,
        "coverage": coverage,
        "period_coverage": periods,
        "proxy_coverage_by_period": proxy_periods,
        "duplicate_profile": duplicates,
        "m_per_issue_distribution": m_distribution,
        "proxy_surface_profile": triplets,
        "intersections": _intersections(data_root),
    }


def _csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = sorted({k for r in rows for k in r}) if rows else ["status"]
    with path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=names, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))


def _roles(inventory: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for item in inventory:
        role = str(item["role"])
        lane = str(item["lane"])
        routing = SOURCE_ROUTING.get(
            lane,
            {
                "advance_to_251": False,
                "advance_to_252": False,
                "decision": "UNMAPPED_LANE_NO_ROUTING",
            },
        )
        rows.append(
            {
                "source_id": item["source_id"],
                "lane": lane,
                "role": role,
                **routing,
            }
        )
    return rows


def annotate_decision_field_profiles(
    profiles: list[dict[str, object]], field_inventory: list[dict[str, object]]
) -> None:
    """Bind each decision-field nullness profile to its canonical field lane."""
    lanes = {
        (str(row["source_id"]), str(row["table"]), str(row["column"])): str(
            row["admissible_use"]
        )
        for row in field_inventory
    }
    for row in profiles:
        lane = lanes.get(
            (str(row["source_id"]), str(row["table"]), str(row["field"])), "RAW_ONLY"
        )
        row["admissible_use"] = lane
        row["availability_used_for_role"] = lane == "HISTORICAL_PROXY_CANDIDATE"


def source_feature_availability(
    field_inventory: list[dict[str, object]],
    inventory: list[dict[str, object]],
    proxy_surfaces: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Keep generic R8 fields separate from Issue-250 scoped surfaces."""
    out: list[dict[str, object]] = []
    for item in inventory:
        source_id = str(item["source_id"])
        for family in (
            "identity_schedule",
            "timestamp",
            "market_feature",
            "label_settlement",
        ):
            fields = [
                row
                for row in field_inventory
                if str(row["source_id"]) == source_id
                and str(row["field_family"]) == family
            ]
            generic_admissible = sum(
                row["admissible_use"] == "HISTORICAL_PROXY_CANDIDATE" for row in fields
            )
            source_surfaces = [
                row for row in proxy_surfaces if str(row["source_id"]) == source_id
            ]
            if family == "market_feature":
                surface_evidence = sum(
                    str(row.get("admissible_use", ""))
                    in {
                        "HISTORICAL_PROXY_CANDIDATE",
                        "HISTORICAL_PROXY_DESCRIPTIVE",
                        "AUXILIARY_RELATIVE_PROXY",
                    }
                    for row in source_surfaces
                )
            elif family == "identity_schedule":
                surface_evidence = int(
                    any(
                        int(row.get("native_identity_valid_match_count", 0)) > 0
                        for row in source_surfaces
                    )
                )
            elif family == "timestamp":
                surface_evidence = len(
                    {
                        str(row.get("snapshot_horizon", ""))
                        for row in source_surfaces
                        if row.get("time_semantics") == "RETROSPECTIVE_RELATIVE_PROXY"
                    }
                )
            else:
                surface_evidence = 0
            out.append(
                {
                    "source_id": source_id,
                    "field_family": family,
                    "observed_field_count": len(fields),
                    "r8_generic_admissible_field_count": generic_admissible,
                    "issue250_scoped_surface_evidence_count": surface_evidence,
                    "present": generic_admissible > 0 or surface_evidence > 0,
                    "role": item["role"],
                    "admissibility_note": "R8_GENERIC_FIELDS_AND_ISSUE250_SCOPED_SURFACES_REPORTED_SEPARATELY",
                }
            )
    return out


def verify_hist40_scope_overrides(rows: list[dict[str, str]]) -> list[str]:
    expected = {
        (row["source_id"], row["table"], row["column"], row["market"]): row
        for row in HIST40_SCOPE_OVERRIDES
    }
    observed = {
        (row["source_id"], row["table"], row["column"], row["market"]): row
        for row in rows
    }
    problems: list[str] = []
    if set(observed) != set(expected):
        problems.append("R8 field-market override key mismatch")
        return problems
    for key, wanted in expected.items():
        for column in (
            "scope_level",
            "admissible_use",
            "integration_decision",
            "destination_layer",
            "provenance_grade",
        ):
            if observed[key].get(column) != wanted[column]:
                problems.append(
                    f"R8 field-market override mismatch: {'.'.join(key)}:{column}"
                )
    return problems


def verify_proxy_role_gate(
    source_inventory: list[dict[str, str]],
    proxy_surfaces: list[dict[str, str]],
) -> list[str]:
    """Recompute the source role from the exact accepted Euro proxy surface."""
    source = next(
        (row for row in source_inventory if row["source_id"] == "beidan_xlsm"), None
    )
    if source is None:
        return ["historical proxy source missing"]
    accepted = [
        row
        for row in proxy_surfaces
        if row.get("source_id") == "beidan_xlsm"
        and row.get("market") == "euro_1x2"
        and row.get("proxy_policy_id") == PROXY_POLICY_ID
        and row.get("role_gate_eligible", "").lower() == "true"
    ]
    buckets = {row.get("snapshot_horizon", "") for row in accepted}
    positive = all(
        int(row.get("native_identity_valid_match_count", 0)) > 0 for row in accepted
    )
    expected = (
        "HISTORICAL_PROXY"
        if buckets == set(PROXY_SNAPSHOTS) and positive
        else "RAW_ONLY"
    )
    return (
        []
        if source.get("role") == expected
        else ["historical proxy role gate recomputation mismatch"]
    )


def verify_source_routing(
    source_inventory: list[dict[str, str]], source_roles: list[dict[str, str]]
) -> list[str]:
    """Recompute all #251/#252 routing from the explicit source-lane contract."""
    expected = {str(row["source_id"]): row for row in _roles(source_inventory)}
    observed = {row["source_id"]: row for row in source_roles}
    if set(expected) != set(observed):
        return ["source routing key mismatch"]
    problems: list[str] = []
    for source_id, wanted in expected.items():
        row = observed[source_id]
        for column in ("lane", "role", "decision"):
            if str(row.get(column, "")) != str(wanted[column]):
                problems.append(f"source routing mismatch: {source_id}:{column}")
        for column in ("advance_to_251", "advance_to_252"):
            actual = str(row.get(column, "")).lower() == "true"
            if actual is not bool(wanted[column]):
                problems.append(f"source routing mismatch: {source_id}:{column}")
    return problems


def verify_field_lane_crosswalk(
    field_inventory: list[dict[str, str]], source_inventory: list[dict[str, str]]
) -> list[str]:
    """Independently recompute every packaged field lane from R8 + source identity."""
    sources = {row["source_id"]: row for row in source_inventory}
    problems: list[str] = []
    for row in field_inventory:
        source = sources.get(row["source_id"])
        if source is None:
            problems.append(f"field lane source missing: {row['source_id']}")
            continue
        expected = profile_field_lane(
            row["source_id"],
            row["table"],
            row["column"],
            source["role"],
            source.get("content_sha256", ""),
        )
        if row.get("admissible_use") != expected:
            problems.append(
                f"field lane recomputation mismatch: {row['source_id']}.{row['table']}.{row['column']}"
            )
    return problems


def _simple_svg(
    path: Path, title: str, rows: list[dict[str, object]], label: str, value: str
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    vals = [
        max(
            0,
            int(r.get(value, 0) if str(r.get(value, "")).lstrip("-").isdigit() else 0),
        )
        for r in rows
    ]
    maxv = max(vals, default=1)
    h = 50 + 32 * max(1, len(rows))
    text = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{h}"><style>text{{font-family:monospace;font-size:12px}}</style><text x="10" y="20">{title}</text>'
    ]
    for i, (r, v) in enumerate(zip(rows, vals)):
        y = 36 + i * 32
        width = 650 * v / maxv if maxv else 0
        text.append(
            f'<text x="10" y="{y + 13}">{str(r.get(label, ""))[:30]}</text><rect x="220" y="{y}" width="{width:.1f}" height="17" fill="#2f6f9f"/><text x="{230 + width:.1f}" y="{y + 13}">{v}</text>'
        )
    path.write_text("".join(text) + "</svg>", encoding="utf-8")


def rewrite_checksums(package: Path) -> None:
    values = {
        p.relative_to(package).as_posix(): _sha256(p)
        for p in sorted(package.rglob("*"))
        if p.is_file() and p.name != "SHA256SUMS.json"
    }
    (package / "SHA256SUMS.json").write_text(
        json.dumps(values, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _semantic_hash(package: Path, relative: str) -> str:
    return _sha256(package / relative)


def _m_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[int]] = {}
    for row in rows:
        grouped.setdefault(str(row["source_id"]), []).append(int(row["m_matches"]))
    out: list[dict[str, object]] = []
    for source_id, values in sorted(grouped.items()):
        ordered = sorted(values)
        out.append(
            {
                "source_id": source_id,
                "issue_count": len(values),
                "median_m": ordered[len(ordered) // 2],
                "min_m": ordered[0],
                "max_m": ordered[-1],
            }
        )
    return out


def _fsync_tree(root: Path) -> None:
    for path in sorted((item for item in root.rglob("*") if item.is_file())):
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    directories = [root, *(item for item in root.rglob("*") if item.is_dir())]
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _publish_new_directory(stage: Path, target: Path) -> None:
    """Crash-safe write-once publication; never delete an accepted package."""
    _fsync_tree(stage)
    if target.exists():
        raise FileExistsError(f"refusing to replace existing package: {target}")
    os.replace(stage, target)
    descriptor = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verify_package(
    package: Path, *, trusted_anchor: dict[str, object] | None = None
) -> dict[str, object]:
    problems = []
    try:
        manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
        sums = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    except Exception as err:
        return {"verified": False, "problems": [f"unreadable package: {err}"]}
    if manifest.get("issue") != ISSUE:
        problems.append("manifest issue mismatch")
    if manifest.get("implementation_sha256", "") != _sha256(Path(__file__)):
        problems.append("producer implementation hash mismatch")
    if manifest.get("crosswalk_sha256", "") != _sha256(HIST40_CROSSWALK):
        problems.append("R8 crosswalk hash mismatch")
    if trusted_anchor is None:
        problems.append("external trusted anchor required")
    else:
        if trusted_anchor.get("issue") != ISSUE:
            problems.append("trusted anchor issue mismatch")
        if trusted_anchor.get("implementation_sha256", "") != manifest.get(
            "implementation_sha256", ""
        ):
            problems.append("trusted anchor implementation mismatch")
        if trusted_anchor.get("crosswalk_sha256", "") != manifest.get(
            "crosswalk_sha256", ""
        ):
            problems.append("trusted anchor crosswalk mismatch")
        if trusted_anchor.get("manifest_sha256", "") != _sha256(
            package / "MANIFEST.json"
        ):
            problems.append("trusted anchor manifest mismatch")
        anchored_hashes = trusted_anchor.get("semantic_hashes")
        if not isinstance(anchored_hashes, dict):
            problems.append("trusted anchor semantic hashes missing")
    payload_hashes = {
        path.relative_to(package).as_posix(): _sha256(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name not in {"MANIFEST.json", "SHA256SUMS.json"}
    }
    declared_hashes = manifest.get("semantic_hashes", {})
    if not isinstance(declared_hashes, dict) or declared_hashes != payload_hashes:
        problems.append("manifest payload hash inventory mismatch")
    if trusted_anchor is not None and isinstance(
        trusted_anchor.get("semantic_hashes"), dict
    ):
        if trusted_anchor["semantic_hashes"] != payload_hashes:
            problems.append("trusted anchor payload hash inventory mismatch")
    observed = {
        p.relative_to(package).as_posix(): _sha256(p)
        for p in sorted(package.rglob("*"))
        if p.is_file() and p.name != "SHA256SUMS.json"
    }
    if sums != observed:
        problems.append("checksum inventory mismatch")
    required = (
        "tables/source_inventory.csv",
        "tables/field_inventory.csv",
        "tables/hist40_scope_overrides.csv",
        "tables/source_role_matrix.csv",
        "tables/intersection_levels.csv",
        "tables/field_profile.csv",
        "tables/coverage_by_source.csv",
        "tables/coverage_by_period.csv",
        "tables/proxy_coverage_by_period.csv",
        "tables/proxy_surface_profile.csv",
        "tables/source_feature_availability.csv",
        "tables/duplicate_profile.csv",
        "tables/m_per_issue_distribution.csv",
        "tables/unresolved_question_ledger.csv",
        "evidence/req_sc_evidence.csv",
        "figures/source_feature_heatmap.svg",
        "figures/time_issue_coverage.svg",
        "figures/m_per_issue.svg",
        "REPORT.md",
    )
    for rel in required:
        if not (package / rel).exists():
            problems.append(f"missing decision artifact: {rel}")
        elif manifest.get("semantic_hashes", {}).get(rel) != _semantic_hash(
            package, rel
        ):
            problems.append(f"semantic hash mismatch: {rel}")
    if (package / "tables/source_inventory.csv").exists() and (
        package / "tables/source_role_matrix.csv"
    ).exists():
        inventory_rows = _read_csv(package / "tables/source_inventory.csv")
        role_rows = _read_csv(package / "tables/source_role_matrix.csv")
        inv = {r["source_id"]: r["role"] for r in inventory_rows}
        roles = {r["source_id"]: r["role"] for r in role_rows}
        if inv != roles:
            problems.append("role recomputation mismatch")
        problems.extend(verify_source_routing(inventory_rows, role_rows))
    if (package / "tables/source_inventory.csv").exists() and (
        package / "tables/field_inventory.csv"
    ).exists():
        problems.extend(
            verify_field_lane_crosswalk(
                _read_csv(package / "tables/field_inventory.csv"),
                _read_csv(package / "tables/source_inventory.csv"),
            )
        )
    if (package / "tables/hist40_scope_overrides.csv").exists():
        problems.extend(
            verify_hist40_scope_overrides(
                _read_csv(package / "tables/hist40_scope_overrides.csv")
            )
        )
    if (package / "tables/source_inventory.csv").exists() and (
        package / "tables/proxy_surface_profile.csv"
    ).exists():
        problems.extend(
            verify_proxy_role_gate(
                _read_csv(package / "tables/source_inventory.csv"),
                _read_csv(package / "tables/proxy_surface_profile.csv"),
            )
        )
    if (package / "tables/coverage_by_period.csv").exists():
        coverage_rows = _read_csv(package / "tables/coverage_by_period.csv")
        if any("cell_count" in row for row in coverage_rows):
            problems.append("coverage record grain mislabeled as cell_count")
    if (package / "tables/proxy_coverage_by_period.csv").exists():
        for row in _read_csv(package / "tables/proxy_coverage_by_period.csv"):
            if int(row["physical_cell_count"]) != 3 * int(row["vector_row_count"]):
                problems.append("proxy physical-cell denominator mismatch")
                break
            if int(row["non_null_physical_cell_count"]) > int(
                row["physical_cell_count"]
            ):
                problems.append("proxy non-null cells exceed denominator")
                break
    if (package / "tables/intersection_levels.csv").exists():
        levels = {
            r["level"] for r in _read_csv(package / "tables/intersection_levels.csv")
        }
        if levels != set(INTERSECTION_LEVELS):
            problems.append("three-level intersection closure mismatch")
    return {"verified": not problems, "problems": problems}


def build_package(repo_root: Path, data_root: Path, target: Path | None = None) -> Path:
    package = target or repo_root / "results" / PACKAGE_NAME
    package.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{package.name}.", dir=package.parent))
    try:
        data = profile(data_root)
        inventory = data["source_inventory"]
        roles = _roles(inventory)
        availability = source_feature_availability(
            data["field_inventory"], inventory, data["proxy_surface_profile"]
        )
        names = {
            "source_inventory": inventory,
            "field_inventory": data["field_inventory"],
            "hist40_scope_overrides": data["hist40_scope_overrides"],
            "field_profile": data["field_profile"],
            "coverage_by_source": data["coverage"],
            "coverage_by_period": data["period_coverage"],
            "proxy_coverage_by_period": data["proxy_coverage_by_period"],
            "duplicate_profile": data["duplicate_profile"],
            "m_per_issue_distribution": data["m_per_issue_distribution"],
            "proxy_surface_profile": data["proxy_surface_profile"],
            "intersection_levels": data["intersections"],
            "source_role_matrix": roles,
            "source_feature_availability": availability,
        }
        for name, rows in names.items():
            _csv(stage / "tables" / f"{name}.csv", rows)
        unresolved = [
            {
                "question_id": "U1",
                "question": "Which proposed mappings become canonical?",
                "owner_issue": "#251",
                "status": "DEFERRED",
            },
            {
                "question_id": "U2",
                "question": "What sealing/source-clock rules promote forward evidence?",
                "owner_issue": "#252",
                "status": "DEFERRED",
            },
            {
                "question_id": "U3",
                "question": "Which measured gaps justify recovery?",
                "owner_issue": "#235/#236/#237/#248",
                "status": "PI_DECISION_REQUIRED",
            },
        ]
        _csv(stage / "tables/unresolved_question_ledger.csv", unresolved)
        evidence_paths = {
            1: "MANIFEST.json;REPLAY via scripts/build_bj250_source_census.py",
            2: "tables/source_inventory.csv",
            3: "tables/coverage_by_period.csv;tables/proxy_coverage_by_period.csv;tables/intersection_levels.csv",
            4: "tables/proxy_surface_profile.csv",
            5: "tables/field_inventory.csv;tables/hist40_scope_overrides.csv",
            6: "tables/source_role_matrix.csv;tables/unresolved_question_ledger.csv",
            7: "MANIFEST.json;SHA256SUMS.json",
            8: "independent EV required",
            9: "MANIFEST.json.hist40_baseline;tables/source_inventory.csv",
            10: "tables/proxy_surface_profile.csv;REPORT.md",
            11: "tables/source_inventory.csv.lineage_root",
            12: "tables/intersection_levels.csv",
            13: "MANIFEST.json.prohibitions",
            14: "tables/coverage_by_period.csv;tables/proxy_coverage_by_period.csv",
            15: "tables/source_role_matrix.csv;PI/user checkpoint required",
        }
        evidence = [
            {
                "requirement": f"REQ-SC{x:02d}",
                "status": "PI_DECISION_PENDING"
                if x == 15
                else ("EV_PENDING" if x == 8 else "EVIDENCE_PRESENT"),
                "evidence": evidence_paths[x],
            }
            for x in range(1, 16)
        ]
        _csv(stage / "evidence/req_sc_evidence.csv", evidence)
        _simple_svg(
            stage / "figures/source_feature_heatmap.svg",
            "Source x field-family scoped availability",
            availability,
            "source_id",
            "issue250_scoped_surface_evidence_count",
        )
        _simple_svg(
            stage / "figures/time_issue_coverage.svg",
            "Time/issue source-record coverage",
            data["period_coverage"],
            "year_or_range",
            "coverage_record_count",
        )
        _simple_svg(
            stage / "figures/m_per_issue.svg",
            "Median M per source",
            _m_summary(data["m_per_issue_distribution"]),
            "source_id",
            "median_m",
        )
        historical = next(row for row in inventory if row["source_id"] == "beidan_xlsm")
        report = f"""# BJ-UNIFIED-SOURCE-CENSUS-001 R5 PI takeover

Assessment only: no crawl, backfill, imputation, model, ticket or ROI work occurred.

The historical source role is recomputed from one coherent surface under `{PROXY_POLICY_ID}`: same-source native identity + Beijing line + positive `euro_1x2` vectors at all of `initial/10h/1h`. It is not inferred by combining unrelated table counts. Common gate-valid matches: **{historical["proxy_gate_valid_matches"]}**; qualifying buckets: **{historical["proxy_gate_bucket_count"]}/3**.

Match, vector-row and physical-cell denominators are separate. Generic R8 field decisions remain in `field_inventory.csv`; the two finer R8 field×market prohibitions remain intact in `hist40_scope_overrides.csv`. Candidate identity ranges are non-authoritative and canonical causal overlap remains deferred to #251/#252. Mutable forward sources remain raw/unfrozen until #252 defines and verifies clock/sealing rules.

Downstream routing is explicit: the historical relative-time proxy and both strict-forward lanes advance to #252; identity support advances only to #251; settlement and derived copies advance to neither.
"""
        (stage / "REPORT.md").write_text(report, encoding="utf-8")
        semantic = {
            path.relative_to(stage).as_posix(): _sha256(path)
            for path in sorted(stage.rglob("*"))
            if path.is_file() and path.name not in {"MANIFEST.json", "SHA256SUMS.json"}
        }
        manifest = {
            "issue": ISSUE,
            "package": PACKAGE_NAME,
            "assessment_only": True,
            "data_root_supplied": True,
            "hist40_baseline": HIST40_RELEASE,
            "proxy_policy_id": PROXY_POLICY_ID,
            "logical_sources": len(inventory),
            "roles": {row["source_id"]: row["role"] for row in inventory},
            "canonical_causal_intersection": canonical_causal_intersection(),
            "semantic_hashes": semantic,
            "implementation_source": "src/source_census/census.py",
            "implementation_sha256": _sha256(Path(__file__)),
            "crosswalk_sha256": _sha256(HIST40_CROSSWALK),
            "prohibitions": [
                "no_crawl",
                "no_backfill",
                "no_imputation",
                "no_model",
                "no_roi",
                "no_identity_or_temporal_policy_freeze",
            ],
        }
        (stage / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        rewrite_checksums(stage)
        verdict = verify_package(stage, trusted_anchor=package_anchor(stage))
        if not verdict["verified"]:
            raise RuntimeError(str(verdict["problems"]))
        _publish_new_directory(stage, package)
        return package
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def build_fixture_package(package: Path) -> Path:
    """Build a tiny, semantically complete package for verifier tests."""
    package.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{package.name}.fixture.", dir=package.parent)
    )
    inventory = lineage_decisions(
        [
            {
                "source_id": "beidan_xlsm",
                "lineage_root": "beidan_xlsm",
                "lane": "historical_relative_time_proxy",
                "role": "RAW_ONLY",
                "content_sha256": "fixture",
            }
        ]
    )
    tables: dict[str, list[dict[str, object]]] = {
        "source_inventory": inventory,
        "source_role_matrix": _roles(inventory),
        "field_inventory": [
            {
                "source_id": "beidan_xlsm",
                "table": "market_snapshots",
                "column": "v1",
                "admissible_use": "RAW_ONLY",
            }
        ],
        "hist40_scope_overrides": [dict(row) for row in HIST40_SCOPE_OVERRIDES],
        "intersection_levels": [
            {"level": level}
            for level in INTERSECTION_LEVELS
        ],
        "field_profile": [{"source_id": "beidan_xlsm", "status": "fixture"}],
        "coverage_by_source": [{"source_id": "beidan_xlsm", "rows": 1}],
        "coverage_by_period": [
            {
                "source_id": "beidan_xlsm",
                "year_or_range": "fixture",
                "coverage_record_count": 1,
                "record_grain": "SOURCE_COVERAGE_RECORD",
            }
        ],
        "proxy_coverage_by_period": [
            {
                "source_id": "beidan_xlsm",
                "year_or_range": "fixture",
                "market": "euro_1x2",
                "snapshot_horizon": "initial",
                "vector_row_count": 1,
                "physical_cell_count": 3,
                "non_null_physical_cell_count": 3,
            }
        ],
        "proxy_surface_profile": [
            {
                "source_id": "beidan_xlsm",
                "market": "euro_1x2",
                "snapshot_horizon": "initial",
                "proxy_policy_id": PROXY_POLICY_ID,
                "role_gate_eligible": False,
                "native_identity_valid_match_count": 1,
                "status": "fixture",
            }
        ],
        "source_feature_availability": [
            {
                "source_id": "beidan_xlsm",
                "field_family": "market_feature",
                "present": False,
            }
        ],
        "duplicate_profile": [{"source_id": "beidan_xlsm", "duplicate_key_groups": 0}],
        "m_per_issue_distribution": [
            {"source_id": "beidan_xlsm", "issue": "fixture", "m_matches": 1}
        ],
        "unresolved_question_ledger": [{"question_id": "U1", "status": "DEFERRED"}],
    }
    for name, rows in tables.items():
        _csv(stage / "tables" / f"{name}.csv", rows)
    _csv(
        stage / "evidence/req_sc_evidence.csv",
        [
            {
                "requirement": "REQ-SC01",
                "status": "EVIDENCE_PRESENT",
                "evidence": "fixture",
            }
        ],
    )
    for figure in (
        "source_feature_heatmap.svg",
        "time_issue_coverage.svg",
        "m_per_issue.svg",
    ):
        (stage / "figures" / figure).parent.mkdir(parents=True, exist_ok=True)
        (stage / "figures" / figure).write_text(
            "<svg>fixture</svg>\n", encoding="utf-8"
        )
    (stage / "REPORT.md").write_text("# Fixture report\n", encoding="utf-8")
    semantic = {
        path.relative_to(stage).as_posix(): _sha256(path)
        for path in sorted(stage.rglob("*"))
        if path.is_file() and path.name not in {"MANIFEST.json", "SHA256SUMS.json"}
    }
    manifest = {
        "issue": ISSUE,
        "package": "fixture",
        "crosswalk_sha256": _sha256(HIST40_CROSSWALK),
        "implementation_sha256": _sha256(Path(__file__)),
        "semantic_hashes": semantic,
    }
    (stage / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    rewrite_checksums(stage)
    _publish_new_directory(stage, package)
    return package
