#!/usr/bin/env python3
"""Evaluate v3.3.3 primary-only reorder candidates on frozen selections."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from evaluate_structured_decision_chain_shadow import (  # noqa: E402
    OUTCOME_LABEL,
    OUTCOME_ORDER,
    result_rows,
    safe_float,
    structured_decision_for_payload,
)


DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_REPORT = PROJECT_ROOT / "docs/research/v3_3_3_phase2_primary_optimization_2026-07-11.md"
DEFAULT_CSV = PROJECT_ROOT / "docs/research/v3_3_3_phase2_primary_optimization_2026-07-11.csv"
DEFAULT_DEV_ISSUES = ("26071", "26072")
DEFAULT_VALIDATION_ISSUES = ("26073", "26074")
DRAW_GAPS = (0.02, 0.04, 0.06)


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
    raw = value if isinstance(value, list) else str(value or "").replace(",", "+").replace("/", "+").split("+")
    out: list[str] = []
    for value in raw:
        code = str(value).strip()
        if code in OUTCOME_ORDER and code not in out:
            out.append(code)
    return out


def probabilities(payload: dict[str, Any]) -> dict[str, float]:
    return {
        str(row.get("code")): float(safe_float(row.get("probability")) or 0.0)
        for row in result_rows(payload)
        if str(row.get("code")) in OUTCOME_ORDER
    }


def q_values(payload: dict[str, Any]) -> dict[str, float]:
    return {
        str(row.get("code")): float(safe_float(row.get("q")) or 0.0)
        for row in result_rows(payload)
        if str(row.get("code")) in OUTCOME_ORDER
    }


def load_rows(conn: sqlite3.Connection, issues: list[str]) -> list[ReplayRow]:
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in issues)
    rows = conn.execute(
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
          AND m.result_code IS NOT NULL
          AND m.winning_sp IS NOT NULL
          AND datetime(s.generated_at) <= datetime(m.end_time)
        ORDER BY s.issue, s.match_idx
        """,
        issues,
    ).fetchall()
    out: list[ReplayRow] = []
    for row in rows:
        try:
            payload = json.loads(row["input_payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        out.append(
            ReplayRow(
                issue=str(row["issue"]),
                match_idx=int(row["match_idx"]),
                match_id=str(row["match_id"] or ""),
                league=str(row["league"] or ""),
                home=str(row["home"] or ""),
                away=str(row["away"] or ""),
                handicap_line=float(safe_float(row["handicap_line"]) or 0.0),
                kickoff_at=str(row["end_time"] or ""),
                generated_at=str(row["generated_at"] or ""),
                result_code=str(row["result_code"]),
                winning_sp=float(row["winning_sp"]),
                payload=payload,
            )
        )
    return out


def top_within(scores: dict[str, float], codes: list[str]) -> str:
    return max(codes, key=lambda code: (scores.get(code, 0.0), -OUTCOME_ORDER.index(code))) if codes else ""


def ablation_scores(
    decision: dict[str, Any],
    probs: dict[str, float],
    *,
    include_fit: bool,
    include_form: bool,
) -> dict[str, float]:
    scores = {code: probs.get(code, 0.0) * 2.0 for code in OUTCOME_ORDER}
    sections = decision.get("sections", {}) if isinstance(decision.get("sections"), dict) else {}
    if include_fit:
        fit = sections.get("handicap_fit", {}) if isinstance(sections.get("handicap_fit"), dict) else {}
        code = str(fit.get("code") or "")
        if code in scores:
            scores[code] += float(safe_float(fit.get("score")) or 0.0) * 0.9
    if include_form:
        form = sections.get("form_recent", {}) if isinstance(sections.get("form_recent"), dict) else {}
        code = str(form.get("code") or "")
        if code in scores:
            scores[code] += float(safe_float(form.get("score")) or 0.0) * 0.35
    context = sections.get("competition_context", {}) if isinstance(sections.get("competition_context"), dict) else {}
    tags = context.get("tags") if isinstance(context.get("tags"), list) else []
    if "knockout" in tags and probs.get("1", 0.0) >= 0.26:
        scores["1"] += 0.10
    return scores


def candidate_primaries(row: ReplayRow, decision: dict[str, Any], codes: list[str]) -> dict[str, str]:
    probs = probabilities(row.payload)
    qs = q_values(row.payload)
    experiment = (
        decision.get("primary_experiments", {}).get("phase2_probability_first_within_coverage", {})
        if isinstance(decision.get("primary_experiments"), dict)
        else {}
    )
    probability_primary = str(experiment.get("primary_pick") or top_within(probs, codes))
    handicap_gated = (
        decision.get("primary_experiments", {}).get("phase2_handicap_gated_probability_first", {})
        if isinstance(decision.get("primary_experiments"), dict)
        else {}
    )
    candidates = {
        "baseline_v3.3.3": str(decision.get("primary_pick") or (codes[0] if codes else "")),
        "probability_first": probability_primary,
        "handicap_gated_probability_first": str(handicap_gated.get("primary_pick") or decision.get("primary_pick") or ""),
        "q_first_diagnostic": top_within(qs, codes),
        "no_recent_form": top_within(ablation_scores(decision, probs, include_fit=True, include_form=False), codes),
        "no_handicap_fit": top_within(ablation_scores(decision, probs, include_fit=False, include_form=True), codes),
    }
    for gap in DRAW_GAPS:
        primary = probability_primary
        if (
            "1" in codes
            and abs(row.handicap_line) == 1.0
            and probs.get(primary, 0.0) - probs.get("1", 0.0) <= gap + 1e-12
        ):
            primary = "1"
        candidates[f"draw_aware_gap_{gap:.2f}"] = primary
    return candidates


def primary_grade(primary: str, probs: dict[str, float]) -> str:
    ranked = sorted(probs.values(), reverse=True)
    margin = probs.get(primary, 0.0) - (ranked[1] if len(ranked) > 1 else 0.0)
    if probs.get(primary, 0.0) >= 0.42 and margin >= 0.06:
        return "A"
    if probs.get(primary, 0.0) >= 0.36 and margin >= 0.02:
        return "B"
    return "C"


def handicap_bucket(value: float) -> str:
    if value <= -2.0:
        return "home_gives_2plus"
    if value == -1.0:
        return "home_gives_1"
    if value == 0.0:
        return "level"
    if value == 1.0:
        return "home_gets_1"
    if value >= 2.0:
        return "home_gets_2plus"
    return "other"


def evaluate(rows: list[ReplayRow], dev_issues: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        decision = structured_decision_for_payload(row.payload)
        codes = parse_codes(decision.get("selection_codes"))
        if not codes:
            continue
        probs = probabilities(row.payload)
        sections = decision.get("sections", {}) if isinstance(decision.get("sections"), dict) else {}
        fit = sections.get("handicap_fit", {}) if isinstance(sections.get("handicap_fit"), dict) else {}
        form = sections.get("form_recent", {}) if isinstance(sections.get("form_recent"), dict) else {}
        intelligence = row.payload.get("intelligence", {}) if isinstance(row.payload.get("intelligence"), dict) else {}
        coverage_hit = int(row.result_code in codes)
        coverage_profit = row.winning_sp - len(codes) if coverage_hit else -float(len(codes))
        for arm, primary in candidate_primaries(row, decision, codes).items():
            ordered_codes = [primary, *[code for code in codes if code != primary]]
            hit = int(primary == row.result_code)
            p_primary = probs.get(primary, 0.0)
            records.append(
                {
                    "segment": "development" if row.issue in dev_issues else "validation",
                    "arm": arm,
                    "issue": row.issue,
                    "match_idx": row.match_idx,
                    "match_id": row.match_id,
                    "league": row.league,
                    "intelligence_status": str(intelligence.get("status") or "missing"),
                    "handicap_bucket": handicap_bucket(row.handicap_line),
                    "handicap_fit_code": str(fit.get("code") or ""),
                    "form_recent_code": str(form.get("code") or ""),
                    "home": row.home,
                    "away": row.away,
                    "handicap_line": row.handicap_line,
                    "kickoff_at": row.kickoff_at,
                    "generated_at": row.generated_at,
                    "result_code": row.result_code,
                    "winning_sp": row.winning_sp,
                    "baseline_codes": "+".join(codes),
                    "selection_codes": "+".join(ordered_codes),
                    "selection_set": "+".join(sorted(codes)),
                    "depth": len(codes),
                    "primary": primary,
                    "primary_probability": p_primary,
                    "primary_hit": hit,
                    "primary_profit": row.winning_sp - 1.0 if hit else -1.0,
                    "primary_binary_brier": (p_primary - hit) ** 2,
                    "multiclass_brier": sum(
                        (probs.get(code, 0.0) - int(code == row.result_code)) ** 2
                        for code in OUTCOME_ORDER
                    ),
                    "grade": primary_grade(primary, probs),
                    "coverage_hit": coverage_hit,
                    "coverage_profit": coverage_profit,
                }
            )
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    return {
        "n": n,
        "primary_hits": sum(int(row["primary_hit"]) for row in records),
        "primary_hit_rate": sum(int(row["primary_hit"]) for row in records) / n if n else 0.0,
        "primary_profit": sum(float(row["primary_profit"]) for row in records),
        "primary_binary_brier": sum(float(row["primary_binary_brier"]) for row in records) / n if n else 0.0,
        "multiclass_brier": sum(float(row["multiclass_brier"]) for row in records) / n if n else 0.0,
        "coverage_hit_rate": sum(int(row["coverage_hit"]) for row in records) / n if n else 0.0,
        "coverage_profit": sum(float(row["coverage_profit"]) for row in records),
        "avg_depth": sum(int(row["depth"]) for row in records) / n if n else 0.0,
    }


def group_summary(records: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[tuple(str(row[key]) for key in keys)].append(row)
    out = []
    for values, group in sorted(grouped.items()):
        out.append({**dict(zip(keys, values)), **summarize(group)})
    return out


def choose_candidate(records: list[dict[str, Any]]) -> str:
    excluded = {"baseline_v3.3.3", "q_first_diagnostic"}
    complexity = {
        "probability_first": 0,
        "handicap_gated_probability_first": 1,
        "no_handicap_fit": 1,
        "no_recent_form": 1,
        "draw_aware_gap_0.02": 2,
        "draw_aware_gap_0.04": 3,
        "draw_aware_gap_0.06": 4,
    }
    summaries = [
        row for row in group_summary([r for r in records if r["segment"] == "development"], ("arm",))
        if row["arm"] not in excluded
    ]
    return str(
        max(
            summaries,
            key=lambda row: (
                row["primary_hit_rate"],
                -complexity.get(str(row["arm"]), 99),
                -row["primary_binary_brier"],
            ),
        )["arm"]
    )


def fmt_pct(value: float) -> str:
    return f"{value:.1%}"


def md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    lines = ["| " + " | ".join(label for label, _ in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(key, "")).replace("|", "/") for _, key in columns) + " |")
    return "\n".join(lines)


def render_report(records: list[dict[str, Any]], candidate: str, dev_issues: list[str], validation_issues: list[str]) -> str:
    summaries = group_summary(records, ("segment", "arm"))
    baseline_by_segment = {
        row["segment"]: row for row in summaries if row["arm"] == "baseline_v3.3.3"
    }
    summary_rows = []
    for row in summaries:
        baseline = baseline_by_segment[row["segment"]]
        summary_rows.append(
            {
                "segment": row["segment"],
                "arm": row["arm"],
                "n": row["n"],
                "primary": fmt_pct(row["primary_hit_rate"]),
                "delta": f"{(row['primary_hit_rate'] - baseline['primary_hit_rate']) * 100:+.1f}pp",
                "brier": f"{row['primary_binary_brier']:.4f}",
                "primary_profit": f"{row['primary_profit']:.2f}",
                "coverage": fmt_pct(row["coverage_hit_rate"]),
                "depth": f"{row['avg_depth']:.3f}",
            }
        )
    candidate_records = [row for row in records if row["arm"] == candidate]
    grade_rows = []
    for row in group_summary(candidate_records, ("segment", "grade")):
        grade_rows.append(
            {
                "segment": row["segment"],
                "grade": row["grade"],
                "n": row["n"],
                "hit": fmt_pct(row["primary_hit_rate"]),
                "brier": f"{row['primary_binary_brier']:.4f}",
                "profit": f"{row['primary_profit']:.2f}",
            }
        )
    issue_rows = []
    for row in group_summary([r for r in records if r["arm"] in {"baseline_v3.3.3", candidate}], ("issue", "arm")):
        issue_rows.append(
            {
                "issue": row["issue"],
                "arm": row["arm"],
                "n": row["n"],
                "primary": fmt_pct(row["primary_hit_rate"]),
                "brier": f"{row['primary_binary_brier']:.4f}",
                "profit": f"{row['primary_profit']:.2f}",
            }
        )
    switches = []
    baseline = {(r["issue"], r["match_idx"]): r for r in records if r["arm"] == "baseline_v3.3.3"}
    for row in candidate_records:
        base = baseline[(row["issue"], row["match_idx"])]
        if base["primary"] == row["primary"]:
            continue
        switches.append(
            {
                "segment": row["segment"],
                "issue": row["issue"],
                "#": row["match_idx"],
                "match": f"{row['home']} vs {row['away']}",
                "result": OUTCOME_LABEL.get(row["result_code"], row["result_code"]),
                "coverage": row["baseline_codes"],
                "old": base["primary"],
                "new": row["primary"],
                "old_hit": base["primary_hit"],
                "new_hit": row["primary_hit"],
                "fit": row["handicap_fit_code"] or "-",
                "form": row["form_recent_code"] or "-",
            }
        )
    strata_rows = []
    for dimension in ("handicap_bucket", "intelligence_status", "league"):
        candidate_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        baseline_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in records:
            key = (str(row["segment"]), str(row[dimension]))
            if row["arm"] == candidate:
                candidate_groups[key].append(row)
            elif row["arm"] == "baseline_v3.3.3":
                baseline_groups[key].append(row)
        for key, candidate_group in sorted(candidate_groups.items()):
            baseline_group = baseline_groups.get(key, [])
            if not baseline_group or (dimension == "league" and len(candidate_group) < 3):
                continue
            candidate_summary = summarize(candidate_group)
            baseline_summary = summarize(baseline_group)
            strata_rows.append(
                {
                    "segment": key[0],
                    "dimension": dimension,
                    "value": key[1],
                    "n": len(candidate_group),
                    "baseline": fmt_pct(baseline_summary["primary_hit_rate"]),
                    "candidate": fmt_pct(candidate_summary["primary_hit_rate"]),
                    "delta": f"{(candidate_summary['primary_hit_rate'] - baseline_summary['primary_hit_rate']) * 100:+.1f}pp",
                }
            )
    candidate_dev = summarize([r for r in candidate_records if r["segment"] == "development"])
    candidate_val = summarize([r for r in candidate_records if r["segment"] == "validation"])
    base_dev = summarize([r for r in records if r["segment"] == "development" and r["arm"] == "baseline_v3.3.3"])
    base_val = summarize([r for r in records if r["segment"] == "validation" and r["arm"] == "baseline_v3.3.3"])
    val_delta = candidate_val["primary_hit_rate"] - base_val["primary_hit_rate"]
    dev_delta = candidate_dev["primary_hit_rate"] - base_dev["primary_hit_rate"]
    status = "paper-shadow candidate" if dev_delta >= 0.02 and val_delta >= 0.02 else "not eligible"
    return f"""# v3.3.3 Phase 2 主押优化实验

日期：2026-07-11  
状态：{status}  
开发段：{', '.join(dev_issues)}  
后段验证：{', '.join(validation_issues)}

## 边界

- 仅使用 `active` snapshot 且 `generated_at <= kickoff_at`、已有赛果和真实结算 SP 的行。
- 每个候选逐行冻结 v3.3.3 的选择集合；只允许调整第一主押码，覆盖深度、覆盖命中和组合成本不变。
- 26071-26074 已被反复分析，本报告属于诊断/后段验证，不是最终未见样本。正式晋级仍需至少 300 场历史滚动验证和 5 期或 500 场 paper-forward。
- q-first 只作为消融诊断，不参与候选选择。多分类 Brier 使用同一概率向量，理论上各 arm 完全相同。
- `handicap_gated_probability_first` 是查看首轮盘口分层后派生的 v0.2 规则；development 结果存在选择偏差，只能用于描述，独立 forward 从预注册后的新 artifact 开始。

## 总体比较

{md_table(summary_rows, [('段', 'segment'), ('arm', 'arm'), ('n', 'n'), ('主押命中', 'primary'), ('相对基线', 'delta'), ('主押 Brier', 'brier'), ('主押 profit', 'primary_profit'), ('覆盖命中', 'coverage'), ('均深', 'depth')])}

开发段自动选择的候选为 `{candidate}`。开发段相对基线 {dev_delta * 100:+.1f}pp，后段验证 {val_delta * 100:+.1f}pp；当前判断：**{status}**。

## 分期对照

{md_table(issue_rows, [('期号', 'issue'), ('arm', 'arm'), ('n', 'n'), ('主押命中', 'primary'), ('Brier', 'brier'), ('主押 profit', 'profit')])}

## A/B/C 主押等级

等级只使用决策时点主押概率和概率间距：A 为高概率且明显领先，B 为中等强度，其他为 C。

{md_table(grade_rows, [('段', 'segment'), ('等级', 'grade'), ('n', 'n'), ('命中', 'hit'), ('Brier', 'brier'), ('主押 profit', 'profit')])}

## 分层稳定性

联赛仅显示样本数不少于 3 的分组；小分组只用于定位，不作为规则依据。

{md_table(strata_rows, [('段', 'segment'), ('维度', 'dimension'), ('分组', 'value'), ('n', 'n'), ('基线', 'baseline'), ('候选', 'candidate'), ('差值', 'delta')])}

## 候选切换明细

{md_table(switches, [('段', 'segment'), ('期号', 'issue'), ('#', '#'), ('比赛', 'match'), ('赛果', 'result'), ('冻结覆盖', 'coverage'), ('旧押', 'old'), ('新押', 'new'), ('旧中', 'old_hit'), ('新中', 'new_hit'), ('fit', 'fit'), ('form', 'form')]) if switches else '无主押切换。'}

## 结论

- 覆盖集合和成本 invariant 由测试与逐行审计保证，因此覆盖率、平均深度及覆盖 profit 不因主押候选变化。
- 当前样本不足 Phase 2 晋级门槛；即使后段改善，也只能发布为新的 paper shadow，不能修改 `active_v3.3.3`。
- v0.2 的历史开发段优势不是样本外证据，不得与预注册后的 forward 样本合并宣称提升。
- 后续重点是扩大严格开赛前 snapshot 样本，并验证 A/B/C 命中是否单调；不单独因本报告调整资金权重。
"""


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dev-issues", default=",".join(DEFAULT_DEV_ISSUES))
    parser.add_argument("--validation-issues", default=",".join(DEFAULT_VALIDATION_ISSUES))
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    dev_issues = [value.strip() for value in args.dev_issues.split(",") if value.strip()]
    validation_issues = [value.strip() for value in args.validation_issues.split(",") if value.strip()]
    with sqlite3.connect(args.db) as conn:
        rows = load_rows(conn, [*dev_issues, *validation_issues])
    if not rows:
        raise SystemExit("no eligible pre-kickoff settled snapshots")
    records = evaluate(rows, set(dev_issues))
    candidate = choose_candidate(records)
    write_csv(args.csv, records)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(records, candidate, dev_issues, validation_issues), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "records": len(records), "candidate": candidate, "report": str(args.report), "csv": str(args.csv)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
