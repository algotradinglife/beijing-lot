#!/usr/bin/env python3
"""Collect and settle the pre-registered Phase 3 protection paper candidate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_ARTIFACT_ROOTS = (
    ROOT / "results/structured_decision_chain_shadow",
    ROOT / "results/segment_decision_forward_artifacts",
)
DEFAULT_OUTPUT_DIR = ROOT / "results/phase3_protection_forward"
EXPERIMENT_ID = "phase3_drop_switched_ev_home_protection"
EXPERIMENT_VERSION = "v0.1.0000"
OUTCOME_CODES = ("3", "1", "0")
HK_TZ = ZoneInfo("Asia/Hong_Kong")
MIN_ISSUES = 5
MIN_SETTLED_TRIGGERS = 30
MAX_COVERAGE_LOSS = 0.02
MIN_DEPTH_REDUCTION = 0.05
EXPERIMENT_STARTED_AT = datetime(2026, 7, 12, 15, 3, tzinfo=HK_TZ)
SETTLEMENT_STALL_MINUTES = 180


def fnum(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_codes(value: Any) -> list[str]:
    raw = str(value or "").replace(",", "+").replace("/", "+").split("+")
    return list(dict.fromkeys(code.strip() for code in raw if code.strip() in OUTCOME_CODES))


def parse_hk(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HK_TZ)
    return parsed.astimezone(HK_TZ)


def artifact_generated_at(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=HK_TZ)


def candidate_row(row: dict[str, str]) -> bool:
    return (
        row.get("shadow_arm") == "active_v3.3.3"
        and row.get("phase3_protection_experiment_id") == EXPERIMENT_ID
        and row.get("phase3_protection_experiment_version") == EXPERIMENT_VERSION
        and str(row.get("phase3_protection_execution_enabled") or "0") == "0"
    )


def artifact_paths(roots: list[Path]) -> list[Path]:
    found: set[Path] = set()
    for root in roots:
        if root.is_dir():
            found.update(path.resolve() for path in root.rglob("structured_shadow_*.csv"))
    return sorted(found)


def match_rows(conn: sqlite3.Connection) -> dict[tuple[str, int], sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return {
        (str(row["issue"]), int(row["match_idx"])): row
        for row in conn.execute(
            "SELECT issue, match_idx, end_time, result_code, winning_sp FROM matches WHERE end_time IS NOT NULL"
        ).fetchall()
    }


def collect_samples(conn: sqlite3.Connection, roots: list[Path]) -> tuple[list[dict[str, Any]], int]:
    matches = match_rows(conn)
    selected: dict[tuple[str, int], tuple[datetime, dict[str, Any]]] = {}
    accepted_artifacts: set[Path] = set()
    for path in artifact_paths(roots):
        generated_at = artifact_generated_at(path)
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except OSError:
            continue
        accepted_in_file = False
        for row in rows:
            if not candidate_row(row):
                continue
            issue = str(row.get("issue") or "")
            try:
                match_idx = int(row.get("match_idx") or 0)
            except ValueError:
                continue
            match = matches.get((issue, match_idx))
            kickoff = parse_hk(match["end_time"] if match else None)
            if match is None or kickoff is None or generated_at >= kickoff:
                continue
            accepted_in_file = True
            baseline_codes = parse_codes(row.get("phase3_protection_baseline_codes"))
            candidate_codes = parse_codes(row.get("phase3_protection_candidate_codes"))
            sample = {
                "issue": issue,
                "match_idx": match_idx,
                "match_id": str(row.get("match_id") or f"{issue}_{match_idx:03d}"),
                "artifact_path": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
                "artifact_generated_at": generated_at.isoformat(timespec="seconds"),
                "kickoff": kickoff.isoformat(timespec="seconds"),
                "experiment_id": EXPERIMENT_ID,
                "experiment_version": EXPERIMENT_VERSION,
                "baseline_codes": "+".join(baseline_codes),
                "candidate_codes": "+".join(candidate_codes),
                "triggered": int(str(row.get("phase3_protection_triggered") or "0") == "1"),
                "removed_code": str(row.get("phase3_protection_removed_code") or ""),
                "reason": str(row.get("phase3_protection_reason") or ""),
                "execution_enabled": 0,
                "result_code": str(match["result_code"] or ""),
                "winning_sp": match["winning_sp"] if match["winning_sp"] is not None else "",
                "settled": int(bool(match["result_code"]) and match["winning_sp"] is not None),
            }
            key = (issue, match_idx)
            previous = selected.get(key)
            if previous is None or generated_at > previous[0]:
                selected[key] = (generated_at, sample)
        if accepted_in_file:
            accepted_artifacts.add(path)
    return [item[1] for item in sorted(selected.values(), key=lambda value: (value[1]["issue"], value[1]["match_idx"]))], len(accepted_artifacts)


def leg_profit(codes: list[str], result_code: str, winning_sp: float) -> float:
    if not codes:
        return 0.0
    return winning_sp - len(codes) if result_code in codes else -float(len(codes))


def settled_records(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for sample in samples:
        if not sample["settled"]:
            continue
        baseline = parse_codes(sample["baseline_codes"])
        candidate = parse_codes(sample["candidate_codes"])
        if not baseline:
            continue
        result_code = str(sample["result_code"])
        winning_sp = fnum(sample["winning_sp"])
        baseline_hit = int(result_code in baseline)
        candidate_hit = int(result_code in candidate)
        records.append({
            **sample,
            "baseline_depth": len(baseline),
            "candidate_depth": len(candidate),
            "baseline_hit": baseline_hit,
            "candidate_hit": candidate_hit,
            "lost_rescue": int(bool(sample["triggered"]) and baseline_hit and not candidate_hit),
            "baseline_profit": round(leg_profit(baseline, result_code, winning_sp), 6),
            "candidate_profit": round(leg_profit(candidate, result_code, winning_sp), 6),
        })
    return records


def build_alerts(
    *,
    missing_field_indices: list[int],
    missing_sample_indices: list[int],
    execution_enabled_indices: list[int],
    settlement_stalled_indices: list[int],
) -> list[dict[str, Any]]:
    alerts = []
    specs = (
        ("artifact_fields_missing", "bad", "Phase 3 artifact 字段缺失", missing_field_indices),
        ("prekick_sample_missing", "bad", "Phase 3 赛前样本缺失", missing_sample_indices),
        ("execution_enabled", "bad", "Phase 3 候选执行标志误开", execution_enabled_indices),
        ("settlement_stalled", "warn", "Phase 3 样本结算停滞", settlement_stalled_indices),
    )
    for code, severity, label, indices in specs:
        if indices:
            alerts.append({
                "code": code,
                "severity": severity,
                "label": label,
                "detail": f"matches={indices}",
                "match_indices": indices,
            })
    return alerts


def audit_alerts(
    conn: sqlite3.Connection,
    roots: list[Path],
    samples: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    current_time = now or datetime.now(HK_TZ)
    matches = match_rows(conn)
    current_issue_row = conn.execute(
        "SELECT issue FROM matches ORDER BY CAST(issue AS INTEGER) DESC LIMIT 1"
    ).fetchone()
    current_issue = str(current_issue_row[0]) if current_issue_row else ""
    expected_future = {
        (issue, match_idx)
        for (issue, match_idx), match in matches.items()
        for kickoff in [parse_hk(match["end_time"])]
        if issue == current_issue and kickoff is not None and kickoff > current_time and kickoff > EXPERIMENT_STARTED_AT
    }
    latest_plain: dict[tuple[str, int], tuple[datetime, bool, bool]] = {}
    for path in artifact_paths(roots):
        generated_at = artifact_generated_at(path)
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows = csv.DictReader(handle)
                for row in rows:
                    if row.get("shadow_arm") != "active_v3.3.3":
                        continue
                    issue = str(row.get("issue") or "")
                    try:
                        match_idx = int(row.get("match_idx") or 0)
                    except ValueError:
                        continue
                    match = matches.get((issue, match_idx))
                    kickoff = parse_hk(match["end_time"] if match else None)
                    if match is None or kickoff is None or generated_at >= kickoff or kickoff <= EXPERIMENT_STARTED_AT:
                        continue
                    exact_version = (
                        row.get("phase3_protection_experiment_id") == EXPERIMENT_ID
                        and row.get("phase3_protection_experiment_version") == EXPERIMENT_VERSION
                    )
                    execution_enabled = exact_version and str(row.get("phase3_protection_execution_enabled") or "0") != "0"
                    key = (issue, match_idx)
                    previous = latest_plain.get(key)
                    if previous is None or generated_at > previous[0]:
                        latest_plain[key] = (generated_at, exact_version, execution_enabled)
        except OSError:
            continue
    sample_keys = {(str(row["issue"]), int(row["match_idx"])) for row in samples}
    missing_fields = sorted(
        match_idx for key, (_generated, exact, _enabled) in latest_plain.items()
        if key in expected_future and not exact for match_idx in [key[1]]
    )
    missing_samples = sorted(key[1] for key in expected_future if key not in sample_keys and key not in latest_plain)
    execution_enabled = sorted(
        key[1] for key, (_generated, _exact, enabled) in latest_plain.items()
        if key[0] == current_issue and enabled
    )
    stalled = []
    for sample in samples:
        kickoff = parse_hk(sample.get("kickoff"))
        if (
            sample.get("issue") == current_issue
            and not sample.get("settled")
            and kickoff is not None
            and (current_time - kickoff).total_seconds() >= SETTLEMENT_STALL_MINUTES * 60
        ):
            stalled.append(int(sample["match_idx"]))
    return build_alerts(
        missing_field_indices=missing_fields,
        missing_sample_indices=missing_samples,
        execution_enabled_indices=execution_enabled,
        settlement_stalled_indices=sorted(stalled),
    )


def summarize(
    samples: list[dict[str, Any]],
    records: list[dict[str, Any]],
    artifact_count: int,
    alerts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    triggers = [row for row in samples if row["triggered"]]
    settled_triggers = [row for row in records if row["triggered"]]
    issue_count = len({str(row["issue"]) for row in triggers})
    baseline_hits = sum(int(row["baseline_hit"]) for row in records)
    candidate_hits = sum(int(row["candidate_hit"]) for row in records)
    n = len(records)
    baseline_rate = baseline_hits / n if n else 0.0
    candidate_rate = candidate_hits / n if n else 0.0
    baseline_depth = sum(int(row["baseline_depth"]) for row in records) / n if n else 0.0
    candidate_depth = sum(int(row["candidate_depth"]) for row in records) / n if n else 0.0
    baseline_profit = sum(fnum(row["baseline_profit"]) for row in records)
    candidate_profit = sum(fnum(row["candidate_profit"]) for row in records)
    gates = {
        "issues": issue_count >= MIN_ISSUES,
        "settled_triggers": len(settled_triggers) >= MIN_SETTLED_TRIGGERS,
        "coverage_loss": candidate_rate - baseline_rate >= -MAX_COVERAGE_LOSS,
        "depth_reduction": baseline_depth - candidate_depth >= MIN_DEPTH_REDUCTION,
        "profit_non_degradation": candidate_profit >= baseline_profit,
        "execution_disabled": all(not bool(row["execution_enabled"]) for row in samples),
    }
    alert_rows = alerts or []
    return {
        "status": "ready_for_review" if all(gates.values()) else "collecting",
        "experiment_id": EXPERIMENT_ID,
        "experiment_version": EXPERIMENT_VERSION,
        "execution_enabled": False,
        "health_status": "bad" if any(row["severity"] == "bad" for row in alert_rows) else "warn" if alert_rows else "ok",
        "alerts": alert_rows,
        "artifact_count": artifact_count,
        "sampled_rows": len(samples),
        "sampled_issues": sorted({str(row["issue"]) for row in samples}),
        "trigger_count": len(triggers),
        "trigger_issue_count": issue_count,
        "settled_rows": n,
        "settled_trigger_count": len(settled_triggers),
        "lost_rescues": sum(int(row["lost_rescue"]) for row in settled_triggers),
        "baseline_coverage_rate": baseline_rate,
        "candidate_coverage_rate": candidate_rate,
        "coverage_delta": candidate_rate - baseline_rate,
        "baseline_average_depth": baseline_depth,
        "candidate_average_depth": candidate_depth,
        "depth_delta": candidate_depth - baseline_depth,
        "baseline_profit": baseline_profit,
        "candidate_profit": candidate_profit,
        "profit_delta": candidate_profit - baseline_profit,
        "gates": gates,
        "thresholds": {
            "min_issues": MIN_ISSUES,
            "min_settled_triggers": MIN_SETTLED_TRIGGERS,
            "max_coverage_loss": MAX_COVERAGE_LOSS,
            "min_depth_reduction": MIN_DEPTH_REDUCTION,
        },
    }


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# v3.3.3 Phase 3 Protection Forward Monitor",
        "",
        f"状态：`{summary['status']}`  ",
        f"候选：`{summary['experiment_id']}` / `{summary['experiment_version']}`  ",
        "执行：`false`",
        "",
        "## 累计",
        "",
        f"- 样本 {summary['sampled_rows']} 场，触发 {summary['trigger_count']} 次，已结算触发 {summary['settled_trigger_count']} 次，覆盖 {summary['trigger_issue_count']} 期。",
        f"- 覆盖变化 {summary['coverage_delta'] * 100:+.2f}pp，平均深度变化 {summary['depth_delta']:+.3f}，profit proxy 变化 {summary['profit_delta']:+.2f}。",
        f"- 丢失保护救回 {summary['lost_rescues']} 次。",
        "",
        "## 评审门槛",
        "",
    ]
    for gate, passed in summary["gates"].items():
        lines.append(f"- [{'x' if passed else ' '}] `{gate}`")
    lines.extend([
        "",
        "## 数据边界",
        "",
        "- 每场只保留开赛前最后一份 exact-version Active artifact；后生成 artifact 不能回填已开赛场次。",
        "- 达标只进入评审，不自动修改 Active 或下注计划。",
        "",
    ])
    return "\n".join(lines)


def signature(samples: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    values = {
        "samples": [(row["issue"], row["match_idx"], row["artifact_generated_at"], row["result_code"], row["winning_sp"]) for row in samples],
        "health_status": summary.get("health_status"),
        "alerts": summary.get("alerts", []),
    }
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def write_outputs(output_dir: Path, samples: list[dict[str, Any]], records: list[dict[str, Any]], summary: dict[str, Any]) -> bool:
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "state.json"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    current_signature = signature(samples, summary)
    previous = {}
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    if previous.get("signature") == current_signature:
        # The contents are unchanged, but this successful run is still a fresh
        # monitoring heartbeat for the operations status page.
        if summary_path.is_file():
            summary_path.touch()
            if report_path.is_file():
                report_path.touch()
            return False
    for path, rows in ((output_dir / "sampled_rows.csv", samples), (output_dir / "settled_rows.csv", records)):
        if rows:
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        elif path.exists():
            path.unlink()
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_report(summary), encoding="utf-8")
    state_path.write_text(json.dumps({"signature": current_signature}, indent=2) + "\n", encoding="utf-8")
    return True


def run(db: Path = DEFAULT_DB, artifact_roots: list[Path] | None = None, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    roots = artifact_roots or list(DEFAULT_ARTIFACT_ROOTS)
    with sqlite3.connect(db) as conn:
        samples, artifact_count = collect_samples(conn, roots)
        alerts = audit_alerts(conn, roots, samples)
    records = settled_records(samples)
    summary = summarize(samples, records, artifact_count, alerts)
    updated = write_outputs(output_dir, samples, records, summary)
    return {**summary, "updated": updated, "output_dir": str(output_dir)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--artifact-root", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.artifact_root or None, args.output_dir), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
