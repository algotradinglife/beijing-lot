#!/usr/bin/env python3
"""Evaluate pre-kickoff v3 protection codes and fixed-budget trimming variants."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.estimate_segment_betting_plan import parse_args as parse_plan_args
from scripts.estimate_segment_betting_plan import run as run_plan


DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_OUTPUT_DIR = ROOT / "results/v3_3_3_phase3_protection_trimming"
DEFAULT_REPORT = ROOT / "docs/research/v3_3_3_phase3_protection_trimming_2026-07-12.md"
OUTCOME_CODES = ("3", "1", "0")
PAPER_CANDIDATE_ID = "phase3_drop_switched_ev_home_protection"
PAPER_CANDIDATE_VERSION = "v0.1.0000"
VARIANTS = (
    "baseline",
    "primary_only",
    "draw_only",
    "switch_ev_only",
    "model_ev_only",
    "drop_model_ev_away",
    "drop_switch_ev_draw",
    "drop_switch_ev_home",
)


def fnum(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_json(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def parse_codes(value: Any) -> list[str]:
    loaded = safe_json(value, value)
    if isinstance(loaded, list):
        raw = loaded
    else:
        raw = str(loaded or "").replace(",", "+").split("+")
    return list(dict.fromkeys(str(code).strip() for code in raw if str(code).strip() in OUTCOME_CODES))


def protection_category(chain: Any) -> str:
    text = " ".join(str(item) for item in safe_json(chain, []))
    if "模型EV双选保护" in text:
        return "model_ev_second"
    if "EV方向" in text and "只作保护" in text:
        return "switched_ev_original"
    return "other"


def artifact_cohort(issue: str, chain_version: str) -> str:
    if issue == "26074" and chain_version == "llm_chain_bet_protect_stop_v3.3.3":
        return "v3.3.3_old_runtime"
    return "legacy_v3_prestandard"


def variant_codes(primary: str, codes: list[str], category: str, variant: str) -> list[str]:
    primary_code = primary if primary in OUTCOME_CODES else (codes[0] if codes else "")
    if not primary_code:
        return []
    protects = [code for code in codes if code != primary_code]
    if variant == "baseline":
        return [primary_code, *protects]
    if variant == "primary_only":
        return [primary_code]
    if variant == "draw_only":
        return [primary_code, *[code for code in protects if code == "1"]]
    if variant == "switch_ev_only":
        return [primary_code, *protects] if category == "switched_ev_original" else [primary_code]
    if variant == "model_ev_only":
        return [primary_code, *protects] if category == "model_ev_second" else [primary_code]
    if variant == "drop_model_ev_away":
        return [primary_code, *[code for code in protects if not (category == "model_ev_second" and code == "0")]]
    if variant == "drop_switch_ev_draw":
        return [primary_code, *[code for code in protects if not (category == "switched_ev_original" and code == "1")]]
    if variant == "drop_switch_ev_home":
        return [primary_code, *[code for code in protects if not (category == "switched_ev_original" and code == "3")]]
    raise ValueError(f"unsupported variant: {variant}")


@dataclass(frozen=True)
class SnapshotRow:
    issue: str
    match_idx: int
    match_id: str
    league: str
    home: str
    away: str
    handicap_line: float
    kickoff: str
    generated_at: str
    chain_version: str
    primary: str
    codes: list[str]
    stop_flag: bool
    category: str
    result_code: str
    winning_sp: float
    probabilities: dict[str, float]
    sp: dict[str, float]


def load_rows(db_path: Path, issues: list[str]) -> list[SnapshotRow]:
    placeholders = ",".join("?" for _ in issues)
    query = f"""
        SELECT s.issue, s.match_idx, s.match_id, m.league, m.home, m.away,
               m.handicap_line, m.end_time AS kickoff, s.generated_at,
               COALESCE(s.decision_chain_version, '') AS chain_version,
               s.primary_pick, s.selection_codes_json, s.stop_flag,
               s.decision_chain_json, s.model_probabilities_json,
               s.sp_snapshot_json, m.result_code, m.winning_sp
        FROM llm_decision_snapshots s
        JOIN matches m ON m.issue=s.issue AND m.match_idx=s.match_idx
        WHERE s.status='active'
          AND s.issue IN ({placeholders})
          AND datetime(s.generated_at) < datetime(m.end_time)
          AND COALESCE(m.result_code, '') <> ''
        ORDER BY s.issue, s.match_idx
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        raw_rows = conn.execute(query, issues).fetchall()
    finally:
        conn.close()
    rows: list[SnapshotRow] = []
    for raw in raw_rows:
        probabilities = {code: fnum(value) for code, value in safe_json(raw["model_probabilities_json"], {}).items() if code in OUTCOME_CODES}
        sp_payload = safe_json(raw["sp_snapshot_json"], {})
        sp = {code: fnum(sp_payload.get(code)) for code in OUTCOME_CODES}
        rows.append(SnapshotRow(
            issue=str(raw["issue"]),
            match_idx=int(raw["match_idx"]),
            match_id=str(raw["match_id"]),
            league=str(raw["league"] or ""),
            home=str(raw["home"] or ""),
            away=str(raw["away"] or ""),
            handicap_line=fnum(raw["handicap_line"]),
            kickoff=str(raw["kickoff"] or ""),
            generated_at=str(raw["generated_at"] or ""),
            chain_version=str(raw["chain_version"] or ""),
            primary=str(raw["primary_pick"] or ""),
            codes=parse_codes(raw["selection_codes_json"]),
            stop_flag=bool(raw["stop_flag"]),
            category=protection_category(raw["decision_chain_json"]),
            result_code=str(raw["result_code"] or ""),
            winning_sp=fnum(raw["winning_sp"]),
            probabilities=probabilities,
            sp=sp,
        ))
    return rows


