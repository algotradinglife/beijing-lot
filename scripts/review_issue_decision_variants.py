from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "docs/research"
DEFAULT_DETAIL_DIR = PROJECT_ROOT / "results/issue_reviews"
OUTCOME_LABEL = {"3": "胜", "1": "平", "0": "负"}
OUTCOME_ORDER = ("3", "1", "0")


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def safe_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_codes(value: Any) -> list[str]:
    if isinstance(value, list):
        parts = value
    else:
        parts = str(value or "").replace(",", "+").split("+")
    return [str(part).strip() for part in parts if str(part).strip() in OUTCOME_LABEL]


def labels(codes: list[str]) -> str:
    return "+".join(OUTCOME_LABEL.get(code, code) for code in codes) if codes else "停"


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


def num(value: float | None, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def md_table(records: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    lines = ["| " + " | ".join(title for title, _key in columns) + " |"]
    lines.append("| " + " | ".join("---" for _title, _key in columns) + " |")
    for record in records:
        values = []
        for _title, key in columns:
            value = record.get(key, "")
            if isinstance(value, float):
                value = f"{value:.4f}"
            values.append(str(value).replace("\n", " ").replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def load_matches(db_path: Path, issue: str) -> dict[int, dict[str, Any]]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT
              issue, match_idx, league, home, away, handicap_line, score,
              result_code, result_label, winning_sp,
              sp_home, sp_draw, sp_away,
              avg_odds_home, avg_odds_draw, avg_odds_away
            FROM matches
            WHERE issue=?
            ORDER BY match_idx
            """,
            (issue,),
        ).fetchall()
    finally:
        con.close()
    return {int(row["match_idx"]): dict(row) for row in rows}


def artifact_candidates(issue: str) -> list[Path]:
    patterns = [
        f"results/structured_decision_chain_shadow/{issue}_*_shadow_v3.3.3/structured_shadow_{issue}.csv",
        f"results/structured_decision_chain_shadow/{issue}_*_shadow_v4.2.0000_execution_late_proxy_fullcap2/structured_shadow_{issue}.csv",
        f"results/structured_decision_chain_shadow/{issue}_*_shadow_v4.2.0005_execution_late_proxy_fullcap2/structured_shadow_{issue}.csv",
    ]
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(path) for path in glob.glob(str(PROJECT_ROOT / pattern)))
    return sorted(set(paths), key=lambda path: path.stat().st_mtime)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def arm_label(row: dict[str, str], path: Path) -> str:
    arm = str(row.get("shadow_arm") or "")
    policy = str(row.get("execution_policy_version") or "")
    if arm == "shadow_v3.3.3":
        return "shadow_v3.3.3 默认"
    if "v4.2.0005" in arm or "v4.2.0005" in policy:
        return "v4.2.0005 late-proxy 观察"
    if "v4.2.0000" in arm and "0004" in policy:
        return "v4.2.0004 late-proxy 观察"
    return arm or path.parent.name


def choose_artifacts(issue: str) -> dict[str, Path]:
    chosen: dict[str, Path] = {}
    for path in artifact_candidates(issue):
        rows = read_csv_rows(path)
        if not rows:
            continue
        label = arm_label(rows[0], path)
        chosen[label] = path
    return chosen


def evaluate_artifact(issue: str, path: Path, matches: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = read_csv_rows(path)
    if not rows:
        return []
    label = arm_label(rows[0], path)
    out: list[dict[str, Any]] = []
    for row in rows:
        idx = safe_int(row.get("match_idx"))
        if idx is None:
            continue
        match = matches.get(idx, {})
        actual = str(match.get("result_code") or row.get("actual_code") or "")
        winning_sp = safe_float(match.get("winning_sp"))
        codes = parse_codes(row.get("shadow_selection_codes"))
        primary = str(row.get("shadow_primary") or "")
        if primary not in OUTCOME_LABEL:
            primary = codes[0] if codes else ""
        if primary and primary not in codes and codes:
            primary = codes[0]
        coverage_hit = bool(actual and actual in codes)
        primary_hit = bool(actual and primary == actual)
        protect_hit = bool(coverage_hit and not primary_hit)
        stake = float(len(codes))
        gross = float(winning_sp or 0.0) if coverage_hit and winning_sp is not None else 0.0
        profit = gross - stake if actual else 0.0
        selection_type = "no-buy" if not codes else "single" if len(codes) == 1 else "double" if len(codes) == 2 else "full"
        q_values = {code: safe_float(row.get(f"q_{code}") or row.get(f"execution_q_{code}")) for code in OUTCOME_ORDER}
        p_values = {code: safe_float(row.get(f"p_{code}")) for code in OUTCOME_ORDER}
        sp_values = {
            code: safe_float(row.get(f"sp_{code}") or row.get(f"execution_sp_{code}"))
            for code in OUTCOME_ORDER
        }
        actual_label = OUTCOME_LABEL.get(actual, str(match.get("result_label") or row.get("actual_label") or ""))
        out.append(
            {
                "arm": label,
                "artifact": str(path.relative_to(PROJECT_ROOT)),
                "issue": issue,
                "match_idx": idx,
                "league": match.get("league") or row.get("league") or "",
                "home": match.get("home") or row.get("home") or "",
                "away": match.get("away") or row.get("away") or "",
                "handicap": match.get("handicap_line") if match.get("handicap_line") is not None else row.get("handicap_line"),
                "score": match.get("score") or row.get("score") or "",
                "actual_code": actual,
                "actual": actual_label,
                "winning_sp": winning_sp,
                "selection_codes": "+".join(codes),
                "selection": labels(codes),
                "primary": primary,
                "primary_label": OUTCOME_LABEL.get(primary, ""),
                "selection_type": selection_type,
                "stake": stake,
                "gross": gross,
                "profit": profit,
                "roi": profit / stake if stake else None,
                "coverage_hit": int(coverage_hit) if actual else "",
                "primary_hit": int(primary_hit) if actual else "",
                "protect_hit": int(protect_hit) if actual else "",
                "prob_top": row.get("prob_top") or "",
                "q_top": row.get("q_top") or "",
                "p_3": p_values["3"],
                "p_1": p_values["1"],
                "p_0": p_values["0"],
                "sp_3": sp_values["3"],
                "sp_1": sp_values["1"],
                "sp_0": sp_values["0"],
                "q_3": q_values["3"],
                "q_1": q_values["1"],
                "q_0": q_values["0"],
                "risk_tags": row.get("risk_tags") or "",
                "execution_policy_version": row.get("execution_policy_version") or "",
                "execution_action": row.get("execution_action") or "",
                "execution_reasons": row.get("execution_reasons") or "",
                "execution_unlock_state": row.get("execution_unlock_state") or "",
                "source_sp_3": safe_float(row.get("source_sp_3")),
                "source_sp_1": safe_float(row.get("source_sp_1")),
                "source_sp_0": safe_float(row.get("source_sp_0")),
            }
        )
    return out


def summarize(records: list[dict[str, Any]], total_matches: int) -> dict[str, Any]:
    assessed = [record for record in records if record.get("actual_code")]
    bet = [record for record in assessed if record["stake"] > 0]
    stake = sum(float(record["stake"]) for record in bet)
    profit = sum(float(record["profit"]) for record in bet)
    primary_hits = sum(1 for record in bet if record["primary_hit"] == 1)
    protect_hits = sum(1 for record in bet if record["protect_hit"] == 1)
    coverage_hits = sum(1 for record in bet if record["coverage_hit"] == 1)
    misses = [record for record in bet if record["coverage_hit"] == 0]
    return {
        "arm": records[0]["arm"] if records else "",
        "artifact_rows": len(records),
        "issue_matches": total_matches,
        "missing_decisions": max(0, total_matches - len(records)),
        "assessed": len(assessed),
        "stake": stake,
        "avg_depth": stake / len(bet) if bet else None,
        "primary_hits": primary_hits,
        "protect_hits": protect_hits,
        "coverage_hits": coverage_hits,
        "misses": len(misses),
        "primary_hit_rate": primary_hits / len(bet) if bet else None,
        "protect_save_rate": protect_hits / len(bet) if bet else None,
        "coverage_hit_rate": coverage_hits / len(bet) if bet else None,
        "profit": profit,
        "roi": profit / stake if stake else None,
        "type_counts": dict(Counter(record["selection_type"] for record in records)),
        "miss_actual_counts": dict(Counter(record["actual"] for record in misses)),
    }


def compare_records(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, Any]:
    left_by_idx = {record["match_idx"]: record for record in left}
    right_by_idx = {record["match_idx"]: record for record in right}
    common = sorted(set(left_by_idx) & set(right_by_idx))
    switches: list[dict[str, Any]] = []
    saved: list[dict[str, Any]] = []
    lost: list[dict[str, Any]] = []
    for idx in common:
        a = left_by_idx[idx]
        b = right_by_idx[idx]
        if a["selection_codes"] != b["selection_codes"] or a["primary"] != b["primary"]:
            item = {
                "match_idx": idx,
                "match": f"{a['home']} vs {a['away']}",
                "score": a["score"],
                "actual": a["actual"],
                "left_selection": a["selection"],
                "right_selection": b["selection"],
                "left_hit": a["coverage_hit"],
                "right_hit": b["coverage_hit"],
                "left_profit": round(float(a["profit"]), 4),
                "right_profit": round(float(b["profit"]), 4),
                "risk_tags": a["risk_tags"] or b["risk_tags"],
            }
            switches.append(item)
            if a["coverage_hit"] == 0 and b["coverage_hit"] == 1:
                saved.append(item)
            elif a["coverage_hit"] == 1 and b["coverage_hit"] == 0:
                lost.append(item)
    return {"switches": switches, "saved": saved, "lost": lost}


def tag_counter(records: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in records:
        for tag in str(record.get("risk_tags") or "").split(";"):
            tag = tag.strip()
            if tag:
                counter[tag] += 1
    return counter


def key_case_rows(records_by_arm: dict[str, list[dict[str, Any]]], match_indices: list[int]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for arm, records in records_by_arm.items():
        by_idx = {record["match_idx"]: record for record in records}
        for idx in match_indices:
            record = by_idx.get(idx)
            if not record:
                continue
            out.append(
                {
                    "arm": arm,
                    "#": idx,
                    "match": f"{record['home']} vs {record['away']}",
                    "score": record["score"],
                    "actual": f"{record['actual']}({num(record['winning_sp'])})",
                    "selection": record["selection"],
                    "hit": record["coverage_hit"],
                    "profit": round(float(record["profit"]), 4),
                    "p": f"{pct(record['p_3'])}/{pct(record['p_1'])}/{pct(record['p_0'])}",
                    "q": f"{num(record['q_3'])}/{num(record['q_1'])}/{num(record['q_0'])}",
                    "sp": f"{num(record['sp_3'])}/{num(record['sp_1'])}/{num(record['sp_0'])}",
                    "reason": record["execution_reasons"] or record["risk_tags"],
                }
            )
    return out


def render_report(
    *,
    issue: str,
    matches: dict[int, dict[str, Any]],
    summaries: list[dict[str, Any]],
    records_by_arm: dict[str, list[dict[str, Any]]],
    comparisons: dict[str, dict[str, Any]],
    detail_csv: Path,
) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    settled = [m for m in matches.values() if m.get("result_code") and m.get("winning_sp") is not None]
    result_counts = Counter(OUTCOME_LABEL.get(str(m.get("result_code")), str(m.get("result_code"))) for m in settled)
    summary_rows = [
        {
            "arm": row["arm"],
            "rows": row["artifact_rows"],
            "missing": row["missing_decisions"],
            "hit": pct(row["coverage_hit_rate"]),
            "primary": pct(row["primary_hit_rate"]),
            "protect": pct(row["protect_save_rate"]),
            "stake": num(row["stake"], 0),
            "depth": num(row["avg_depth"]),
            "profit": num(row["profit"]),
            "roi": pct(row["roi"]),
            "types": row["type_counts"],
            "misses": row["miss_actual_counts"],
        }
        for row in summaries
    ]
    default_arm = next((arm for arm in records_by_arm if arm.startswith("shadow_v3.3.3")), "")
    latest_arm = next((arm for arm in records_by_arm if "0005" in arm), "")
    default_records = records_by_arm.get(default_arm, [])
    latest_records = records_by_arm.get(latest_arm, [])
    default_misses = sorted(
        [record for record in default_records if record["coverage_hit"] == 0],
        key=lambda record: (record["actual"], -float(record["winning_sp"] or 0)),
    )
    miss_rows = [
        {
            "#": record["match_idx"],
            "match": f"{record['home']} vs {record['away']}",
            "score": record["score"],
            "actual": f"{record['actual']}({num(record['winning_sp'])})",
            "selection": record["selection"],
            "prob_top": OUTCOME_LABEL.get(record["prob_top"], record["prob_top"]),
            "q_top": OUTCOME_LABEL.get(record["q_top"], record["q_top"]),
            "p": f"{pct(record['p_3'])}/{pct(record['p_1'])}/{pct(record['p_0'])}",
            "q": f"{num(record['q_3'])}/{num(record['q_1'])}/{num(record['q_0'])}",
            "risk": record["risk_tags"],
        }
        for record in default_misses[:18]
    ]
    protection_rows = [
        {
            "#": record["match_idx"],
            "match": f"{record['home']} vs {record['away']}",
            "score": record["score"],
            "actual": f"{record['actual']}({num(record['winning_sp'])})",
            "selection": record["selection"],
            "profit": num(record["profit"]),
            "risk": record["risk_tags"],
        }
        for record in default_records
        if record["protect_hit"] == 1
    ][:18]
    switch = comparisons.get(f"{default_arm} -> {latest_arm}", {}) if default_arm and latest_arm else {}
    saved_rows = switch.get("saved", [])[:12]
    lost_rows = switch.get("lost", [])[:12]
    tag_rows = [
        {"tag": tag, "count": count}
        for tag, count in tag_counter(default_records).most_common(12)
    ]
    key_rows = key_case_rows(records_by_arm, [51, 61, 63])
    return f"""# 26072 期决策复盘

生成时间：{generated}

## 数据边界

- 赛果/结算：`matches` 中 26072 共 {len(matches)} 场，已有赛果和 `winning_sp` 的场次 {len(settled)} 场。
- 决策样本：结构化决策产物覆盖 65 场，#66/#67 没有赛前结构化决策产物，不纳入押/保命中率。
- 收益口径：单腿 proxy，每覆盖一个结果计 1 单位成本；命中返还该场真实北单 `winning_sp`。这不是 N 串票级收益。
- 默认复盘对象：`shadow_v3.3.3`。v4.2 late-proxy 只作为观察版对照，strict 等非实战版本不纳入。

本期真实赛果分布：{dict(result_counts)}

## 总览

{md_table(summary_rows, [
        ("版本", "arm"),
        ("决策场", "rows"),
        ("无决策", "missing"),
        ("押+保命中", "hit"),
        ("主押命中", "primary"),
        ("保中", "protect"),
        ("成本", "stake"),
        ("均深", "depth"),
        ("profit proxy", "profit"),
        ("ROI proxy", "roi"),
        ("票型", "types"),
        ("漏中结果", "misses"),
    ])}

## 默认版漏中

{md_table(miss_rows, [
        ("#", "#"),
        ("比赛", "match"),
        ("比分", "score"),
        ("赛果", "actual"),
        ("押保", "selection"),
        ("概率top", "prob_top"),
        ("q top", "q_top"),
        ("P 3/1/0", "p"),
        ("q 3/1/0", "q"),
        ("标签", "risk"),
    ])}

## 默认版保护救票

{md_table(protection_rows, [
        ("#", "#"),
        ("比赛", "match"),
        ("比分", "score"),
        ("赛果", "actual"),
        ("押保", "selection"),
        ("单腿收益", "profit"),
        ("标签", "risk"),
    ])}

## v3.3.3 vs v4.2.0005 late-proxy

v4.2.0005 的主要价值是修正 v4.2.0004 在 #61 上的异常 SP/q 单选问题。它把 #61 从单选胜改成 `负+平`，覆盖了实际客胜。

切换后救回的场次：

{md_table(saved_rows, [
        ("#", "match_idx"),
        ("比赛", "match"),
        ("比分", "score"),
        ("赛果", "actual"),
        ("v3.3.3", "left_selection"),
        ("v4.2.0005", "right_selection"),
        ("v3收益", "left_profit"),
        ("v4收益", "right_profit"),
        ("标签", "risk_tags"),
    ])}

切换后丢失的场次：

{md_table(lost_rows, [
        ("#", "match_idx"),
        ("比赛", "match"),
        ("比分", "score"),
        ("赛果", "actual"),
        ("v3.3.3", "left_selection"),
        ("v4.2.0005", "right_selection"),
        ("v3收益", "left_profit"),
        ("v4收益", "right_profit"),
        ("标签", "risk_tags"),
    ])}

## 重点场

{md_table(key_rows, [
        ("版本", "arm"),
        ("#", "#"),
        ("比赛", "match"),
        ("比分", "score"),
        ("赛果", "actual"),
        ("押保", "selection"),
        ("命中", "hit"),
        ("收益", "profit"),
        ("P 3/1/0", "p"),
        ("q 3/1/0", "q"),
        ("SP 3/1/0", "sp"),
        ("原因/标签", "reason"),
    ])}

## 标签分布

{md_table(tag_rows, [("标签", "tag"), ("次数", "count")])}

## 结论

1. `shadow_v3.3.3` 本期表现可用：覆盖命中率高，保护腿贡献明显，符合“先胜率、q 做保”的方向。
2. 本期 profit proxy 为正，但不要把它等同 N 串收益；它说明腿级押保质量尚可，后续还要进入票池组合和资金深度复盘。
3. #61 验证了我们前面的问题判断：极端早盘北单 SP/q 不能主导执行。v4.2.0005 的 extreme source q guard 是正确修复方向。
4. v4.2.0005 仍只能作为观察版：它会改变保护结构，救回一部分场，也会丢掉一部分原 v3.3.3 覆盖，尚不足以替代默认版。
5. 下一步策略开发应继续沿着 `v4.3 probability-first`：胜率决定主押，q/EV 决定保护和厚度，欧赔均值/临场 SP 只做异常锚和 sanity check。

明细 CSV：`{detail_csv.relative_to(PROJECT_ROOT)}`
"""


def run(issue: str, db_path: Path, report_dir: Path, detail_dir: Path) -> tuple[Path, Path, dict[str, Any]]:
    matches = load_matches(db_path, issue)
    artifacts = choose_artifacts(issue)
    if not artifacts:
        raise SystemExit(f"No decision artifacts found for issue {issue}")
    records_by_arm = {
        label: evaluate_artifact(issue, path, matches)
        for label, path in artifacts.items()
    }
    summaries = [summarize(records, len(matches)) for records in records_by_arm.values()]
    comparisons: dict[str, dict[str, Any]] = {}
    labels_list = list(records_by_arm)
    default_label = next((label for label in labels_list if label.startswith("shadow_v3.3.3")), labels_list[0])
    for label in labels_list:
        if label == default_label:
            continue
        comparisons[f"{default_label} -> {label}"] = compare_records(records_by_arm[default_label], records_by_arm[label])

    detail_dir.mkdir(parents=True, exist_ok=True)
    detail_csv = detail_dir / f"issue_{issue}_decision_variant_review.csv"
    fieldnames = list(next(iter(next(iter(records_by_arm.values()))), {}).keys())
    with detail_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for records in records_by_arm.values():
            writer.writerows(records)

    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"issue_{issue}_decision_review_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    report_path.write_text(
        render_report(
            issue=issue,
            matches=matches,
            summaries=summaries,
            records_by_arm=records_by_arm,
            comparisons=comparisons,
            detail_csv=detail_csv,
        ),
        encoding="utf-8",
    )
    return report_path, detail_csv, {
        "issue": issue,
        "artifacts": {label: str(path.relative_to(PROJECT_ROOT)) for label, path in artifacts.items()},
        "summaries": summaries,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review settled issue decision variants against final Beidan results.")
    parser.add_argument("--issue", default="26072")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--detail-dir", type=Path, default=DEFAULT_DETAIL_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_path, detail_csv, summary = run(args.issue, args.db, args.report_dir, args.detail_dir)
    print(json.dumps({"report": str(report_path), "detail_csv": str(detail_csv), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
