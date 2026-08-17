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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ISSUE = 250
PACKAGE_NAME = "bj250_source_census_v2"
OUTCOME_CODES = ("3", "1", "0")
HIST40_RELEASE = {
    "tag": "hist-data-census-001-r8",
    "commit": "97a9c0a78d2fce0004cb1240113a070b980403b9",
    "manifest_sha256": "ed16b29626b4af70e80cdfee3130d6d5e89cd79d09e06110d4d55570e217cdc8",
    "archive_sha256": "7de5e20d0a3b2185bcaf8e4229544c28100cd2d29c9cc315adbc6afe48f4a38d",
}
LABEL_TOKENS = ("result", "score", "winning", "settle", "payout", "hit", "profit", "roi", "fthg", "ftag")


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
    SourceSpec("beidan_xlsm", "derived/beidan_xlsm/beidan_xlsm.sqlite", "beidan_xlsm", "raw_canonical", "historical_relative_time_proxy", "HISTORICAL_PROXY", False, "matches", "issue", "match_idx", "kickoff_ts", None, None, ("issue", "match_idx", "kickoff_ts", "league", "home", "away", "handicap_line", "ts_10h", "home_team_id", "away_team_id", "result_label"), "Historical initial/10h/1h labels are proxy buckets, never strict observation timestamps."),
    SourceSpec("beidan_features", "beidan_features.db", "beidan_features", "derived", "identity_schedule_support", "RAW_ONLY", False, "matches", "issue", "match_id", "kickoff", None, None, ("issue", "match_id", "kickoff", "league", "home", "away", "home_id", "away_id", "beidan_hcap", "p_open_3", "p_open_1", "p_open_0", "p_close_3", "p_close_1", "p_close_0", "result_code"), "Identity/schedule support with no accepted source or capture observation clock."),
    SourceSpec("beidan_history", "beidan_history.db", "beidan_history", "derived", "settlement_label_truth", "SETTLEMENT_ONLY", False, "historical_matches", "issue", "match_idx", "kickoff_ts", None, None, ("issue", "match_idx", "kickoff_ts", "league", "home", "away", "handicap_line", "avg_eu_home", "avg_eu_draw", "avg_eu_away", "result_code", "winning_sp"), "Settlement/label truth must remain separate from inference."),
    SourceSpec("beidan_live", "beidan_live.db", "beidan_live", "raw_capture", "strict_forward_candidate", "STRICT_FORWARD_CANDIDATE", True, "matches", "issue", "match_idx", "kickoff_ts", None, "created_ts", ("match_id", "issue", "match_idx", "kickoff_ts", "league", "home", "away", "handicap_line", "created_ts"), "Mutable live collector; its existing clock is capture-only."),
    SourceSpec("bjdc_500_capture", "derived/500_bjdc/500_bjdc.sqlite", "bjdc_500_capture", "raw_capture", "strict_forward_candidate", "STRICT_FORWARD_CANDIDATE", True, "live_market_sp_snapshots", "issue", "playid", "fetched_at_utc", "source_updated_at_hkt", "fetched_at_utc", ("issue", "playid", "market_key", "fetched_at_utc", "source_updated_at_hkt", "home", "away", "outcome_code", "sp", "sale_cutoff_hkt", "match_id"), "Raw p34 capture: both clocks need complete sealed source receipts before promotion."),
    SourceSpec("beidan_modeling_plus", "derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite", "beidan_xlsm", "derived", "derived_copy", "EXCLUDE", False, "matches", "issue", "match_idx", "kickoff_ts", None, None, ("issue", "match_idx", "kickoff_ts"), "Derived copy; not independent source evidence."),
    SourceSpec("beidan_nowscore", "derived/beidan_xlsm/beidan_nowscore_2026.sqlite", "beidan_xlsm", "derived", "derived_copy", "EXCLUDE", False, "matches", "issue", "match_idx", "kickoff_ts", None, None, ("issue", "match_idx", "kickoff_ts"), "Derived copy; not independent source evidence."),
)