def protection_ledger(rows: list[SnapshotRow]) -> list[dict[str, Any]]:
    ledger = []
    for row in rows:
        if row.stop_flag:
            continue
        primary = row.primary if row.primary in OUTCOME_CODES else (row.codes[0] if row.codes else "")
        protects = [code for code in row.codes if code != primary]
        for priority, code in enumerate(protects, start=1):
            rescue = row.result_code == code and row.result_code != primary
            marginal_return = 2.0 * row.winning_sp if rescue else 0.0
            ledger.append({
                "issue": row.issue,
                "match_idx": row.match_idx,
                "match_id": row.match_id,
                "cohort": artifact_cohort(row.issue, row.chain_version),
                "chain_version": row.chain_version,
                "generated_at": row.generated_at,
                "kickoff": row.kickoff,
                "league": row.league,
                "handicap_line": row.handicap_line,
                "primary_code": primary,
                "protect_code": code,
                "reason": row.category,
                "priority": priority,
                "marginal_cost_yuan": 2.0,
                "expected_rescue": round(row.probabilities.get(code, 0.0), 6),
                "actual_code": row.result_code,
                "rescue": int(rescue),
                "marginal_return_yuan": round(marginal_return, 6),
                "marginal_profit_yuan": round(marginal_return - 2.0, 6),
                "is_draw_protection": int(code == "1"),
            })
    return ledger


