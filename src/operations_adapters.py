"""Database/config adapters for Operations Status v2 collection facts."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


COLLECTION_PLAN_SCHEMA = "data_collection_plan_v1"
CHECKPOINT_COLLECTORS = frozenset(
    {
        "score_model_euro_titan",
        "score_model_over_under_titan",
        "correct_score_price_okooo",
    }
)
MARKET_BY_COLLECTOR = {
    "market_sp_total_goals_500": ("40",),
    "market_sp_upper_lower_odd_even_500": ("41",),
    "market_sp_correct_score_500": ("42",),
    "market_sp_half_full_500": ("51",),
    "score_model_euro_titan": ("euro_1x2",),
    "score_model_over_under_titan": ("over_under",),
    "correct_score_price_okooo": ("correct_score",),
}
TABLE_TELEMETRY_BY_COVERAGE = {
    "nowscore_details": "nowscore_match_details",
    "match_intelligence": "match_intel_digest",
    "match_details_500": "match_details_500",
}


class CollectionPlanError(ValueError):
    """The machine-readable collector plan is missing or invalid."""


def _safe_diagnostic_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(
        r"(?<![:\w])/(?:home|Users|tmp|var|opt|srv|root|private|mnt)/[^\s,;]+",
        "[redacted-path]",
        text,
    )
    return re.sub(r"\b[A-Za-z]:\\[^\s,;]+", "[redacted-path]", text)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def load_collection_plan(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectionPlanError(f"cannot read collector plan: {type(exc).__name__}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != COLLECTION_PLAN_SCHEMA:
        raise CollectionPlanError("collector plan schema_version must be data_collection_plan_v1")
    collectors = payload.get("collectors")
    if not isinstance(collectors, list) or not collectors:
        raise CollectionPlanError("collector plan must contain a non-empty collectors list")
    ids: set[str] = set()
    for item in collectors:
        if not isinstance(item, dict):
            raise CollectionPlanError("collector entry must be an object")
        collector_id = str(item.get("collector_id") or "")
        if not collector_id or collector_id in ids:
            raise CollectionPlanError("collector_id must be present and unique")
        ids.add(collector_id)
        if item.get("importance") not in {"critical", "important", "fallback"}:
            raise CollectionPlanError(f"collector {collector_id} has invalid importance")
        for field in ("schedule_interval_sec", "stale_after_sec"):
            if not isinstance(item.get(field), (int, float)) or float(item[field]) < 0:
                raise CollectionPlanError(f"collector {collector_id} has invalid {field}")
    return payload


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _iso(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value else ""


def _fetch_telemetry(
    conn: sqlite3.Connection,
    *,
    issue: str,
    kind: str,
) -> dict[str, Any]:
    if not kind or not _table_exists(conn, "fetch_log"):
        return {}
    row = conn.execute(
        """
        SELECT
          MAX(fetched_at) AS last_attempt_at,
          MAX(CASE WHEN ok=1 THEN fetched_at ELSE '' END) AS last_success_at,
          MAX(CASE WHEN ok=0 THEN fetched_at ELSE '' END) AS last_error_at,
          SUM(CASE WHEN ok=1 THEN 1 ELSE 0 END) AS ok_count,
          SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS fail_count,
          COUNT(*) AS total_attempts,
          SUM(COALESCE(rows_parsed, 0)) AS rows_parsed
        FROM fetch_log
        WHERE kind=? AND (issue=? OR issue IS NULL)
        """,
        (kind, issue),
    ).fetchone()
    if row is None or not row["last_attempt_at"]:
        return {}
    last_attempt = str(row["last_attempt_at"] or "")
    last_success = str(row["last_success_at"] or "")
    error_row = conn.execute(
        """
        SELECT error
        FROM fetch_log
        WHERE kind=? AND (issue=? OR issue IS NULL) AND ok=0
        ORDER BY fetched_at DESC, id DESC
        LIMIT 1
        """,
        (kind, issue),
    ).fetchone()
    first_unhealthy_row = conn.execute(
        """
        SELECT MIN(fetched_at)
        FROM fetch_log
        WHERE kind=? AND (issue=? OR issue IS NULL) AND ok=0
          AND (?='' OR fetched_at>?)
        """,
        (kind, issue, last_success, last_success),
    ).fetchone()
    return {
        "last_attempt_at": last_attempt,
        "last_success_at": last_success,
        "last_error_at": str(row["last_error_at"] or ""),
        "first_unhealthy_at": str(first_unhealthy_row[0] or "") if first_unhealthy_row else "",
        "latest_attempt_failed": str(row["last_error_at"] or "") == last_attempt,
        "ok_count": int(row["ok_count"] or 0),
        "fail_count": int(row["fail_count"] or 0),
        "total_attempts": int(row["total_attempts"] or 0),
        "rows_parsed": int(row["rows_parsed"] or 0),
        "error": str(error_row["error"] or "") if error_row else "",
    }


def _table_telemetry(
    conn: sqlite3.Connection,
    *,
    issue: str,
    table: str,
) -> dict[str, Any]:
    columns = _columns(conn, table)
    if not {"issue", "fetched_at", "status"}.issubset(columns):
        return {}
    row = conn.execute(
        f"""
        SELECT
          MAX(fetched_at) AS last_attempt_at,
          MAX(CASE WHEN status='ok' THEN fetched_at ELSE '' END) AS last_success_at,
          MAX(CASE WHEN status!='ok' THEN fetched_at ELSE '' END) AS last_error_at,
          SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) AS ok_count,
          SUM(CASE WHEN status!='ok' THEN 1 ELSE 0 END) AS fail_count,
          COUNT(*) AS total_attempts
        FROM {table}
        WHERE issue=?
        """,
        (issue,),
    ).fetchone()
    if row is None or not row["last_attempt_at"]:
        return {}
    last_attempt = str(row["last_attempt_at"] or "")
    last_success = str(row["last_success_at"] or "")
    last_error = str(row["last_error_at"] or "")
    first_unhealthy_row = conn.execute(
        f"""
        SELECT MIN(fetched_at)
        FROM {table}
        WHERE issue=? AND status!='ok' AND (?='' OR fetched_at>?)
        """,
        (issue, last_success, last_success),
    ).fetchone()
    error = ""
    if last_error == last_attempt and "error" in columns:
        error_row = conn.execute(
            f"""
            SELECT error
            FROM {table}
            WHERE issue=? AND status!='ok'
            ORDER BY fetched_at DESC
            LIMIT 1
            """,
            (issue,),
        ).fetchone()
        error = str(error_row[0] or "") if error_row else ""
    return {
        "last_attempt_at": last_attempt,
        "last_success_at": last_success,
        "last_error_at": last_error,
        "first_unhealthy_at": str(first_unhealthy_row[0] or "") if first_unhealthy_row else "",
        "latest_attempt_failed": bool(last_error and last_error == last_attempt),
        "ok_count": int(row["ok_count"] or 0),
        "fail_count": int(row["fail_count"] or 0),
        "total_attempts": int(row["total_attempts"] or 0),
        "rows_parsed": int(row["ok_count"] or 0),
        "error": error,
    }


def _count_distinct(
    conn: sqlite3.Connection,
    table: str,
    *,
    issue: str,
    playid: int | None = None,
    status_ok: bool = False,
) -> set[int]:
    columns = _columns(conn, table)
    if not {"issue", "match_idx"}.issubset(columns) and not {"issue", "row_idx"}.issubset(columns):
        return set()
    identity = "match_idx" if "match_idx" in columns else "row_idx"
    where = ["issue=?"]
    params: list[Any] = [issue]
    if playid is not None and "playid" in columns:
        where.append("playid=?")
        params.append(playid)
    if status_ok and "status" in columns:
        where.append("status='ok'")
    query = f"SELECT DISTINCT {identity} FROM {table} WHERE {' AND '.join(where)}"
    return {int(row[0]) for row in conn.execute(query, params) if row[0] is not None}


def _coverage(
    conn: sqlite3.Connection,
    *,
    collector: Mapping[str, Any],
    issue: str,
    expected_indices: set[int],
) -> dict[str, Any]:
    check = str(collector.get("coverage_check") or "")
    actual: set[int] = set()
    if check == "issue_list":
        expected = {"current"}
        row = conn.execute(
            "SELECT 1 FROM issues WHERE issue=? LIMIT 1",
            (issue,),
        ).fetchone() if _table_exists(conn, "issues") else None
        actual_labels = {"current"} if row else set()
        return {
            "expected_count": 1,
            "covered_count": len(actual_labels),
            "missing_count": 1 - len(actual_labels),
            "missing_match_ids": [],
            "coverage_rate": float(len(actual_labels)),
        }
    if check == "matches_sp":
        if _table_exists(conn, "matches"):
            columns = _columns(conn, "matches")
            sp_fields = [field for field in ("sp_home", "sp_draw", "sp_away") if field in columns]
            condition = " AND ".join(f"{field} IS NOT NULL" for field in sp_fields) or "1=1"
            actual = {
                int(row[0])
                for row in conn.execute(
                    f"SELECT match_idx FROM matches WHERE issue=? AND {condition}",
                    (issue,),
                )
            }
    elif check == "live_sp_snapshots":
        actual = _count_distinct(conn, "live_sp_snapshots", issue=issue, playid=34)
    elif check.startswith("market_sp_"):
        playid = next(
            (
                int(value)
                for value in MARKET_BY_COLLECTOR.get(str(collector.get("collector_id")), ())
                if value.isdigit()
            ),
            None,
        )
        actual = _count_distinct(conn, "live_market_sp_snapshots", issue=issue, playid=playid)
    elif check == "nowscore_mapping":
        actual = _count_distinct(conn, "nowscore_bjdc_matches", issue=issue)
    elif check == "nowscore_details":
        actual = _count_distinct(conn, "nowscore_match_details", issue=issue, status_ok=True)
    elif check == "match_intelligence":
        actual = _count_distinct(conn, "match_intel_digest", issue=issue, status_ok=True)
    elif check == "match_details_500":
        actual = _count_distinct(conn, "match_details_500", issue=issue, status_ok=True)
    else:
        return {
            "expected_count": len(expected_indices),
            "covered_count": 0,
            "missing_count": 0,
            "missing_match_ids": [],
            "coverage_rate": None,
            "coverage_status": "not_applicable",
        }
    missing = sorted(expected_indices - actual)
    expected_count = len(expected_indices)
    covered_count = max(0, expected_count - len(missing))
    return {
        "expected_count": expected_count,
        "covered_count": covered_count,
        "missing_count": len(missing),
        "missing_match_ids": [f"{issue}_{idx:03d}" for idx in missing],
        "coverage_rate": (covered_count / expected_count) if expected_count else None,
        "coverage_status": (
            "ok"
            if expected_count and not missing
            else "partial"
            if covered_count
            else "missing"
        ),
    }


def _source_meta(conn: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(conn, "source_meta"):
        return {}
    return {str(row[0]): str(row[1] or "") for row in conn.execute("SELECT key,value FROM source_meta")}


def _legacy_prekick_facts(
    database_path: Path,
    *,
    issue: str,
    expected_indices: set[int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    actual: set[int] = set()
    telemetry: dict[str, Any] = {}
    if database_path.is_file():
        try:
            external = sqlite3.connect(
                f"file:{database_path.resolve()}?mode=ro",
                uri=True,
            )
            external.row_factory = sqlite3.Row
            try:
                row = external.execute(
                    """
                    SELECT MAX(s.snapshot_ts) AS last_success_at, COUNT(*) AS snapshot_count
                    FROM snapshots s
                    JOIN matches m ON m.match_id=s.match_id
                    WHERE m.issue=?
                    """,
                    (issue,),
                ).fetchone()
                actual = {
                    int(item[0])
                    for item in external.execute(
                        """
                        SELECT DISTINCT m.match_idx
                        FROM snapshots s
                        JOIN matches m ON m.match_id=s.match_id
                        WHERE m.issue=?
                        """,
                        (issue,),
                    )
                    if item[0] is not None
                }
            finally:
                external.close()
            if row and row["last_success_at"]:
                last_success = str(row["last_success_at"])
                telemetry = {
                    "last_attempt_at": last_success,
                    "last_success_at": last_success,
                    "last_error_at": "",
                    "latest_attempt_failed": False,
                    "ok_count": int(row["snapshot_count"] or 0),
                    "fail_count": 0,
                    "total_attempts": int(row["snapshot_count"] or 0),
                    "rows_parsed": int(row["snapshot_count"] or 0),
                    "error": "",
                }
        except sqlite3.Error as exc:
            telemetry = {
                "last_attempt_at": "",
                "last_success_at": "",
                "last_error_at": "",
                "latest_attempt_failed": True,
                "ok_count": 0,
                "fail_count": 1,
                "total_attempts": 1,
                "rows_parsed": 0,
                "error": f"legacy prekick database probe failed: {type(exc).__name__}",
            }
    missing = sorted(expected_indices - actual)
    expected_count = len(expected_indices)
    covered_count = max(0, expected_count - len(missing))
    coverage = {
        "expected_count": expected_count,
        "covered_count": covered_count,
        "missing_count": len(missing),
        "missing_match_ids": [f"{issue}_{idx:03d}" for idx in missing],
        "coverage_rate": (covered_count / expected_count) if expected_count else None,
        "coverage_status": (
            "ok"
            if expected_count and not missing
            else "partial"
            if covered_count
            else "missing"
        ),
    }
    return telemetry, coverage


def build_collection_domain(
    conn: sqlite3.Connection,
    *,
    issue: str,
    current_issue: str,
    observed_at: datetime,
    plan_path: Path,
) -> dict[str, Any]:
    """Build independent collector facts from the registered collection plan."""

    try:
        plan = load_collection_plan(plan_path)
    except CollectionPlanError as exc:
        return {
            "status": "failed",
            "plan_status": "failed",
            "plan_schema_version": "",
            "plan_error": str(exc),
            "collectors": [],
        }

    expected_indices = (
        {
            int(row[0])
            for row in conn.execute(
                "SELECT match_idx FROM matches WHERE issue=? ORDER BY match_idx",
                (issue,),
            )
        }
        if _table_exists(conn, "matches")
        else set()
    )
    source_meta = _source_meta(conn)
    project_root = plan_path.resolve().parent.parent
    issue_first_seen_at = ""
    issue_columns = _columns(conn, "issues")
    if "first_seen_at" in issue_columns:
        issue_row = conn.execute(
            "SELECT first_seen_at FROM issues WHERE issue=? LIMIT 1",
            (issue,),
        ).fetchone()
        issue_first_seen_at = str(issue_row[0] or "") if issue_row else ""
    rows: list[dict[str, Any]] = []
    is_current = issue == current_issue
    for definition in plan["collectors"]:
        collector = dict(definition)
        collector_id = str(collector["collector_id"])
        enabled = bool(collector.get("enabled"))
        telemetry = _fetch_telemetry(
            conn,
            issue=issue,
            kind=str(collector.get("fetch_log_kind") or ""),
        )
        coverage_check = str(collector.get("coverage_check") or "")
        if not telemetry and coverage_check in TABLE_TELEMETRY_BY_COVERAGE:
            telemetry = _table_telemetry(
                conn,
                issue=issue,
                table=TABLE_TELEMETRY_BY_COVERAGE[coverage_check],
            )
        if (
            collector_id in {"score_model_euro_titan", "score_model_over_under_titan"}
            and (
                source_meta.get("score_model_odds_last_attempt_at")
                or source_meta.get("score_model_odds_last_success_at")
            )
        ):
            telemetry = {
                **telemetry,
                "last_attempt_at": source_meta.get("score_model_odds_last_attempt_at", ""),
                "last_success_at": source_meta.get("score_model_odds_last_success_at", ""),
                "latest_attempt_failed": source_meta.get("score_model_odds_last_status") == "failed",
                "error": (
                    "最近比分模型赔率检查点失败"
                    if source_meta.get("score_model_odds_last_status") == "failed"
                    else telemetry.get("error", "")
                ),
            }
        coverage = _coverage(
            conn,
            collector=collector,
            issue=issue,
            expected_indices=expected_indices,
        )
        if collector_id == "legacy_prekick_snapshot":
            database_path = project_root / str(collector.get("database") or "")
            telemetry, coverage = _legacy_prekick_facts(
                database_path,
                issue=issue,
                expected_indices=expected_indices,
            )
        interval = float(collector.get("schedule_interval_sec") or 0)
        stale_after = float(collector.get("stale_after_sec") or 0)
        attempt_at = _parse_time(telemetry.get("last_attempt_at"))
        success_at = _parse_time(telemetry.get("last_success_at"))
        age_seconds = (
            max(0.0, (observed_at.astimezone(success_at.tzinfo) - success_at).total_seconds())
            if success_at
            else None
        )
        next_due = attempt_at + timedelta(seconds=interval) if attempt_at and interval else None
        if not enabled or not is_current:
            status = "not_applicable"
            status_detail = "待命采集器" if not enabled else "历史期不执行当前期采集 SLA"
        elif collector_id in CHECKPOINT_COLLECTORS and not telemetry:
            status = "due"
            status_detail = "按 segment 检查点运行；当前无通用 fetch_log 遥测"
        elif not telemetry:
            status = "missing"
            status_detail = "尚无该采集器的运行遥测"
        elif telemetry.get("latest_attempt_failed"):
            status = "failed"
            status_detail = "最近一次采集尝试失败"
        elif coverage.get("coverage_status") in {"missing", "partial"}:
            status = str(coverage["coverage_status"])
            status_detail = "当前期覆盖不完整"
        elif stale_after and (age_seconds is None or age_seconds > stale_after):
            status = "stale"
            status_detail = "最近成功已超过该采集器 SLA"
        else:
            status = "ok"
            status_detail = "最近成功和当前期覆盖符合计划"
        if status == "stale" and success_at and stale_after:
            first_unhealthy_at = _iso(success_at + timedelta(seconds=stale_after))
        elif status == "failed":
            first_unhealthy_at = str(
                telemetry.get("first_unhealthy_at")
                or telemetry.get("last_error_at")
                or issue_first_seen_at
            )
        elif status in {"missing", "partial"}:
            first_unhealthy_at = str(
                issue_first_seen_at
                or telemetry.get("last_attempt_at")
                or telemetry.get("last_success_at")
            )
        else:
            first_unhealthy_at = ""
        rows.append(
            {
                "collector_id": collector_id,
                "label": str(collector.get("label") or collector_id),
                "importance": str(collector.get("importance") or "important"),
                "enabled": enabled,
                "owner_process": str(collector.get("owner_process") or ""),
                "process_status": "not_applicable",
                "status": status,
                "status_detail": status_detail,
                "schedule_interval_sec": interval,
                "stale_after_sec": stale_after,
                "last_attempt_at": str(telemetry.get("last_attempt_at") or ""),
                "last_success_at": str(telemetry.get("last_success_at") or ""),
                "last_error_at": str(telemetry.get("last_error_at") or ""),
                "first_unhealthy_at": first_unhealthy_at,
                "next_due_at": _iso(next_due),
                "age_minutes": round(age_seconds / 60, 3) if age_seconds is not None else None,
                "coverage_rate": coverage.get("coverage_rate"),
                "covered_count": int(coverage.get("covered_count") or 0),
                "expected_count": int(coverage.get("expected_count") or 0),
                "missing_count": int(coverage.get("missing_count") or 0),
                "missing_match_ids": list(coverage.get("missing_match_ids") or []),
                "ok_count": int(telemetry.get("ok_count") or 0),
                "fail_count": int(telemetry.get("fail_count") or 0),
                "total_attempts": int(telemetry.get("total_attempts") or 0),
                "rows_parsed": int(telemetry.get("rows_parsed") or 0),
                "error": _safe_diagnostic_text(telemetry.get("error")),
                "markets": list(MARKET_BY_COLLECTOR.get(collector_id, ())),
                "auto_recovery_expected": enabled and interval > 0,
                "retry_count": int(telemetry.get("fail_count") or 0),
                "maintenance_action": str(collector.get("maintenance_action") or ""),
                "links": [
                    {
                        "kind": "page",
                        "label": "采集明细",
                        "ref": f"operations:#collector-{collector_id}",
                    }
                ],
            }
        )
    relevant_statuses = [row["status"] for row in rows if row["enabled"] and row["status"] != "not_applicable"]
    rank = {
        "failed": 8,
        "blocked": 7,
        "missing": 6,
        "stale": 5,
        "partial": 4,
        "due": 3,
        "running": 2,
        "ok": 1,
        "not_applicable": 0,
    }
    status = max(relevant_statuses, key=lambda value: rank.get(value, 9), default="not_applicable")
    return {
        "status": status,
        "plan_status": "ok",
        "plan_schema_version": str(plan["schema_version"]),
        "plan_ref": "config:data_collection_plan_v1",
        "plan_error": "",
        "collectors": rows,
    }
