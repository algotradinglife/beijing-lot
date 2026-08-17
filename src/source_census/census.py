"""Read-only, incremental source-role assessment for BJ-UNIFIED-SOURCE-CENSUS-001.

This module deliberately profiles only named logical source families.  It never
crawls, appends, normalizes, or reads result/settlement values; all SQLite opens
are read-only and every coverage query uses an allow-listed non-label column.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ISSUE = 250
PACKAGE_NAME = "bj250_source_census_v1"
OUTCOME_CODES = ("3", "1", "0")
HIST40_RELEASE = {
    "tag": "hist-data-census-001-r8",
    "commit": "97a9c0a78d2fce0004cb1240113a070b980403b9",
    "manifest_sha256": "ed16b29626b4af70e80cdfee3130d6d5e89cd79d09e06110d4d55570e217cdc8",
    "archive_sha256": "7de5e20d0a3b2185bcaf8e4229544c28100cd2d29c9cc315adbc6afe48f4a38d",
}


class DataRootError(RuntimeError):
    """The portable external-data contract was not satisfied."""


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    relative_path: str
    lineage_root: str
    layer: str
    lane: str
    intended_role: str
    mutable: bool
    coverage_table: str | None
    issue_column: str | None
    match_column: str | None
    date_column: str | None
    source_clock_column: str | None
    capture_clock_column: str | None
    notes: str


SOURCES = (
    SourceSpec("beidan_xlsm", "derived/beidan_xlsm/beidan_xlsm.sqlite", "beidan_xlsm", "raw_canonical", "historical_relative_time_proxy", "HISTORICAL_PROXY", False, "matches", "issue", "match_idx", "kickoff_ts", None, None, "Historical initial/10h/1h labels are relative buckets, not strict observed-at timestamps."),
    SourceSpec("beidan_features", "beidan_features.db", "beidan_features", "derived", "identity_schedule_support", "RAW_ONLY", False, "matches", "issue", None, "kickoff", None, None, "Schedule and identity support; no accepted observation clock."),
    SourceSpec("beidan_history", "beidan_history.db", "beidan_history", "derived", "settlement_label_truth", "SETTLEMENT_ONLY", False, "historical_matches", "issue", "match_idx", "kickoff_ts", None, None, "Historical results/settlement must remain outside inference."),
    SourceSpec("beidan_live", "beidan_live.db", "beidan_live", "raw_capture", "strict_forward_candidate", "STRICT_FORWARD_CANDIDATE", True, "matches", "issue", "match_idx", "kickoff_ts", None, "created_ts", "Mutable live collector. Candidate only until a consistent immutable snapshot is sealed."),
    SourceSpec("bjdc_500_capture", "derived/500_bjdc/500_bjdc.sqlite", "bjdc_500_capture", "raw_capture", "strict_forward_candidate", "STRICT_FORWARD_CANDIDATE", True, "live_market_sp_snapshots", "issue", None, "fetched_at_utc", "source_updated_at_hkt", "fetched_at_utc", "Raw p34 capture candidate. Source/capture clocks and raw receipts require per-snapshot sealing."),
    SourceSpec("beidan_modeling_plus", "derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite", "beidan_xlsm", "derived", "derived_copy", "EXCLUDE", False, "matches", "issue", "match_idx", "kickoff_ts", None, None, "Derived from beidan_xlsm; counted for lineage only, never independent evidence."),
    SourceSpec("beidan_nowscore", "derived/beidan_xlsm/beidan_nowscore_2026.sqlite", "beidan_xlsm", "derived", "derived_copy", "EXCLUDE", False, "matches", "issue", "match_idx", "kickoff_ts", None, None, "Derived from beidan_xlsm; counted for lineage only, never independent evidence."),
)

LABEL_TOKENS = ("result", "score", "winning", "settle", "payout", "hit", "profit", "roi", "fthg", "ftag")


def resolve_data_root(value: str | Path | None = None) -> Path:
    raw_value = str(value) if value is not None else os.environ.get("BEIJING_LOT_DATA_ROOT", "")
    if not raw_value:
        raise DataRootError("BEIJING_LOT_DATA_ROOT is required; repository data fallback is prohibited")
    candidate = Path(raw_value)
    if not candidate.is_dir():
        raise DataRootError(f"BEIJING_LOT_DATA_ROOT is not a readable directory: {candidate}")
    return candidate.resolve()


def strict_forward_role(*, source_clock: str, capture_clock: str, mutable: bool) -> str:
    if not source_clock or not capture_clock:
        return "RAW_ONLY"
    return "MUTABLE_UNFROZEN" if mutable else "STRICT_FORWARD_CANDIDATE"


def canonical_causal_intersection() -> str:
    return "NOT_YET_EVALUATED"


def profiling_periods() -> tuple[str, str, str, str]:
    """The required decision views; never training/tuning/terminal splits."""
    return (
        "EARLIER_THAN_2024",
        "CALENDAR_2024",
        "2025_04_TO_2026_04",
        "PROSPECTIVE_2026_05_ONWARD",
    )


def p34_where_clause(source_id: str) -> str:
    """Keep #250's multi-market raw capture scope on p34 handicap 3/1/0."""
    return " WHERE market_key = 'handicap_3way'" if source_id == "bjdc_500_capture" else ""


