#!/usr/bin/env python3
"""Publish v4.2 execution shadow artifacts after live SP refresh."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[0]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import apply_decision_execution_policy_v4_2 as execution_policy  # noqa: E402
import evaluate_structured_decision_chain_v4_2 as decision_chain  # noqa: E402
from src.decision_artifact_completeness import format_completeness_error, structured_csv_completeness  # noqa: E402


DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_SHADOW_DIR = PROJECT_ROOT / "results/structured_decision_chain_shadow"
DEFAULT_WORK_DIR = PROJECT_ROOT / "results/v4_2_execution_publish_work"
DEFAULT_ARTIFACT_VERSION_ID = "v4.2.0005"
STRICT_POLICY_NAME = "strict_fullcap2"
LATE_PROXY_POLICY_NAME = "late_proxy_fullcap2"


def execution_shadow_arm_prefix(artifact_version_id: str) -> str:
    return f"shadow_{artifact_version_id}_execution"


def execution_variant_id(artifact_version_id: str, policy_name: str) -> str:
    return f"{execution_shadow_arm_prefix(artifact_version_id)}_{policy_name}"


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def fnum(value: Any, default: float = 0.0) -> float:
    if value in {None, ""}:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def source_candidate_ok(path: Path, issue: str) -> bool:
    rows = read_csv_rows(path)
    if not rows:
        return False
    first = rows[0]
    if str(first.get("issue") or issue) != issue:
        return False
    shadow_arm = str(first.get("shadow_arm") or "")
    if "_execution_" in shadow_arm:
        return False
    required = {"issue", "match_idx", "active_selection_codes", "shadow_selection_codes", "p_3", "p_1", "p_0"}
    return required.issubset(first)


def find_source_structured_csv(issue: str, shadow_dir: Path) -> Path | None:
    candidates = [
        path
        for path in shadow_dir.glob(f"{issue}_*/structured_shadow_{issue}.csv")
        if path.is_file() and source_candidate_ok(path, issue)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda path: (0 if "shadow_v3.3.3" in path.parent.name else 1, -path.stat().st_mtime))
    return candidates[0]


def parse_dt(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def latest_live_sp_refresh(conn: sqlite3.Connection, issue: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT fetched_at, rows_parsed, status, ok, error
        FROM fetch_log
        WHERE issue=? AND kind='live_sp_xml' AND ok=1 AND COALESCE(rows_parsed, 0) > 0
        ORDER BY fetched_at DESC, id DESC
        LIMIT 1
        """,
        (issue,),
    ).fetchone()
    return dict(row) if row else None


def has_valid_late_refresh(conn: sqlite3.Connection, issue: str, *, max_age_minutes: float) -> tuple[bool, dict[str, Any]]:
    if max_age_minutes <= 0:
        return True, {"policy": "age_check_disabled"}
    if not table_exists(conn, "fetch_log"):
        return False, {"reason": "fetch_log_missing"}
    row = latest_live_sp_refresh(conn, issue)
    if not row:
        return False, {"reason": "no_successful_live_sp_xml"}
    fetched_at = parse_dt(str(row.get("fetched_at") or ""))
    if fetched_at is None:
        return False, {"reason": "unparseable_live_sp_time", "row": row}
    age_minutes = max(0.0, (datetime.now(timezone.utc) - fetched_at.astimezone(timezone.utc)).total_seconds() / 60.0)
    payload = {"fetched_at": row.get("fetched_at"), "rows_parsed": row.get("rows_parsed"), "age_minutes": round(age_minutes, 3)}
    if age_minutes > max_age_minutes:
        return False, {"reason": "live_sp_refresh_stale", **payload}
    return True, payload


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def published_csv_path(shadow_dir: Path, issue: str, variant_id: str, date_slug: str) -> Path:
    return shadow_dir / f"{issue}_{date_slug}_{variant_id}" / f"structured_shadow_{issue}.csv"


def report_path(work_dir: Path, issue: str, policy_name: str, date_slug: str) -> Path:
    return work_dir / issue / f"{date_slug}_{policy_name}.md"


def ensure_decision_csv(
    *,
    issue: str,
    source_csv: Path,
    decision_csv: Path | None,
    db_path: Path,
    work_dir: Path,
    date_slug: str,
) -> Path:
    if decision_csv is not None:
        return decision_csv
    output_dir = work_dir / issue / f"{date_slug}_decision"
    report = work_dir / issue / f"{date_slug}_decision.md"
    csv_path, _jsonl_path, _report_path, _summary = decision_chain.run(
        issue=issue,
        structured_csv=source_csv,
        db_path=db_path,
        output_dir=output_dir,
        report_path=report,
        budget_mode="tight",
    )
    return csv_path


