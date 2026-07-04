#!/usr/bin/env python3.14
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.live_score_refresh_loop import resolve_issues  # noqa: E402
from src.decision_api.app import create_app  # noqa: E402
from src.sqlite_runtime import connect_sqlite  # noqa: E402


DEFAULT_DB = Path(os.environ.get("BEIDAN_LIVE_SQLITE", ROOT / "data/derived/500_bjdc/500_bjdc.sqlite")).expanduser()
FORBIDDEN_TRACKED_SUFFIXES = {".sqlite", ".db", ".xlsm", ".xlsx"}
REQUIRED_DB_TABLES = {"issues", "matches"}


def _record(checks: list[dict[str, Any]], name: str, ok: bool, **details: Any) -> None:
    checks.append({"name": name, "ok": bool(ok), **details})


def _assert_response(checks: list[dict[str, Any]], name: str, response: Any, expected: int = 200) -> dict[str, Any]:
    payload = response.get_json(silent=True) or {}
    _record(checks, name, response.status_code == expected, status=response.status_code)
    if response.status_code != expected:
        raise RuntimeError(f"{name} failed: HTTP {response.status_code} {response.get_data(as_text=True)[:300]}")
    return payload


def _check_strategy_version_context(checks: list[dict[str, Any]], name: str, payload: dict[str, Any]) -> None:
    context = payload.get("strategy_version_context")
    ok = (
        isinstance(context, dict)
        and context.get("schema_version") == "strategy_version_context_v1"
        and bool(context.get("selected_variant_id"))
        and context.get("selection_status") in {"ok", "degraded"}
    )
    _record(
        checks,
        name,
        ok,
        selected_variant_id=context.get("selected_variant_id") if isinstance(context, dict) else "",
        selection_status=context.get("selection_status") if isinstance(context, dict) else "",
    )
    if not ok:
        raise RuntimeError(f"{name} missing usable strategy_version_context")


def _latest_settled_issue(db_path: Path) -> str:
    with connect_sqlite(db_path, row_factory=True, readonly=True) as conn:
        row = conn.execute(
            """
            SELECT issue
            FROM matches
            GROUP BY issue
            HAVING COUNT(*) > 0
               AND SUM(CASE WHEN winning_sp IS NOT NULL THEN 1 ELSE 0 END) = COUNT(*)
            ORDER BY MAX(COALESCE(end_time, '')) DESC, MAX(COALESCE(fetched_at, '')) DESC
            LIMIT 1
            """
        ).fetchone()
    return str(row["issue"]) if row else ""


def _validate_smoke_db(db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(
            f"SQLite DB not found: {db_path}. "
            "Pass --db or set BEIDAN_LIVE_SQLITE to the live 500_bjdc.sqlite path."
        )
    with connect_sqlite(db_path, row_factory=True, readonly=True) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    tables = {str(row["name"]) for row in rows}
    missing = sorted(REQUIRED_DB_TABLES - tables)
    if missing:
        raise RuntimeError(
            f"SQLite DB {db_path} is not a usable live Beidan DB; missing tables: {missing}. "
            "Pass --db or set BEIDAN_LIVE_SQLITE to the populated 500_bjdc.sqlite."
        )


def _tracked_data_file_violations() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git ls-files failed")
    violations: list[str] = []
    for line in proc.stdout.splitlines():
        path = line.strip()
        suffix = Path(path).suffix.lower()
        if path.startswith("data/") or suffix in FORBIDDEN_TRACKED_SUFFIXES:
            violations.append(path)
    return violations


def run_smoke(db_path: Path, issue: str, settlement_issue: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    _validate_smoke_db(db_path)

    app = create_app(sqlite_db=db_path)
    with app.test_client() as client:
        _assert_response(checks, "healthz", client.get("/healthz"))

        dashboard = _assert_response(checks, "dashboard", client.get(f"/api/issues/{issue}/dashboard"))
        _check_strategy_version_context(checks, "dashboard_strategy_version_context", dashboard)
        resolved_issue = str(dashboard.get("issue") or issue)
        matches = dashboard.get("matches") if isinstance(dashboard.get("matches"), list) else []
        if not matches:
            raise RuntimeError(f"dashboard returned no matches for {issue}")
        first_match = matches[0]
        if not first_match.get("selected_decision_variant_id"):
            raise RuntimeError("first dashboard match has no selected_decision_variant_id")
        match_id = str(first_match.get("match_id") or "")
        if not match_id:
            raise RuntimeError("first dashboard match has no match_id")
        _record(
            checks,
            "dashboard_payload",
            True,
            issue=resolved_issue,
            matches=len(matches),
            source_count=len(dashboard.get("source_freshness") or []),
            last_snapshot_ts=dashboard.get("last_snapshot_ts") or "",
        )

        match_detail = _assert_response(checks, "match_detail", client.get(f"/api/matches/{match_id}"))
        _check_strategy_version_context(checks, "match_detail_strategy_version_context", match_detail)
        _assert_response(checks, "operations", client.get(f"/api/issues/{resolved_issue}/operations"))
        _assert_response(checks, "signals", client.get(f"/api/issues/{resolved_issue}/signals"))
        main_strategy = _assert_response(checks, "main_strategy", client.get(f"/api/issues/{resolved_issue}/main-strategy"))
        _check_strategy_version_context(checks, "main_strategy_version_context", main_strategy)

        settled_issue = _latest_settled_issue(db_path) if settlement_issue == "auto" else settlement_issue
        if not settled_issue:
            raise RuntimeError("no fully settled issue found for settlement smoke")
        settlement = _assert_response(checks, "settlement", client.get(f"/api/issues/{settled_issue}/settlement"))
        _check_strategy_version_context(checks, "settlement_strategy_version_context", settlement)
        _record(
            checks,
            "settlement_payload",
            True,
            issue=settled_issue,
            ticket_count=settlement.get("ticket_count", settlement.get("ticketCount", 0)),
        )

    resolved_refresh_issues = resolve_issues(db_path, [issue])
    _record(checks, "score_refresh_resolve_issues", bool(resolved_refresh_issues), issues=resolved_refresh_issues)
    if not resolved_refresh_issues:
        raise RuntimeError(f"score refresh safe path could not resolve {issue}")

    violations = _tracked_data_file_violations()
    _record(checks, "git_no_tracked_large_data_files", not violations, violations=violations)
    if violations:
        raise RuntimeError(f"tracked data/db files found: {violations}")

    return {
        "ok": all(check["ok"] for check in checks),
        "db": str(db_path),
        "issue": issue,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test the Beidan decision dashboard data chain.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Live 500_bjdc.sqlite path. Defaults to BEIDAN_LIVE_SQLITE or data/derived/500_bjdc/500_bjdc.sqlite.")
    parser.add_argument("--issue", default="current")
    parser.add_argument("--settlement-issue", default="auto")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_smoke(args.db, args.issue, args.settlement_issue)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"OK data-chain smoke db={result['db']} issue={result['issue']}")
        for check in result["checks"]:
            status = "PASS" if check["ok"] else "FAIL"
            detail = {key: value for key, value in check.items() if key not in {"name", "ok"}}
            print(f"{status} {check['name']} {json.dumps(detail, ensure_ascii=False, sort_keys=True)}")


if __name__ == "__main__":
    main()
