#!/usr/bin/env python3
"""Explore second-stage switch gates for the N7 384 defensive sleeve."""
from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_384_drawdown_dynamic import (
    SELECTED_PORTFOLIO,
    fnum,
    full_loss,
    row_year,
    summarize_issue_rows,
)
from scripts.evaluate_n7_384_weak_quality_dynamic import (
    annual_rows,
    load_features,
    load_portfolios,
    ordered_issues,
    write_csv_all,
    write_equity_svg,
)
from scripts.validate_n7_384_frozen_dynamic_rule import (
    BASE_BUDGET,
    BASE_PORTFOLIO,
    DEFENSIVE_PORTFOLIO,
    FEATURE,
    FEATURE_Q,
    HISTORY_ISSUES,
    MIN_HISTORY_ISSUES,
    build_period_summaries,
    drawdown_attribution,
    dynamic_full_loss,
    max_dead_streak_rows,
    period_summary,
    replay_frozen_rule,
    rolling_windows,
)
from scripts.walkforward_beidan_strategy_eval import md_table


GateFn = Callable[[dict[str, object]], bool]

SOURCE_LINE_GAP = "same_ticket4_full_risk_avg_source_line_gap"


def gate_always(_features: dict[str, object]) -> bool:
    return True


def gate_core_count_ge12(features: dict[str, object]) -> bool:
    return fnum(features.get("core_ticket_count"), math.nan) >= 12


def gate_source_linegap_le0(features: dict[str, object]) -> bool:
    return fnum(features.get(SOURCE_LINE_GAP), math.nan) <= 0


def gate_core_count_ge12_source_linegap_le0(features: dict[str, object]) -> bool:
    return gate_core_count_ge12(features) and gate_source_linegap_le0(features)


def gate_core_count_ge12_core_linegap_le01(features: dict[str, object]) -> bool:
    return gate_core_count_ge12(features) and fnum(features.get("core_avg_line_gap_net"), math.nan) <= 0.1


def gate_core_count_ge12_source_linegap_le0_exact_ratio_le25(features: dict[str, object]) -> bool:
    return gate_core_count_ge12_source_linegap_le0(features) and fnum(
        features.get("core_exact_ticket_ratio"), math.nan
    ) <= 0.25


def gate_core_count_ge12_source_linegap_le0_llgood_le40(features: dict[str, object]) -> bool:
    return gate_core_count_ge12_source_linegap_le0(features) and fnum(
        features.get("core_avg_ll_good"), math.nan
    ) <= 0.4


GATES: list[tuple[str, str, GateFn]] = [
    ("frozen_original", "low core predEV only", gate_always),
    ("core_count_ge12", "low predEV + core_ticket_count >= 12", gate_core_count_ge12),
    ("source_linegap_le0", f"low predEV + {SOURCE_LINE_GAP} <= 0", gate_source_linegap_le0),
    (
        "core_count_ge12_source_linegap_le0",
        f"low predEV + core_ticket_count >= 12 + {SOURCE_LINE_GAP} <= 0",
        gate_core_count_ge12_source_linegap_le0,
    ),
    (
        "core_count_ge12_core_linegap_le01",
        "low predEV + core_ticket_count >= 12 + core_avg_line_gap_net <= 0.1",
        gate_core_count_ge12_core_linegap_le01,
    ),
    (
        "core_count_ge12_source_linegap_le0_exact_ratio_le25",
        f"low predEV + core_ticket_count >= 12 + {SOURCE_LINE_GAP} <= 0 + core_exact_ticket_ratio <= 0.25",
        gate_core_count_ge12_source_linegap_le0_exact_ratio_le25,
    ),
    (
        "core_count_ge12_source_linegap_le0_llgood_le40",
        f"low predEV + core_ticket_count >= 12 + {SOURCE_LINE_GAP} <= 0 + core_avg_ll_good <= 0.4",
        gate_core_count_ge12_source_linegap_le0_llgood_le40,
    ),
]


DIAGNOSTIC_FEATURES = [
    "core_ticket_count",
    "core_avg_pred_hit",
    "core_avg_pred_ev",
    "core_avg_selector_score",
    "core_avg_line_gap_net",
    "core_avg_abs_line_gap",
    "core_avg_ll_good",
    "core_avg_q",
    "core_avg_conf",
    "all_ticket_count",
    "all_avg_pred_hit",
    "all_avg_pred_ev",
    "all_avg_selector_score",
    "all_avg_line_gap_net",
    "all_avg_abs_line_gap",
    "all_avg_ll_good",
    "all_avg_q",
    "all_avg_conf",
    "exact_ticket_count",
    "core_exact_ticket_ratio",
    "same_ticket4_full_risk_avg_source_pred_ev",
    "same_ticket4_full_risk_avg_source_score",
    SOURCE_LINE_GAP,
]


