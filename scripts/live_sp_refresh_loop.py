#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrape_500_bjdc import (  # noqa: E402
    DEFAULT_DB,
    DEFAULT_UA,
    create_schema,
    fetch_issue_list,
    issue_year,
    parse_playids,
    scrape_issue,
    scrape_live_sp,
)
from src.sqlite_runtime import connect_sqlite  # noqa: E402
from src.multimarket_p0 import (  # noqa: E402
    DEFAULT_SEGMENT_FREEZE_ROOT,
    HKT,
    MultimarketP0Error,
    TARGET_PLAYIDS as P0_TARGET_PLAYIDS,
    build_settlement_truth,
    freeze_segment,
    parse_hkt,
    segment_event_id,
)


DEFAULT_INTERVAL_SEC = 900.0


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _current_issue(issue_rows: list[dict[str, object]]) -> str:
    for row in issue_rows:
        if int(row.get("is_current") or 0):
            return str(row["issue"])
    return str(issue_rows[0]["issue"]) if issue_rows else ""


def _split_requested_issues(raw_values: list[str]) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for part in raw.replace("，", ",").split(","):
            issue = part.strip()
            if issue and issue not in seen:
                issues.append(issue)
                seen.add(issue)
    return issues


def _open_local_issues(
    conn,
    *,
    min_year: int | None,
    limit: int,
) -> list[str]:
    if limit <= 0:
        return []
    where = ""
    params: list[object] = []
    if min_year is not None:
        where = "WHERE CAST(substr(issue, 1, 2) AS INTEGER) + 2000 >= ?"
        params.append(min_year)
    rows = conn.execute(
        f"""
        SELECT
          issue,
          COUNT(*) AS n_matches,
          SUM(CASE WHEN winning_sp IS NOT NULL THEN 1 ELSE 0 END) AS n_settled,
          MAX(COALESCE(end_time, '')) AS latest_end_time,
          MAX(COALESCE(fetched_at, '')) AS latest_fetched_at
        FROM matches
        {where}
        GROUP BY issue
        HAVING n_matches > n_settled
        ORDER BY latest_end_time DESC, CAST(issue AS INTEGER) DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [str(row["issue"]) for row in rows]


def resolve_sp_refresh_issues(
    conn,
    issue_rows: list[dict[str, object]],
    requested: list[str],
    *,
    recent_count: int,
    open_limit: int,
    open_year_lookback: int,
) -> list[str]:
    requested = _split_requested_issues(requested)
    current = _current_issue(issue_rows)
    recent = [str(row["issue"]) for row in issue_rows[: max(0, recent_count)]]
    current_year = issue_year(current) if current else None
    min_year = None if current_year is None else max(2000, current_year - open_year_lookback)
    open_issues = _open_local_issues(conn, min_year=min_year, limit=open_limit)

    selected: list[str] = []
    for issue in [*requested, *recent, *open_issues]:
        resolved = current if issue == "current" else issue
        if resolved and resolved not in selected:
            selected.append(resolved)
    return selected


def _scrape_namespace(args: argparse.Namespace, playid: int) -> SimpleNamespace:
    return SimpleNamespace(
        timeout=args.timeout,
        user_agent=args.user_agent,
        force=args.force,
        keep_going=True,
        live_sp=True,
        playid=playid,
        sleep=0,
    )


def _record_source_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO source_meta(key, value) VALUES(?, ?)", (key, value))


def _prospective_config() -> tuple[datetime, int]:
    task = yaml.safe_load((ROOT / ".research/tasks/BJ-MM-FREEZE-001.yaml").read_text(encoding="utf-8"))
    registration = task["spec"]["context"]["preregistration"]
    return parse_hkt(str(registration["activation_utc"])), int(registration["required_prospective_segment_events"])


def _ensure_segment_freeze_evidence_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS multimarket_segment_freeze_events (
            event_id TEXT PRIMARY KEY, issue TEXT NOT NULL, segment_idx INTEGER NOT NULL,
            effective_freeze_at_hkt TEXT NOT NULL, activation_utc TEXT NOT NULL,
            ordinal INTEGER NOT NULL UNIQUE, selected_at_utc TEXT NOT NULL,
            UNIQUE(issue, segment_idx)
        );
        CREATE TABLE IF NOT EXISTS multimarket_segment_freeze_attempts (
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
            attempted_at_utc TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL,
            FOREIGN KEY(event_id) REFERENCES multimarket_segment_freeze_events(event_id)
        );
        """
    )


