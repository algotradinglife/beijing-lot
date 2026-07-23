#!/usr/bin/env python3
"""Backtest SP-favorite disagreement protection on frozen v3.3.3 inputs."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from evaluate_structured_decision_chain_shadow import (  # noqa: E402
    OUTCOME_ORDER,
    safe_float,
    structured_decision_for_payload,
)


DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_REPORT = PROJECT_ROOT / "docs/research/v3_3_3_sp_disagreement_guard_backtest_2026-07-11.md"
DEFAULT_CSV = PROJECT_ROOT / "docs/research/v3_3_3_sp_disagreement_guard_backtest_2026-07-11.csv"
DEFAULT_ISSUES = ("26071", "26072", "26073", "26074")
MEDIUM_MARGIN = 0.08
STRONG_MARGIN = 0.20


@dataclass(frozen=True)
class ReplayRow:
    issue: str
    match_idx: int
    match_id: str
    league: str
    home: str
    away: str
    handicap_line: float
    kickoff_at: str
    generated_at: str
    result_code: str
    winning_sp: float
    payload: dict[str, Any]


def parse_codes(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else str(value or "").replace(",", "+").split("+")
    codes: list[str] = []
    for value in raw:
        code = str(value).strip()
        if code in OUTCOME_ORDER and code not in codes:
            codes.append(code)
    return codes


def load_rows(conn: sqlite3.Connection, issues: list[str]) -> list[ReplayRow]:
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in issues)
    raw_rows = conn.execute(
        f"""
        WITH active AS (
            SELECT s.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.issue, s.match_idx
                       ORDER BY s.generated_at DESC, s.snapshot_id DESC
                   ) AS rn
            FROM llm_decision_snapshots s
            WHERE s.status='active' AND s.issue IN ({placeholders})
        )
        SELECT s.issue, s.match_idx, s.match_id, s.generated_at,
               s.input_payload_json, m.league, m.home, m.away,
               m.handicap_line, m.end_time, m.result_code, m.winning_sp
        FROM active s
        JOIN matches m ON m.issue=s.issue AND m.match_idx=s.match_idx
        WHERE s.rn=1
          AND m.result_code IN ('3','1','0')
          AND m.winning_sp IS NOT NULL
          AND datetime(s.generated_at) <= datetime(m.end_time)
        ORDER BY CAST(s.issue AS INTEGER), s.match_idx
        """,
        issues,
    ).fetchall()
    rows: list[ReplayRow] = []
    for raw in raw_rows:
        try:
            payload = json.loads(raw["input_payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        sp = payload.get("sp") if isinstance(payload.get("sp"), dict) else {}
        if any(safe_float(sp.get(code)) is None for code in OUTCOME_ORDER):
            continue
        rows.append(
            ReplayRow(
                issue=str(raw["issue"]),
                match_idx=int(raw["match_idx"]),
                match_id=str(raw["match_id"] or ""),
                league=str(raw["league"] or ""),
                home=str(raw["home"] or ""),
                away=str(raw["away"] or ""),
                handicap_line=float(safe_float(raw["handicap_line"]) or 0.0),
                kickoff_at=str(raw["end_time"] or ""),
                generated_at=str(raw["generated_at"] or ""),
                result_code=str(raw["result_code"]),
                winning_sp=float(raw["winning_sp"]),
                payload=payload,
            )
        )
    return rows


def sp_implied(payload: dict[str, Any]) -> tuple[str, float, float]:
    sp = payload.get("sp") if isinstance(payload.get("sp"), dict) else {}
    inverse = {code: 1.0 / float(sp[code]) for code in OUTCOME_ORDER}
    total = sum(inverse.values())
    probabilities = {code: inverse[code] / total for code in OUTCOME_ORDER}
    ranked = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
    return ranked[0][0], ranked[0][1], ranked[0][1] - ranked[1][1]


def arm_codes(
    baseline: list[str],
    sp_top: str,
    sp_margin: float,
) -> dict[str, tuple[list[str], str]]:
    disagreement = len(baseline) == 1 and sp_top not in baseline
    medium = disagreement and sp_margin >= MEDIUM_MARGIN
    strong = disagreement and sp_margin >= STRONG_MARGIN

    def protected(enabled: bool) -> list[str]:
        return baseline + [sp_top] if enabled else list(baseline)

    return {
        "baseline_v3.3.3": (list(baseline), "baseline"),
        "sp_conflict_protect_0.08": (protected(medium), "protect" if medium else "baseline"),
        "sp_strong_protect_0.20": (protected(strong), "protect" if strong else "baseline"),
        "sp_tiered_guard_0.08_0.20": (
            protected(strong) if strong else ([] if medium else list(baseline)),
            "protect" if strong else "skip" if medium else "baseline",
        ),
    }


def leg_profit(codes: list[str], result_code: str, winning_sp: float) -> float:
    if not codes:
        return 0.0
    return winning_sp - len(codes) if result_code in codes else -float(len(codes))


def evaluate(rows: list[ReplayRow]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        decision = structured_decision_for_payload(row.payload)
        baseline = parse_codes(decision.get("selection_codes"))
        if not baseline:
            continue
        sp_top, sp_top_probability, sp_margin = sp_implied(row.payload)
        for arm, (codes, action) in arm_codes(baseline, sp_top, sp_margin).items():
            records.append(
                {
                    "issue": row.issue,
                    "match_idx": row.match_idx,
                    "match": f"{row.home} vs {row.away}",
                    "league": row.league,
                    "handicap_line": row.handicap_line,
                    "arm": arm,
                    "action": action,
                    "baseline_codes": "+".join(baseline),
                    "selection_codes": "+".join(codes),
                    "sp_top": sp_top,
                    "sp_top_probability": round(sp_top_probability, 6),
                    "sp_margin": round(sp_margin, 6),
                    "result_code": row.result_code,
                    "depth": len(codes),
                    "coverage_hit": int(row.result_code in codes),
                    "stake": len(codes),
                    "profit": round(leg_profit(codes, row.result_code, row.winning_sp), 6),
                }
            )
    return records


def summarize(records: list[dict[str, Any]], issues: set[str] | None = None) -> list[dict[str, Any]]:
    selected = [row for row in records if issues is None or row["issue"] in issues]
    arms = sorted({str(row["arm"]) for row in selected})
    summaries: list[dict[str, Any]] = []
    for arm in arms:
        rows = [row for row in selected if row["arm"] == arm]
        n = len(rows)
        stake = sum(int(row["stake"]) for row in rows)
        profit = sum(float(row["profit"]) for row in rows)
        depths = Counter(int(row["depth"]) for row in rows)
        summaries.append(
            {
                "arm": arm,
                "n": n,
                "coverage_hits": sum(int(row["coverage_hit"]) for row in rows),
                "coverage_rate": sum(int(row["coverage_hit"]) for row in rows) / n if n else 0.0,
                "stake": stake,
                "profit": profit,
                "roi": profit / stake if stake else 0.0,
                "protect_count": sum(row["action"] == "protect" for row in rows),
                "skip_count": sum(row["action"] == "skip" for row in rows),
                "single": depths[1],
                "double": depths[2],
                "full": depths[3],
            }
        )
    return summaries


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]) if records else [])
        if records:
            writer.writeheader()
            writer.writerows(records)


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def summary_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| arm | n | 覆盖命中 | stake | profit | ROI | 新保护 | 跳过 | 单/双/全 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['arm']} | {row['n']} | {row['coverage_hits']}/{row['n']} ({pct(row['coverage_rate'])}) "
            f"| {row['stake']} | {row['profit']:.2f} | {pct(row['roi'])} | {row['protect_count']} "
            f"| {row['skip_count']} | {row['single']}/{row['double']}/{row['full']} |"
        )
    return lines


def write_report(path: Path, records: list[dict[str, Any]], issues: list[str]) -> None:
    prior_issues = [issue for issue in issues if issue != "26074"]
    lines = [
        "# v3.3.3 北单 SP 冲突保护回测",
        "",
        "日期：2026-07-11  ",
        f"期次：{', '.join(issues)}",
        "",
        "## 口径",
        "",
        "- 只使用 `active` snapshot 且生成时间不晚于该场开赛时间的行。",
        "- 要求赛前 snapshot 内三项北单 SP 完整，并已有正式赛果和结算 SP。",
        "- 只在基线为单选且北单 SP 隐含热门不在基线选择时触发。",
        "- `0.08` 为 SP 热门相对第二名领先至少 8pp；`0.20` 为至少 20pp。",
        "- stake/profit 是每个选择码 1 单位的单腿代理，不是实际组合票 ROI。",
        "",
        "## 总体",
        "",
        *summary_table(summarize(records)),
        "",
        "## 发现期之前（26071-26073）",
        "",
        "该机制由 26074 的 #1/#5 提出，因此以下切片更接近真正的既往回测。",
        "",
        *summary_table(summarize(records, set(prior_issues))),
        "",
        "## 分期",
        "",
    ]
    for issue in issues:
        issue_rows = [row for row in records if row["issue"] == issue]
        if not issue_rows:
            continue
        lines.extend([f"### {issue}", "", *summary_table(summarize(issue_rows)), ""])
    trigger_rows = [
        row for row in records
        if row["arm"] == "sp_conflict_protect_0.08" and row["action"] == "protect"
    ]
    lines.extend([
        "## 0.08 保护触发明细",
        "",
        "| 期次 | # | 比赛 | 基线 | SP热门 | 领先 | 赛果 | 是否救回 |",
        "|---|---:|---|---|---|---:|---|---|",
    ])
    for row in trigger_rows:
        rescued = row["result_code"] == row["sp_top"] and row["result_code"] not in row["baseline_codes"].split("+")
        lines.append(
            f"| {row['issue']} | {row['match_idx']} | {row['match']} | {row['baseline_codes']} | {row['sp_top']} "
            f"| {pct(float(row['sp_margin']))} | {row['result_code']} | {'是' if rescued else '否'} |"
        )
    lines.extend([
        "",
        "## 结论规则",
        "",
        "- 覆盖提升必须同时对照新增 stake；保护命中不等于组合层收益改善。",
        "- 26074 已用于提出该机制，因此只能视为诊断样本，不能作为独立 forward 证据。",
        "- 在新期预注册 forward 之前，不修改正式 v3.3.3 或下注资金权重。",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issues", default=",".join(DEFAULT_ISSUES))
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    issues = [part.strip() for part in args.issues.split(",") if part.strip()]
    with sqlite3.connect(args.db) as conn:
        rows = load_rows(conn, issues)
    records = evaluate(rows)
    write_csv(args.csv, records)
    write_report(args.report, records, issues)
    print(json.dumps({"issues": issues, "rows": len(rows), "records": len(records), "report": str(args.report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
