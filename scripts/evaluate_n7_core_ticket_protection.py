#!/usr/bin/env python3
"""Ticket-level protection on the N7 core inside the fixed 192/64 portfolio.

This script rebuilds protection variants from the actual high-N core selected
tickets instead of reusing earlier same-ticket protection arms, which were based
on a different N7 source.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_high_n_fixed256_diversity import (
    ISSUE_BUDGET,
    annual_rows,
    fnum,
    full_loss,
    load_issue_calendar,
    max_dead_streak,
    max_drawdown_units,
    row_order,
    row_year,
    summarize,
    with_calendar,
    write_equity_svg,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n7_same_ticket_leg_coverage import (
    action_lookup,
    convert_ticket,
    parse_ticket,
    single_rows,
)
from scripts.walkforward_beidan_strategy_eval import (
    default_db_path,
    load_action_rows,
    md_table,
    settle_ticket,
    write_csv,
)


SOURCE_STRATEGY = "ev_m0p95_p0p8_full_opt__budget256_fractional"
CORE_SELECTOR = "topology_neg0_ge6_d0"
N5_OVERLAP_PATH = Path(
    "results/n_dynamic_issue_smoothing_optional_budget256_overlap050_20260628/"
    "n_dynamic_issue_depth_issue_profit.csv"
)
N5_OVERLAP_STRATEGY = "dynamic_static_n5x90__budget256_fractional"
N5_QUALITY_STRATEGY = "dynamic_low5_mid7_high7x30__budget256_fractional"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv_all(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    first_keys = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(first_keys))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=first_keys + extra)
        writer.writeheader()
        writer.writerows(rows)


def load_core_source_rows(path: Path) -> list[dict[str, object]]:
    rows = []
    for row in read_csv_rows(path):
        if row.get("source_strategy") != SOURCE_STRATEGY:
            continue
        if row.get("selector") != CORE_SELECTOR:
            continue
        rows.append(dict(row))
    if not rows:
        raise SystemExit(f"no core selected tickets in {path}")
    return rows


def load_issue_arm(path: Path, strategy: str, arm: str, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for row in read_csv_rows(path):
        if row.get("strategy") != strategy:
            continue
        copied = dict(row)
        copied["arm"] = arm
        out[str(row["issue"])] = copied
    if not out:
        raise SystemExit(f"missing issue arm: {arm} {path} {strategy}")
    return with_calendar(out, calendar)


def protection_score(row: dict[str, object], mode: str) -> float:
    ev = fnum(row.get("pred_ev_per_stake"))
    hit = fnum(row.get("pred_hit_prob"))
    selector_score = fnum(row.get("selector_score"))
    line_net = fnum(row.get("line_gap_support_net"))
    abs_gap = fnum(row.get("avg_abs_line_gap"))
    ll_bad = fnum(row.get("ll_bad_count"))
    if mode == "top_ev":
        return ev
    if mode == "top_score":
        return selector_score
    if mode == "low_hit":
        return -hit
    if mode == "risk":
        return math.log1p(max(ev, 0.0)) * (1.0 - min(max(hit, 0.0), 1.0)) + 0.75 * abs_gap - 0.20 * line_net + 0.50 * ll_bad
    if mode == "linegap_weak":
        return -line_net + 0.50 * abs_gap + 0.35 * ll_bad
    if mode == "linegap_ev_weak":
        return math.log1p(max(ev, 0.0)) - 0.85 * line_net + 0.50 * abs_gap + 0.35 * ll_bad
    if mode == "low_hit_linegap":
        return (1.0 - min(max(hit, 0.0), 1.0)) - 0.65 * line_net + 0.50 * abs_gap + 0.35 * ll_bad
    raise ValueError(f"unknown protection mode: {mode}")


def scaled_settled_row(ticket, source: dict[str, object], strategy: str, source_scale: float, protection_applied: int) -> dict[str, object]:
    raw = settle_ticket(ticket)
    scaled = dict(raw)
    scaled.update(
        {
            "strategy": strategy,
            "source_strategy": source.get("strategy", ""),
            "source_selector": source.get("selector", ""),
            "source_ticket_idx": source.get("ticket_idx", ""),
            "source_pred_ev_per_stake": fnum(source.get("pred_ev_per_stake")),
            "source_pred_hit_prob": fnum(source.get("pred_hit_prob")),
            "source_selector_score": fnum(source.get("selector_score")),
            "source_line_gap_support_net": fnum(source.get("line_gap_support_net")),
            "source_avg_abs_line_gap": fnum(source.get("avg_abs_line_gap")),
            "source_ll_bad_count": fnum(source.get("ll_bad_count")),
            "protection_applied": protection_applied,
            "raw_stake_before_source_weight": raw["stake_units"],
            "source_weight_scale": source_scale,
        }
    )
    for key in ("stake_units", "payout_units", "profit_units"):
        scaled[key] = fnum(raw[key]) * source_scale
    scaled["roi"] = fnum(scaled["profit_units"]) / fnum(scaled["stake_units"]) if fnum(scaled["stake_units"]) else math.nan
    scaled["pred_ev_per_stake"] = fnum(source.get("pred_ev_per_stake"))
    scaled["pred_hit_prob"] = fnum(source.get("pred_hit_prob"))
    return scaled


def build_protected_ticket_rows(
    *,
    source_rows: list[dict[str, object]],
    actions: dict[tuple[int, str], object],
    single: dict[tuple[int, str], object],
    policy: str,
    mode: str,
    protect_count: int,
    snapshot: str,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in source_rows:
        grouped[str(row["issue"])].append(row)

    strategy = f"core_tp_{policy}_{mode}_k{protect_count}"
    only_strategy = f"core_tp_only_{policy}_{mode}_k{protect_count}"
    out: list[dict[str, object]] = []
    for issue, rows in grouped.items():
        ranked = sorted(rows, key=lambda row: protection_score(row, mode), reverse=True)
        protected_ids = {id(row) for row in ranked[:protect_count]}
        for row in rows:
            base_ticket = parse_ticket(row, actions)
            if base_ticket is None:
                continue
            base_raw = settle_ticket(base_ticket)
            source_scale = fnum(row.get("stake_units")) / fnum(base_raw.get("stake_units"), 1.0)
            apply_protection = id(row) in protected_ids
            if apply_protection:
                converted = convert_ticket(
                    base_ticket,
                    strategy=strategy,
                    policy=policy,
                    cover_count=1,
                    single=single,
                    actions=actions,
                    snapshot=snapshot,
                )
                converted_row = scaled_settled_row(converted, row, strategy, source_scale, 1)
                out.append(converted_row)
                only_row = dict(converted_row)
                only_row["strategy"] = only_strategy
                out.append(only_row)
            else:
                base_ticket = type(base_ticket)(
                    strategy=strategy,
                    issue=base_ticket.issue,
                    n_legs=base_ticket.n_legs,
                    ticket_idx=base_ticket.ticket_idx,
                    train_start_issue=base_ticket.train_start_issue,
                    train_end_issue=base_ticket.train_end_issue,
                    legs=base_ticket.legs,
                )
                out.append(scaled_settled_row(base_ticket, row, strategy, source_scale, 0))
    return out


def build_base_ticket_rows(
    *,
    source_rows: list[dict[str, object]],
    actions: dict[tuple[int, str], object],
) -> list[dict[str, object]]:
    out = []
    for row in source_rows:
        ticket = parse_ticket(row, actions)
        if ticket is None:
            continue
        ticket = type(ticket)(
            strategy="core_base",
            issue=ticket.issue,
            n_legs=ticket.n_legs,
            ticket_idx=ticket.ticket_idx,
            train_start_issue=ticket.train_start_issue,
            train_end_issue=ticket.train_end_issue,
            legs=ticket.legs,
        )
        raw = settle_ticket(ticket)
        source_scale = fnum(row.get("stake_units")) / fnum(raw.get("stake_units"), 1.0)
        out.append(scaled_settled_row(ticket, row, "core_base", source_scale, 0))
    return out


def strategy_issue_map(rows: list[dict[str, object]], calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in rows:
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[str(row["strategy"])][str(row["issue"])] = copied
    return dict(out)


def combine_portfolio(
    *,
    portfolio: str,
    issues: list[str],
    arms: dict[str, dict[str, dict[str, object]]],
    allocation: dict[str, float],
    calendar: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    out = []
    for issue in issues:
        profit = 0.0
        tickets = 0.0
        hits = 0.0
        parts = []
        missing_units = 0.0
        for arm, units in allocation.items():
            row = arms.get(arm, {}).get(issue)
            if row is None:
                missing_units += units
                continue
            scale = units / fnum(row.get("stake_units"), ISSUE_BUDGET)
            profit += fnum(row.get("profit_units")) * scale
            tickets += fnum(row.get("tickets")) * scale
            hits += fnum(row.get("hits")) * scale
            parts.append(f"{arm}:{units:g}")
        if missing_units:
            fallback = arms["n5_quality_overlap"].get(issue) or arms["n5_overlap"].get(issue)
            if fallback is None:
                raise SystemExit(f"missing fallback issue {issue}")
            scale = missing_units / fnum(fallback.get("stake_units"), ISSUE_BUDGET)
            profit += fnum(fallback.get("profit_units")) * scale
            tickets += fnum(fallback.get("tickets")) * scale
            hits += fnum(fallback.get("hits")) * scale
            parts.append(f"fallback_n5_quality:{missing_units:g}")
        row = {
            "portfolio": portfolio,
            "issue": issue,
            "stake_units": ISSUE_BUDGET,
            "profit_units": profit,
            "roi": profit / ISSUE_BUDGET,
            "tickets": tickets,
            "hits": hits,
            "parts": ";".join(parts),
            "state": "static",
        }
        row.update(calendar.get(issue, {}))
        out.append(row)
    return out


def ordered_issues(calendar: dict[str, dict[str, object]], arms: dict[str, dict[str, dict[str, object]]]) -> list[str]:
    issues = set(arms["n5_overlap"].keys()) | set(arms["core_base__budget256_fractional"].keys())
    return sorted(issues, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def summarize_protection_rows(ticket_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = defaultdict(list)
    for row in ticket_rows:
        grouped[str(row["strategy"])].append(row)
    out = []
    for strategy, rows in sorted(grouped.items()):
        protected = [row for row in rows if int(fnum(row.get("protection_applied"))) == 1]
        out.append(
            {
                "strategy": strategy,
                "raw_tickets": len(rows),
                "protected_raw_tickets": len(protected),
                "protected_share": len(protected) / len(rows) if rows else math.nan,
                "raw_stake_units": sum(fnum(row.get("stake_units")) for row in rows),
                "raw_profit_units": sum(fnum(row.get("profit_units")) for row in rows),
                "raw_roi": (
                    sum(fnum(row.get("profit_units")) for row in rows)
                    / sum(fnum(row.get("stake_units")) for row in rows)
                    if rows
                    else math.nan
                ),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    action_rows = load_action_rows(args.db, args.min_year)
    actions = action_lookup(action_rows)
    single = single_rows(action_rows)
    source_rows = load_core_source_rows(args.selected_tickets)

    raw_rows = build_base_ticket_rows(source_rows=source_rows, actions=actions)
    for policy in args.policies.split(","):
        for mode in args.modes.split(","):
            for count in args.protect_counts:
                raw_rows.extend(
                    build_protected_ticket_rows(
                        source_rows=source_rows,
                        actions=actions,
                        single=single,
                        policy=policy.strip(),
                        mode=mode.strip(),
                        protect_count=int(count),
                        snapshot=args.snapshot,
                    )
                )

    budgeted = budgeted_ticket_rows(raw_rows, issue_budget_units=ISSUE_BUDGET, fractional=True)
    issue_rows = issue_profit_rows(budgeted)
    issue_maps = strategy_issue_map(issue_rows, calendar)
    n5_overlap = load_issue_arm(args.n5_overlap_path, N5_OVERLAP_STRATEGY, "n5_overlap", calendar)
    n5_quality = load_issue_arm(args.n5_overlap_path, N5_QUALITY_STRATEGY, "n5_quality_overlap", calendar)
    arms: dict[str, dict[str, dict[str, object]]] = {
        **issue_maps,
        "n5_overlap": n5_overlap,
        "n5_quality_overlap": n5_quality,
    }
    issues = ordered_issues(calendar, arms)

    portfolio_rows: list[dict[str, object]] = []
    portfolio_series: dict[str, list[dict[str, object]]] = {}
    base_strategy = "core_base__budget256_fractional"
    baseline = combine_portfolio(
        portfolio="baseline_core192_n5ov64_rebuilt",
        issues=issues,
        arms=arms,
        allocation={base_strategy: 192.0, "n5_overlap": 64.0},
        calendar=calendar,
    )
    portfolio_rows.extend(baseline)
    portfolio_series["baseline_core192_n5ov64_rebuilt"] = baseline

    for policy in args.policies.split(","):
        for mode in args.modes.split(","):
            for count in args.protect_counts:
                stem = f"{policy.strip()}_{mode.strip()}_k{int(count)}"
                protected_strategy = f"core_tp_{stem}__budget256_fractional"
                only_strategy = f"core_tp_only_{stem}__budget256_fractional"
                replace_name = f"replace192_{stem}_n5ov64"
                sleeve_name = f"sleeve160_tp32_{stem}_n5ov64"
                rows = combine_portfolio(
                    portfolio=replace_name,
                    issues=issues,
                    arms=arms,
                    allocation={protected_strategy: 192.0, "n5_overlap": 64.0},
                    calendar=calendar,
                )
                portfolio_rows.extend(rows)
                portfolio_series[replace_name] = rows
                rows = combine_portfolio(
                    portfolio=sleeve_name,
                    issues=issues,
                    arms=arms,
                    allocation={base_strategy: 160.0, only_strategy: 32.0, "n5_overlap": 64.0},
                    calendar=calendar,
                )
                portfolio_rows.extend(rows)
                portfolio_series[sleeve_name] = rows

    summaries = [summarize(rows, args.recent_min_year, args.recent_max_year) for rows in portfolio_series.values()]
    summaries.sort(
        key=lambda row: (
            fnum(row["max_drawdown_units"]),
            fnum(row["profit_units"]),
            fnum(row["issue_win_rate"]),
        ),
        reverse=True,
    )
    annual = annual_rows(portfolio_rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "n7_core_ticket_protection_raw_tickets.csv", raw_rows)
    write_csv_all(args.output_dir / "n7_core_ticket_protection_budgeted_tickets.csv", budgeted)
    write_csv(args.output_dir / "n7_core_ticket_protection_issue_profit.csv", issue_rows)
    write_csv(args.output_dir / "n7_core_ticket_protection_portfolio_issue_profit.csv", portfolio_rows)
    write_csv(args.output_dir / "n7_core_ticket_protection_summary.csv", summaries)
    write_csv(args.output_dir / "n7_core_ticket_protection_annual.csv", annual)
    write_csv(args.output_dir / "n7_core_ticket_protection_raw_summary.csv", summarize_protection_rows(raw_rows))

    summary_df = pd.DataFrame(summaries)
    top_profit = summary_df.sort_values(["profit_units", "max_drawdown_units"], ascending=[False, False]).head(12)
    top_dd = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False]).head(12)
    baseline_summary = summary_df[summary_df["portfolio"] == "baseline_core192_n5ov64_rebuilt"]
    summary_lookup = {str(row["portfolio"]): row for row in summaries}

    def metric_text(name: str) -> str:
        row = summary_lookup[name]
        return (
            f"`{name}`: profit `{fnum(row['profit_units']):,.0f}`, "
            f"ROI `{fnum(row['roi']):.2f}`, maxDD `{fnum(row['max_drawdown_units']):,.0f}`, "
            f"max full-loss streak `{int(fnum(row['max_dead_streak']))}`, "
            f"recent profit `{fnum(row['recent_profit_units']):,.0f}`, "
            f"ex-best ROI `{fnum(row['roi_ex_best_issue']):.2f}`"
        )

    plot_names = ["baseline_core192_n5ov64_rebuilt"]
    plot_names += [name for name in top_dd["portfolio"].tolist() if name not in plot_names][:5]
    write_equity_svg(
        args.figure_path,
        {name: portfolio_series[name] for name in plot_names if name in portfolio_series},
        calendar,
    )

    report = [
        "# N7 Core Ticket-Level Protection",
        "",
        "## Scope",
        "",
        f"- Source tickets: `{args.selected_tickets}` / `{SOURCE_STRATEGY}` / `{CORE_SELECTOR}`.",
        "- 每期总预算仍为 `256`：主对照是 `192` N7 core + `64` N5 overlap。",
        "- 保护动作只在 N7 core 的少量 ticket 上加一条腿覆盖，不额外加预算。",
        f"- Leg protection snapshot: `{args.snapshot}`; policies: `{args.policies}`; selection modes: `{args.modes}`; counts: `{','.join(str(x) for x in args.protect_counts)}`.",
        "",
        "## Baseline Rebuild",
        "",
        md_table(
            baseline_summary[
                [
                    "portfolio",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_units",
                    "recent_roi",
                    "roi_ex_best_issue",
                ]
            ].to_dict("records"),
            limit=5,
        ),
        "",
        "## Decision",
        "",
        f"- 推荐进入下一轮主测：{metric_text('sleeve160_tp32_draw_top_ev_k1_n5ov64')}。结构是 `160` 原始 N7 core + `32` 只投每期 top-EV protected ticket + `64` N5 overlap；保护动作为给该 top-EV 票中最值得补的腿加 `draw`。",
        f"- 更防守但收益较弱：{metric_text('replace192_draw_top_ev_k1_n5ov64')}。maxDD 略好，但 profit 和近三年都不如推荐版。",
        f"- 最低 maxDD 备选：{metric_text('sleeve160_tp32_full_top_ev_k3_n5ov64')}。适合只看回撤，但 ROI 明显低于推荐版。",
        f"- 不建议追逐最高 profit 的 low-hit 保护：{metric_text('sleeve160_tp32_draw_low_hit_k1_n5ov64')}。它主要靠 2018 单期巨奖，maxDD 反而变差，ex-best ROI 也低。",
        "",
        "## Top By MaxDD",
        "",
        md_table(
            top_dd[
                [
                    "portfolio",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_drawdown_full_loss_equiv",
                    "max_dead_streak",
                    "max_loss_streak",
                    "recent_profit_units",
                    "recent_roi",
                    "roi_ex_best_issue",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Top By Profit",
        "",
        md_table(
            top_profit[
                [
                    "portfolio",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_units",
                    "recent_roi",
                    "roi_ex_best_issue",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Interpretation",
        "",
        "- `replace192_*` 表示 core 的 192 units 全部使用“少量 ticket 加保护”的重建 core。",
        "- `sleeve160_tp32_*` 表示 160 units 原始 core + 32 units 只投被保护的 ticket + 64 units N5 overlap，更接近小比例保护。",
        "- 如果保护组合 maxDD 没有明显下降、但 profit/ROI 下滑，说明当前保护选择只是稀释凸性，下一步应改进“哪条腿需要保护”的识别，而不是增加保护比例。",
        "",
        f"Figure: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument(
        "--selected-tickets",
        type=Path,
        default=Path("results/high_n_selector_20260628/high_n_selector_selected_tickets.csv"),
    )
    parser.add_argument("--n5-overlap-path", type=Path, default=N5_OVERLAP_PATH)
    parser.add_argument("--snapshot", choices=("10h", "1h", "final"), default="1h")
    parser.add_argument("--policies", default="draw,alt,full")
    parser.add_argument("--modes", default="top_ev,low_hit,risk")
    parser.add_argument("--protect-counts", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_core_ticket_protection_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_core_ticket_protection_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_core_ticket_protection_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