def _record_segment_attempt(conn, event_id: str, status: str, reason: str = "") -> None:
    conn.execute(
        "INSERT INTO multimarket_segment_freeze_attempts(event_id,attempted_at_utc,status,reason) VALUES(?,?,?,?)",
        (event_id, datetime.now(timezone.utc).isoformat(timespec="seconds"), status, reason),
    )


def publish_due_segment_freezes(conn, issues: list[str], *, output_root: Path = DEFAULT_SEGMENT_FREEZE_ROOT,
                                now: datetime | None = None) -> list[dict[str, object]]:
    """Research-only, idempotent recovery for passed p40/p42 segment windows.

    It only delegates to the strict as-of publisher; it never fetches later data
    as a substitute and never invokes a strategy or execution path.
    """
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='segment_decision_windows'").fetchone() is None:
        return []
    _ensure_segment_freeze_evidence_schema(conn)
    activation, required_events = _prospective_config()
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(segment_decision_windows)")}
    manual = "manual_frozen_at" if "manual_frozen_at" in columns else "NULL"
    rows = conn.execute(
        f"SELECT issue,segment_idx,freeze_at,{manual} AS manual_frozen_at FROM segment_decision_windows "
        "ORDER BY issue,segment_idx",
    ).fetchall()
    current = (now or datetime.now(timezone.utc)).astimezone(HKT)
    existing = conn.execute(
        "SELECT event_id,issue,segment_idx,effective_freeze_at_hkt,ordinal FROM multimarket_segment_freeze_events ORDER BY ordinal"
    ).fetchall()
    selected_keys = {(str(row["issue"]), int(row["segment_idx"])) for row in existing}
    remaining = required_events - len(existing)
    candidates: list[tuple[datetime, str, int, str]] = []
    for row in rows:
        effective = str(row["manual_frozen_at"] or row["freeze_at"] or "")
        if not effective:
            continue
        decision_at = parse_hkt(effective)
        issue, segment_idx = str(row["issue"]), int(row["segment_idx"])
        if decision_at > activation and decision_at <= current and (issue, segment_idx) not in selected_keys:
            candidates.append((decision_at, issue, segment_idx, effective))
    for decision_at, issue, segment_idx, _effective in sorted(candidates)[:max(0, remaining)]:
        event_id = segment_event_id(issue, segment_idx, decision_at)
        conn.execute(
            "INSERT INTO multimarket_segment_freeze_events(event_id,issue,segment_idx,effective_freeze_at_hkt,activation_utc,ordinal,selected_at_utc) VALUES(?,?,?,?,?,?,?)",
            (event_id, issue, segment_idx, decision_at.isoformat(timespec="seconds"), activation.astimezone(timezone.utc).isoformat(timespec="seconds"), len(existing) + 1, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        existing.append(conn.execute("SELECT event_id,issue,segment_idx,effective_freeze_at_hkt,ordinal FROM multimarket_segment_freeze_events WHERE event_id=?", (event_id,)).fetchone())
    results: list[dict[str, object]] = []
    for row in existing:
        issue, segment_idx, event_id = str(row["issue"]), int(row["segment_idx"]), str(row["event_id"])
        issue, segment_idx = str(row["issue"]), int(row["segment_idx"])
        try:
            result = freeze_segment(conn, issue, segment_idx, output_root)
            _record_segment_attempt(conn, event_id, "complete", "")
            results.append({"issue": issue, "segment_idx": segment_idx, "status": "complete", "event_id": result["event_id"]})
        except (MultimarketP0Error, OSError, ValueError) as exc:
            _record_segment_attempt(conn, event_id, "retry", str(exc))
            results.append({"issue": issue, "segment_idx": segment_idx, "status": "retry", "reason": str(exc)})
    return results


def run_once(conn, args: argparse.Namespace) -> int:
    issue_rows = fetch_issue_list(conn, args)
    current = _current_issue(issue_rows)
    selected = resolve_sp_refresh_issues(
        conn,
        issue_rows,
        args.issue,
        recent_count=args.recent_count,
        open_limit=args.open_limit,
        open_year_lookback=args.open_year_lookback,
    )
    print(f"[{now_iso()}] live_sp_refresh current={current or '-'} selected={','.join(selected)}", flush=True)
    _record_source_meta(conn, "last_live_sp_refresh_started_at", now_iso())
    _record_source_meta(conn, "last_live_sp_refresh_selected_issues", ",".join(selected))
    conn.commit()

    playids = parse_playids(args.playid)
    issue_args = _scrape_namespace(args, playids[0])
    total_rows = 0
    total_live_rows = 0
    for index, issue in enumerate(selected, start=1):
        print(f"[{now_iso()}] live_sp_refresh issue={issue} {index}/{len(selected)}", flush=True)
        total_rows += scrape_issue(conn, issue, issue_args)
        if args.live_sp:
            for playid in playids:
                if playid != 34 and issue != current:
                    continue
                scrape_args = _scrape_namespace(args, playid)
                total_live_rows += scrape_live_sp(conn, issue, scrape_args)
        if any(playid in P0_TARGET_PLAYIDS for playid in playids):
            try:
                build_settlement_truth(conn, issue)
            except MultimarketP0Error as exc:
                print(f"[{now_iso()}] multimarket_settlement skipped issue={issue}: {exc}", flush=True)
        if args.sleep and index < len(selected):
            time.sleep(args.sleep)

    if any(playid in P0_TARGET_PLAYIDS for playid in playids):
        segment_results = publish_due_segment_freezes(conn, selected)
        _record_source_meta(conn, "last_multimarket_segment_freeze_results", json.dumps(segment_results, sort_keys=True))

    _record_source_meta(conn, "last_live_sp_refresh_finished_at", now_iso())
    _record_source_meta(conn, "last_live_sp_refresh_issue_count", str(len(selected)))
    _record_source_meta(conn, "last_live_sp_refresh_html_rows", str(total_rows))
    _record_source_meta(conn, "last_live_sp_refresh_xml_rows", str(total_live_rows))
    conn.commit()
    print(
        f"[{now_iso()}] live_sp_refresh done issues={len(selected)} "
        f"html_rows={total_rows} live_sp_rows={total_live_rows}",
        flush=True,
    )
    return total_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh 500.com BJDC issue HTML settlements and live SP XML on a low-frequency loop."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue", action="append", default=["current"], help="Issue id, comma-separated list, or current.")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    parser.add_argument("--recent-count", type=int, default=4)
    parser.add_argument("--open-limit", type=int, default=12)
    parser.add_argument("--open-year-lookback", type=int, default=1)
    parser.add_argument(
        "--playid",
        action="append",
        help="BJDC play id or comma-separated ids; repeatable. Default: 34,40,41,42,51.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--user-agent", default=DEFAULT_UA)
    parser.add_argument("--no-force", action="store_false", dest="force", default=True)
    parser.add_argument("--no-live-sp", action="store_false", dest="live_sp", default=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_sqlite(args.db, row_factory=True)
    create_schema(conn)

    while True:
        started = time.monotonic()
        try:
            run_once(conn, args)
        except Exception as exc:
            print(f"[{now_iso()}] live_sp_refresh error {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if args.once:
            return
        elapsed = time.monotonic() - started
        time.sleep(max(30.0, args.interval - elapsed))


if __name__ == "__main__":
    main()
