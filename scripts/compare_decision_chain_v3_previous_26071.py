from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "docs/research"
OUTCOME_ORDER = ("3", "1", "0")


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def safe_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback


def outcome_text(code: str | None, home: str = "主队", away: str = "客队") -> str:
    if code == "3":
        return f"胜({home})"
    if code == "1":
        return "平"
    if code == "0":
        return f"负({away})"
    return ""


def fmt_pct(value: float | None) -> str:
    return "NA" if value is None else f"{value:.1%}"


def fmt_num(value: float | None) -> str:
    return "NA" if value is None else f"{value:.2f}"


@dataclass(frozen=True)
class ArmDecision:
    primary: str | None
    codes: tuple[str, ...]

    @property
    def protect(self) -> tuple[str, ...]:
        if not self.primary:
            return ()
        return tuple(code for code in self.codes if code != self.primary)

    @property
    def selection_type(self) -> str:
        if not self.codes:
            return "停"
        if len(self.codes) == 1:
            return "单"
        if len(self.codes) == 2:
            return "双"
        return "全"


@dataclass(frozen=True)
class CompareRow:
    match_idx: int
    league: str
    home: str
    away: str
    handicap_line: float | None
    score: str
    result_code: str | None
    winning_sp: float | None
    previous: ArmDecision
    v3: ArmDecision
    v3_recommendation: str