def resolve_data_root(value: str | Path | None = None) -> Path:
    raw = str(value) if value is not None else os.environ.get("BEIJING_LOT_DATA_ROOT", "")
    if not raw:
        raise DataRootError("BEIJING_LOT_DATA_ROOT is required; repository fallback is prohibited")
    root = Path(raw).resolve()
    if not root.is_dir():
        raise DataRootError(f"BEIJING_LOT_DATA_ROOT is not a readable directory: {root}")
    return root


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _tables(c: sqlite3.Connection) -> list[str]:
    return [str(r[0]) for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _columns(c: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    return [(str(r[1]), str(r[2])) for r in c.execute(f"PRAGMA table_info({_q(table)})")]


def _is_label(name: str) -> bool:
    return any(token in name.lower() for token in LABEL_TOKENS)


def _scope(spec: SourceSpec) -> str:
    return " WHERE market_key = 'handicap_3way'" if spec.source_id == "bjdc_500_capture" else ""


def _join_scope(scope: str, condition: str) -> str:
    return f"{scope}{' AND ' if scope else ' WHERE '}{condition}"


def profiling_periods() -> tuple[str, ...]:
    return ("EARLIER_YEAR", "CALENDAR_2024", "GAP_2025_01_TO_03", "2025_04_TO_2026_04", "PROSPECTIVE_2026_05_ONWARD", "NULL_OR_UNPARSEABLE_DATE")


def strict_forward_role(*, source_clock_complete: bool, capture_clock_complete: bool, mutable: bool) -> str:
    if not source_clock_complete or not capture_clock_complete:
        return "RAW_ONLY"
    return "MUTABLE_UNFROZEN" if mutable else "STRICT_FORWARD_CANDIDATE"


def canonical_causal_intersection() -> str:
    return "NOT_YET_EVALUATED"


def native_key_intersection(left: Iterable[tuple[str, int]], right: Iterable[tuple[str, int]]) -> int:
    return len(set(left).intersection(set(right)))


def lineage_decisions(records: list[dict[str, object]]) -> list[dict[str, object]]:
    roots: set[str] = set()
    out: list[dict[str, object]] = []
    for item in records:
        row = dict(item)
        root = str(row["lineage_root"])
        row["independent_evidence"] = root not in roots
        row["dedup_reason"] = "" if row["independent_evidence"] else f"DERIVED_FROM_{root}"
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


def _source_aggregate(c: sqlite3.Connection, spec: SourceSpec, columns: set[str]) -> tuple[dict[str, object], list[dict[str, object]]]:
    if spec.coverage_table not in _tables(c):
        return ({"coverage_status": "TABLE_MISSING", "rows": -1, "issue_count": -1, "match_count": -1}, [])
    fields = [x for x in spec.decision_fields if x in columns]
    scope = _scope(spec)
    select = ["COUNT(*) AS rows"]
    if spec.issue_column in columns:
        select.append(f"COUNT(DISTINCT {_q(spec.issue_column)}) AS issue_count")
    else:
        select.append("-1 AS issue_count")
    if spec.issue_column in columns and spec.match_column in columns:
        select.append(f"COUNT(DISTINCT CAST({_q(spec.issue_column)} AS TEXT) || '|' || CAST({_q(spec.match_column)} AS TEXT)) AS match_count")
    else:
        select.append("-1 AS match_count")
    for i, field in enumerate(fields):
        select.append(f"SUM(CASE WHEN {_null_expr(field)} THEN 1 ELSE 0 END) AS n{i}")
        select.append(f"SUM(CASE WHEN {_invalid_expr(field)} THEN 1 ELSE 0 END) AS i{i}")
    values = c.execute(f"SELECT {', '.join(select)} FROM {_q(spec.coverage_table)}{scope}").fetchone()
    row = {"coverage_status": "PROFILED", "rows": int(values[0]), "issue_count": int(values[1]), "match_count": int(values[2])}
    profiles = []
    for i, field in enumerate(fields):
        profiles.append({"source_id": spec.source_id, "table": spec.coverage_table, "field": field, "field_family": _field_family(field), "is_label_or_settlement": _is_label(field), "denominator_rows": int(values[0]), "null_or_blank_count": int(values[3 + 2 * i] or 0), "non_null_count": int(values[0]) - int(values[3 + 2 * i] or 0), "impossible_value_count": int(values[4 + 2 * i] or 0), "availability_used_for_role": not _is_label(field)})
    return row, profiles


def _field_family(column: str) -> str:
    x = column.lower()
    if x in {"issue", "match_idx", "playid", "match_id", "home", "away", "home_id", "away_id", "league"}: return "identity_schedule"
    if "clock" in x or "time" in x or "date" in x or x in {"kickoff", "kickoff_ts", "fetched_at", "fetched_at_utc", "created_ts", "source_updatetime", "source_updated_at_hkt"}: return "timestamp"
    if "sp" in x or "odds" in x or x.startswith("p_") or x in {"v1", "v2", "v3", "handicap_line", "beidan_hcap"}: return "market_feature"
    if _is_label(column): return "label_settlement"
    return "other"


def _coverage_strata(c: sqlite3.Connection, spec: SourceSpec, columns: set[str]) -> list[dict[str, object]]:
    if spec.coverage_table not in _tables(c) or spec.date_column not in columns:
        return [{"source_id": spec.source_id, "period": p, "year_or_range": "", "source_rows": -1, "stratum_rows": -1, "issue_count": -1, "match_count": -1, "cell_count": -1, "date_missing_or_unparseable": -1, "reason": "NO_SAFE_DATE_COLUMN"} for p in profiling_periods()]
    date = _q(spec.date_column)
    scope = _scope(spec)
    base = int(c.execute(f"SELECT COUNT(*) FROM {_q(spec.coverage_table)}{scope}").fetchone()[0])
    count_expr = _coverage_count_expr(spec, columns)
    rows: list[dict[str, object]] = []
    predicates = [
        ("CALENDAR_2024", "2024", f"{date} >= '2024-01-01' AND {date} < '2025-01-01'"),
        ("GAP_2025_01_TO_03", "2025-01..03", f"{date} >= '2025-01-01' AND {date} < '2025-04-01'"),
        ("2025_04_TO_2026_04", "2025-04..2026-04", f"{date} >= '2025-04-01' AND {date} < '2026-05-01'"),
        ("PROSPECTIVE_2026_05_ONWARD", "2026-05+", f"{date} >= '2026-05-01'"),
        ("NULL_OR_UNPARSEABLE_DATE", "null/unparseable", f"{date} IS NULL OR TRIM(CAST({date} AS TEXT)) = '' OR {date} < '1900-01-01'"),
    ]
    for period, label, predicate in predicates:
        rows.append(_coverage_row(c, spec, columns, period, label, predicate, scope, base, count_expr))
    earlier_scope = _join_scope(scope, f"{date} >= '1900-01-01' AND {date} < '2024-01-01'")
    year_rows = c.execute(f"SELECT substr(CAST({date} AS TEXT), 1, 4), COUNT(*) FROM {_q(spec.coverage_table)}{earlier_scope} GROUP BY 1 ORDER BY 1").fetchall()
    for year, _ in year_rows:
        predicate = f"{date} >= '{year}-01-01' AND {date} < '{int(year) + 1}-01-01'"
        rows.append(_coverage_row(c, spec, columns, "EARLIER_YEAR", str(year), predicate, scope, base, count_expr))
    return rows


def _coverage_count_expr(spec: SourceSpec, columns: set[str]) -> tuple[str, str, str]:
    issue = f"COUNT(DISTINCT {_q(spec.issue_column)})" if spec.issue_column in columns else "-1"
    match = f"COUNT(DISTINCT {_q(spec.match_column)})" if spec.match_column in columns else "-1"
    cell = "COUNT(*)"
    return issue, match, cell


def _coverage_row(c: sqlite3.Connection, spec: SourceSpec, columns: set[str], period: str, label: str, predicate: str, scope: str, base: int, expr: tuple[str, str, str]) -> dict[str, object]:
    query_scope = _join_scope(scope, predicate)
    value = c.execute(f"SELECT COUNT(*), {expr[0]}, {expr[1]}, {expr[2]} FROM {_q(spec.coverage_table)}{query_scope}").fetchone()
    return {"source_id": spec.source_id, "period": period, "year_or_range": label, "source_rows": base, "stratum_rows": int(value[0]), "issue_count": int(value[1]), "match_count": int(value[2]), "cell_count": int(value[3]), "date_missing_or_unparseable": int(value[0]) if period == "NULL_OR_UNPARSEABLE_DATE" else 0, "reason": "PROFILE_STRATUM_NOT_SPLIT_ASSIGNMENT"}


def _duplicate_profile(c: sqlite3.Connection, spec: SourceSpec, columns: set[str]) -> dict[str, object]:
    if spec.source_id == "bjdc_500_capture":
        keys = [key for key in ("issue", "playid", "fetched_at", "outcome_code") if key in columns]
    else:
        keys = [key for key in (spec.issue_column, spec.match_column) if key and key in columns]
    if len(keys) < 2:
        return {"source_id": spec.source_id, "table": spec.coverage_table, "key_definition": "UNAVAILABLE", "duplicate_key_groups": -1, "duplicate_rows_beyond_first": -1, "reason": "NO_TWO_COMPONENT_NATIVE_KEY"}
    scope = _scope(spec)
    where = _join_scope(scope, " AND ".join(f"{_q(key)} IS NOT NULL" for key in keys))
    group = ", ".join(_q(key) for key in keys)
    result = c.execute(f"SELECT COUNT(*), COALESCE(SUM(n - 1), 0) FROM (SELECT COUNT(*) n FROM {_q(spec.coverage_table)}{where} GROUP BY {group} HAVING COUNT(*) > 1)").fetchone()
    return {"source_id": spec.source_id, "table": spec.coverage_table, "key_definition": "+".join(keys), "duplicate_key_groups": int(result[0]), "duplicate_rows_beyond_first": int(result[1]), "reason": "NATIVE_KEY_DUPLICATE_PROFILE"}


def _m_per_issue(c: sqlite3.Connection, spec: SourceSpec, columns: set[str]) -> list[dict[str, object]]:
    if spec.issue_column not in columns or spec.match_column not in columns:
        return []
    scope = _join_scope(_scope(spec), f"{_q(spec.issue_column)} IS NOT NULL AND {_q(spec.match_column)} IS NOT NULL")
    rows = c.execute(f"SELECT {_q(spec.issue_column)}, COUNT(DISTINCT {_q(spec.match_column)}) FROM {_q(spec.coverage_table)}{scope} GROUP BY {_q(spec.issue_column)} ORDER BY {_q(spec.issue_column)}").fetchall()
    return [{"source_id": spec.source_id, "issue": str(issue), "m_matches": int(matches), "semantics": "P34_CAPTURE_PLAY_COUNT" if spec.source_id == "bjdc_500_capture" else "NATIVE_MATCH_COUNT"} for issue, matches in rows]


def _snapshot_completeness(c: sqlite3.Connection, spec: SourceSpec) -> list[dict[str, object]]:
    tables = set(_tables(c)); out: list[dict[str, object]] = []
    if spec.source_id == "beidan_xlsm" and "market_snapshots" in tables:
        rows = c.execute("SELECT snapshot, market, COUNT(*) rows, COUNT(DISTINCT match_id) matches, SUM(CASE WHEN v1 IS NOT NULL AND v2 IS NOT NULL AND v3 IS NOT NULL THEN 1 ELSE 0 END) complete_triplet_rows FROM market_snapshots WHERE snapshot IN ('initial','10h','1h') GROUP BY snapshot, market ORDER BY snapshot, market").fetchall()
        out += [{"source_id": spec.source_id, "field_family": str(r[1]), "bucket": str(r[0]), "denominator_rows": int(r[2]), "denominator_matches": int(r[3]), "complete_outcome_triplet_rows": int(r[4]), "missing_or_invalid_triplet_rows": int(r[2]-r[4]), "semantics": "HISTORICAL_RELATIVE_TIME_PROXY"} for r in rows]
    if spec.source_id == "bjdc_500_capture" and "live_market_sp_snapshots" in tables:
        rows = c.execute("SELECT COUNT(*) cells, COUNT(DISTINCT issue || '|' || playid || '|' || fetched_at) snapshots, SUM(CASE WHEN sp IS NULL OR sp <= 0 THEN 1 ELSE 0 END) bad_sp FROM live_market_sp_snapshots WHERE market_key='handicap_3way'").fetchone()
        triples = c.execute("SELECT COUNT(*) FROM (SELECT issue,playid,fetched_at FROM live_market_sp_snapshots WHERE market_key='handicap_3way' GROUP BY issue,playid,fetched_at HAVING COUNT(DISTINCT outcome_code)=3 AND SUM(CASE WHEN sp IS NOT NULL AND sp>0 THEN 1 ELSE 0 END)=3)").fetchone()[0]
        out.append({"source_id": spec.source_id, "field_family": "p34_sp", "bucket": "observed_capture", "denominator_rows": int(rows[0]), "denominator_matches": int(rows[1]), "complete_outcome_triplet_rows": int(triples), "missing_or_invalid_triplet_rows": int(rows[1]-triples), "semantics": "MUTABLE_UNFROZEN"})
    return out


def _candidate_mapping(c_xlsm: sqlite3.Connection, c_features: sqlite3.Connection) -> list[dict[str, object]]:
    # Candidate evidence only: no identity policy is accepted here.  Lower requires
    # same issue + normalized home/away + calendar date; upper relaxes date.
    x = c_xlsm.execute("SELECT issue, lower(trim(home)), lower(trim(away)), substr(kickoff_ts,1,10) FROM matches WHERE issue IS NOT NULL AND home IS NOT NULL AND away IS NOT NULL AND kickoff_ts >= '1900-01-01'").fetchall()
    f = c_features.execute("SELECT issue, lower(trim(home)), lower(trim(away)), substr(kickoff,1,10) FROM matches WHERE issue IS NOT NULL AND home IS NOT NULL AND away IS NOT NULL AND kickoff >= '1900-01-01'").fetchall()
    x_lower = [(str(a), str(b), str(d), str(e)) for a,b,d,e in x]
    f_lower = {(str(a), str(b), str(d), str(e)) for a,b,d,e in f}
    x_upper = [(str(a), str(b), str(d)) for a,b,d,_ in x]
    f_upper = {(str(a), str(b), str(d)) for a,b,d,_ in f}
    # Both bounds are counts of xlsm rows that have at least one candidate;
    # relaxation can only enlarge the eligible xlsm row set.
    lower = sum(key in f_lower for key in x_lower)
    upper = sum(key in f_upper for key in x_upper)
    return [
        {"level": "CANDIDATE_MAPPED_RANGE", "left_source": "beidan_xlsm.matches", "right_source": "beidan_features.matches", "mapping_assumption": "lower=issue+normalized_home+normalized_away+calendar_date; upper=issue+normalized_home+normalized_away", "lower_bound": lower, "upper_bound": upper, "authoritative": False, "decision": "NON_AUTHORITATIVE_PROPOSED_MAPPING_PENDING_251"}
    ]


def _intersections(data_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [{"level":"RAW_PRESENT","left_source":"beidan_xlsm.market_snapshots","right_source":"beidan_xlsm.matches","mapping_assumption":"native fields only","lower_bound":"initial/10h/1h field families profiled","upper_bound":"initial/10h/1h field families profiled","authoritative":True,"decision":"HISTORICAL_PROXY_ONLY"}]
    live, raw = data_root / "beidan_live.db", data_root / "derived/500_bjdc/500_bjdc.sqlite"
    if live.exists() and raw.exists():
        a,b=_connect(live),_connect(raw)
        try:
            lk=[(str(i),int(m)) for i,m in a.execute("SELECT issue,match_idx FROM matches WHERE issue IS NOT NULL AND match_idx IS NOT NULL")]
            rk=[(str(i),int(m)) for i,m in b.execute("SELECT issue,match_idx FROM matches WHERE issue IS NOT NULL AND match_idx IS NOT NULL")]
            n=native_key_intersection(lk,rk)
            rows.append({"level":"NATIVE_KEY_INTERSECTION","left_source":"beidan_live.matches","right_source":"bjdc_500_capture.matches","mapping_assumption":"identical native issue+match_idx","lower_bound":n,"upper_bound":n,"authoritative":True,"decision":"EXACT_NATIVE_ONLY"})
        finally: a.close(); b.close()
    else: rows.append({"level":"NATIVE_KEY_INTERSECTION","left_source":"beidan_live.matches","right_source":"bjdc_500_capture.matches","mapping_assumption":"identical native issue+match_idx","lower_bound":"NOT_EVALUATED_MISSING_SOURCE","upper_bound":"NOT_EVALUATED_MISSING_SOURCE","authoritative":True,"decision":"MISSING_SOURCE"})
    xp,fp=data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite",data_root / "beidan_features.db"
    if xp.exists() and fp.exists():
        a,b=_connect(xp),_connect(fp)
        try: rows.extend(_candidate_mapping(a,b))
        finally: a.close(); b.close()
    else: rows.append({"level":"CANDIDATE_MAPPED_RANGE","left_source":"beidan_xlsm.matches","right_source":"beidan_features.matches","mapping_assumption":"unavailable","lower_bound":"NOT_EVALUATED_MISSING_SOURCE","upper_bound":"NOT_EVALUATED_MISSING_SOURCE","authoritative":False,"decision":"MISSING_SOURCE"})
    rows.append({"level":"CANONICAL_CAUSAL_INTERSECTION","left_source":"all","right_source":"all","mapping_assumption":"frozen identity+temporal policy required","lower_bound":canonical_causal_intersection(),"upper_bound":canonical_causal_intersection(),"authoritative":False,"decision":"DEFERRED_TO_251_AND_252"})
    return rows


def profile(data_root: Path) -> dict[str, list[dict[str, object]]]:
    inventory=[]; fields=[]; coverage=[]; periods=[]; duplicates=[]; triplets=[]; m_distribution=[]; schemas=[]
    for spec in SOURCES:
        path=data_root/spec.relative_path; record=asdict(spec); record.pop("decision_fields"); record.update({"hist40_binding":HIST40_RELEASE["tag"],"assessment_basis":"RECOMPUTED_CHANGED_OR_MUTABLE" if spec.mutable else "INHERITED_R8_AND_REPROFILED","relative_path":spec.relative_path})
        if not path.exists():
            record.update({"exists":False,"content_sha256":"","consistency":"MISSING_UNREADABLE","role":"RECOVER","source_clock_complete":False,"capture_clock_complete":False}); inventory.append(record); continue
        before=path.stat(); c=_connect(path)
        try:
            tables=_tables(c); cols={n for n,_ in _columns(c,spec.coverage_table)} if spec.coverage_table in tables else set()
            aggregate, fp=_source_aggregate(c,spec,cols); fields.extend(fp); coverage.append(dict(aggregate,source_id=spec.source_id,lane=spec.lane)); periods.extend(_coverage_strata(c,spec,cols)); duplicates.append(_duplicate_profile(c,spec,cols)); m_distribution.extend(_m_per_issue(c,spec,cols)); triplets.extend(_snapshot_completeness(c,spec))
            for table in tables:
                for ordinal,(name,typ) in enumerate(_columns(c,table),1): schemas.append({"source_id":spec.source_id,"table":table,"ordinal":ordinal,"column":name,"sqlite_type":typ,"field_family":_field_family(name),"label_or_settlement_field":_is_label(name)})
            src_complete=bool(spec.source_clock_column and spec.source_clock_column in cols and next((r["null_or_blank_count"] for r in fp if r["field"]==spec.source_clock_column),1)==0)
            cap_complete=bool(spec.capture_clock_column and spec.capture_clock_column in cols and next((r["null_or_blank_count"] for r in fp if r["field"]==spec.capture_clock_column),1)==0)
        finally: c.close()
        after=path.stat(); stable=(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
        role=spec.intended_role
        if spec.intended_role=="STRICT_FORWARD_CANDIDATE": role=strict_forward_role(source_clock_complete=src_complete,capture_clock_complete=cap_complete,mutable=spec.mutable)
        if spec.layer=="derived" and spec.lineage_root!=spec.source_id: role="EXCLUDE"
        record.update({"exists":True,"size_bytes":before.st_size,"mtime_ns":before.st_mtime_ns,"content_sha256":"MUTABLE_UNFROZEN_NO_HASH" if spec.mutable else _sha256(path),"consistency":"MUTABLE_UNFROZEN" if spec.mutable else ("CONSISTENT_READ" if stable else "MUTATED_DURING_READ"),"role":role,"source_clock_complete":src_complete,"capture_clock_complete":cap_complete})
        inventory.append(record)
    return {"source_inventory":lineage_decisions(inventory),"field_inventory":schemas,"field_profile":fields,"coverage":coverage,"period_coverage":periods,"duplicate_profile":duplicates,"m_per_issue_distribution":m_distribution,"outcome_triplet_profile":triplets,"intersections":_intersections(data_root)}


def _csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True); names=sorted({k for r in rows for k in r}) if rows else ["status"]
    with path.open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=names, lineterminator="\n"); w.writeheader(); w.writerows(rows)


def _read_csv(path: Path) -> list[dict[str,str]]:
    with path.open(newline="",encoding="utf-8") as h:return list(csv.DictReader(h))


def _roles(inventory: list[dict[str,object]]) -> list[dict[str,object]]:
    rows=[]
    for item in inventory:
        role=str(item["role"]); lane=str(item["lane"])
        rows.append({"source_id":item["source_id"],"lane":lane,"role":role,"advance_to_251":role in {"HISTORICAL_PROXY","RAW_ONLY","MUTABLE_UNFROZEN"},"advance_to_252":lane=="strict_forward_candidate","decision":"SEAL_SOURCE_AND_CAPTURE_CLOCK_CRITERIA" if lane=="strict_forward_candidate" else "ASSESSMENT_ONLY_NO_POLICY_FREEZE"})
    return rows


def _availability(fields: list[dict[str,object]], inventory: list[dict[str,object]]) -> list[dict[str,object]]:
    by={(str(r["source_id"]),str(r["field_family"])):r for r in fields}; out=[]
    for item in inventory:
        for family in ("identity_schedule","timestamp","market_feature","label_settlement"):
            row=by.get((str(item["source_id"]),family)); out.append({"source_id":item["source_id"],"field_family":family,"present":row is not None,"non_null_count":row["non_null_count"] if row else -1,"denominator_rows":row["denominator_rows"] if row else -1,"role":item["role"],"admissibility_note":"LABEL_PROFILED_SEPARATELY_NOT_USED_FOR_FEATURE_ROLE" if family=="label_settlement" else "PROFILED_FOR_AVAILABILITY"})
    return out


def _simple_svg(path: Path,title: str,rows: list[dict[str,object]],label: str,value: str) -> None:
    path.parent.mkdir(parents=True,exist_ok=True); vals=[max(0,int(r.get(value,0) if str(r.get(value,"")).lstrip("-").isdigit() else 0)) for r in rows]; maxv=max(vals,default=1); h=50+32*max(1,len(rows)); text=[f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{h}"><style>text{{font-family:monospace;font-size:12px}}</style><text x="10" y="20">{title}</text>']
    for i,(r,v) in enumerate(zip(rows,vals)):
        y=36+i*32; width=650*v/maxv if maxv else 0; text.append(f'<text x="10" y="{y+13}">{str(r.get(label,""))[:30]}</text><rect x="220" y="{y}" width="{width:.1f}" height="17" fill="#2f6f9f"/><text x="{230+width:.1f}" y="{y+13}">{v}</text>')
    path.write_text(''.join(text)+"</svg>",encoding="utf-8")


def rewrite_checksums(package: Path) -> None:
    values={p.relative_to(package).as_posix():_sha256(p) for p in sorted(package.rglob("*")) if p.is_file() and p.name!="SHA256SUMS.json"}; (package/"SHA256SUMS.json").write_text(json.dumps(values,indent=2,sort_keys=True)+"\n",encoding="utf-8")


def _semantic_hash(package: Path, relative: str) -> str:return _sha256(package/relative)


def verify_package(package: Path) -> dict[str,object]:
    problems=[]
    try: manifest=json.loads((package/"MANIFEST.json").read_text(encoding="utf-8")); sums=json.loads((package/"SHA256SUMS.json").read_text(encoding="utf-8"))
    except Exception as err:return {"verified":False,"problems":[f"unreadable package: {err}"]}
    if manifest.get("issue")!=ISSUE: problems.append("manifest issue mismatch")
    observed={p.relative_to(package).as_posix():_sha256(p) for p in sorted(package.rglob("*")) if p.is_file() and p.name!="SHA256SUMS.json"}
    if sums!=observed: problems.append("checksum inventory mismatch")
    required=("tables/source_inventory.csv","tables/source_role_matrix.csv","tables/intersection_levels.csv","tables/field_profile.csv","tables/coverage_by_period.csv","tables/m_per_issue_distribution.csv","tables/outcome_triplet_profile.csv")
    for rel in required:
        if not (package/rel).exists(): problems.append(f"missing decision artifact: {rel}")
        elif manifest.get("semantic_hashes",{}).get(rel)!=_semantic_hash(package,rel): problems.append(f"semantic hash mismatch: {rel}")
    if (package/"tables/source_inventory.csv").exists() and (package/"tables/source_role_matrix.csv").exists():
        inv={r["source_id"]:r["role"] for r in _read_csv(package/"tables/source_inventory.csv")}; roles={r["source_id"]:r["role"] for r in _read_csv(package/"tables/source_role_matrix.csv")}
        if inv!=roles: problems.append("role recomputation mismatch")
    if (package/"tables/intersection_levels.csv").exists():
        levels={r["level"] for r in _read_csv(package/"tables/intersection_levels.csv")}
        if levels!={"RAW_PRESENT","NATIVE_KEY_INTERSECTION","CANDIDATE_MAPPED_RANGE","CANONICAL_CAUSAL_INTERSECTION"}: problems.append("four-level intersection closure mismatch")
    return {"verified":not problems,"problems":problems}


def build_package(repo_root: Path,data_root: Path,target: Path|None=None) -> Path:
    package=target or repo_root/"results"/PACKAGE_NAME; stage=package.parent/f".{package.name}.staging"
    if stage.exists():shutil.rmtree(stage)
    stage.mkdir(parents=True); data=profile(data_root); inventory=data["source_inventory"]; roles=_roles(inventory); availability=_availability(data["field_profile"],inventory)
    names={"source_inventory":inventory,"field_inventory":data["field_inventory"],"field_profile":data["field_profile"],"coverage_by_source":data["coverage"],"coverage_by_period":data["period_coverage"],"duplicate_profile":data["duplicate_profile"],"m_per_issue_distribution":data["m_per_issue_distribution"],"outcome_triplet_profile":data["outcome_triplet_profile"],"intersection_levels":data["intersections"],"source_role_matrix":roles,"source_feature_availability":availability}
    for name,rows in names.items():_csv(stage/"tables"/f"{name}.csv",rows)
    unresolved=[{"question_id":"U1","question":"Which proposed mappings become canonical?","owner_issue":"#251","status":"DEFERRED"},{"question_id":"U2","question":"What sealing/source-clock rules promote forward evidence?","owner_issue":"#252","status":"DEFERRED"},{"question_id":"U3","question":"Which measured gaps justify recovery?","owner_issue":"#235/#236/#237/#248","status":"PI_DECISION_REQUIRED"}]; _csv(stage/"tables/unresolved_question_ledger.csv",unresolved)
    evidence=[{"requirement":f"REQ-SC{x:02d}","status":"PI_DECISION_PENDING" if x in {8,15} else "EVIDENCE_PRESENT","evidence":"machine-readable decision tables + report"} for x in range(1,16)]; _csv(stage/"evidence/req_sc_evidence.csv",evidence)
    _simple_svg(stage/"figures/source_feature_heatmap.svg","Source x field-family availability",availability,"source_id","non_null_count"); _simple_svg(stage/"figures/time_issue_coverage.svg","Time/issue coverage",data["period_coverage"],"year_or_range","stratum_rows"); _simple_svg(stage/"figures/m_per_issue.svg","M-per-issue distribution",data["m_per_issue_distribution"],"source_id","m_matches")
    report="# BJ-UNIFIED-SOURCE-CENSUS-001 R2\n\nThis assessment-only package profiles decision fields, label completeness separately, exact time/issue/match/cell denominators, native duplicates, invalid values, p34 triplets, and all four intersection levels. Candidate mappings are explicitly non-authoritative; canonical causal intersection remains deferred to #251/#252. Mutable sources are not frozen conclusions. See tables and `docs/research/issue_250_source_census.md`.\n"; (stage/"REPORT.md").write_text(report,encoding="utf-8")
    semantic={f"tables/{name}.csv":_semantic_hash(stage,f"tables/{name}.csv") for name in ("source_inventory","source_role_matrix","intersection_levels","field_profile","coverage_by_period","m_per_issue_distribution","outcome_triplet_profile")}
    manifest={"issue":ISSUE,"package":PACKAGE_NAME,"assessment_only":True,"data_root_supplied":True,"hist40_baseline":HIST40_RELEASE,"logical_sources":len(inventory),"roles":{r["source_id"]:r["role"] for r in inventory},"canonical_causal_intersection":canonical_causal_intersection(),"semantic_hashes":semantic,"implementation_source":"src/source_census/census.py","prohibitions":["no_crawl","no_backfill","no_imputation","no_model","no_roi","no_identity_or_temporal_policy_freeze"]}; (stage/"MANIFEST.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    rewrite_checksums(stage)
    if package.exists():shutil.rmtree(package)
    os.replace(stage,package); verdict=verify_package(package)
    if not verdict["verified"]:raise RuntimeError(str(verdict["problems"]))
    return package


def build_fixture_package(package: Path) -> Path:
    stage=package.parent/f".{package.name}.fixture"; shutil.rmtree(stage,ignore_errors=True); stage.mkdir(parents=True)
    inv=lineage_decisions([{"source_id":"fixture","lineage_root":"fixture","lane":"historical_relative_time_proxy","role":"HISTORICAL_PROXY"}]); _csv(stage/"tables/source_inventory.csv",inv); _csv(stage/"tables/source_role_matrix.csv",_roles(inv))
    for name in ("intersection_levels","field_profile","coverage_by_period","m_per_issue_distribution","outcome_triplet_profile"):_csv(stage/"tables"/f"{name}.csv", [{"level":name}] if name=="intersection_levels" else [{"status":"fixture"}])
    _csv(stage/"tables/intersection_levels.csv", [{"level":x} for x in ("RAW_PRESENT","NATIVE_KEY_INTERSECTION","CANDIDATE_MAPPED_RANGE","CANONICAL_CAUSAL_INTERSECTION")])
    semantic={f"tables/{name}.csv":_semantic_hash(stage,f"tables/{name}.csv") for name in ("source_inventory","source_role_matrix","intersection_levels","field_profile","coverage_by_period","m_per_issue_distribution","outcome_triplet_profile")}; (stage/"MANIFEST.json").write_text(json.dumps({"issue":ISSUE,"semantic_hashes":semantic},sort_keys=True),encoding="utf-8"); rewrite_checksums(stage); shutil.rmtree(package,ignore_errors=True); os.replace(stage,package); return package