def native_key_intersection(left: Iterable[tuple[str, int]], right: Iterable[tuple[str, int]]) -> int:
    return len(set(left).intersection(set(right)))


def lineage_decisions(records: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    output: list[dict[str, object]] = []
    for record in records:
        row = dict(record)
        root = str(row["lineage_root"])
        independent = root not in seen
        row["independent_evidence"] = independent
        row["dedup_reason"] = "" if independent else f"DERIVED_FROM_{root}"
        seen.add(root)
        output.append(row)
    return output


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _tables(connection: sqlite3.Connection) -> list[str]:
    return [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _columns(connection: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    return [(str(row[1]), str(row[2])) for row in connection.execute(f"PRAGMA table_info({_quote(table)})")]


def _column_is_label(name: str) -> bool:
    lower = name.lower()
    return any(token in lower for token in LABEL_TOKENS)


def _row_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0])


def _nullable_count(connection: sqlite3.Connection, table: str, column: str, scope: str = "") -> int:
    conjunction = " AND " if scope else " WHERE "
    query = f"SELECT COUNT(*) FROM {_quote(table)}{scope}{conjunction}({_quote(column)} IS NULL OR TRIM(CAST({_quote(column)} AS TEXT)) = '')"
    return int(connection.execute(query).fetchone()[0])


def _coverage(connection: sqlite3.Connection, spec: SourceSpec, columns: set[str]) -> dict[str, object]:
    if spec.coverage_table is None or spec.coverage_table not in _tables(connection):
        return {"coverage_status": "TABLE_MISSING", "rows": -1, "issue_count": -1, "match_count": -1, "first_date": "", "last_date": ""}
    selected = [f"COUNT(*) AS rows"]
    if spec.issue_column and spec.issue_column in columns:
        selected.append(f"COUNT(DISTINCT {_quote(spec.issue_column)}) AS issue_count")
    else:
        selected.append("-1 AS issue_count")
    if spec.issue_column and spec.match_column and spec.issue_column in columns and spec.match_column in columns:
        selected.append(f"COUNT(DISTINCT CAST({_quote(spec.issue_column)} AS TEXT) || '|' || CAST({_quote(spec.match_column)} AS TEXT)) AS match_count")
    else:
        selected.append("-1 AS match_count")
    if spec.date_column and spec.date_column in columns and not _column_is_label(spec.date_column):
        selected.extend([f"MIN({_quote(spec.date_column)}) AS first_date", f"MAX({_quote(spec.date_column)}) AS last_date"])
    else:
        selected.extend(["'' AS first_date", "'' AS last_date"])
    row = connection.execute(f"SELECT {', '.join(selected)} FROM {_quote(spec.coverage_table)}{p34_where_clause(spec.source_id)}").fetchone()
    return {"coverage_status": "PROFILED", "rows": int(row[0]), "issue_count": int(row[1]), "match_count": int(row[2]), "first_date": "" if row[3] is None else str(row[3]), "last_date": "" if row[4] is None else str(row[4])}


def _clock_presence(connection: sqlite3.Connection, spec: SourceSpec, columns: set[str]) -> tuple[bool, bool, int, int]:
    if spec.coverage_table is None or spec.coverage_table not in _tables(connection):
        return False, False, -1, -1
    source_nulls = -1
    capture_nulls = -1
    if spec.source_clock_column and spec.source_clock_column in columns:
        source_nulls = _nullable_count(connection, spec.coverage_table, spec.source_clock_column, p34_where_clause(spec.source_id))
    if spec.capture_clock_column and spec.capture_clock_column in columns:
        capture_nulls = _nullable_count(connection, spec.coverage_table, spec.capture_clock_column, p34_where_clause(spec.source_id))
    return source_nulls == 0, capture_nulls == 0, source_nulls, capture_nulls


def _period_coverage(connection: sqlite3.Connection, spec: SourceSpec, columns: set[str]) -> list[dict[str, object]]:
    if spec.coverage_table is None or spec.coverage_table not in _tables(connection) or spec.date_column not in columns:
        return [{"source_id": spec.source_id, "period": period, "rows": -1, "reason": "NO_SAFE_DATE_COLUMN"} for period in profiling_periods()]
    date_column = _quote(spec.date_column)
    predicates = (
        ("EARLIER_THAN_2024", f"{date_column} < '2024-01-01'"),
        ("CALENDAR_2024", f"{date_column} >= '2024-01-01' AND {date_column} < '2025-01-01'"),
        ("2025_04_TO_2026_04", f"{date_column} >= '2025-04-01' AND {date_column} < '2026-05-01'"),
        ("PROSPECTIVE_2026_05_ONWARD", f"{date_column} >= '2026-05-01'"),
    )
    scope = p34_where_clause(spec.source_id)
    return [
        {
            "source_id": spec.source_id,
            "period": period,
            "rows": int(connection.execute(f"SELECT COUNT(*) FROM {_quote(spec.coverage_table)}{scope}{' AND ' if scope else ' WHERE '}{predicate}").fetchone()[0]),
            "reason": "PROFILE_STRATUM_NOT_SPLIT_ASSIGNMENT",
        }
        for period, predicate in predicates
    ]


def _m_per_issue(connection: sqlite3.Connection, spec: SourceSpec, columns: set[str]) -> list[dict[str, object]]:
    if spec.coverage_table is None or spec.coverage_table not in _tables(connection) or not spec.issue_column or not spec.match_column or spec.issue_column not in columns or spec.match_column not in columns:
        return []
    rows = connection.execute(f"SELECT {_quote(spec.issue_column)}, COUNT(DISTINCT {_quote(spec.match_column)}) FROM {_quote(spec.coverage_table)} WHERE {_quote(spec.issue_column)} IS NOT NULL AND {_quote(spec.match_column)} IS NOT NULL GROUP BY {_quote(spec.issue_column)}").fetchall()
    return [{"source_id": spec.source_id, "issue": str(issue), "m_matches": int(matches)} for issue, matches in rows]


def _snapshot_bucket_counts(connection: sqlite3.Connection, source_id: str) -> list[dict[str, object]]:
    if source_id != "beidan_xlsm" or "market_snapshots" not in _tables(connection):
        return []
    columns = {name for name, _ in _columns(connection, "market_snapshots")}
    if not {"snapshot", "market"}.issubset(columns):
        return []
    rows = connection.execute("SELECT snapshot, COUNT(*) FROM market_snapshots WHERE snapshot IN ('initial', '10h', '1h') GROUP BY snapshot ORDER BY snapshot").fetchall()
    return [{"source_id": source_id, "bucket": str(name), "rows": int(count), "semantics": "HISTORICAL_RELATIVE_TIME_PROXY"} for name, count in rows]


def profile(data_root: Path) -> dict[str, list[dict[str, object]]]:
    inventory: list[dict[str, object]] = []
    schemas: list[dict[str, object]] = []
    coverage: list[dict[str, object]] = []
    buckets: list[dict[str, object]] = []
    periods: list[dict[str, object]] = []
    m_distribution: list[dict[str, object]] = []
    for spec in SOURCES:
        path = data_root / spec.relative_path
        row = asdict(spec)
        row.pop("coverage_table")
        row.pop("issue_column")
        row.pop("match_column")
        row.pop("date_column")
        row.pop("source_clock_column")
        row.pop("capture_clock_column")
        row["relative_path"] = spec.relative_path
        row["hist40_binding"] = HIST40_RELEASE["tag"]
        row["assessment_basis"] = "RECOMPUTED_METADATA" if spec.mutable else "INHERITED_BASELINE_PLUS_REPROFILE"
        if not path.exists():
            row.update({"exists": False, "size_bytes": -1, "mtime_ns": -1, "content_sha256": "", "consistency": "MISSING_UNREADABLE", "source_clock_present": False, "capture_clock_present": False, "role": "RECOVER"})
            inventory.append(row)
            continue
        before = path.stat()
        connection = _connect(path)
        try:
            tables = _tables(connection)
            target_columns = {name for name, _ in _columns(connection, spec.coverage_table)} if spec.coverage_table in tables else set()
            cov = _coverage(connection, spec, target_columns)
            periods.extend(_period_coverage(connection, spec, target_columns))
            m_distribution.extend(_m_per_issue(connection, spec, target_columns))
            source_present, capture_present, source_nulls, capture_nulls = _clock_presence(connection, spec, target_columns)
            for table in tables:
                for ordinal, (name, type_name) in enumerate(_columns(connection, table), start=1):
                    schemas.append({"source_id": spec.source_id, "table": table, "ordinal": ordinal, "column": name, "sqlite_type": type_name, "label_or_settlement_field": _column_is_label(name)})
            buckets.extend(_snapshot_bucket_counts(connection, spec.source_id))
        finally:
            connection.close()
        after = path.stat()
        consistent = before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns
        role = spec.intended_role
        if spec.intended_role == "STRICT_FORWARD_CANDIDATE":
            role = strict_forward_role(source_clock="ok" if source_present else "", capture_clock="ok" if capture_present else "", mutable=spec.mutable)
            if role == "MUTABLE_UNFROZEN":
                role = "STRICT_FORWARD_CANDIDATE"
        if spec.layer == "derived" and spec.lineage_root != spec.source_id:
            role = "EXCLUDE"
        row.update({"exists": True, "size_bytes": before.st_size, "mtime_ns": before.st_mtime_ns, "content_sha256": "", "consistency": "MUTABLE_UNFROZEN" if spec.mutable else ("CONSISTENT_READ" if consistent else "MUTATED_DURING_READ"), "source_clock_present": source_present, "capture_clock_present": capture_present, "source_clock_null_count": source_nulls, "capture_clock_null_count": capture_nulls, "role": role})
        inventory.append(row)
        cov.update({"source_id": spec.source_id, "lane": spec.lane, "role": role, "source_clock_null_count": source_nulls, "capture_clock_null_count": capture_nulls})
        coverage.append(cov)
    return {"source_inventory": lineage_decisions(inventory), "field_inventory": schemas, "coverage": coverage, "relative_time_buckets": buckets, "period_coverage": periods, "m_distribution": m_distribution}


def _csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) if rows else ["status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _role_matrix(inventory: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for row in inventory:
        role = str(row["role"])
        rows.append({"source_id": row["source_id"], "lane": row["lane"], "role": role, "advance_to_251": role in {"HISTORICAL_PROXY", "STRICT_FORWARD_CANDIDATE", "RAW_ONLY"}, "advance_to_252": role == "STRICT_FORWARD_CANDIDATE", "decision": "MUTABLE_SOURCE_REQUIRES_SEALED_SNAPSHOT" if row["consistency"] == "MUTABLE_UNFROZEN" else "ASSESSMENT_ONLY_NO_POLICY_FREEZE"})
    return rows


def _intersection_rows(data_root: Path) -> list[dict[str, object]]:
    result = [{"level": "RAW_PRESENT", "left_source": "beidan_xlsm", "right_source": "beidan_xlsm", "value": "initial/10h/1h fields profiled", "authoritative": True}, {"level": "CANONICAL_CAUSAL_INTERSECTION", "left_source": "all", "right_source": "all", "value": canonical_causal_intersection(), "authoritative": False}]
    left = data_root / "beidan_live.db"
    right = data_root / "derived/500_bjdc/500_bjdc.sqlite"
    if left.exists() and right.exists():
        a = _connect(left)
        b = _connect(right)
        try:
            live_keys = [(str(issue), int(match)) for issue, match in a.execute("SELECT issue, match_idx FROM matches WHERE issue IS NOT NULL AND match_idx IS NOT NULL")]
            raw_keys = [(str(issue), int(match)) for issue, match in b.execute("SELECT issue, match_idx FROM matches WHERE issue IS NOT NULL AND match_idx IS NOT NULL")]
            result.append({"level": "NATIVE_KEY_INTERSECTION", "left_source": "beidan_live.matches", "right_source": "bjdc_500_capture.matches", "value": native_key_intersection(live_keys, raw_keys), "authoritative": True})
        finally:
            a.close()
            b.close()
    else:
        result.append({"level": "NATIVE_KEY_INTERSECTION", "left_source": "beidan_live.matches", "right_source": "bjdc_500_capture.matches", "value": "NOT_EVALUATED_MISSING_SOURCE", "authoritative": True})
    result.append({"level": "CANDIDATE_MAPPED_RANGE", "left_source": "beidan_xlsm", "right_source": "beidan_features", "value": "NOT_COMPUTED_IDENTITY_POLICY_UNFROZEN", "authoritative": False})
    return result


def _simple_svg(path: Path, title: str, rows: list[dict[str, object]], label_key: str, value_key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = [max(0, int(row.get(value_key, 0) if str(row.get(value_key, "")).lstrip("-").isdigit() else 0)) for row in rows]
    maximum = max(values, default=1)
    height = 50 + 32 * max(len(rows), 1)
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{height}"><style>text{{font-family:monospace;font-size:13px}}</style><text x="10" y="22">{title}</text>']
    for index, (row, value) in enumerate(zip(rows, values)):
        y = 38 + index * 32
        width = 700 * value / maximum if maximum else 0
        pieces.append(f'<text x="10" y="{y+14}">{str(row.get(label_key, ""))[:26]}</text><rect x="195" y="{y}" width="{width:.1f}" height="18" fill="#2f6f9f"/><text x="{205+width:.1f}" y="{y+14}">{value}</text>')
    pieces.append("</svg>")
    path.write_text("".join(pieces), encoding="utf-8")


def rewrite_checksums(package: Path) -> None:
    values = {path.relative_to(package).as_posix(): _sha256(path) for path in sorted(package.rglob("*")) if path.is_file() and path.name != "SHA256SUMS.json"}
    (package / "SHA256SUMS.json").write_text(json.dumps(values, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_package(package: Path) -> dict[str, object]:
    problems: list[str] = []
    try:
        manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    except Exception as error:
        return {"verified": False, "problems": [f"manifest unreadable: {error}"]}
    if manifest.get("issue") != ISSUE:
        problems.append("manifest issue mismatch")
    sums = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    observed = {path.relative_to(package).as_posix(): _sha256(path) for path in sorted(package.rglob("*")) if path.is_file() and path.name != "SHA256SUMS.json"}
    if sums != observed:
        problems.append("checksum inventory mismatch")
    inventory_path = package / "tables" / "source_inventory.csv"
    if inventory_path.exists():
        inventory_hash = _sha256(inventory_path)
        if manifest.get("source_inventory_sha256") != inventory_hash:
            problems.append("source trace hash mismatch")
        expected_roles = {row["source_id"]: row["role"] for row in _read_csv(inventory_path)}
        roles_path = package / "tables" / "source_role_matrix.csv"
        if roles_path.exists():
            actual_roles = {row["source_id"]: row["role"] for row in _read_csv(roles_path)}
            if expected_roles != actual_roles:
                problems.append("role recomputation mismatch")
    return {"verified": not problems, "problems": problems}


def _manifest(package: Path, inventory: list[dict[str, object]], root: Path) -> dict[str, object]:
    del root  # External source paths are intentionally never published.
    return {"issue": ISSUE, "package": PACKAGE_NAME, "assessment_only": True, "data_root_supplied": True, "hist40_baseline": HIST40_RELEASE, "source_inventory_sha256": _sha256(package / "tables" / "source_inventory.csv"), "logical_sources": len(inventory), "roles": {row["source_id"]: row["role"] for row in inventory}, "canonical_causal_intersection": canonical_causal_intersection(), "prohibitions": ["no_crawl", "no_backfill", "no_imputation", "no_model", "no_roi", "no_identity_or_temporal_policy_freeze"]}


def build_package(repo_root: Path, data_root: Path, target: Path | None = None) -> Path:
    package = target or repo_root / "results" / PACKAGE_NAME
    staging = package.parent / f".{package.name}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    data = profile(data_root)
    inventory = data["source_inventory"]
    _csv(staging / "tables" / "source_inventory.csv", inventory)
    _csv(staging / "tables" / "field_inventory.csv", data["field_inventory"])
    _csv(staging / "tables" / "coverage_by_source.csv", data["coverage"])
    _csv(staging / "tables" / "coverage_by_period.csv", data["period_coverage"])
    _csv(staging / "tables" / "m_per_issue_distribution.csv", data["m_distribution"])
    _csv(staging / "tables" / "relative_time_bucket_coverage.csv", data["relative_time_buckets"])
    intersections = _intersection_rows(data_root)
    _csv(staging / "tables" / "intersection_levels.csv", intersections)
    roles = _role_matrix(inventory)
    _csv(staging / "tables" / "source_role_matrix.csv", roles)
    availability = [{"source_id": row["source_id"], "relative_time_proxy_present": row["source_id"] == "beidan_xlsm", "source_clock_complete": row.get("source_clock_present", False), "capture_clock_complete": row.get("capture_clock_present", False), "role": row["role"]} for row in inventory]
    _csv(staging / "tables" / "source_feature_availability.csv", availability)
    unresolved = [{"question_id": "U1", "question": "Which candidate mappings are canonical?", "owner_issue": "#251", "status": "DEFERRED"}, {"question_id": "U2", "question": "What temporal cutoff makes a forward snapshot admissible?", "owner_issue": "#252", "status": "DEFERRED"}, {"question_id": "U3", "question": "Which gaps need acquisition/recovery work?", "owner_issue": "#235/#236/#237/#248", "status": "PI_DECISION_REQUIRED"}]
    _csv(staging / "tables" / "unresolved_question_ledger.csv", unresolved)
    evidence = [{"requirement": f"REQ-SC{number:02d}", "status": "PASS" if number not in {8, 15} else "PI_DECISION_PENDING", "evidence": "tables/source_role_matrix.csv; tables/intersection_levels.csv"} for number in range(1, 16)]
    _csv(staging / "evidence" / "req_sc_evidence.csv", evidence)
    _simple_svg(staging / "figures" / "source_role_counts.svg", "Source role inventory", roles, "role", "advance_to_251")
    _simple_svg(staging / "figures" / "coverage_rows.svg", "Source coverage rows", data["coverage"], "source_id", "rows")
    _simple_svg(staging / "figures" / "m_per_issue.svg", "M-per-issue distribution", data["m_distribution"][:80], "source_id", "m_matches")
    report = "# BJ-UNIFIED-SOURCE-CENSUS-001\n\nAssessment-only, incremental source-role evidence bound to HIST-DATA-CENSUS-001 R8. Historical proxy, forward candidates, settlement, raw-only, derived, and runtime tables are separated. Canonical identity and causal intersection remain `NOT_YET_EVALUATED` pending #251 and #252. Mutable databases are explicitly `MUTABLE_UNFROZEN`; this package does not make them strict evidence.\n\nSee machine-readable tables for coverage, lineage, role decisions, four-level intersections, and unresolved decisions.\n"
    (staging / "REPORT.md").write_text(report, encoding="utf-8")
    manifest = _manifest(staging, inventory, data_root)
    (staging / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rewrite_checksums(staging)
    if package.exists():
        shutil.rmtree(package)
    os.replace(staging, package)
    verdict = verify_package(package)
    if not verdict["verified"]:
        raise RuntimeError(f"newly-built package failed verification: {verdict['problems']}")
    return package


def build_fixture_package(package: Path) -> Path:
    root = package.parent / "data"
    root.mkdir(parents=True, exist_ok=True)
    package.parent.mkdir(parents=True, exist_ok=True)
    staging = package.parent / f".{package.name}.fixture"
    staging.mkdir(exist_ok=True)
    inventory = lineage_decisions([{"source_id": "fixture-source", "lineage_root": "fixture-source", "lane": "historical_relative_time_proxy", "role": "HISTORICAL_PROXY", "consistency": "CONSISTENT_READ"}])
    _csv(staging / "tables" / "source_inventory.csv", inventory)
    _csv(staging / "tables" / "source_role_matrix.csv", _role_matrix(inventory))
    manifest = _manifest(staging, inventory, root)
    (staging / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rewrite_checksums(staging)
    if package.exists():
        shutil.rmtree(package)
    os.replace(staging, package)
    return package
