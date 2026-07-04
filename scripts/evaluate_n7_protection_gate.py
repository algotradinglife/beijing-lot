#!/usr/bin/env python3
"""Hard-gate the N7 protected-ticket sleeve by changed-leg structure.

The prior protected sleeve buys one top-EV N7 ticket per issue after adding a
draw leg. This script tests whether that sleeve should only fire when the
actual changed leg matches the rescue profile observed in attribution:

* base action 0 -> protected action 10;
* Beidan handicap equals -2;
* 1h draw probability is low;
* Beidan line is deeper than Asian consensus.

When a gate does not fire, the fixed 256-unit issue budget is still spent by
falling back to the existing N5 quality/overlap sleeve through combine_portfolio.
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
    load_issue_calendar,
    summarize,
    write_equity_svg,
)
from scripts.evaluate_n7_core_ticket_protection import (
    N5_OVERLAP_PATH,
    N5_OVERLAP_STRATEGY,
    N5_QUALITY_STRATEGY,
    combine_portfolio,
    load_issue_arm,
    write_csv_all,
)
from scripts.evaluate_n7_high_sp_anchor_protection import load_line_gaps
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n7_protection_allocation_grid import (
    CORE_ARM,
    PROTECT_ARMS,
    load_strategy_maps,
    max_underwater_profit_window,
)
from scripts.evaluate_n7_same_ticket_leg_coverage import action_lookup, single_rows
from scripts.walkforward_beidan_strategy_eval import default_db_path, load_action_rows, md_table, write_csv


ORIGINAL_PROTECT_ARM = PROTECT_ARMS["draw_top_ev_k1"]
ORIGINAL_ONLY_RAW = "core_tp_only_draw_top_ev_k1"
BASE_RAW = "core_base"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_legs(raw: object) -> dict[int, dict[str, object]]:
    out: dict[int, dict[str, object]] = {}
    for item in str(raw).split(";"):
        if not item:
            continue
        left, hcp_raw = item.split("@", 1) if "@" in item else (item, "")
        match_raw, action_code = left.split(":", 1)
        hcp = fnum(hcp_raw, math.nan)
        out[int(match_raw)] = {"action_code": action_code, "hcp": hcp}
    return out


def changed_leg(base: dict[str, object], protected: dict[str, object]) -> dict[str, object]:
    base_legs = parse_legs(base.get("legs", ""))
    protected_legs = parse_legs(protected.get("legs", ""))
    changes = []
    for match_id, base_leg in base_legs.items():
        protected_leg = protected_legs.get(match_id)
        if protected_leg is None:
            continue
        if base_leg["action_code"] == protected_leg["action_code"]:
            continue
        changes.append(
            {
                "match_id": match_id,
                "base_action": str(base_leg["action_code"]),
                "protected_action": str(protected_leg["action_code"]),
                "hcp": fnum(protected_leg["hcp"], fnum(base_leg["hcp"], math.nan)),
            }
        )
    if len(changes) != 1:
        return {
            "changed_leg_count": len(changes),
            "match_id": "",
            "base_action": "",
            "protected_action": "",
            "hcp": math.nan,
        }
    out = dict(changes[0])
    out["changed_leg_count"] = 1
    return out


def base_key(row: dict[str, object]) -> tuple[str, str]:
    return str(row.get("issue", "")), str(row.get("source_ticket_idx") or row.get("ticket_idx") or "")


def gate_pass(
    *,
    gate: str,
    base_action: str,
    protected_action: str,
    hcp: float,
    draw_1h_p: float,
    line_gap: float,
    draw_threshold: float,
    line_gap_threshold: float,
) -> bool:
    action_hcp = base_action == "0" and protected_action == "10" and hcp == -2
    if gate == "action_hcp":
        return action_hcp
    if gate == "action_hcp_lowdraw":
        return action_hcp and draw_1h_p < draw_threshold
    if gate == "action_hcp_posgap":
        return action_hcp and line_gap > 0
    if gate == "strict":
        return action_hcp and draw_1h_p < draw_threshold and line_gap > 0
    if gate == "strict_gap05":
        return action_hcp and draw_1h_p < draw_threshold and line_gap >= line_gap_threshold
    raise ValueError(f"unknown gate: {gate}")


def enrich_and_gate_raw_rows(
    *,
    raw_rows: list[dict[str, str]],
    db: Path,
    min_year: int,
    snapshot: str,
    gates: list[str],
    draw_threshold: float,
    line_gap_threshold: float,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    action_rows = load_action_rows(db, min_year)
    singles = single_rows(action_rows)
    line_gaps = load_line_gaps(db, snapshot)

    base_rows = {
        (str(row.get("issue", "")), str(row.get("source_ticket_idx") or row.get("ticket_idx") or "")): row
        for row in raw_rows
        if row.get("strategy") == BASE_RAW
    }
    protected_rows = [row for row in raw_rows if row.get("strategy") == ORIGINAL_ONLY_RAW]
    gated_raw: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    for row in protected_rows:
        key = base_key(row)
        base = base_rows.get(key)
        if base is None:
            continue
        changed = changed_leg(base, row)
        match_id_raw = changed.get("match_id", "")
        match_id = int(match_id_raw) if str(match_id_raw) else 0
        draw_row = singles.get((match_id, "1"))
        draw_1h_p = fnum(getattr(draw_row, "euro_1h_p", None), math.nan) if draw_row is not None else math.nan
        line_gap = fnum(line_gaps.get(match_id), math.nan)
        base_profit = fnum(base.get("profit_units"))
        protected_profit = fnum(row.get("profit_units"))
        protected_hit = int(fnum(row.get("hit")))
        base_hit = int(fnum(base.get("hit")))
        audit = {
            "issue": row.get("issue", ""),
            "source_ticket_idx": row.get("source_ticket_idx", ""),
            "match_id": match_id if match_id else "",
            "base_action": changed.get("base_action", ""),
            "protected_action": changed.get("protected_action", ""),
            "base_to_protected": (
                f"{changed.get('base_action', '')}->{changed.get('protected_action', '')}"
                if changed.get("base_action") or changed.get("protected_action")
                else ""
            ),
            "hcp": changed.get("hcp", math.nan),
            "draw_1h_p": draw_1h_p,
            "line_gap": line_gap,
            "source_pred_ev_per_stake": fnum(row.get("source_pred_ev_per_stake")),
            "source_pred_hit_prob": fnum(row.get("source_pred_hit_prob")),
            "source_selector_score": fnum(row.get("source_selector_score")),
            "base_raw_stake": fnum(base.get("stake_units")),
            "protected_raw_stake": fnum(row.get("stake_units")),
            "base_raw_profit": base_profit,
            "protected_raw_profit": protected_profit,
            "delta_raw_profit": protected_profit - base_profit,
            "base_hit": base_hit,
            "protected_hit": protected_hit,
            "rescued_by_protection": 1 if protected_hit and not base_hit else 0,
        }
        for gate in gates:
            passed = gate_pass(
                gate=gate,
                base_action=str(changed.get("base_action", "")),
                protected_action=str(changed.get("protected_action", "")),
                hcp=fnum(changed.get("hcp"), math.nan),
                draw_1h_p=draw_1h_p,
                line_gap=line_gap,
                draw_threshold=draw_threshold,
                line_gap_threshold=line_gap_threshold,
            )
            audit[f"pass_{gate}"] = 1 if passed else 0
            if passed:
                copied = dict(row)
                copied["strategy"] = f"core_tp_only_draw_top_ev_k1_gate_{gate}"
                copied.update(
                    {
                        "gate": gate,
                        "changed_match_id": match_id,
                        "base_action": changed.get("base_action", ""),
                        "protected_action": changed.get("protected_action", ""),
                        "changed_hcp": changed.get("hcp", math.nan),
                        "draw_1h_p": draw_1h_p,
                        "line_gap": line_gap,
                    }
                )
                gated_raw.append(copied)
        audit_rows.append(audit)
    return gated_raw, audit_rows


def gate_summary_rows(audit_rows: list[dict[str, object]], gates: list[str]) -> list[dict[str, object]]:
    out = []
    for gate in gates:
        rows = [row for row in audit_rows if int(fnum(row.get(f"pass_{gate}"))) == 1]
        raw_base_stake = sum(fnum(row.get("base_raw_stake")) for row in rows)
        raw_protected_stake = sum(fnum(row.get("protected_raw_stake")) for row in rows)
        raw_protected_profit = sum(fnum(row.get("protected_raw_profit")) for row in rows)
        raw_base_profit = sum(fnum(row.get("base_raw_profit")) for row in rows)
        raw_delta = sum(fnum(row.get("delta_raw_profit")) for row in rows)
        out.append(
            {
                "gate": gate,
                "tickets": len(rows),
                "issues": len({str(row.get("issue")) for row in rows}),
                "rescues": sum(int(fnum(row.get("rescued_by_protection"))) for row in rows),
                "protected_hits": sum(int(fnum(row.get("protected_hit"))) for row in rows),
                "avg_draw_1h_p": (
                    sum(fnum(row.get("draw_1h_p")) for row in rows) / len(rows) if rows else math.nan
                ),
                "avg_line_gap": sum(fnum(row.get("line_gap")) for row in rows) / len(rows) if rows else math.nan,
                "base_raw_profit": raw_base_profit,
                "protected_raw_profit": raw_protected_profit,
                "delta_raw_profit": raw_delta,
                "base_raw_stake": raw_base_stake,
                "protected_raw_stake": raw_protected_stake,
                "incremental_raw_stake": raw_protected_stake - raw_base_stake,
                "protected_raw_roi": raw_protected_profit / raw_protected_stake if raw_protected_stake else math.nan,
            }
        )
    return out


def ordered_issues(calendar: dict[str, dict[str, object]], arms: dict[str, dict[str, dict[str, object]]]) -> list[str]:
    issues = set()
    for arm in (CORE_ARM, "n5_overlap", "n5_quality_overlap"):
        issues.update(arms.get(arm, {}).keys())
    return sorted(issues, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def add_portfolio(
    *,
    name: str,
    allocation: dict[str, float],
    issues: list[str],
    arms: dict[str, dict[str, dict[str, object]]],
    calendar: dict[str, dict[str, object]],
    all_rows: list[dict[str, object]],
    series: dict[str, list[dict[str, object]]],
    meta: dict[str, dict[str, object]],
    extra: dict[str, object],
) -> None:
    rows = combine_portfolio(
        portfolio=name,
        issues=issues,
        arms=arms,
        allocation=allocation,
        calendar=calendar,
    )
    for row in rows:
        row.update(extra)
    all_rows.extend(rows)
    series[name] = rows
    meta[name] = extra


def run(args: argparse.Namespace) -> None:
    gates = [gate.strip() for gate in args.gates.split(",") if gate.strip()]
    calendar = load_issue_calendar(args.db)
    raw_rows = read_csv_rows(args.raw_ticket_path)
    gated_raw, audit_rows = enrich_and_gate_raw_rows(
        raw_rows=raw_rows,
        db=args.db,
        min_year=args.min_year,
        snapshot=args.snapshot,
        gates=gates,
        draw_threshold=args.draw_threshold,
        line_gap_threshold=args.line_gap_threshold,
    )
    gated_budgeted = budgeted_ticket_rows(gated_raw, issue_budget_units=ISSUE_BUDGET, fractional=True)
    gated_issue_rows = issue_profit_rows(gated_budgeted)

    arms = load_strategy_maps(args.protection_issue_profit, calendar)
    gated_maps = load_strategy_maps_from_rows(gated_issue_rows, calendar)
    arms.update(gated_maps)
    arms["n5_overlap"] = load_issue_arm(N5_OVERLAP_PATH, N5_OVERLAP_STRATEGY, "n5_overlap", calendar)
    arms["n5_quality_overlap"] = load_issue_arm(N5_OVERLAP_PATH, N5_QUALITY_STRATEGY, "n5_quality_overlap", calendar)
    issues = ordered_issues(calendar, arms)

    all_rows: list[dict[str, object]] = []
    series: dict[str, list[dict[str, object]]] = {}
    meta: dict[str, dict[str, object]] = {}

    add_portfolio(
        name="current_c144_p48_original_n5ov64",
        allocation={CORE_ARM: 144.0, ORIGINAL_PROTECT_ARM: 48.0, "n5_overlap": 64.0},
        issues=issues,
        arms=arms,
        calendar=calendar,
        all_rows=all_rows,
        series=series,
        meta=meta,
        extra={"core_units": 144.0, "protect_units": 48.0, "n5_units": 64.0, "gate": "original"},
    )
    add_portfolio(
        name="baseline_core192_n5ov64",
        allocation={CORE_ARM: 192.0, "n5_overlap": 64.0},
        issues=issues,
        arms=arms,
        calendar=calendar,
        all_rows=all_rows,
        series=series,
        meta=meta,
        extra={"core_units": 192.0, "protect_units": 0.0, "n5_units": 64.0, "gate": "none"},
    )

    for gate in gates:
        arm = f"core_tp_only_draw_top_ev_k1_gate_{gate}__budget256_fractional"
        for protect in args.protect_units:
            core = args.core_units
            n5 = ISSUE_BUDGET - core - protect
            if n5 < args.min_n5_units:
                continue
            name = f"gate_{gate}_c{core:g}_p{protect:g}_n5ov{n5:g}"
            add_portfolio(
                name=name,
                allocation={CORE_ARM: core, arm: protect, "n5_overlap": n5},
                issues=issues,
                arms=arms,
                calendar=calendar,
                all_rows=all_rows,
                series=series,
                meta=meta,
                extra={"core_units": core, "protect_units": protect, "n5_units": n5, "gate": gate},
            )

    summaries = []
    for name, rows in series.items():
        summary = summarize(rows, args.recent_min_year, args.recent_max_year)
        summary.update(meta.get(name, {}))
        summary.update(max_underwater_profit_window(rows))
        summaries.append(summary)
    summary_df = pd.DataFrame(summaries)
    summary_df["profit_to_dd"] = summary_df["profit_units"] / summary_df["max_drawdown_units"].abs()
    summary_df["recommended_score"] = (
        summary_df["profit_units"]
        + 1.8 * summary_df["max_drawdown_units"]
        + 90000.0 * summary_df["roi_ex_best_issue"]
        + 35000.0 * summary_df["recent_roi"]
    )
    summary_df = summary_df.sort_values(
        ["recommended_score", "profit_units", "max_drawdown_units"],
        ascending=[False, False, False],
    )
    annual = annual_rows(all_rows)
    gate_summary = gate_summary_rows(audit_rows, gates)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "protection_gate_raw_tickets.csv", gated_raw)
    write_csv_all(args.output_dir / "protection_gate_budgeted_tickets.csv", gated_budgeted)
    write_csv(args.output_dir / "protection_gate_issue_profit.csv", gated_issue_rows)
    write_csv_all(args.output_dir / "protection_gate_changed_leg_audit.csv", audit_rows)
    write_csv_all(args.output_dir / "protection_gate_summary.csv", gate_summary)
    write_csv_all(args.output_dir / "protection_gate_portfolio_issue_profit.csv", all_rows)
    summary_df.to_csv(args.output_dir / "protection_gate_portfolio_summary.csv", index=False)
    write_csv(args.output_dir / "protection_gate_portfolio_annual.csv", annual)

    current = summary_df[summary_df["portfolio"] == "current_c144_p48_original_n5ov64"].iloc[0]
    selected = summary_df[
        summary_df["portfolio"].isin(["current_c144_p48_original_n5ov64", "baseline_core192_n5ov64"])
        | summary_df["portfolio"].str.contains("_p48_")
    ].copy()
    top_score = summary_df.head(12)
    top_profit = summary_df.sort_values(["profit_units", "max_drawdown_units"], ascending=[False, False]).head(12)
    better_dd = summary_df[summary_df["max_drawdown_units"] >= fnum(current["max_drawdown_units"])].copy()
    better_dd = better_dd.sort_values(["profit_units", "recommended_score"], ascending=[False, False]).head(12)

    plot_names = ["current_c144_p48_original_n5ov64", "baseline_core192_n5ov64"]
    for name in top_score["portfolio"].head(4).tolist() + better_dd["portfolio"].head(4).tolist():
        if name not in plot_names:
            plot_names.append(name)
    write_equity_svg(args.figure_path, {name: series[name] for name in plot_names if name in series}, calendar)

    best = summary_df.iloc[0]
    best_better_dd = better_dd.iloc[0] if not better_dd.empty else best
    report = [
        "# N7 Protected Ticket Hard Gate",
        "",
        "## Scope",
        "",
        "- 固定每期 `256` units。",
        "- 当前对照：`144` N7 core + `48` original top-EV draw protected sleeve + `64` N5 overlap。",
        "- 新规则只 gate protected sleeve；不触发时，空出的 protected 预算通过既有 fallback 进入 N5 quality/overlap。",
        f"- Gate inputs use `{args.snapshot}` market snapshot only: draw probability and Asian handicap line_gap. No final SP or result is used by the selector.",
        f"- Draw threshold: `{args.draw_threshold}`; strict gap threshold: `{args.line_gap_threshold}`.",
        "",
        "## Decision",
        "",
        f"- 综合推荐分最高：`{best['portfolio']}`，profit `{fnum(best['profit_units']):,.0f}`，ROI `{fnum(best['roi']):.2f}`，maxDD `{fnum(best['max_drawdown_units']):,.0f}`，近三年 profit `{fnum(best['recent_profit_units']):,.0f}`，ex-best ROI `{fnum(best['roi_ex_best_issue']):.2f}`。",
        f"- 在 maxDD 不差于当前原始方案的约束下，最好的是：`{best_better_dd['portfolio']}`，profit `{fnum(best_better_dd['profit_units']):,.0f}`，ROI `{fnum(best_better_dd['roi']):.2f}`，maxDD `{fnum(best_better_dd['max_drawdown_units']):,.0f}`。",
        "",
        "## Gate Raw Summary",
        "",
        md_table(
            gate_summary,
            limit=20,
        ),
        "",
        "## Same 48-Unit Protected Sleeve Comparison",
        "",
        md_table(
            selected.sort_values(["protect_units", "recommended_score"], ascending=[False, False])[
                [
                    "portfolio",
                    "gate",
                    "core_units",
                    "protect_units",
                    "n5_units",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_units",
                    "recent_roi",
                    "roi_ex_best_issue",
                    "profit_to_dd",
                ]
            ].to_dict("records"),
            limit=30,
        ),
        "",
        "## Top Recommended Score",
        "",
        md_table(
            top_score[
                [
                    "portfolio",
                    "gate",
                    "core_units",
                    "protect_units",
                    "n5_units",
                    "profit_units",
                    "roi",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_units",
                    "roi_ex_best_issue",
                    "recommended_score",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Top Profit",
        "",
        md_table(
            top_profit[
                [
                    "portfolio",
                    "gate",
                    "core_units",
                    "protect_units",
                    "n5_units",
                    "profit_units",
                    "roi",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_units",
                    "roi_ex_best_issue",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## MaxDD Not Worse Than Current",
        "",
        md_table(
            better_dd[
                [
                    "portfolio",
                    "gate",
                    "profit_units",
                    "roi",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_units",
                    "roi_ex_best_issue",
                    "profit_to_dd",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Interpretation",
        "",
        "- `action_hcp` tests only the structural rescue profile: `0->10` and Beidan hcp `-2`.",
        "- `strict` additionally requires low 1h draw probability and positive line_gap.",
        "- If strict gates lose too much profit, the observed rescue profile is better used as a diagnostic tag than as a hard production gate.",
        f"- Figure: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")


def load_strategy_maps_from_rows(
    rows: list[dict[str, object]], calendar: dict[str, dict[str, object]]
) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in rows:
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[str(row["strategy"])][str(row["issue"])] = copied
    return dict(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--snapshot", choices=("10h", "1h", "final"), default="1h")
    parser.add_argument(
        "--raw-ticket-path",
        type=Path,
        default=Path("results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_raw_tickets.csv"),
    )
    parser.add_argument(
        "--protection-issue-profit",
        type=Path,
        default=Path("results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_issue_profit.csv"),
    )
    parser.add_argument("--gates", default="action_hcp,action_hcp_lowdraw,action_hcp_posgap,strict,strict_gap05")
    parser.add_argument("--draw-threshold", type=float, default=0.24)
    parser.add_argument("--line-gap-threshold", type=float, default=0.5)
    parser.add_argument("--core-units", type=float, default=144.0)
    parser.add_argument("--protect-units", type=float, nargs="+", default=[16, 24, 32, 48, 64])
    parser.add_argument("--min-n5-units", type=float, default=48.0)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_protection_gate_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_protection_gate_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_protection_gate_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