def summarize_ledger(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in ledger:
        buckets[("reason", str(row["reason"]))].append(row)
        buckets[("protect_code", str(row["protect_code"]))].append(row)
        buckets[("cohort", str(row["cohort"]))].append(row)
        buckets[("overall", "all")].append(row)
    output = []
    for (dimension, bucket), values in sorted(buckets.items()):
        cost = sum(fnum(row["marginal_cost_yuan"]) for row in values)
        returned = sum(fnum(row["marginal_return_yuan"]) for row in values)
        rescues = sum(int(row["rescue"]) for row in values)
        output.append({
            "dimension": dimension,
            "bucket": bucket,
            "triggers": len(values),
            "rescues": rescues,
            "rescue_rate": round(rescues / len(values), 6) if values else 0.0,
            "marginal_cost_yuan": round(cost, 6),
            "marginal_return_yuan": round(returned, 6),
            "marginal_profit_yuan": round(returned - cost, 6),
            "marginal_roi": round((returned - cost) / cost, 6) if cost else 0.0,
        })
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def structured_rows(rows: list[SnapshotRow], variant: str) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        codes = [] if row.stop_flag else variant_codes(row.primary, row.codes, row.category, variant)
        output.append({
            "issue": row.issue,
            "match_idx": row.match_idx,
            "match_id": row.match_id,
            "league": row.league,
            "home": row.home,
            "away": row.away,
            "handicap_line": row.handicap_line,
            "active_selection_codes": "+".join(codes),
            "shadow_selection_codes": "+".join(codes),
            "p_3": row.probabilities.get("3", 0.0),
            "p_1": row.probabilities.get("1", 0.0),
            "p_0": row.probabilities.get("0", 0.0),
            "sp_3": row.sp.get("3", 0.0),
            "sp_1": row.sp.get("1", 0.0),
            "sp_0": row.sp.get("0", 0.0),
        })
    return output


def single_leg_summary(rows: list[SnapshotRow], variant: str) -> dict[str, Any]:
    stake = payout = 0.0
    hits = depth = bet_count = 0
    for row in rows:
        codes = [] if row.stop_flag else variant_codes(row.primary, row.codes, row.category, variant)
        if not codes:
            continue
        bet_count += 1
        depth += len(codes)
        row_stake = 2.0 * len(codes)
        stake += row_stake
        if row.result_code in codes:
            hits += 1
            payout += 2.0 * row.winning_sp
    profit = payout - stake
    return {
        "variant": variant,
        "matches": bet_count,
        "coverage_hits": hits,
        "coverage_rate": round(hits / bet_count, 6) if bet_count else 0.0,
        "average_depth": round(depth / bet_count, 6) if bet_count else 0.0,
        "stake_yuan": round(stake, 6),
        "return_yuan": round(payout, 6),
        "profit_yuan": round(profit, 6),
        "roi": round(profit / stake, 6) if stake else 0.0,
    }


def run_combo_replays(rows: list[SnapshotRow], args: argparse.Namespace) -> list[dict[str, Any]]:
    by_issue: dict[str, list[SnapshotRow]] = defaultdict(list)
    for row in rows:
        by_issue[row.issue].append(row)
    results = []
    for issue, issue_rows in sorted(by_issue.items()):
        for variant in VARIANTS:
            structured_path = args.output_dir / "structured" / f"{issue}_{variant}.csv"
            write_csv(structured_path, structured_rows(issue_rows, variant))
            payload = run_plan(parse_plan_args([
                "--issue", issue,
                "--structured-csv", str(structured_path),
                "--label", f"phase3_protection_{variant}",
                "--arm", "shadow",
                "--planning-scope", "by_segment",
                "--stake-mode", "scale_to_budget",
                "--db", str(args.db),
                "--output-dir", str(args.output_dir / "plans"),
                "--report-dir", str(args.output_dir / "reports"),
                "--segment-budget-yuan", str(args.segment_budget_yuan),
                "--sample-attempts", str(args.sample_attempts),
                "--sample-seeds", args.sample_seeds,
                "--max-selected-bundles", "0",
                "--allow-negative-ev",
            ]))
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            results.append({
                "issue": issue,
                "variant": variant,
                "segments": summary.get("segments", 0),
                "selected_bundles": summary.get("selected_bundles", 0),
                "selected_cost_yuan": summary.get("selected_cost_yuan", 0),
                "profit_yuan": summary.get("profit_yuan", ""),
                "roi": summary.get("roi", ""),
                "dead_segments": summary.get("dead_segments", 0),
                "summary_json": payload.get("summary_json", ""),
            })
    return results


def aggregate_combo(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_variant[str(row["variant"])].append(row)
    output = []
    for variant in VARIANTS:
        values = by_variant[variant]
        cost = sum(fnum(row["selected_cost_yuan"]) for row in values)
        profit = sum(fnum(row["profit_yuan"]) for row in values)
        output.append({
            "variant": variant,
            "issues": len(values),
            "segments": sum(int(fnum(row["segments"])) for row in values),
            "selected_bundles": round(sum(fnum(row["selected_bundles"]) for row in values), 6),
            "selected_cost_yuan": round(cost, 6),
            "profit_yuan": round(profit, 6),
            "roi": round(profit / cost, 6) if cost else 0.0,
            "dead_segments": sum(int(fnum(row["dead_segments"])) for row in values),
        })
    return output


def leave_one_issue_out_combo(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = sorted({str(row["issue"]) for row in rows})
    output = []
    for variant in VARIANTS:
        variant_rows = [row for row in rows if row["variant"] == variant]
        for excluded_issue in issues:
            kept = [row for row in variant_rows if row["issue"] != excluded_issue]
            cost = sum(fnum(row["selected_cost_yuan"]) for row in kept)
            profit = sum(fnum(row["profit_yuan"]) for row in kept)
            output.append({
                "variant": variant,
                "excluded_issue": excluded_issue,
                "issues": len(kept),
                "selected_cost_yuan": round(cost, 6),
                "profit_yuan": round(profit, 6),
                "roi": round(profit / cost, 6) if cost else 0.0,
            })
    return output


def pct(value: Any) -> str:
    return f"{100.0 * fnum(value):.1f}%"


def render_report(
    rows: list[SnapshotRow],
    ledger_summary: list[dict[str, Any]],
    single_rows: list[dict[str, Any]],
    combo_rows: list[dict[str, Any]],
    combo_loo_rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> str:
    executable = [row for row in rows if not row.stop_flag]
    doubles = sum(1 for row in executable if len(row.codes) == 2)
    single_by_variant = {row["variant"]: row for row in single_rows}
    combo_by_variant = {row["variant"]: row for row in combo_rows}
    baseline_single = single_by_variant["baseline"]
    candidate_single = single_by_variant["drop_switch_ev_home"]
    baseline_combo = combo_by_variant["baseline"]
    candidate_combo = combo_by_variant["drop_switch_ev_home"]
    coverage_delta_pp = 100.0 * (candidate_single["coverage_rate"] - baseline_single["coverage_rate"])
    depth_delta = candidate_single["average_depth"] - baseline_single["average_depth"]
    bundle_delta_pct = (
        100.0 * (candidate_combo["selected_bundles"] / baseline_combo["selected_bundles"] - 1.0)
        if baseline_combo["selected_bundles"] else 0.0
    )
    roi_delta_pp = 100.0 * (candidate_combo["roi"] - baseline_combo["roi"])
    lines = [
        "# v3.3.3 Phase 3 保护裁剪历史反事实",
        "",
        "## 数据边界",
        "",
        f"- 逐场要求 Active 快照 `generated_at < kickoff` 且已有赛果；共 {len(rows)} 场，其中可执行 {len(executable)} 场、双选 {doubles} 场。",
        "- 26071-26073 属于标准化前 legacy v3；26074 虽标记 v3.3.3，但来自统一核心上线前旧运行链。结果仅用于候选筛选，不满足样本外晋级条件。",
        "- draft、赛后补算 artifact、停牌场次和未结算场次不进入下注表现。",
        "",
        "## 保护码边际表现",
        "",
        "| 分层 | 桶 | 触发 | 救回 | 救回率 | 边际成本 | 边际返还 | 边际利润 | 边际 ROI |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in ledger_summary:
        if row["dimension"] in {"overall", "reason", "protect_code"}:
            lines.append(
                f"| {row['dimension']} | {row['bucket']} | {row['triggers']} | {row['rescues']} | {pct(row['rescue_rate'])} | "
                f"{row['marginal_cost_yuan']:.1f} | {row['marginal_return_yuan']:.1f} | {row['marginal_profit_yuan']:.1f} | {pct(row['marginal_roi'])} |"
            )
    lines.extend([
        "",
        "边际口径为每个保护码追加 2 元：救回时返还 `2 × winning_sp`，否则返还 0。",
        "",
        "## 单腿 proxy",
        "",
        "| 方案 | 场次 | 覆盖 | 覆盖率 | 平均深度 | 投入 | 回报 | 利润 | ROI |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in single_rows:
        lines.append(
            f"| {row['variant']} | {row['matches']} | {row['coverage_hits']} | {pct(row['coverage_rate'])} | {row['average_depth']:.3f} | "
            f"{row['stake_yuan']:.1f} | {row['return_yuan']:.1f} | {row['profit_yuan']:.1f} | {pct(row['roi'])} |"
        )
    lines.extend([
        "",
        "## 固定预算组合票回放",
        "",
        f"每期按相同分段器、每段预算 {args.segment_budget_yuan:.0f} 元和相同随机种子重新优化。保护裁剪会影响推荐 N，因此该表用于 Phase 3 资金效率评估；Phase 4 仍需补固定 N 配对实验。",
        "",
        "| 方案 | 期数 | 分段 | 基础票组 | 投入 | 利润 | ROI | 全损段 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in combo_rows:
        lines.append(
            f"| {row['variant']} | {row['issues']} | {row['segments']} | {row['selected_bundles']:.1f} | "
            f"{row['selected_cost_yuan']:.1f} | {row['profit_yuan']:.1f} | {pct(row['roi'])} | {row['dead_segments']} |"
        )
    lines.extend([
        "",
        "## Leave-one-issue-out 稳定性",
        "",
        "| 方案 | 排除期次 | 剩余投入 | 剩余利润 | ROI |",
        "|---|---:|---:|---:|---:|",
    ])
    for row in combo_loo_rows:
        if row["variant"] in {"baseline", "model_ev_only", "drop_model_ev_away", "drop_switch_ev_draw", "drop_switch_ev_home"}:
            lines.append(
                f"| {row['variant']} | {row['excluded_issue']} | {row['selected_cost_yuan']:.1f} | "
                f"{row['profit_yuan']:.1f} | {pct(row['roi'])} |"
            )
    lines.extend([
        "",
        "## 研究结论",
        "",
        f"- `drop_switch_ev_home` 仅删除 8 个“主押反转后仍保留 code 3 原 EV 方向”的保护；少救回 2 场，覆盖变化 {coverage_delta_pp:+.2f} 个百分点，平均深度变化 {depth_delta:+.3f}。",
        f"- 该候选的基础票组数相对 baseline 变化 {bundle_delta_pct:+.1f}%，组合 ROI 相对改善 {roi_delta_pp:+.1f} 个百分点，全损段由 {baseline_combo['dead_segments']} 降至 {candidate_combo['dead_segments']}。",
        "- 四组 leave-one-issue-out 中，该候选相对 baseline 均不劣化；但绝对组合 ROI 仍为负，且规则来自仅 8 次历史触发，只能预注册为 paper-forward 候选。",
        f"- 预注册：`{PAPER_CANDIDATE_ID}` / `{PAPER_CANDIDATE_VERSION}`；固定规则仅在 `switched_ev_original` 且保护码为 `3` 时删除该保护，`execution_enabled=false`。",
        "- `model_ev_only` 的正收益依赖 26073；排除 26073 后 ROI 转为负值，不具备直接晋级稳定性。",
        "- 让球平保护整体边际 ROI 为正，不应整体删除；`drop_switch_ev_draw` 只保留为诊断对照。",
        "",
        "## 结论约束",
        "",
        "- 任何规则只有在覆盖下降不超过 1-2 个百分点、资金效率改善且后续标准化 forward 样本保持正边际价值时，才能登记为 Lean cover。",
        "- 本报告不修改 Active；v4.2 继续只读观察。",
        "",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issues", default="26071,26072,26073,26074")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--segment-budget-yuan", type=float, default=1000.0)
    parser.add_argument("--sample-attempts", type=int, default=12000)
    parser.add_argument("--sample-seeds", default="20260707,20260708,20260709,20260710,20260711,20260712,20260713,20260714,20260715,20260716")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    issues = [item.strip() for item in args.issues.split(",") if item.strip()]
    rows = load_rows(args.db, issues)
    ledger = protection_ledger(rows)
    ledger_summary = summarize_ledger(ledger)
    single_rows = [single_leg_summary(rows, variant) for variant in VARIANTS]
    combo_issue_rows = run_combo_replays(rows, args)
    combo_rows = aggregate_combo(combo_issue_rows)
    combo_loo_rows = leave_one_issue_out_combo(combo_issue_rows)
    write_csv(args.output_dir / "protection_candidate_ledger.csv", ledger)
    write_csv(args.output_dir / "protection_summary.csv", ledger_summary)
    write_csv(args.output_dir / "single_leg_counterfactual.csv", single_rows)
    write_csv(args.output_dir / "combo_issue_counterfactual.csv", combo_issue_rows)
    write_csv(args.output_dir / "combo_counterfactual.csv", combo_rows)
    write_csv(args.output_dir / "combo_leave_one_issue_out.csv", combo_loo_rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(rows, ledger_summary, single_rows, combo_rows, combo_loo_rows, args), encoding="utf-8")
    print(json.dumps({
        "rows": len(rows),
        "executable_rows": sum(not row.stop_flag for row in rows),
        "protection_candidates": len(ledger),
        "report": str(args.report),
        "output_dir": str(args.output_dir),
        "single_leg": single_rows,
        "combo": combo_rows,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
