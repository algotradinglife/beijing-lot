from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluate_structured_decision_chain_shadow import (
    OUTCOME_LABEL,
    OUTCOME_ORDER,
    leg_profit,
    result_rows,
    safe_float,
    structured_decision_for_payload,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_REPORT = PROJECT_ROOT / "docs/research/euro_avg_sp_shadow_backtest.md"
DEFAULT_CSV = PROJECT_ROOT / "docs/research/euro_avg_sp_shadow_backtest.csv"


@dataclass(frozen=True)
class SnapshotRow:
    issue: str
    match_idx: int
    league: str
    home: str
    away: str
    score: str
    result_code: str | None
    winning_sp: float | None
    result_source: str
    payload: dict[str, Any]


def outcome_text(code: str | None) -> str:
    if code in OUTCOME_LABEL:
        return OUTCOME_LABEL[code]
    return "-"


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


def num(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def md_table(records: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    lines = ["| " + " | ".join(title for title, _ in columns) + " |"]
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for record in records:
        values = []
        for _title, key in columns:
            value = record.get(key, "")
            if isinstance(value, float):
                value = f"{value:.4f}"
            values.append(str(value).replace("\n", " ").replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def complete_triplet(values: dict[str, Any]) -> bool:
    return all(safe_float(values.get(code)) is not None and float(values.get(code) or 0) > 0 for code in OUTCOME_ORDER)


def euro_avg_sp_from_payload(payload: dict[str, Any]) -> dict[str, float | None]:
    current_avg = (
        payload.get("market", {})
        .get("odds_consensus", {})
        .get("current_avg", {})
    )
    return {
        "3": safe_float(current_avg.get("home")),
        "1": safe_float(current_avg.get("draw")),
        "0": safe_float(current_avg.get("away")),
    }


def payload_with_euro_avg_sp(payload: dict[str, Any]) -> dict[str, Any] | None:
    euro_sp = euro_avg_sp_from_payload(payload)
    if not complete_triplet(euro_sp):
        return None
    cloned = copy.deepcopy(payload)
    original_sp = cloned.get("sp") if isinstance(cloned.get("sp"), dict) else {}
    cloned["sp"] = {
        **euro_sp,
        "display_source": "euro_avg_current_avg_substitute",
        "prediction_source": "euro_avg_current_avg_substitute",
        "snapshot_ts": original_sp.get("snapshot_ts") or original_sp.get("prediction_snapshot_ts") or "",
        "original_sp_source": original_sp.get("prediction_source") or original_sp.get("display_source") or "",
    }
    return cloned


def load_rows(conn: sqlite3.Connection, issues: list[str]) -> list[SnapshotRow]:
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in issues)
    has_nowscore = bool(
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nowscore_bjdc_matches'").fetchone()
    )
    nowscore_cols = (
        """
            n.score AS nowscore_score,
            n.result_code AS nowscore_result_code,
            n.status AS nowscore_status,
            n.status_text AS nowscore_status_text
        """
        if has_nowscore
        else """
            NULL AS nowscore_score,
            NULL AS nowscore_result_code,
            NULL AS nowscore_status,
            NULL AS nowscore_status_text
        """
    )
    nowscore_join = (
        """
        LEFT JOIN nowscore_bjdc_matches n
          ON n.issue=s.issue AND n.match_idx=s.match_idx
        """
        if has_nowscore
        else ""
    )
    rows = conn.execute(
        f"""
        WITH active AS (
            SELECT
                s.*,
                ROW_NUMBER() OVER (
                    PARTITION BY s.issue, s.match_idx
                    ORDER BY s.generated_at DESC, s.snapshot_id DESC
                ) AS rn
            FROM llm_decision_snapshots s
            WHERE s.status='active'
              AND s.issue IN ({placeholders})
        )
        SELECT
            s.issue,
            s.match_idx,
            s.input_payload_json,
            m.league,
            m.home,
            m.away,
            m.score,
            m.result_code,
            m.winning_sp,
            {nowscore_cols}
        FROM active s
        LEFT JOIN matches m
          ON m.issue=s.issue AND m.match_idx=s.match_idx
        {nowscore_join}
        WHERE s.rn=1
        ORDER BY s.issue, s.match_idx
        """,
        issues,
    ).fetchall()
    out: list[SnapshotRow] = []
    for row in rows:
        try:
            payload = json.loads(row["input_payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        nowscore_finished = str(row["nowscore_status"] or "") == "finished" or "完场" in str(row["nowscore_status_text"] or "")
        result_code = row["result_code"]
        result_source = "matches"
        if result_code is None and nowscore_finished and row["nowscore_result_code"] is not None:
            result_code = row["nowscore_result_code"]
            result_source = "nowscore"
        score = str(row["score"] or "")
        if not score and nowscore_finished and row["nowscore_score"]:
            score = str(row["nowscore_score"])
        out.append(
            SnapshotRow(
                issue=str(row["issue"]),
                match_idx=int(row["match_idx"]),
                league=str(row["league"] or payload.get("match", {}).get("league") or ""),
                home=str(row["home"] or payload.get("match", {}).get("home") or ""),
                away=str(row["away"] or payload.get("match", {}).get("away") or ""),
                score=score,
                result_code=str(result_code) if result_code is not None else None,
                winning_sp=safe_float(row["winning_sp"]),
                result_source=result_source if result_code is not None else "",
                payload=payload,
            )
        )
    return out


def available_issues(conn: sqlite3.Connection) -> list[str]:
    conn.row_factory = sqlite3.Row
    return [
        str(row["issue"])
        for row in conn.execute(
            """
            SELECT issue
            FROM llm_decision_snapshots
            WHERE status='active'
            GROUP BY issue
            ORDER BY issue
            """
        )
    ]


def codes_from_decision(decision: dict[str, Any]) -> list[str]:
    return [str(code) for code in decision.get("selection_codes", []) if str(code) in OUTCOME_ORDER]


def q_map(payload: dict[str, Any]) -> dict[str, float | None]:
    return {str(row["code"]): safe_float(row.get("q")) for row in result_rows(payload)}


def top_code_by_q(payload: dict[str, Any]) -> str:
    rows = [row for row in result_rows(payload) if safe_float(row.get("q")) is not None]
    if not rows:
        return ""
    return str(max(rows, key=lambda row: float(row["q"]))["code"])


def top_code_by_probability(payload: dict[str, Any]) -> str:
    rows = [row for row in result_rows(payload) if safe_float(row.get("probability")) is not None]
    if not rows:
        return ""
    return str(max(rows, key=lambda row: float(row["probability"]))["code"])


def evaluate_row(row: SnapshotRow, arm: str, payload: dict[str, Any]) -> dict[str, Any]:
    decision = structured_decision_for_payload(payload)
    codes = codes_from_decision(decision)
    q_values = q_map(payload)
    max_q = max((value for value in q_values.values() if value is not None), default=None)
    hit = bool(row.result_code and row.result_code in codes)
    primary = str(decision.get("primary_pick") or "")
    return {
        "arm": arm,
        "issue": row.issue,
        "match_idx": row.match_idx,
        "league": row.league,
        "home": row.home,
        "away": row.away,
        "score": row.score,
        "actual_code": row.result_code or "",
        "actual": outcome_text(row.result_code),
        "winning_sp": row.winning_sp,
        "result_source": row.result_source,
        "judgment": decision.get("judgment", ""),
        "selection_codes": "+".join(codes),
        "selection_labels": "+".join(outcome_text(code) for code in codes),
        "selection_type": "no-buy" if not codes else "single" if len(codes) == 1 else "double" if len(codes) == 2 else "full",
        "primary": primary,
        "primary_label": outcome_text(primary),
        "stop_flag": int(bool(decision.get("stop_flag"))),
        "stake": len(codes),
        "coverage_hit": int(hit) if row.result_code else "",
        "primary_hit": int(primary == row.result_code) if row.result_code else "",
        "profit_proxy": leg_profit(codes, row.result_code, row.winning_sp) if row.result_code and row.winning_sp is not None else "",
        "prob_top": top_code_by_probability(payload),
        "q_top": top_code_by_q(payload),
        "max_q": max_q,
        "q_3": q_values.get("3"),
        "q_1": q_values.get("1"),
        "q_0": q_values.get("0"),
        "sp_3": safe_float(payload.get("sp", {}).get("3")),
        "sp_1": safe_float(payload.get("sp", {}).get("1")),
        "sp_0": safe_float(payload.get("sp", {}).get("0")),
        "risk_tags": ";".join(decision.get("risk_tags", [])),
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    result_known = [record for record in records if record["actual_code"]]
    bet = [record for record in result_known if record["stake"]]
    profit_known = [record for record in result_known if record["profit_proxy"] != ""]
    stake = sum(int(record["stake"]) for record in profit_known)
    profit_values = [safe_float(record["profit_proxy"]) for record in profit_known]
    profit = sum(value for value in profit_values if value is not None)
    max_q_values = [safe_float(record["max_q"]) for record in records if safe_float(record["max_q"]) is not None]
    sorted_q = sorted(value for value in max_q_values if value is not None)

    def quantile(q: float) -> float | None:
        if not sorted_q:
            return None
        pos = (len(sorted_q) - 1) * q
        low = math.floor(pos)
        high = math.ceil(pos)
        if low == high:
            return sorted_q[low]
        return sorted_q[low] * (high - pos) + sorted_q[high] * (pos - low)

    return {
        "n": len(records),
        "result_known": len(result_known),
        "profit_known": len(profit_known),
        "bet_matches": len(bet),
        "stake": stake,
        "coverage_hits": sum(1 for record in bet if record["coverage_hit"] == 1),
        "primary_hits": sum(1 for record in bet if record["primary_hit"] == 1),
        "coverage_hit_rate": sum(1 for record in bet if record["coverage_hit"] == 1) / len(bet) if bet else None,
        "primary_hit_rate": sum(1 for record in bet if record["primary_hit"] == 1) / len(bet) if bet else None,
        "profit_proxy": round(profit, 4),
        "roi_proxy": profit / stake if stake else None,
        "avg_stake_per_profit_known": stake / len(profit_known) if profit_known else None,
        "type_counts": dict(Counter(record["selection_type"] for record in records)),
        "q_p50": quantile(0.50),
        "q_p90": quantile(0.90),
        "q_p95": quantile(0.95),
        "q_max": max(sorted_q) if sorted_q else None,
        "q_ge_2": sum(1 for value in max_q_values if value is not None and value >= 2.0),
        "q_ge_5": sum(1 for value in max_q_values if value is not None and value >= 5.0),
    }


def render_report(
    *,
    issues: list[str],
    native_records: list[dict[str, Any]],
    euro_records: list[dict[str, Any]],
    unavailable: list[SnapshotRow],
    csv_path: Path,
) -> str:
    native_summary = summarize(native_records)
    euro_summary = summarize(euro_records)
    by_key_native = {(record["issue"], record["match_idx"]): record for record in native_records}
    by_key_euro = {(record["issue"], record["match_idx"]): record for record in euro_records}
    common_keys = sorted(set(by_key_native) & set(by_key_euro))
    switches = []
    for key in common_keys:
        native = by_key_native[key]
        euro = by_key_euro[key]
        if native["selection_codes"] != euro["selection_codes"] or native["q_top"] != euro["q_top"]:
            switches.append(
                {
                    "issue": key[0],
                    "#": key[1],
                    "match": f"{native['home']} vs {native['away']}",
                    "score": native["score"] or "-",
                    "actual": native["actual"],
                    "native": native["selection_labels"] or "-",
                    "euro": euro["selection_labels"] or "-",
                    "native_hit": native["coverage_hit"],
                    "euro_hit": euro["coverage_hit"],
                    "native_q_top": outcome_text(native["q_top"]),
                    "euro_q_top": outcome_text(euro["q_top"]),
                    "native_max_q": num(safe_float(native["max_q"])),
                    "euro_max_q": num(safe_float(euro["max_q"])),
                }
            )

    issue_rows = []
    for issue in issues:
        n_records = [record for record in native_records if record["issue"] == issue]
        e_records = [record for record in euro_records if record["issue"] == issue]
        if not n_records or not e_records:
            continue
        n_sum = summarize(n_records)
        e_sum = summarize(e_records)
        issue_rows.append(
            {
                "issue": issue,
                "native_hit": pct(n_sum["coverage_hit_rate"]),
                "euro_hit": pct(e_sum["coverage_hit_rate"]),
                "native_roi": pct(n_sum["roi_proxy"]),
                "euro_roi": pct(e_sum["roi_proxy"]),
                "native_profit": n_sum["profit_proxy"],
                "euro_profit": e_sum["profit_proxy"],
                "native_stake": n_sum["stake"],
                "euro_stake": e_sum["stake"],
                "native_types": n_sum["type_counts"],
                "euro_types": e_sum["type_counts"],
            }
        )

    summary_rows = [
        {
            "arm": "北单SP快照",
            "n": native_summary["n"],
            "result_known": native_summary["result_known"],
            "profit_known": native_summary["profit_known"],
            "hit": pct(native_summary["coverage_hit_rate"]),
            "primary": pct(native_summary["primary_hit_rate"]),
            "stake": native_summary["stake"],
            "avg_depth": num(native_summary["avg_stake_per_profit_known"]),
            "profit": native_summary["profit_proxy"],
            "roi": pct(native_summary["roi_proxy"]),
            "types": native_summary["type_counts"],
        },
        {
            "arm": "欧赔均值替代",
            "n": euro_summary["n"],
            "result_known": euro_summary["result_known"],
            "profit_known": euro_summary["profit_known"],
            "hit": pct(euro_summary["coverage_hit_rate"]),
            "primary": pct(euro_summary["primary_hit_rate"]),
            "stake": euro_summary["stake"],
            "avg_depth": num(euro_summary["avg_stake_per_profit_known"]),
            "profit": euro_summary["profit_proxy"],
            "roi": pct(euro_summary["roi_proxy"]),
            "types": euro_summary["type_counts"],
        },
    ]
    stability_rows = [
        {
            "arm": "北单SP快照",
            "q_p50": num(native_summary["q_p50"]),
            "q_p90": num(native_summary["q_p90"]),
            "q_p95": num(native_summary["q_p95"]),
            "q_max": num(native_summary["q_max"]),
            "q_ge_2": native_summary["q_ge_2"],
            "q_ge_5": native_summary["q_ge_5"],
        },
        {
            "arm": "欧赔均值替代",
            "q_p50": num(euro_summary["q_p50"]),
            "q_p90": num(euro_summary["q_p90"]),
            "q_p95": num(euro_summary["q_p95"]),
            "q_max": num(euro_summary["q_max"]),
            "q_ge_2": euro_summary["q_ge_2"],
            "q_ge_5": euro_summary["q_ge_5"],
        },
    ]
    issue_61 = [
        record
        for record in (by_key_native.get(("26072", 61)), by_key_euro.get(("26072", 61)))
        if record
    ]
    issue_61_rows = [
        {
            "arm": "北单SP快照" if record["arm"] == "native_sp" else "欧赔均值替代",
            "selection": record["selection_labels"],
            "hit": record["coverage_hit"],
            "sp": f"{num(record['sp_3'], 2)}/{num(record['sp_1'], 2)}/{num(record['sp_0'], 2)}",
            "q": f"{num(record['q_3'])}/{num(record['q_1'])}/{num(record['q_0'])}",
            "q_top": outcome_text(record["q_top"]),
            "risk": record["risk_tags"],
        }
        for record in issue_61
    ]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    return f"""# 欧赔均值替代北单 SP 快照回测

生成时间：{generated}

## 数据边界

- 样本：`llm_decision_snapshots.status='active'` 中可复算的期号：{", ".join(issues)}。
- 替代口径：只把 payload 里的 `sp.3/1/0` 换成同一 payload 的 `market.odds_consensus.current_avg.home/draw/away`；模型概率、情报、让球、赛果不变。
- 命中口径：优先使用 `matches.result_code`；主表未写入但 nowscore 已完场时，用 nowscore 赛果只评估命中。
- 结算口径：profit proxy 只使用已有真实北单 `winning_sp` 的行；每覆盖一个结果记 1 单位成本，命中返还该场 `winning_sp`。
- 注意：这是 26071-26072 的 live 决策链小样本回测，不代表长期历史收益。

## 整体结果

{md_table(summary_rows, [
        ("口径", "arm"),
        ("样本", "n"),
        ("有赛果", "result_known"),
        ("有SP结算", "profit_known"),
        ("押+保命中", "hit"),
        ("主押命中", "primary"),
        ("成本", "stake"),
        ("均深", "avg_depth"),
        ("profit proxy", "profit"),
        ("ROI proxy", "roi"),
        ("票型", "types"),
    ])}

## q 稳定性

{md_table(stability_rows, [
        ("口径", "arm"),
        ("q p50", "q_p50"),
        ("q p90", "q_p90"),
        ("q p95", "q_p95"),
        ("q max", "q_max"),
        ("q>=2", "q_ge_2"),
        ("q>=5", "q_ge_5"),
    ])}

## 分期结果

{md_table(issue_rows, [
        ("期号", "issue"),
        ("北单命中", "native_hit"),
        ("欧赔命中", "euro_hit"),
        ("北单ROI", "native_roi"),
        ("欧赔ROI", "euro_roi"),
        ("北单profit", "native_profit"),
        ("欧赔profit", "euro_profit"),
        ("北单成本", "native_stake"),
        ("欧赔成本", "euro_stake"),
        ("北单票型", "native_types"),
        ("欧赔票型", "euro_types"),
    ])}

## #61 专项

{md_table(issue_61_rows, [
        ("口径", "arm"),
        ("押保", "selection"),
        ("命中", "hit"),
        ("赔率/替代价 3/1/0", "sp"),
        ("q 3/1/0", "q"),
        ("q top", "q_top"),
        ("风险", "risk"),
    ])}

## 发生切换的场次

{md_table(switches[:40], [
        ("期号", "issue"),
        ("#", "#"),
        ("比赛", "match"),
        ("比分", "score"),
        ("赛果", "actual"),
        ("北单SP押保", "native"),
        ("欧赔押保", "euro"),
        ("北单命中", "native_hit"),
        ("欧赔命中", "euro_hit"),
        ("北单q top", "native_q_top"),
        ("欧赔q top", "euro_q_top"),
        ("北单max_q", "native_max_q"),
        ("欧赔max_q", "euro_max_q"),
    ])}

完整 CSV：`{csv_path.relative_to(PROJECT_ROOT)}`

## 结论

欧赔均值替代明显压低了北单早盘 SP 的极端 q，尤其能修正 #61 这类 `北单早盘异常高 SP -> q 爆表 -> 后续重定价失效` 的问题。代价是它会改变 q top 和保护方向；当前小样本里命中率略降，但总成本也下降，ROI proxy 接近。更合理的用法不是直接替代结算 SP，而是把欧赔均值作为 q 稳定锚：当北单 SP 与欧赔均值严重背离时，限制该方向单选或强制加入概率 top/q top 保护。
"""


def run(db_path: Path, issues: list[str], report_path: Path, csv_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    try:
        resolved_issues = issues or available_issues(conn)
        rows = load_rows(conn, resolved_issues)
    finally:
        conn.close()
    native_records: list[dict[str, Any]] = []
    euro_records: list[dict[str, Any]] = []
    unavailable: list[SnapshotRow] = []
    for row in rows:
        native_records.append(evaluate_row(row, "native_sp", row.payload))
        euro_payload = payload_with_euro_avg_sp(row.payload)
        if euro_payload is None:
            unavailable.append(row)
            continue
        euro_records.append(evaluate_row(row, "euro_avg_sp", euro_payload))

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "arm",
        "issue",
        "match_idx",
        "league",
        "home",
        "away",
        "score",
        "actual",
        "actual_code",
        "winning_sp",
        "result_source",
        "judgment",
        "selection_labels",
        "selection_codes",
        "selection_type",
        "primary_label",
        "stop_flag",
        "stake",
        "coverage_hit",
        "primary_hit",
        "profit_proxy",
        "prob_top",
        "q_top",
        "max_q",
        "q_3",
        "q_1",
        "q_0",
        "sp_3",
        "sp_1",
        "sp_0",
        "risk_tags",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in native_records + euro_records:
            writer.writerow({key: record.get(key, "") for key in fieldnames})

    report = render_report(
        issues=resolved_issues,
        native_records=native_records,
        euro_records=euro_records,
        unavailable=unavailable,
        csv_path=csv_path,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    return report_path, csv_path, {
        "native": summarize(native_records),
        "euro": summarize(euro_records),
        "unavailable": len(unavailable),
        "rows": len(rows),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest replacing Beidan SP snapshots with same-time European average odds in shadow chain.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue", action="append", default=[], help="Issue to include. Repeatable. Defaults to all active snapshot issues.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_path, csv_path, summary = run(args.db, args.issue, args.report, args.csv)
    print(json.dumps({"report": str(report_path), "csv": str(csv_path), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