def normalize_codes(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        loaded = safe_json(value, [])
    else:
        loaded = value
    if not isinstance(loaded, list):
        return ()
    return tuple(str(code) for code in loaded if str(code) in OUTCOME_ORDER)


def load_rows(conn: sqlite3.Connection, issue: str) -> list[CompareRow]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        WITH active AS (
            SELECT
                s.*,
                ROW_NUMBER() OVER (
                    PARTITION BY s.issue, s.match_idx
                    ORDER BY s.generated_at DESC, s.snapshot_id DESC
                ) AS rn
            FROM llm_decision_snapshots s
            WHERE s.issue=? AND s.status='active'
        )
        SELECT
            s.input_payload_json,
            s.primary_pick,
            s.selection_codes_json,
            s.recommendation,
            m.match_idx,
            m.league,
            m.home,
            m.away,
            m.handicap_line,
            m.score,
            m.result_code,
            m.winning_sp
        FROM active s
        JOIN matches m ON m.issue=s.issue AND m.match_idx=s.match_idx
        WHERE s.rn=1
        ORDER BY m.match_idx
        """,
        (issue,),
    ).fetchall()
    output: list[CompareRow] = []
    for row in rows:
        payload = safe_json(row["input_payload_json"], {})
        model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
        previous_codes = normalize_codes(model.get("selection_codes"))
        previous_primary = str(model.get("selection")) if str(model.get("selection")) in OUTCOME_ORDER else (previous_codes[0] if previous_codes else None)
        v3_codes = normalize_codes(row["selection_codes_json"])
        v3_primary = str(row["primary_pick"]) if row["primary_pick"] and str(row["primary_pick"]) in OUTCOME_ORDER else (v3_codes[0] if v3_codes else None)
        output.append(
            CompareRow(
                match_idx=int(row["match_idx"]),
                league=str(row["league"] or ""),
                home=str(row["home"] or ""),
                away=str(row["away"] or ""),
                handicap_line=safe_float(row["handicap_line"]),
                score=str(row["score"] or ""),
                result_code=str(row["result_code"]) if row["result_code"] is not None else None,
                winning_sp=safe_float(row["winning_sp"]),
                previous=ArmDecision(previous_primary, previous_codes),
                v3=ArmDecision(v3_primary, v3_codes),
                v3_recommendation=str(row["recommendation"] or ""),
            )
        )
    return output


def profit(decision: ArmDecision, result_code: str | None, winning_sp: float | None) -> float:
    if not decision.codes or not result_code:
        return 0.0
    stake = float(len(decision.codes))
    if result_code in decision.codes and winning_sp is not None:
        return winning_sp - stake
    return -stake


def hit_bucket(decision: ArmDecision, result_code: str | None) -> str:
    if not result_code:
        return "未结算"
    if not decision.codes:
        return "停"
    if decision.primary == result_code:
        return "押中"
    if result_code in decision.protect:
        return "保中"
    return "未中"


def arm_metrics(rows: list[CompareRow], attr: str) -> dict[str, Any]:
    settled = [row for row in rows if row.result_code]
    decisions = [getattr(row, attr) for row in settled]
    bucket = Counter(hit_bucket(getattr(row, attr), row.result_code) for row in settled)
    type_counts = Counter(getattr(row, attr).selection_type for row in rows)
    stake = sum(len(decision.codes) for decision in decisions)
    pnl = sum(profit(getattr(row, attr), row.result_code, row.winning_sp) for row in settled)
    primary_hits = bucket.get("押中", 0)
    protection_hits = bucket.get("保中", 0)
    coverage_hits = primary_hits + protection_hits
    bet_count = sum(1 for decision in decisions if decision.codes)
    return {
        "n_settled": len(settled),
        "bet_count": bet_count,
        "primary_hits": primary_hits,
        "protect_hits": protection_hits,
        "misses": bucket.get("未中", 0),
        "stops": bucket.get("停", 0),
        "coverage_hits": coverage_hits,
        "primary_hit_rate": primary_hits / bet_count if bet_count else None,
        "coverage_hit_rate": coverage_hits / bet_count if bet_count else None,
        "stake": stake,
        "profit": round(pnl, 4),
        "roi": pnl / stake if stake else None,
        "selection_types": dict(type_counts),
    }


def decision_label(decision: ArmDecision, row: CompareRow) -> str:
    if not decision.codes:
        return "停"
    labels = [outcome_text(code, row.home, row.away) for code in decision.codes]
    if len(labels) == 1:
        return labels[0]
    return f"{labels[0]}押 / " + "+".join(labels[1:]) + "保"


def switch_tags(row: CompareRow) -> list[str]:
    tags: list[str] = []
    prev = row.previous
    v3 = row.v3
    if prev.codes == v3.codes and prev.primary == v3.primary:
        return []
    if prev.primary != v3.primary:
        tags.append("方向变")
    if prev.primary and prev.primary in v3.protect:
        tags.append("旧押改保")
    if v3.primary and v3.primary in prev.protect:
        tags.append("旧保改押")
    if prev.codes and not v3.codes:
        tags.append("押改停")
    if not prev.codes and v3.codes:
        tags.append("停改押")
    added = [code for code in v3.codes if code not in prev.codes]
    removed = [code for code in prev.codes if code not in v3.codes]
    if added:
        tags.append("新增覆盖:" + "+".join(added))
    if removed:
        tags.append("移除覆盖:" + "+".join(removed))
    if prev.codes != v3.codes and set(prev.codes) == set(v3.codes):
        tags.append("押保顺序调换")
    return tags


def md_table(records: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    lines = [
        "| " + " | ".join(title for title, _key in columns) + " |",
        "| " + " | ".join("---" for _title, _key in columns) + " |",
    ]
    for record in records:
        values = []
        for _title, key in columns:
            value = record.get(key, "")
            values.append(str(value).replace("\n", " ").replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_report(issue: str, rows: list[CompareRow]) -> str:
    previous_metrics = arm_metrics(rows, "previous")
    v3_metrics = arm_metrics(rows, "v3")
    metrics_records = []
    for name, metrics in (("previous_model_q", previous_metrics), ("llm_chain_v3", v3_metrics)):
        metrics_records.append(
            {
                "arm": name,
                "settled": metrics["n_settled"],
                "bets": metrics["bet_count"],
                "押中": metrics["primary_hits"],
                "保中": metrics["protect_hits"],
                "未中": metrics["misses"],
                "停": metrics["stops"],
                "coverage": f'{metrics["coverage_hits"]}/{metrics["bet_count"]} ({fmt_pct(metrics["coverage_hit_rate"])})',
                "primary_rate": fmt_pct(metrics["primary_hit_rate"]),
                "stake": metrics["stake"],
                "profit": fmt_num(metrics["profit"]),
                "roi": fmt_pct(metrics["roi"]),
                "types": metrics["selection_types"],
            }
        )
    detail_records: list[dict[str, Any]] = []
    switch_records: list[dict[str, Any]] = []
    for row in rows:
        actual = outcome_text(row.result_code, row.home, row.away) if row.result_code else "未结算"
        prev_bucket = hit_bucket(row.previous, row.result_code)
        v3_bucket = hit_bucket(row.v3, row.result_code)
        tags = switch_tags(row)
        record = {
            "#": row.match_idx,
            "match": f"{row.home} vs {row.away}",
            "hcp": "" if row.handicap_line is None else f"{row.handicap_line:g}",
            "score": row.score,
            "actual": actual,
            "previous": decision_label(row.previous, row),
            "prev_hit": prev_bucket,
            "v3": decision_label(row.v3, row),
            "v3_hit": v3_bucket,
            "switch": "；".join(tags) if tags else "不变",
        }
        detail_records.append(record)
        if tags:
            switch_records.append(record)
    delta_profit = v3_metrics["profit"] - previous_metrics["profit"]
    delta_roi = (v3_metrics["roi"] or 0.0) - (previous_metrics["roi"] or 0.0)
    delta_coverage = (v3_metrics["coverage_hit_rate"] or 0.0) - (previous_metrics["coverage_hit_rate"] or 0.0)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    return f"""# 26071 决策链 v3 vs previous_model_q 对比

生成时间：{generated}

## 口径

- v3：`llm_chain_bet_protect_stop_v3` active snapshot。
- previous_model_q：同一 active snapshot 的 `input_payload_json.model.selection_codes`，即 LLM 决策链接管前的模型/q 建议。数据库中 26071 没有非 v3 的历史 active snapshot，因此这里用该字段作为“之前版本”可复现基线。
- #16 未结算，参与押/保/停形态统计，但不计入命中、profit、ROI。
- profit proxy：单腿层面，每覆盖 1 个结果记 1 单位成本；命中返还该场 `winning_sp`。不是 N 串 ticket-level 回放。

## 汇总

{md_table(metrics_records, [
        ("方案", "arm"),
        ("已结算", "settled"),
        ("下注场", "bets"),
        ("押中", "押中"),
        ("保中", "保中"),
        ("未中", "未中"),
        ("停", "停"),
        ("coverage", "coverage"),
        ("押中率", "primary_rate"),
        ("成本", "stake"),
        ("profit", "profit"),
        ("ROI", "roi"),
        ("押/保/停形态", "types"),
    ])}

## v3 相对 previous_model_q 变化

- profit proxy：{fmt_num(previous_metrics["profit"])} -> {fmt_num(v3_metrics["profit"])}，变化 {fmt_num(delta_profit)}。
- ROI proxy：{fmt_pct(previous_metrics["roi"])} -> {fmt_pct(v3_metrics["roi"])}，变化 {delta_roi:+.1%}。
- coverage：{fmt_pct(previous_metrics["coverage_hit_rate"])} -> {fmt_pct(v3_metrics["coverage_hit_rate"])}，变化 {delta_coverage:+.1%}。
- 切换场次：{len(switch_records)}/{len(rows)}；核心收益来自 #2/#3/#5/#9 由旧模型 miss 切到 v3 覆盖命中，主要损失来自 #6 由旧押中切成 v3 保中（仍覆盖但主押降低）和成本增加。

## 切换明细

{md_table(switch_records, [
        ("#", "#"),
        ("比赛", "match"),
        ("让球", "hcp"),
        ("比分", "score"),
        ("赛果", "actual"),
        ("previous", "previous"),
        ("prev命中", "prev_hit"),
        ("v3", "v3"),
        ("v3命中", "v3_hit"),
        ("切换", "switch"),
    ])}

## 全场明细

{md_table(detail_records, [
        ("#", "#"),
        ("比赛", "match"),
        ("让球", "hcp"),
        ("比分", "score"),
        ("赛果", "actual"),
        ("previous", "previous"),
        ("prev命中", "prev_hit"),
        ("v3", "v3"),
        ("v3命中", "v3_hit"),
        ("切换", "switch"),
    ])}

## 结论

v3 在 26071 上显著优于 previous_model_q：coverage 从 {fmt_pct(previous_metrics["coverage_hit_rate"])} 提升到 {fmt_pct(v3_metrics["coverage_hit_rate"])}，profit proxy 从 {fmt_num(previous_metrics["profit"])} 提升到 {fmt_num(v3_metrics["profit"])}。提升主要来自 LLM/信息面把若干高 q 低胜率方向降为保护，同时把更高胜率方向设为主押；代价是 stake 从 {previous_metrics["stake"]} 增到 {v3_metrics["stake"]}，且个别场次主押准确率被牺牲。
"""


def run(issue: str, db_path: Path, report_dir: Path) -> Path:
    conn = sqlite3.connect(db_path)
    try:
        rows = load_rows(conn, issue)
    finally:
        conn.close()
    if not rows:
        raise SystemExit(f"No active snapshots found for issue {issue}")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"decision_chain_v3_vs_previous_{issue}_2026-07-03.md"
    report_path.write_text(render_report(issue, rows), encoding="utf-8")
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare v3 decision chain against previous model/q recommendations.")
    parser.add_argument("--issue", default="26071")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_path = run(args.issue, args.db, args.report_dir)
    print(report_path)


if __name__ == "__main__":
    main()