def apply_execution(
    *,
    issue: str,
    source_csv: Path,
    decision_csv: Path,
    db_path: Path,
    output_csv: Path,
    report: Path,
    late_refresh_mode: str,
    policy_name: str,
    execution_sp_mode: str,
    shadow_arm_prefix: str,
) -> dict[str, Any]:
    _csv_path, _report_path, summary = execution_policy.apply_policy(
        issue=issue,
        source_csv=source_csv,
        decision_csv=decision_csv,
        db_path=db_path,
        output_csv=output_csv,
        report_path=report,
        late_refresh_mode=late_refresh_mode,
        full_score_threshold=1.40,
        max_full_per_segment=2,
        window_hours=12.0,
        extend_hours="18,24,36",
        min_matches=6,
        max_matches=24,
        policy_name=policy_name,
        execution_sp_mode=execution_sp_mode,
        shadow_arm_prefix=shadow_arm_prefix,
    )
    return summary


def run(
    *,
    issue: str,
    db_path: Path,
    shadow_dir: Path,
    work_dir: Path,
    source_csv: Path | None = None,
    decision_csv: Path | None = None,
    max_refresh_age_minutes: float = 90.0,
    force_late_proxy: bool = False,
    date_slug: str | None = None,
    artifact_version_id: str = DEFAULT_ARTIFACT_VERSION_ID,
) -> dict[str, Any]:
    date = date_slug or utc_slug()
    shadow_arm_prefix = execution_shadow_arm_prefix(artifact_version_id)
    source = source_csv or find_source_structured_csv(issue, shadow_dir)
    if source is None:
        return {"status": "skipped", "reason": "source_structured_csv_missing", "issue": issue}
    if not source.exists():
        return {"status": "skipped", "reason": "source_structured_csv_missing", "issue": issue, "source_csv": str(source)}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        source_completeness = structured_csv_completeness(conn, issue, source)
        if not source_completeness.complete:
            return {
                "status": "skipped",
                "reason": "source_structured_csv_incomplete",
                "issue": issue,
                "source_csv": str(source),
                "completeness": source_completeness.to_dict(),
                "message": format_completeness_error(source_completeness),
            }
        refresh_ok, refresh = (True, {"policy": "forced_late_proxy"}) if force_late_proxy else has_valid_late_refresh(
            conn,
            issue,
            max_age_minutes=max_refresh_age_minutes,
        )
    finally:
        conn.close()

    decision = ensure_decision_csv(
        issue=issue,
        source_csv=source,
        decision_csv=decision_csv,
        db_path=db_path,
        work_dir=work_dir,
        date_slug=date,
    )
    outputs: dict[str, Any] = {}
    strict_csv = published_csv_path(shadow_dir, issue, execution_variant_id(artifact_version_id, STRICT_POLICY_NAME), date)
    outputs[STRICT_POLICY_NAME] = apply_execution(
        issue=issue,
        source_csv=source,
        decision_csv=decision,
        db_path=db_path,
        output_csv=strict_csv,
        report=report_path(work_dir, issue, STRICT_POLICY_NAME, date),
        late_refresh_mode="skip",
        policy_name=STRICT_POLICY_NAME,
        execution_sp_mode="source",
        shadow_arm_prefix=shadow_arm_prefix,
    )
    if refresh_ok:
        late_csv = published_csv_path(shadow_dir, issue, execution_variant_id(artifact_version_id, LATE_PROXY_POLICY_NAME), date)
        outputs[LATE_PROXY_POLICY_NAME] = apply_execution(
            issue=issue,
            source_csv=source,
            decision_csv=decision,
            db_path=db_path,
            output_csv=late_csv,
            report=report_path(work_dir, issue, LATE_PROXY_POLICY_NAME, date),
            late_refresh_mode="proxy",
            policy_name=LATE_PROXY_POLICY_NAME,
            execution_sp_mode="latest_trusted",
            shadow_arm_prefix=shadow_arm_prefix,
        )

    return {
        "status": "published",
        "issue": issue,
        "artifact_version_id": artifact_version_id,
        "source_csv": str(source),
        "decision_csv": str(decision),
        "source_completeness": source_completeness.to_dict(),
        "late_proxy_published": bool(refresh_ok),
        "late_refresh": refresh,
        "outputs": outputs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--shadow-dir", type=Path, default=DEFAULT_SHADOW_DIR)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--source-structured-csv", type=Path, default=None)
    parser.add_argument("--decision-csv", type=Path, default=None)
    parser.add_argument("--max-refresh-age-minutes", type=float, default=90.0)
    parser.add_argument("--force-late-proxy", action="store_true")
    parser.add_argument("--date-slug", default="")
    parser.add_argument("--artifact-version-id", default=DEFAULT_ARTIFACT_VERSION_ID)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run(
        issue=args.issue,
        db_path=args.db,
        shadow_dir=args.shadow_dir,
        work_dir=args.work_dir,
        source_csv=args.source_structured_csv,
        decision_csv=args.decision_csv,
        max_refresh_age_minutes=args.max_refresh_age_minutes,
        force_late_proxy=args.force_late_proxy,
        date_slug=args.date_slug or None,
        artifact_version_id=args.artifact_version_id,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