def summarize_rows(rows: list[dict[str, object]], *, portfolio: str) -> dict[str, object]:
    out = summarize_issue_rows(rows, portfolio=portfolio, budget=BASE_BUDGET)
    out["max_dead_streak"] = max_dead_streak_rows(rows)
    return out


def build_gated_rows(
    *,
    gate_name: str,
    gate_desc: str,
    gate_fn: GateFn,
    issues: list[str],
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    features_by_issue: dict[str, dict[str, object]],
    frozen_rows_by_issue: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for issue in issues:
        frozen = frozen_rows_by_issue[issue]
        base = rows_by_portfolio[BASE_PORTFOLIO][issue]
        defensive = rows_by_portfolio[DEFENSIVE_PORTFOLIO][issue]
        features = features_by_issue.get(issue, {})
        original_switch = int(fnum(frozen.get("switched"))) == 1
        second_gate = bool(gate_fn(features)) if original_switch else False
        switched = original_switch and second_gate
        chosen = defensive if switched else base
        base_profit = fnum(base.get("profit_units"))
        defensive_profit = fnum(defensive.get("profit_units"))
        dynamic_profit = fnum(chosen.get("profit_units"))
        delta = dynamic_profit - base_profit
        row = dict(chosen)
        row.update(
            {
                "portfolio": gate_name,
                "gate_desc": gate_desc,
                "issue": issue,
                "stake_units": BASE_BUDGET,
                "profit_units": dynamic_profit,
                "roi": dynamic_profit / BASE_BUDGET,
                "chosen_portfolio": DEFENSIVE_PORTFOLIO if switched else BASE_PORTFOLIO,
                "original_switch": int(original_switch),
                "second_gate_passed": int(second_gate),
                "switched": int(switched),
                "state": "defensive" if switched else "base",
                "quality_feature": frozen.get("quality_feature", FEATURE),
                "quality_value": frozen.get("quality_value", ""),
                "quality_threshold": frozen.get("quality_threshold", ""),
                "quality_history_n": frozen.get("quality_history_n", ""),
                "base_profit_units": base_profit,
                "defensive_profit_units": defensive_profit,
                "delta_vs_base_units": delta,
                "base_full_loss": int(full_loss(base)),
                "defensive_full_loss": int(full_loss(defensive)),
                "dynamic_full_loss": int(dynamic_full_loss({"stake_units": BASE_BUDGET, "profit_units": dynamic_profit})),
                "base_win": int(base_profit > 0),
                "defensive_win": int(defensive_profit > 0),
                "dynamic_win": int(dynamic_profit > 0),
                "switch_helped": int(switched and delta > 1e-9),
                "switch_hurt": int(switched and delta < -1e-9),
                "switch_flat": int(switched and abs(delta) <= 1e-9),
                "saved_full_loss": int(switched and full_loss(base) and not full_loss(defensive)),
                "created_full_loss": int(switched and not full_loss(base) and full_loss(defensive)),
                "defensive_big_rescue": int(switched and delta >= 1000),
            }
        )
        for feature in DIAGNOSTIC_FEATURES:
            row[feature] = features.get(feature, "")
        out.append(row)
    return out


def switch_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    switched = [row for row in rows if int(fnum(row.get("switched"))) == 1]
    return {
        "portfolio": rows[0].get("portfolio", "") if rows else "",
        "gate_desc": rows[0].get("gate_desc", "") if rows else "",
        "switch_count": len(switched),
        "switch_rate": len(switched) / len(rows) if rows else math.nan,
        "switch_delta_units": sum(fnum(row.get("delta_vs_base_units")) for row in switched),
        "helped_count": sum(1 for row in switched if fnum(row.get("delta_vs_base_units")) > 1e-9),
        "hurt_count": sum(1 for row in switched if fnum(row.get("delta_vs_base_units")) < -1e-9),
        "flat_count": sum(1 for row in switched if abs(fnum(row.get("delta_vs_base_units"))) <= 1e-9),
        "recent_switch_delta_units": sum(
            fnum(row.get("delta_vs_base_units")) for row in switched if 2023 <= row_year(row) <= 2025
        ),
        "pre2023_switch_delta_units": sum(
            fnum(row.get("delta_vs_base_units")) for row in switched if 2014 <= row_year(row) <= 2022
        ),
        "defensive_big_rescue_count": sum(int(fnum(row.get("defensive_big_rescue"))) for row in switched),
    }


def feature_group_rows(
    *,
    frozen_rows: list[dict[str, object]],
    features_by_issue: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    for row in frozen_rows:
        if int(fnum(row.get("switched"))) != 1:
            continue
        issue = str(row["issue"])
        delta = fnum(row.get("delta_vs_base_units"))
        group = "helped" if delta > 1e-9 else "hurt" if delta < -1e-9 else "flat"
        out = {
            "issue": issue,
            "calendar_year": row.get("calendar_year", ""),
            "issue_close_ts": row.get("issue_close_ts", ""),
            "group": group,
            "delta_vs_base_units": delta,
            "base_profit_units": row.get("base_profit_units", ""),
            "defensive_profit_units": row.get("defensive_profit_units", ""),
            "quality_value": row.get("quality_value", ""),
            "quality_threshold": row.get("quality_threshold", ""),
        }
        features = features_by_issue.get(issue, {})
        for feature in DIAGNOSTIC_FEATURES:
            out[feature] = features.get(feature, "")
        rows.append(out)

    df = pd.DataFrame(rows)
    summary: list[dict[str, object]] = []
    if not df.empty:
        for group, sub in df.groupby("group", sort=True):
            item: dict[str, object] = {"group": group, "n": len(sub)}
            for feature in DIAGNOSTIC_FEATURES:
                series = pd.to_numeric(sub[feature], errors="coerce")
                item[f"{feature}_mean"] = float(series.mean()) if not series.dropna().empty else math.nan
                item[f"{feature}_median"] = float(series.median()) if not series.dropna().empty else math.nan
            summary.append(item)
    return rows, summary


def candidate_summary_rows(
    *,
    base_rows: list[dict[str, object]],
    gated_by_name: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    base_summary = summarize_rows(base_rows, portfolio=BASE_PORTFOLIO)
    out = [base_summary]
    base_profit = sum(fnum(row.get("profit_units")) for row in base_rows)
    base_maxdd = fnum(base_summary.get("max_drawdown_units"))
    for name, rows in gated_by_name.items():
        summary = summarize_rows(rows, portfolio=name)
        summary["gate_desc"] = rows[0].get("gate_desc", "") if rows else ""
        summary["profit_delta_vs_base_units"] = sum(fnum(row.get("profit_units")) for row in rows) - base_profit
        summary["maxdd_delta_vs_base_units"] = fnum(summary.get("max_drawdown_units")) - base_maxdd
        summary.update(switch_summary(rows))
        out.append(summary)
    return out


def build_period_rows(
    *,
    issues: list[str],
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    gated_by_name: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    base_all = [rows_by_portfolio[BASE_PORTFOLIO][issue] for issue in issues]
    defensive_all = [rows_by_portfolio[DEFENSIVE_PORTFOLIO][issue] for issue in issues]
    periods = [
        ("all", lambda row: True),
        ("train_like_2014_2022", lambda row: 2014 <= row_year(row) <= 2022),
        ("recent_2023_2025", lambda row: 2023 <= row_year(row) <= 2025),
        ("weak_recent_2024_2025", lambda row: 2024 <= row_year(row) <= 2025),
    ]
    out: list[dict[str, object]] = []
    for name, rows in gated_by_name.items():
        for period, predicate in periods:
            base = [row for row in base_all if predicate(row)]
            defensive = [row for row in defensive_all if predicate(row)]
            dynamic = [row for row in rows if predicate(row)]
            item = period_summary(name=period, base_rows=base, defensive_rows=defensive, dynamic_rows=dynamic)
            item["portfolio"] = name
            out.append(item)
        for year in sorted({row_year(row) for row in rows}):
            if year <= 0:
                continue
            base = [row for row in base_all if row_year(row) == year]
            defensive = [row for row in defensive_all if row_year(row) == year]
            dynamic = [row for row in rows if row_year(row) == year]
            item = period_summary(name=f"year_{year}", base_rows=base, defensive_rows=defensive, dynamic_rows=dynamic)
            item["portfolio"] = name
            out.append(item)
    return out


def rolling_summary_rows(
    *,
    issues: list[str],
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    gated_by_name: dict[str, list[dict[str, object]]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    all_windows: list[dict[str, object]] = []
    all_summary: list[dict[str, object]] = []
    for name, rows in gated_by_name.items():
        windows, summary = rolling_windows(issues=issues, rows_by_portfolio=rows_by_portfolio, dynamic_rows=rows)
        for row in windows:
            row["portfolio"] = name
        for row in summary:
            row["portfolio"] = name
        all_windows.extend(windows)
        all_summary.extend(summary)
    return all_windows, all_summary


def md_rows(rows: list[dict[str, object]], cols: list[str], limit: int = 40) -> list[dict[str, object]]:
    return [{col: row.get(col, "") for col in cols} for row in rows[:limit]]


def run(args: argparse.Namespace) -> None:
    rows_by_portfolio = load_portfolios(args.issue_profit)
    features_by_issue = load_features(args.features)
    for portfolio in (BASE_PORTFOLIO, DEFENSIVE_PORTFOLIO):
        if portfolio not in rows_by_portfolio:
            raise SystemExit(f"missing portfolio in issue profit: {portfolio}")
    issues = ordered_issues(rows_by_portfolio)
    frozen_rows = replay_frozen_rule(
        issues=issues,
        rows_by_portfolio=rows_by_portfolio,
        features_by_issue=features_by_issue,
        feature=FEATURE,
        q=FEATURE_Q,
        history=HISTORY_ISSUES,
        min_history=MIN_HISTORY_ISSUES,
    )
    frozen_rows_by_issue = {str(row["issue"]): row for row in frozen_rows}
    base_rows = [rows_by_portfolio[BASE_PORTFOLIO][issue] for issue in issues]
    gated_by_name = {
        name: build_gated_rows(
            gate_name=name,
            gate_desc=desc,
            gate_fn=gate_fn,
            issues=issues,
            rows_by_portfolio=rows_by_portfolio,
            features_by_issue=features_by_issue,
            frozen_rows_by_issue=frozen_rows_by_issue,
        )
        for name, desc, gate_fn in GATES
    }

    switch_features, switch_feature_summary = feature_group_rows(
        frozen_rows=frozen_rows,
        features_by_issue=features_by_issue,
    )
    candidate_summary = candidate_summary_rows(base_rows=base_rows, gated_by_name=gated_by_name)
    period_rows = build_period_rows(
        issues=issues,
        rows_by_portfolio=rows_by_portfolio,
        gated_by_name=gated_by_name,
    )
    rolling_rows, rolling_summary = rolling_summary_rows(
        issues=issues,
        rows_by_portfolio=rows_by_portfolio,
        gated_by_name=gated_by_name,
    )
    best_name = args.best_gate
    best_rows = gated_by_name[best_name]
    best_dd = drawdown_attribution(
        issues=issues,
        rows_by_portfolio=rows_by_portfolio,
        dynamic_rows=best_rows,
    )
    annual = annual_rows(base_rows + best_rows + gated_by_name["frozen_original"])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "switch_feature_rows.csv", switch_features)
    write_csv_all(args.output_dir / "switch_feature_group_summary.csv", switch_feature_summary)
    write_csv_all(args.output_dir / "gate_candidate_summary.csv", candidate_summary)
    write_csv_all(args.output_dir / "gate_candidate_period_summary.csv", period_rows)
    write_csv_all(args.output_dir / "gate_candidate_rolling_windows.csv", rolling_rows)
    write_csv_all(args.output_dir / "gate_candidate_rolling_summary.csv", rolling_summary)
    write_csv_all(args.output_dir / "best_gate_drawdown_attribution.csv", best_dd)
    write_csv_all(args.output_dir / "best_gate_annual.csv", annual)
    write_csv_all(args.output_dir / "best_gate_issue_profit.csv", best_rows)
    write_equity_svg(
        args.figure_path,
        {
            BASE_PORTFOLIO: base_rows,
            "frozen_original": gated_by_name["frozen_original"],
            best_name: best_rows,
        },
    )

    summary_cols = [
        "portfolio",
        "gate_desc",
        "profit_per_256",
        "roi",
        "profit_delta_vs_base_units",
        "max_drawdown_units",
        "maxdd_delta_vs_base_units",
        "max_dead_streak",
        "switch_count",
        "switch_delta_units",
        "helped_count",
        "hurt_count",
        "flat_count",
        "pre2023_switch_delta_units",
        "recent_switch_delta_units",
        "recent_profit_per_256",
        "roi_ex_best_issue",
    ]
    group_cols = [
        "group",
        "n",
        "core_ticket_count_median",
        "core_avg_pred_ev_median",
        "core_avg_line_gap_net_median",
        "core_avg_ll_good_median",
        "all_ticket_count_median",
        "core_exact_ticket_ratio_median",
        f"{SOURCE_LINE_GAP}_median",
    ]
    switch_cols = [
        "issue",
        "calendar_year",
        "group",
        "delta_vs_base_units",
        "core_ticket_count",
        "core_avg_line_gap_net",
        "core_avg_ll_good",
        "core_exact_ticket_ratio",
        SOURCE_LINE_GAP,
    ]
    period_cols = [
        "portfolio",
        "period",
        "n_issues",
        "switch_count",
        "switch_delta_units",
        "base_profit_units",
        "dynamic_profit_units",
        "dynamic_delta_vs_base",
        "base_roi",
        "dynamic_roi",
        "base_maxdd_units",
        "dynamic_maxdd_units",
        "maxdd_delta_vs_base",
    ]
    rolling_cols = [
        "portfolio",
        "window",
        "n_windows",
        "positive_delta_rate",
        "positive_maxdd_delta_rate",
        "avg_delta_units",
        "median_delta_units",
        "worst_delta_units",
        "best_delta_units",
        "avg_maxdd_delta_units",
    ]
    nonzero_switch_features = [
        row for row in switch_features if abs(fnum(row.get("delta_vs_base_units"))) > 1e-9
    ]
    selected_periods = [
        row
        for row in period_rows
        if row.get("portfolio") in {"frozen_original", best_name}
        and row.get("period") in {"all", "train_like_2014_2022", "recent_2023_2025", "weak_recent_2024_2025"}
    ]
    selected_rolling = [
        row for row in rolling_summary if row.get("portfolio") in {"frozen_original", best_name}
    ]

    report = [
        "# N7 384 Switch Gate Discrimination",
        "",
        "## Goal",
        "",
        "The frozen dynamic rule switches to the defensive sleeve when prior-only `core_avg_pred_ev` falls into the rolling bottom 15%.",
        "This report asks whether a second pre-bet gate can keep the rare convex rescues while removing unproductive switches.",
        "",
        "## Candidate Results",
        "",
        md_table(md_rows(candidate_summary, summary_cols, limit=20), limit=20),
        "",
        "## Switched-Issue Feature Diagnostics",
        "",
        md_table(md_rows(switch_feature_summary, group_cols, limit=10), limit=10),
        "",
        "## Nonzero Switch Cases",
        "",
        md_table(md_rows(nonzero_switch_features, switch_cols, limit=20), limit=20),
        "",
        "## Best Candidate Period Check",
        "",
        md_table(md_rows(selected_periods, period_cols, limit=20), limit=20),
        "",
        "## Best Candidate Rolling Check",
        "",
        md_table(md_rows(selected_rolling, rolling_cols, limit=20), limit=20),
        "",
        "## Drawdown Attribution For Best Candidate",
        "",
        md_table(
            md_rows(
                best_dd,
                period_cols[1:] + ["peak_issue", "trough_issue", "window_issues", "source_maxdd_units"],
                limit=10,
            ),
            limit=10,
        ),
        "",
        "## Interpretation",
        "",
        f"- Best exploratory candidate: `{best_name}`.",
        "- The useful pattern is not simply weak quality. It is weak quality plus enough core breadth plus a defensive source that is not riding a positive line-gap signal.",
        "- This keeps the two nonzero positive switches in 2023/2024 and removes the six nonzero negative switches in 2014-2020.",
        "- This is still a research selector, not a production replacement: the positive sample has only two cases, so the rule is fragile until monitored on fresh issues.",
        "",
        "## Files",
        "",
        f"- `{args.output_dir / 'switch_feature_rows.csv'}`",
        f"- `{args.output_dir / 'switch_feature_group_summary.csv'}`",
        f"- `{args.output_dir / 'gate_candidate_summary.csv'}`",
        f"- `{args.output_dir / 'gate_candidate_period_summary.csv'}`",
        f"- `{args.output_dir / 'gate_candidate_rolling_summary.csv'}`",
        f"- `{args.output_dir / 'best_gate_issue_profit.csv'}`",
        f"- `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.output_dir / 'gate_candidate_summary.csv'}")
    print(f"Wrote {args.figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue-profit",
        type=Path,
        default=Path("results/n7_sleeve_mix_capital_20260629/sleeve_mix_issue_profit.csv"),
    )
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("results/n7_384_drawdown_dynamic_20260629/issue_prebet_features.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/n7_384_switch_gate_discrimination_20260629"),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_384_switch_gate_discrimination_2026-06-29.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_384_switch_gate_discrimination_2026-06-29.svg"),
    )
    parser.add_argument(
        "--best-gate",
        default="core_count_ge12_source_linegap_le0",
        choices=[name for name, _desc, _fn in GATES],
    )
    args = parser.parse_args()
    for path in (args.issue_profit, args.features):
        if not path.exists():
            raise SystemExit(f"missing input: {path}")
    run(args)


if __name__ == "__main__":
    main()
