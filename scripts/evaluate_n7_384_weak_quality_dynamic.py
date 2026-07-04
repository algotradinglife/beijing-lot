#!/usr/bin/env python3
"""Analyze weak N7 issue quality and formally replay 384 dynamic allocators."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_384_drawdown_dynamic import (
    CURRENT_PORTFOLIO,
    SELECTED_PORTFOLIO,
    drawdown_window,
    fnum,
    full_loss,
    max_dead_streak,
    max_drawdown_units,
    max_loss_streak,
    percentile,
    row_order,
    row_year,
    summarize_issue_rows,
)
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


BASE_BUDGET = 384.0
SOURCE_FEATURES = Path("results/n7_384_drawdown_dynamic_20260629/issue_prebet_features.csv")
SOURCE_ISSUE_PROFIT = Path("results/n7_sleeve_mix_capital_20260629/sleeve_mix_issue_profit.csv")

QUALITY_FEATURES = [
    ("core_avg_pred_ev", "low", "predEV"),
    ("core_avg_selector_score", "low", "selector"),
    ("core_avg_line_gap_net", "low", "line_gap"),
    ("core_linegap_x_tickets", "low", "line_gap_x_count"),
    ("core_avg_q", "low", "q"),
    ("core_avg_conf", "low", "confidence"),
    ("core_ticket_count", "low", "core_count"),
    ("core_avg_pred_hit", "low", "pred_hit"),
]

FORMAL_FEATURES = [
    "core_avg_pred_ev",
    "core_avg_selector_score",
    "core_avg_line_gap_net",
    "core_linegap_x_tickets",
    "core_avg_q",
    "weak_count_l20",
    "weak_score_l20",
]

DEFENSIVE_PORTFOLIOS = [
    "b384_dd64_smooth100",
    "b384_dd32_smooth100",
    "b384_dd64_smooth80_convex19",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv_all(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    first = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(first))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=first + extra)
        writer.writeheader()
        writer.writerows(rows)


def load_portfolios(path: Path) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in read_rows(path):
        out[str(row["portfolio"])][str(row["issue"])] = dict(row)
    return dict(out)


def ordered_issues(rows_by_portfolio: dict[str, dict[str, dict[str, object]]]) -> list[str]:
    selected = rows_by_portfolio[SELECTED_PORTFOLIO]
    return sorted(selected, key=lambda issue: row_order(selected[issue]))


def load_features(path: Path) -> dict[str, dict[str, object]]:
    rows = read_rows(path)
    out: dict[str, dict[str, object]] = {}
    for row in rows:
        copied: dict[str, object] = dict(row)
        for key, value in row.items():
            if key in {"issue"}:
                continue
            try:
                copied[key] = float(value)
            except (TypeError, ValueError):
                copied[key] = value
        out[str(row["issue"])] = copied
    return out


def rolling_flags(
    *,
    issues: list[str],
    features_by_issue: dict[str, dict[str, object]],
    history: int,
    min_history: int,
    q: float,
) -> dict[str, dict[str, object]]:
    histories: dict[str, list[float]] = {feature: [] for feature, _side, _label in QUALITY_FEATURES}
    out: dict[str, dict[str, object]] = {}
    for issue in issues:
        src = features_by_issue.get(issue, {})
        row: dict[str, object] = {"issue": issue, "history_n": 0}
        weak_count = 0
        weak_score = 0.0
        valid_count = 0
        for feature, side, label in QUALITY_FEATURES:
            value = fnum(src.get(feature), math.nan)
            hist = histories[feature][-history:]
            threshold = math.nan
            flag = 0
            severity = 0.0
            if len(hist) >= min_history and math.isfinite(value):
                threshold = percentile(hist, q if side == "low" else 1.0 - q)
                if math.isfinite(threshold):
                    if side == "low":
                        flag = int(value <= threshold)
                        spread = abs(threshold) + abs(percentile(hist, 0.50)) + 1e-9
                        severity = max(0.0, (threshold - value) / spread)
                    else:
                        flag = int(value >= threshold)
                        spread = abs(threshold) + abs(percentile(hist, 0.50)) + 1e-9
                        severity = max(0.0, (value - threshold) / spread)
            row[f"{label}_value"] = value if math.isfinite(value) else ""
            row[f"{label}_threshold_l{int(q * 100)}"] = threshold if math.isfinite(threshold) else ""
            row[f"{label}_weak_l{int(q * 100)}"] = flag
            row[f"{label}_severity_l{int(q * 100)}"] = severity
            weak_count += flag
            weak_score += severity
            valid_count += int(math.isfinite(value))
            if math.isfinite(value):
                histories[feature].append(value)
        row["history_n"] = min((len(vals) for vals in histories.values()), default=0)
        row[f"weak_count_l{int(q * 100)}"] = weak_count
        row[f"weak_score_l{int(q * 100)}"] = weak_score
        row[f"weak_valid_count_l{int(q * 100)}"] = valid_count
        out[issue] = row
    return out


def merge_feature_rows(
    *,
    issues: list[str],
    selected_rows: dict[str, dict[str, object]],
    features_by_issue: dict[str, dict[str, object]],
    flag_sets: dict[float, dict[str, dict[str, object]]],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    selected_series = [selected_rows[issue] for issue in issues]
    maxdd = drawdown_window(selected_series)
    maxdd_issues = {
        str(row["issue"])
        for row in selected_series[int(maxdd["start_idx"]) : int(maxdd["end_idx"]) + 1]
    }
    for issue in issues:
        base = dict(features_by_issue.get(issue, {}))
        selected = selected_rows[issue]
        row: dict[str, object] = {
            "issue": issue,
            "issue_order": selected.get("issue_order", ""),
            "calendar_year": selected.get("calendar_year", ""),
            "profit_units": fnum(selected.get("profit_units")),
            "roi": fnum(selected.get("profit_units")) / BASE_BUDGET,
            "full_loss": int(full_loss(selected)),
            "win": int(fnum(selected.get("profit_units")) > 0),
            "in_maxdd_window": int(issue in maxdd_issues),
        }
        for key, value in base.items():
            if key not in row:
                row[key] = value
        for q, flags in flag_sets.items():
            for key, value in flags.get(issue, {}).items():
                if key != "issue":
                    row[key] = value
        out.append(row)
    return out


def summarize_subset(name: str, rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {
            "segment": name,
            "n_issues": 0,
            "profit_units": 0.0,
            "roi": math.nan,
            "win_rate": math.nan,
            "full_loss_rate": math.nan,
            "max_drawdown_units": math.nan,
            "max_loss_streak": 0,
            "max_dead_streak": 0,
        }
    stake = len(rows) * BASE_BUDGET
    profit = sum(fnum(row.get("profit_units")) for row in rows)
    return {
        "segment": name,
        "n_issues": len(rows),
        "stake_units": stake,
        "profit_units": profit,
        "roi": profit / stake if stake else math.nan,
        "profit_per_issue": profit / len(rows),
        "win_rate": sum(1 for row in rows if fnum(row.get("profit_units")) > 0) / len(rows),
        "full_loss_rate": sum(1 for row in rows if int(fnum(row.get("full_loss"))) == 1) / len(rows),
        "max_drawdown_units": max_drawdown_units(rows),
        "max_loss_streak": max_loss_streak(rows),
        "max_dead_streak": max_dead_streak_from_flag(rows),
        "maxdd_window_capture_rate": sum(1 for row in rows if int(fnum(row.get("in_maxdd_window"))) == 1)
        / max(1, sum(1 for row in rows if True)),
    }


def max_dead_streak_from_flag(rows: list[dict[str, object]]) -> int:
    cur = 0
    best = 0
    for row in sorted(rows, key=row_order):
        if int(fnum(row.get("full_loss"))) == 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def weak_quality_tables(issue_rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    rows = sorted(issue_rows, key=row_order)
    full_loss_total = sum(int(fnum(row.get("full_loss"))) for row in rows)
    maxdd_total = sum(int(fnum(row.get("in_maxdd_window"))) for row in rows)

    segment_rows: list[dict[str, object]] = [
        summarize_subset("all", rows),
        summarize_subset("maxdd_window", [row for row in rows if int(fnum(row.get("in_maxdd_window"))) == 1]),
        summarize_subset("not_maxdd_window", [row for row in rows if int(fnum(row.get("in_maxdd_window"))) == 0]),
    ]
    for q in (0.15, 0.20, 0.25, 0.30):
        count_col = f"weak_count_l{int(q * 100)}"
        score_col = f"weak_score_l{int(q * 100)}"
        for cutoff in (1, 2, 3, 4):
            sub = [row for row in rows if fnum(row.get(count_col), -1) >= cutoff]
            summary = summarize_subset(f"weak_count_l{int(q * 100)}_ge{cutoff}", sub)
            summary.update(
                {
                    "rule": count_col,
                    "cutoff": cutoff,
                    "full_loss_capture": sum(int(fnum(row.get("full_loss"))) for row in sub) / max(full_loss_total, 1),
                    "maxdd_window_capture": sum(int(fnum(row.get("in_maxdd_window"))) for row in sub) / max(maxdd_total, 1),
                }
            )
            segment_rows.append(summary)
        vals = sorted(fnum(row.get(score_col), math.nan) for row in rows if math.isfinite(fnum(row.get(score_col), math.nan)))
        if vals:
            threshold = vals[int(max(0, min(len(vals) - 1, math.floor(0.80 * (len(vals) - 1)))))]
            sub = [row for row in rows if fnum(row.get(score_col), -1) >= threshold and fnum(row.get("history_n"), 0) >= 40]
            summary = summarize_subset(f"weak_score_l{int(q * 100)}_top20", sub)
            summary.update(
                {
                    "rule": score_col,
                    "cutoff": threshold,
                    "full_loss_capture": sum(int(fnum(row.get("full_loss"))) for row in sub) / max(full_loss_total, 1),
                    "maxdd_window_capture": sum(int(fnum(row.get("in_maxdd_window"))) for row in sub) / max(maxdd_total, 1),
                }
            )
            segment_rows.append(summary)

    by_score: list[dict[str, object]] = []
    for q in (0.15, 0.20, 0.25, 0.30):
        count_col = f"weak_count_l{int(q * 100)}"
        for score, sub in sorted(_groupby(rows, lambda row, c=count_col: int(fnum(row.get(c), 0))).items()):
            summary = summarize_subset(f"{count_col}_{score}", sub)
            summary.update({"weak_quantile": q, "weak_count": score})
            by_score.append(summary)

    signal_rows: list[dict[str, object]] = []
    for q in (0.15, 0.20, 0.25, 0.30):
        for _feature, _side, label in QUALITY_FEATURES:
            col = f"{label}_weak_l{int(q * 100)}"
            sub = [row for row in rows if int(fnum(row.get(col), 0)) == 1]
            summary = summarize_subset(col, sub)
            summary.update(
                {
                    "signal": col,
                    "weak_quantile": q,
                    "full_loss_capture": sum(int(fnum(row.get("full_loss"))) for row in sub) / max(full_loss_total, 1),
                    "maxdd_window_capture": sum(int(fnum(row.get("in_maxdd_window"))) for row in sub) / max(maxdd_total, 1),
                }
            )
            signal_rows.append(summary)
    signal_rows.sort(key=lambda row: (fnum(row.get("full_loss_rate")), fnum(row.get("maxdd_window_capture"))), reverse=True)
    return segment_rows, by_score, signal_rows


def _groupby(rows: list[dict[str, object]], key_fn) -> dict[object, list[dict[str, object]]]:
    out: dict[object, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        out[key_fn(row)].append(row)
    return dict(out)


def replay_dynamic(
    *,
    name: str,
    issues: list[str],
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    issue_rows_by_issue: dict[str, dict[str, object]],
    feature: str,
    bad_side: str,
    q: float,
    defensive_portfolio: str,
    history: int,
    min_history: int,
) -> list[dict[str, object]]:
    histories: list[float] = []
    out: list[dict[str, object]] = []
    selected_rows = rows_by_portfolio[SELECTED_PORTFOLIO]
    for issue in issues:
        current = fnum(issue_rows_by_issue.get(issue, {}).get(feature), math.nan)
        recent = histories[-history:]
        threshold = math.nan
        chosen = SELECTED_PORTFOLIO
        state = "base"
        if len(recent) >= min_history and math.isfinite(current):
            threshold = percentile(recent, q if bad_side == "low" else 1.0 - q)
            is_defensive = current <= threshold if bad_side == "low" else current >= threshold
            if is_defensive and defensive_portfolio in rows_by_portfolio:
                chosen = defensive_portfolio
                state = "defensive"
        source = rows_by_portfolio.get(chosen, {}).get(issue) or selected_rows[issue]
        row = dict(source)
        row["portfolio"] = name
        row["chosen_portfolio"] = chosen
        row["state"] = state
        row["quality_feature"] = feature
        row["quality_value"] = current if math.isfinite(current) else ""
        row["quality_threshold"] = threshold if math.isfinite(threshold) else ""
        row["quality_history_n"] = len(recent)
        out.append(row)
        if math.isfinite(current):
            histories.append(current)
    return out


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for (portfolio, year), vals in sorted(_groupby(rows, lambda row: (str(row["portfolio"]), row_year(row))).items()):
        stake = sum(fnum(row.get("stake_units"), BASE_BUDGET) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "portfolio": portfolio,
                "year": year,
                "n_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals),
                "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals),
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def summarize_dynamic(
    rows: list[dict[str, object]],
    *,
    feature: str,
    q: float,
    defensive_portfolio: str,
    history: int,
    baseline: dict[str, object],
) -> dict[str, object]:
    summary = summarize_issue_rows(rows, portfolio=str(rows[0]["portfolio"]), budget=BASE_BUDGET)
    states = Counter(str(row.get("state")) for row in rows)
    chosen = Counter(str(row.get("chosen_portfolio")) for row in rows)
    best = max(fnum(row.get("profit_units")) for row in rows)
    stake = sum(fnum(row.get("stake_units"), BASE_BUDGET) for row in rows)
    profit = sum(fnum(row.get("profit_units")) for row in rows)
    summary.update(
        {
            "feature": feature,
            "q": q,
            "defensive_portfolio": defensive_portfolio,
            "history": history,
            "state_mix": ";".join(f"{key}:{value}" for key, value in sorted(states.items())),
            "chosen_mix": ";".join(f"{key}:{value}" for key, value in chosen.most_common()),
            "profit_per_256_delta_vs_base": fnum(summary.get("profit_per_256")) - fnum(baseline.get("profit_per_256")),
            "roi_delta_vs_base": fnum(summary.get("roi")) - fnum(baseline.get("roi")),
            "maxdd_delta_vs_base": fnum(summary.get("max_drawdown_units")) - fnum(baseline.get("max_drawdown_units")),
            "recent_profit_per_256_delta_vs_base": fnum(summary.get("recent_profit_per_256"))
            - fnum(baseline.get("recent_profit_per_256")),
            "roi_ex_best_issue": (profit - best) / (stake - BASE_BUDGET) if stake > BASE_BUDGET else math.nan,
        }
    )
    return summary


def formal_dynamic_grid(
    *,
    issues: list[str],
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    issue_rows: list[dict[str, object]],
    output_dir: Path,
) -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]], list[dict[str, object]]]:
    issue_rows_by_issue = {str(row["issue"]): row for row in issue_rows}
    selected_rows = [rows_by_portfolio[SELECTED_PORTFOLIO][issue] for issue in issues]
    baseline = summarize_issue_rows(selected_rows, portfolio=SELECTED_PORTFOLIO, budget=BASE_BUDGET)
    summaries: list[dict[str, object]] = []
    selected_series: dict[str, list[dict[str, object]]] = {SELECTED_PORTFOLIO: selected_rows}

    for feature in FORMAL_FEATURES:
        bad_side = "low"
        if feature.startswith("weak_"):
            bad_side = "high"
        for q in (0.10, 0.15, 0.20, 0.25, 0.30):
            for defensive in DEFENSIVE_PORTFOLIOS:
                if defensive not in rows_by_portfolio:
                    continue
                for history in (60, 80, 120):
                    name = (
                        f"dyn_{feature}_{bad_side}_q{int(q * 100)}_h{history}"
                        f"__def_{defensive}__base_{SELECTED_PORTFOLIO}"
                    )
                    rows = replay_dynamic(
                        name=name,
                        issues=issues,
                        rows_by_portfolio=rows_by_portfolio,
                        issue_rows_by_issue=issue_rows_by_issue,
                        feature=feature,
                        bad_side=bad_side,
                        q=q,
                        defensive_portfolio=defensive,
                        history=history,
                        min_history=40,
                    )
                    summaries.append(
                        summarize_dynamic(
                            rows,
                            feature=feature,
                            q=q,
                            defensive_portfolio=defensive,
                            history=history,
                            baseline=baseline,
                        )
                    )
                    selected_series[name] = rows

    summary_df = pd.DataFrame(summaries)
    if summary_df.empty:
        return [], {}, []
    summary_df["balanced_score"] = (
        summary_df["profit_per_256_delta_vs_base"]
        + 4.0 * summary_df["maxdd_delta_vs_base"]
        + 0.35 * summary_df["recent_profit_per_256_delta_vs_base"]
    )
    summary_df = summary_df.sort_values(["balanced_score", "profit_per_256"], ascending=[False, False])
    summaries = summary_df.to_dict("records")

    chosen_names = [SELECTED_PORTFOLIO]
    for row in summaries[:8]:
        name = str(row["portfolio"])
        if name not in chosen_names:
            chosen_names.append(name)
    selected_issue_rows: list[dict[str, object]] = []
    chosen_series = {SELECTED_PORTFOLIO: selected_rows}
    for name in chosen_names[1:]:
        rows = selected_series[name]
        selected_issue_rows.extend(rows)
        chosen_series[name] = rows
    write_csv_all(output_dir / "dynamic_allocator_formal_selected_issue_profit.csv", selected_issue_rows)
    annual = annual_rows([row for name in chosen_names for row in selected_series[name]])
    return summaries, chosen_series, annual


def dynamic_stability_summary(dynamic_summary: list[dict[str, object]]) -> list[dict[str, object]]:
    if not dynamic_summary:
        return []
    df = pd.DataFrame(dynamic_summary).copy()
    df["positive_both"] = (df["profit_per_256_delta_vs_base"] > 0) & (df["maxdd_delta_vs_base"] > 0)
    grouped = []
    for keys, sub in df.groupby(["feature", "q", "defensive_portfolio"], sort=False):
        feature, q, defensive = keys
        grouped.append(
            {
                "feature": feature,
                "q": q,
                "defensive_portfolio": defensive,
                "n_histories": len(sub),
                "positive_both_count": int(sub["positive_both"].sum()),
                "positive_both_rate": float(sub["positive_both"].mean()),
                "profit_delta_mean": float(sub["profit_per_256_delta_vs_base"].mean()),
                "profit_delta_min": float(sub["profit_per_256_delta_vs_base"].min()),
                "profit_delta_max": float(sub["profit_per_256_delta_vs_base"].max()),
                "maxdd_delta_mean": float(sub["maxdd_delta_vs_base"].mean()),
                "maxdd_delta_min": float(sub["maxdd_delta_vs_base"].min()),
                "maxdd_delta_max": float(sub["maxdd_delta_vs_base"].max()),
                "recent_delta_mean": float(sub["recent_profit_per_256_delta_vs_base"].mean()),
                "best_balanced_score": float(sub["balanced_score"].max()),
            }
        )
    grouped.sort(
        key=lambda row: (
            fnum(row["positive_both_rate"]),
            fnum(row["maxdd_delta_mean"]),
            fnum(row["profit_delta_mean"]),
        ),
        reverse=True,
    )
    return grouped


def equity_points(rows: list[dict[str, object]]) -> list[tuple[int, float, int]]:
    equity = 0.0
    points: list[tuple[int, float, int]] = []
    for idx, row in enumerate(sorted(rows, key=row_order)):
        equity += fnum(row.get("profit_units"))
        points.append((idx, equity, row_year(row)))
    return points


def write_equity_svg(path: Path, series: dict[str, list[dict[str, object]]]) -> None:
    width, height = 1220, 640
    left, right, top, bottom = 76, 28, 32, 74
    plot_w, plot_h = width - left - right, height - top - bottom
    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#bcbd22", "#111827"]
    points_by_name = {name: equity_points(rows) for name, rows in series.items()}
    all_points = [point for pts in points_by_name.values() for point in pts]
    if not all_points:
        path.write_text("", encoding="utf-8")
        return
    max_x = max(x for x, _y, _year in all_points) or 1
    min_y = min(0.0, min(y for _x, y, _year in all_points))
    max_y = max(0.0, max(y for _x, y, _year in all_points))
    pad = max((max_y - min_y) * 0.08, 1000.0)
    min_y -= pad
    max_y += pad

    def sx(x: int) -> float:
        return left + plot_w * x / max_x

    def sy(y: float) -> float:
        return top + plot_h * (max_y - y) / (max_y - min_y)

    elems = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
    ]
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y_value = min_y + (max_y - min_y) * frac
        y = sy(y_value)
        elems.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        elems.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-size="12" fill="#374151">{y_value:,.0f}</text>')
    base_points = next(iter(points_by_name.values()))
    marks: dict[int, int] = {}
    for x, _y, year in base_points:
        marks.setdefault(year, x)
    for year, x0 in sorted(marks.items()):
        if year % 2 == 0 or year in (2014, 2025):
            x = sx(x0)
            elems.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_h}" stroke="#f3f4f6"/>')
            elems.append(f'<text x="{x:.2f}" y="{height - 38}" text-anchor="middle" font-size="12" fill="#374151">{year}</text>')
    zero = sy(0)
    elems.append(f'<line x1="{left}" y1="{zero:.2f}" x2="{left + plot_w}" y2="{zero:.2f}" stroke="#9ca3af" stroke-dasharray="4 4"/>')
    for idx, (name, pts) in enumerate(points_by_name.items()):
        color = colors[idx % len(colors)]
        coords = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y, _year in pts)
        elems.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.2"/>')
        lx, ly = left + 12 + (idx % 2) * 540, top + 18 + (idx // 2) * 22
        elems.append(f'<line x1="{lx}" y1="{ly - 5}" x2="{lx + 26}" y2="{ly - 5}" stroke="{color}" stroke-width="3"/>')
        elems.append(f'<text x="{lx + 34}" y="{ly}" font-size="12" fill="#111827">{name[:92]}</text>')
    elems.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(elems), encoding="utf-8")


def md_rows(rows: list[dict[str, object]], cols: list[str], limit: int = 20) -> list[dict[str, object]]:
    return [{col: row.get(col, "") for col in cols} for row in rows[:limit]]


def run(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows_by_portfolio = load_portfolios(args.issue_profit)
    features_by_issue = load_features(args.features)
    issues = ordered_issues(rows_by_portfolio)
    selected_rows_by_issue = rows_by_portfolio[SELECTED_PORTFOLIO]

    flag_sets = {
        q: rolling_flags(
            issues=issues,
            features_by_issue=features_by_issue,
            history=args.history_issues,
            min_history=args.min_history_issues,
            q=q,
        )
        for q in (0.15, 0.20, 0.25, 0.30)
    }
    issue_rows = merge_feature_rows(
        issues=issues,
        selected_rows=selected_rows_by_issue,
        features_by_issue=features_by_issue,
        flag_sets=flag_sets,
    )
    segment_summary, by_score, signal_summary = weak_quality_tables(issue_rows)
    dynamic_summary, dynamic_series, dynamic_annual = formal_dynamic_grid(
        issues=issues,
        rows_by_portfolio=rows_by_portfolio,
        issue_rows=issue_rows,
        output_dir=args.output_dir,
    )
    stability_summary = dynamic_stability_summary(dynamic_summary)

    write_csv_all(args.output_dir / "weak_quality_issue_features.csv", issue_rows)
    write_csv_all(args.output_dir / "weak_quality_segment_summary.csv", segment_summary)
    write_csv_all(args.output_dir / "weak_quality_by_score.csv", by_score)
    write_csv_all(args.output_dir / "weak_quality_signal_summary.csv", signal_summary)
    write_csv_all(args.output_dir / "dynamic_allocator_formal_summary.csv", dynamic_summary)
    write_csv_all(args.output_dir / "dynamic_allocator_formal_annual.csv", dynamic_annual)
    write_csv_all(args.output_dir / "dynamic_allocator_stability_summary.csv", stability_summary)
    write_equity_svg(args.figure_path, dynamic_series)

    dyn_df = pd.DataFrame(dynamic_summary)
    positive = []
    best_dd = []
    if not dyn_df.empty:
        positive = dyn_df[
            (dyn_df["profit_per_256_delta_vs_base"] > 0)
            & (dyn_df["maxdd_delta_vs_base"] > 0)
        ].sort_values(["maxdd_delta_vs_base", "profit_per_256_delta_vs_base"], ascending=[False, False])
        best_dd = dyn_df.sort_values(
            ["maxdd_delta_vs_base", "profit_per_256_delta_vs_base"],
            ascending=[False, False],
        )
    selected_static = summarize_issue_rows(
        [rows_by_portfolio[SELECTED_PORTFOLIO][issue] for issue in issues],
        portfolio=SELECTED_PORTFOLIO,
        budget=BASE_BUDGET,
    )
    weak_cols = [
        "segment",
        "n_issues",
        "profit_units",
        "roi",
        "profit_per_issue",
        "win_rate",
        "full_loss_rate",
        "max_drawdown_units",
        "max_dead_streak",
        "full_loss_capture",
        "maxdd_window_capture",
    ]
    dyn_cols = [
        "portfolio",
        "feature",
        "q",
        "defensive_portfolio",
        "history",
        "profit_per_256",
        "profit_per_256_delta_vs_base",
        "roi",
        "max_drawdown_units",
        "maxdd_delta_vs_base",
        "max_dead_streak",
        "recent_profit_per_256",
        "recent_profit_per_256_delta_vs_base",
        "state_mix",
    ]
    report = [
        "# N7 384 Weak Quality And Dynamic Allocator",
        "",
        "## Scope",
        "",
        f"- Static reference: `{SELECTED_PORTFOLIO}`.",
        "- Weak quality flags use prior rolling feature history only.",
        f"- Rolling history: `{args.history_issues}` issues; minimum history: `{args.min_history_issues}` issues.",
        "- Formal allocator keeps the 384-unit budget fixed and only switches the N7 sleeve mix.",
        "",
        "## Static Reference",
        "",
        md_table([selected_static]),
        "",
        "## Weak Quality Segments",
        "",
        md_table(md_rows(segment_summary, weak_cols, limit=30), limit=30),
        "",
        "## Weak Count Buckets",
        "",
        md_table(md_rows(by_score, ["segment", "weak_quantile", "weak_count", "n_issues", "roi", "win_rate", "full_loss_rate", "max_drawdown_units"], limit=80), limit=80),
        "",
        "## Single Weak Signals",
        "",
        md_table(md_rows(signal_summary, weak_cols + ["signal"], limit=32), limit=32),
        "",
        "## Dynamic Allocator: Profit And MaxDD Both Improve",
        "",
        md_table(md_rows(positive.to_dict("records") if isinstance(positive, pd.DataFrame) else [], dyn_cols, limit=30), limit=30),
        "",
        "## Dynamic Allocator: Best MaxDD Improvement",
        "",
        md_table(md_rows(best_dd.to_dict("records") if isinstance(best_dd, pd.DataFrame) else [], dyn_cols, limit=30), limit=30),
        "",
        "## Dynamic Allocator: Top Balanced",
        "",
        md_table(md_rows(dynamic_summary, dyn_cols + ["balanced_score"], limit=30), limit=30),
        "",
        "## Parameter Stability",
        "",
        md_table(
            md_rows(
                stability_summary,
                [
                    "feature",
                    "q",
                    "defensive_portfolio",
                    "n_histories",
                    "positive_both_count",
                    "positive_both_rate",
                    "profit_delta_mean",
                    "profit_delta_min",
                    "maxdd_delta_mean",
                    "maxdd_delta_min",
                    "recent_delta_mean",
                ],
                limit=40,
            ),
            limit=40,
        ),
        "",
        "## Interpretation",
        "",
    ]
    if segment_summary:
        wc20 = [row for row in segment_summary if row.get("segment") == "weak_count_l20_ge2"]
        if wc20:
            row = wc20[0]
            report.append(
                f"- `weak_count_l20 >= 2` captures `{fnum(row.get('maxdd_window_capture')):.1%}` of the maxDD-window issues and `{fnum(row.get('full_loss_capture')):.1%}` of full-loss issues, with ROI `{fnum(row.get('roi')):.3f}`."
            )
    if isinstance(positive, pd.DataFrame) and not positive.empty:
        best = positive.iloc[0].to_dict()
        report.append(
            f"- Best strict positive dynamic candidate: `{best['portfolio']}`; profit/256 delta `{fnum(best['profit_per_256_delta_vs_base']):.1f}`, maxDD delta `{fnum(best['maxdd_delta_vs_base']):.1f}`."
        )
    else:
        report.append("- No formal dynamic candidate improved both profit/256 and maxDD in this grid.")
    report.extend(
        [
            "- Weak quality flags are not no-trade filters: they raise full-loss risk, but they also contain many high-convexity winners. Use them to switch sleeve style, not to blindly skip issues.",
            "- Treat dynamic switching as a paper arm unless it remains stable across a stricter walk-forward split and recent-window checks.",
            "",
            "## Files",
            "",
            f"- `{args.output_dir / 'weak_quality_issue_features.csv'}`",
            f"- `{args.output_dir / 'weak_quality_segment_summary.csv'}`",
            f"- `{args.output_dir / 'weak_quality_by_score.csv'}`",
            f"- `{args.output_dir / 'weak_quality_signal_summary.csv'}`",
            f"- `{args.output_dir / 'dynamic_allocator_formal_summary.csv'}`",
            f"- `{args.output_dir / 'dynamic_allocator_formal_annual.csv'}`",
            f"- `{args.output_dir / 'dynamic_allocator_stability_summary.csv'}`",
            f"- `{args.figure_path}`",
            "",
        ]
    )
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")
    print(f"Wrote {args.output_dir / 'dynamic_allocator_formal_summary.csv'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=SOURCE_FEATURES)
    parser.add_argument("--issue-profit", type=Path, default=SOURCE_ISSUE_PROFIT)
    parser.add_argument("--history-issues", type=int, default=80)
    parser.add_argument("--min-history-issues", type=int, default=40)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/n7_384_weak_quality_dynamic_20260629"),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_384_weak_quality_dynamic_allocator_2026-06-29.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_384_weak_quality_dynamic_allocator_2026-06-29.svg"),
    )
    args = parser.parse_args()
    for path in (args.features, args.issue_profit):
        if not path.exists():
            raise SystemExit(f"missing input: {path}")
    run(args)


if __name__ == "__main__":
    main()
