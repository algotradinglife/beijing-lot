#!/usr/bin/env python3
"""Settle and monitor the v3.3.3 Phase 2 primary-only forward experiment."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_ARTIFACT_DIR = ROOT / "results/structured_decision_chain_shadow"
DEFAULT_OUTPUT_DIR = ROOT / "results/phase2_primary_forward"
EXPERIMENTS = (
    {
        "experiment_id": "phase2_probability_first_within_coverage",
        "version": "v0.1.0000",
        "prefix": "phase2_probability",
        "id_field": "phase2_primary_experiment_id",
        "version_field": "phase2_primary_experiment_version",
    },
    {
        "experiment_id": "phase2_handicap_gated_probability_first",
        "version": "v0.2.0000",
        "prefix": "phase2_handicap_gated",
        "id_field": "phase2_handicap_gated_experiment_id",
        "version_field": "phase2_handicap_gated_experiment_version",
    },
    {
        "experiment_id": "phase2_seasonal_league_soft_tiebreak",
        "version": "v0.1.0000",
        "prefix": "phase2_league_soft",
        "id_field": "phase2_league_soft_experiment_id",
        "version_field": "phase2_league_soft_experiment_version",
    },
)
PRIMARY_EXPERIMENT_ID = str(EXPERIMENTS[0]["experiment_id"])
HK_TZ = ZoneInfo("Asia/Hong_Kong")
OUTCOME_ORDER = ("3", "1", "0")
MIN_ROWS = 300
MIN_ISSUES = 5
MIN_PRIMARY_DELTA = 0.02
MAX_BRIER_DEGRADATION = 0.01


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def parse_codes(value: Any) -> list[str]:
    raw = str(value or "").replace(",", "+").replace("/", "+").split("+")
    out: list[str] = []
    for item in raw:
        code = item.strip()
        if code in OUTCOME_ORDER and code not in out:
            out.append(code)
    return out


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


def artifact_has_experiment(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            first = next(reader, None)
    except OSError:
        return False
    if not first or first.get("shadow_arm") != "active_v3.3.3":
        return False
    return all(
        first.get(str(experiment["id_field"])) == experiment["experiment_id"]
        and first.get(str(experiment["version_field"])) == experiment["version"]
        for experiment in EXPERIMENTS
    )


def issue_cutoffs(conn: sqlite3.Connection) -> dict[str, datetime]:
    rows = conn.execute(
        """
        SELECT issue, MIN(end_time) AS first_kickoff
        FROM matches
        WHERE end_time IS NOT NULL
        GROUP BY issue
        """
    ).fetchall()
    out: dict[str, datetime] = {}
    for issue, cutoff in rows:
        parsed = parse_hk(cutoff)
        if parsed:
            out[str(issue)] = parsed
    return out


def select_forward_artifacts(conn: sqlite3.Connection, artifact_dir: Path) -> dict[str, Path]:
    cutoffs = issue_cutoffs(conn)
    candidates: dict[str, list[Path]] = defaultdict(list)
    for path in artifact_dir.glob("*_*/structured_shadow_*.csv"):
        match = re.fullmatch(r"structured_shadow_(\d+)\.csv", path.name)
        if not match:
            continue
        issue = match.group(1)
        cutoff = cutoffs.get(issue)
        if cutoff is None or artifact_generated_at(path) > cutoff or not artifact_has_experiment(path):
            continue
        candidates[issue].append(path)
    return {
        issue: max(paths, key=lambda path: (artifact_generated_at(path), str(path)))
        for issue, paths in candidates.items()
    }


def load_settled_records(conn: sqlite3.Connection, artifacts: dict[str, Path]) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    records: list[dict[str, Any]] = []
    for issue, path in sorted(artifacts.items()):
        matches = {
            int(row["match_idx"]): row
            for row in conn.execute(
                """
                SELECT match_idx, league, handicap_line, result_code, winning_sp
                FROM matches
                WHERE issue=? AND result_code IS NOT NULL AND winning_sp IS NOT NULL
                """,
                (issue,),
            )
        }
        with path.open(encoding="utf-8", newline="") as handle:
            for artifact_row in csv.DictReader(handle):
                try:
                    match_idx = int(artifact_row.get("match_idx") or 0)
                except ValueError:
                    continue
                match = matches.get(match_idx)
                if match is None:
                    continue
                baseline_codes = parse_codes(artifact_row.get("shadow_selection_codes"))
                baseline_primary = str(artifact_row.get("shadow_primary") or "")
                result_code = str(match["result_code"])
                if not baseline_codes:
                    continue
                p_by_code = {
                    code: float(safe_float(artifact_row.get(f"p_{code}")) or 0.0)
                    for code in OUTCOME_ORDER
                }
                baseline_hit = int(baseline_primary == result_code)
                baseline_p = p_by_code.get(baseline_primary, 0.0)
                winning_sp = float(match["winning_sp"])
                for experiment in EXPERIMENTS:
                    prefix = str(experiment["prefix"])
                    candidate_codes = parse_codes(artifact_row.get(f"{prefix}_selection_codes"))
                    candidate_primary = str(artifact_row.get(f"{prefix}_primary") or "")
                    if not candidate_codes or candidate_primary not in candidate_codes:
                        continue
                    candidate_hit = int(candidate_primary == result_code)
                    candidate_p = float(
                        (safe_float(artifact_row.get(f"{prefix}_primary_probability")) or 0.0)
                        if prefix == "phase2_league_soft"
                        else p_by_code.get(candidate_primary, 0.0)
                    )
                    records.append({
                        "experiment_id": experiment["experiment_id"],
                        "experiment_version": experiment["version"],
                        "issue": issue,
                        "match_idx": match_idx,
                        "league": str(match["league"] or ""),
                        "handicap_line": float(safe_float(match["handicap_line"]) or 0.0),
                        "artifact_path": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
                        "artifact_generated_at": artifact_generated_at(path).isoformat(timespec="seconds"),
                        "baseline_codes": "+".join(baseline_codes),
                        "candidate_codes": "+".join(candidate_codes),
                        "coverage_invariant": sorted(baseline_codes) == sorted(candidate_codes),
                        "baseline_primary": baseline_primary,
                        "candidate_primary": candidate_primary,
                        "changed": baseline_primary != candidate_primary,
                        "grade": str(artifact_row.get(f"{prefix}_grade") or ""),
                        "gate_applied": str(artifact_row.get(f"{prefix}_gate_applied") or ""),
                        "result_code": result_code,
                        "winning_sp": winning_sp,
                        "baseline_hit": baseline_hit,
                        "candidate_hit": candidate_hit,
                        "baseline_profit": winning_sp - 1.0 if baseline_hit else -1.0,
                        "candidate_profit": winning_sp - 1.0 if candidate_hit else -1.0,
                        "baseline_brier": (baseline_p - baseline_hit) ** 2,
                        "candidate_brier": (candidate_p - candidate_hit) ** 2,
                    })
    return records


def summarize(records: list[dict[str, Any]], experiment: dict[str, str] | None = None) -> dict[str, Any]:
    n = len(records)
    issues = sorted({str(row["issue"]) for row in records})
    baseline_hits = sum(int(row["baseline_hit"]) for row in records)
    candidate_hits = sum(int(row["candidate_hit"]) for row in records)
    baseline_rate = baseline_hits / n if n else 0.0
    candidate_rate = candidate_hits / n if n else 0.0
    baseline_brier = sum(float(row["baseline_brier"]) for row in records) / n if n else 0.0
    candidate_brier = sum(float(row["candidate_brier"]) for row in records) / n if n else 0.0
    invariants_ok = all(bool(row["coverage_invariant"]) for row in records)
    gates = {
        "rows": n >= MIN_ROWS,
        "issues": len(issues) >= MIN_ISSUES,
        "primary_delta": candidate_rate - baseline_rate >= MIN_PRIMARY_DELTA,
        "coverage_invariant": invariants_ok,
        "brier": candidate_brier - baseline_brier <= MAX_BRIER_DEGRADATION,
    }
    return {
        "status": "ready_for_review" if all(gates.values()) else "collecting",
        "experiment_id": str((experiment or {}).get("experiment_id") or (records[0]["experiment_id"] if records else "")),
        "experiment_version": str((experiment or {}).get("version") or (records[0]["experiment_version"] if records else "")),
        "rows": n,
        "issues": issues,
        "issue_count": len(issues),
        "changed_rows": sum(int(bool(row["changed"])) for row in records),
        "baseline_primary_hits": baseline_hits,
        "candidate_primary_hits": candidate_hits,
        "baseline_primary_hit_rate": baseline_rate,
        "candidate_primary_hit_rate": candidate_rate,
        "primary_delta": candidate_rate - baseline_rate,
        "baseline_primary_profit": sum(float(row["baseline_profit"]) for row in records),
        "candidate_primary_profit": sum(float(row["candidate_profit"]) for row in records),
        "baseline_brier": baseline_brier,
        "candidate_brier": candidate_brier,
        "brier_delta": candidate_brier - baseline_brier,
        "coverage_invariant": invariants_ok,
        "gates": gates,
        "thresholds": {
            "min_rows": MIN_ROWS,
            "min_issues": MIN_ISSUES,
            "min_primary_delta": MIN_PRIMARY_DELTA,
            "max_brier_degradation": MAX_BRIER_DEGRADATION,
        },
    }


def record_signature(records: list[dict[str, Any]]) -> str:
    payload = {
        "experiments": EXPERIMENTS,
        "records": [
            (row["experiment_id"], row["issue"], row["match_idx"], row["artifact_generated_at"], row["result_code"], row["winning_sp"])
            for row in records
        ],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def render_report(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        "# v3.3.3 Phase 2 Forward Monitor",
        "",
        f"状态：`{summary['status']}`  ",
        "候选：全局 probability-first v0.1；盘口门控 v0.2；赛季联赛软择优 v0.1",
        "",
        "## 累计",
        "",
        "| candidate | rows | issues | changed | baseline hit | candidate hit | delta | Brier delta | invariant | status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for experiment in EXPERIMENTS:
        item = summary["candidates"][str(experiment["experiment_id"])]
        lines.append(
            f"| {item['experiment_id']} / {item['experiment_version']} | {item['rows']} | {item['issue_count']} | "
            f"{item['changed_rows']} | {item['baseline_primary_hit_rate']:.1%} | {item['candidate_primary_hit_rate']:.1%} | "
            f"{item['primary_delta'] * 100:+.1f}pp | {item['brier_delta']:+.4f} | "
            f"{item['coverage_invariant']} | {item['status']} |"
        )
    lines.extend([
        "",
        "## 晋级门槛",
        "",
    ])
    for experiment in EXPERIMENTS:
        item = summary["candidates"][str(experiment["experiment_id"])]
        lines.extend([f"### `{item['experiment_id']}`", ""])
        for gate, passed in item["gates"].items():
            lines.append(f"- [{'x' if passed else ' '}] `{gate}`")
        lines.extend(["", "| issue | n | changed | baseline | candidate | delta |", "| --- | --- | --- | --- | --- | --- |"])
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in records:
            if row["experiment_id"] == item["experiment_id"]:
                grouped[str(row["issue"])].append(row)
        for issue, group in sorted(grouped.items()):
            issue_summary = summarize(group, experiment)
            lines.append(
                f"| {issue} | {issue_summary['rows']} | {issue_summary['changed_rows']} | "
                f"{issue_summary['baseline_primary_hit_rate']:.1%} | {issue_summary['candidate_primary_hit_rate']:.1%} | "
                f"{issue_summary['primary_delta'] * 100:+.1f}pp |"
            )
        lines.append("")
    if not records:
        lines.extend(["", "当前没有同时满足实验版本和首场开赛前锁定要求的已结算 forward artifact。"])
    lines.extend(
        [
            "",
            "## 数据边界",
            "",
            "- 只读取首场开赛前生成的 `active_v3.3.3` artifact。",
            "- 只接受预注册实验版本；旧 artifact、赛后重算和 v4.2 派生产物不会补入样本。",
            "- `ready_for_review` 只表示达到评审门槛，不会自动修改 release/default。",
            "",
        ]
    )
    return "\n".join(lines)


def write_if_changed(output_dir: Path, records: list[dict[str, Any]], summary: dict[str, Any]) -> bool:
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "state.json"
    signature = record_signature(records)
    previous: dict[str, Any] = {}
    if state_path.is_file():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    if previous.get("signature") == signature:
        return False
    csv_path = output_dir / "settled_rows.csv"
    if records:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    elif csv_path.exists():
        csv_path.unlink()
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(summary, records), encoding="utf-8")
    state_path.write_text(json.dumps({"signature": signature}, indent=2) + "\n", encoding="utf-8")
    return True


def run(db: Path = DEFAULT_DB, artifact_dir: Path = DEFAULT_ARTIFACT_DIR, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    with sqlite3.connect(db) as conn:
        artifacts = select_forward_artifacts(conn, artifact_dir)
        records = load_settled_records(conn, artifacts)
    candidate_summaries = {
        str(experiment["experiment_id"]): summarize(
            [row for row in records if row["experiment_id"] == experiment["experiment_id"]],
            experiment,
        )
        for experiment in EXPERIMENTS
    }
    primary = candidate_summaries[PRIMARY_EXPERIMENT_ID]
    summary = {
        **primary,
        "status": "ready_for_review"
        if any(item["status"] == "ready_for_review" for item in candidate_summaries.values())
        else "collecting",
        "candidates": candidate_summaries,
    }
    updated = write_if_changed(output_dir, records, summary)
    return {**summary, "updated": updated, "output_dir": str(output_dir), "artifact_count": len(artifacts)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.artifact_dir, args.output_dir), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
