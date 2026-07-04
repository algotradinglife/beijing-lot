#!/usr/bin/env python3
"""Analyze the selected N7 384 profile drawdown and test dynamic sleeve allocation."""
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

from scripts.walkforward_beidan_strategy_eval import md_table


SELECTED_PORTFOLIO = "b384_dd32_smooth80_convex19"
CURRENT_PORTFOLIO = "current_reference_256"
SOURCE_STRATEGY = "ev_m0p95_p0p8_full_opt__budget256_fractional"
CORE_SELECTOR = "topology_neg0_ge6_d0"
EXACT_SELECTOR = "topology_exact_6n0_1p3_d0"

DD_ARM = "n7prot_same_ticket2_alt_risk__budget256_fractional"
SMOOTH_ARM = "n7prot_same_ticket4_full_risk__budget256_fractional"
SMOOTH_SAFE_ARM = "n7prot_c4_k2_full_risk__budget256_fractional"
CONVEX_ARM = "n7prot_same_ticket2_draw_risk__budget256_fractional"

SELECTED_ALLOCATION = {
    "current": 256.0,
    DD_ARM: 32.0,
    SMOOTH_ARM: 76.8,
    CONVEX_ARM: 19.2,
}


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
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


def row_order(row: dict[str, object]) -> tuple[int, str]:
    order = row.get("issue_order")
    if order not in ("", None):
        return int(float(str(order))), str(row.get("issue", ""))
    return 10**9, str(row.get("issue", ""))


def row_year(row: dict[str, object]) -> int:
    year = row.get("calendar_year")
    if year not in ("", None):
        return int(float(str(year)))
    issue = str(row.get("issue", ""))
    if len(issue) >= 2 and issue[:2].isdigit():
        yy = int(issue[:2])
        return 2000 + yy if yy < 80 else 1900 + yy
    return 0


def full_loss(row: dict[str, object]) -> bool:
    stake = fnum(row.get("stake_units"))
    return stake > 0 and fnum(row.get("profit_units")) <= -0.999 * stake


def max_drawdown_units(rows: list[dict[str, object]]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for row in sorted(rows, key=row_order):
        equity += fnum(row.get("profit_units"))
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def max_loss_streak(rows: list[dict[str, object]]) -> int:
    cur = 0
    best = 0
    for row in sorted(rows, key=row_order):
        if fnum(row.get("profit_units")) <= 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def max_dead_streak(rows: list[dict[str, object]]) -> int:
    cur = 0
    best = 0
    for row in sorted(rows, key=row_order):
        if full_loss(row):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def drawdown_window(rows: list[dict[str, object]]) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    equity = 0.0
    peak = 0.0
    peak_idx = -1
    worst_dd = 0.0
    worst = {
        "peak_issue": "",
        "trough_issue": "",
        "start_idx": 0,
        "end_idx": -1,
        "maxdd_units": 0.0,
        "issues": 0,
    }
    for idx, row in enumerate(ordered):
        equity += fnum(row.get("profit_units"))
        if equity >= peak:
            peak = equity
            peak_idx = idx
            continue
        dd = equity - peak
        if dd < worst_dd:
            worst_dd = dd
            worst = {
                "peak_issue": str(ordered[peak_idx]["issue"]) if peak_idx >= 0 else "",
                "trough_issue": str(row["issue"]),
                "start_idx": peak_idx + 1,
                "end_idx": idx,
                "maxdd_units": dd,
                "issues": idx - peak_idx,
            }
    return worst


def summarize_issue_rows(rows: list[dict[str, object]], *, portfolio: str, budget: float) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in ordered)
    profit = sum(fnum(row.get("profit_units")) for row in ordered)
    recent = [row for row in ordered if 2023 <= row_year(row) <= 2025]
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    best = max((fnum(row.get("profit_units")) for row in ordered), default=0.0)
    return {
        "portfolio": portfolio,
        "issues": len(ordered),
        "stake_units": stake,
        "profit_units": profit,
        "profit_per_256": profit / (budget / 256.0) if budget else math.nan,
        "roi": profit / stake if stake else math.nan,
        "issue_win_rate": sum(1 for row in ordered if fnum(row.get("profit_units")) > 0) / len(ordered)
        if ordered
        else math.nan,
        "non_full_loss_rate": sum(1 for row in ordered if not full_loss(row)) / len(ordered) if ordered else math.nan,
        "full_loss_rate": sum(1 for row in ordered if full_loss(row)) / len(ordered) if ordered else math.nan,
        "max_drawdown_units": max_drawdown_units(ordered),
        "max_drawdown_per_256": max_drawdown_units(ordered) / (budget / 256.0) if budget else math.nan,
        "max_loss_streak": max_loss_streak(ordered),
        "max_dead_streak": max_dead_streak(ordered),
        "best_issue_profit_units": best,
        "roi_ex_best_issue": (profit - best) / (stake - budget) if stake > budget else math.nan,
        "recent_profit_per_256": recent_profit / (budget / 256.0) if budget else math.nan,
    }


def load_portfolio_issue_rows(path: Path) -> dict[str, dict[str, dict[str, object]]]:
    rows_by_port: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in read_csv_rows(path):
        port = str(row["portfolio"])
        issue = str(row["issue"])
        if issue in rows_by_port[port]:
            continue
        copied = dict(row)
        rows_by_port[port][issue] = copied
    return dict(rows_by_port)


def load_strategy_issue_rows(path: Path) -> dict[str, dict[str, dict[str, object]]]:
    rows_by_strategy: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in read_csv_rows(path):
        strategy = str(row["strategy"])
        issue = str(row["issue"])
        if issue in rows_by_strategy[strategy]:
            continue
        rows_by_strategy[strategy][issue] = dict(row)
    return dict(rows_by_strategy)


def selected_component_rows(
    *,
    issues: list[str],
    selected_rows: dict[str, dict[str, object]],
    current_rows: dict[str, dict[str, object]],
    arm_rows: dict[str, dict[str, dict[str, object]]],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for issue in issues:
        selected = selected_rows[issue]
        for name, units in SELECTED_ALLOCATION.items():
            if name == "current":
                source = current_rows[issue]
                source_stake = fnum(source.get("stake_units"), 256.0)
                source_profit = fnum(source.get("profit_units"))
                source_hits = fnum(source.get("hits"))
                source_tickets = fnum(source.get("tickets"))
            else:
                source = arm_rows.get(name, {}).get(issue)
                if not source:
                    source_stake = 0.0
                    source_profit = 0.0
                    source_hits = 0.0
                    source_tickets = 0.0
                else:
                    source_stake = fnum(source.get("stake_units"), 256.0)
                    source_profit = fnum(source.get("profit_units"))
                    source_hits = fnum(source.get("hits"))
                    source_tickets = fnum(source.get("tickets"))
            scale = units / source_stake if source_stake > 0 else 0.0
            row = {
                "component": name,
                "issue": issue,
                "stake_units": units,
                "profit_units": source_profit * scale,
                "source_profit_units": source_profit,
                "source_stake_units": source_stake,
                "source_scale": scale,
                "tickets": source_tickets * scale,
                "hits": source_hits * scale,
            }
            for key in ("issue_order", "calendar_year", "issue_close_ts", "season_year"):
                row[key] = selected.get(key, "")
            out.append(row)
    return out


def summarize_components(component_rows: list[dict[str, object]], window_issues: set[str]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for component in sorted({str(row["component"]) for row in component_rows}):
        rows = [row for row in component_rows if str(row["component"]) == component]
        for label, subset in (
            ("maxdd_window", [row for row in rows if str(row["issue"]) in window_issues]),
            ("outside_window", [row for row in rows if str(row["issue"]) not in window_issues]),
            ("all", rows),
        ):
            stake = sum(fnum(row.get("stake_units")) for row in subset)
            profit = sum(fnum(row.get("profit_units")) for row in subset)
            out.append(
                {
                    "component": component,
                    "segment": label,
                    "issues": len(subset),
                    "stake_units": stake,
                    "profit_units": profit,
                    "roi": profit / stake if stake else math.nan,
                    "win_issues": sum(1 for row in subset if fnum(row.get("profit_units")) > 0),
                    "full_loss_issues": sum(1 for row in subset if full_loss(row)),
                    "avg_profit_per_issue": profit / len(subset) if subset else math.nan,
                }
            )
    return out


def aggregate_ticket_features(path: Path) -> dict[str, dict[str, object]]:
    rows = pd.read_csv(path)
    rows = rows[rows["source_strategy"] == SOURCE_STRATEGY].copy()
    rows["issue"] = rows["issue"].astype(str)
    numeric_cols = [
        "pred_hit_prob",
        "pred_ev_per_stake",
        "selector_score",
        "line_gap_support_net",
        "avg_abs_line_gap",
        "ll_bad_count",
        "ll_good_count",
        "avg_q_score",
        "avg_conf_weight",
        "selected_stake_units",
    ]
    for col in numeric_cols:
        if col in rows.columns:
            rows[col] = pd.to_numeric(rows[col], errors="coerce")

    out: dict[str, dict[str, object]] = defaultdict(dict)
    for label, selector in (("all", None), ("core", CORE_SELECTOR), ("exact", EXACT_SELECTOR)):
        sub = rows if selector is None else rows[rows["selector"] == selector]
        if sub.empty:
            continue
        grouped = sub.groupby("issue", sort=False)
        prefix = f"{label}_"
        stats = grouped.agg(
            ticket_count=("ticket_idx", "count"),
            avg_pred_hit=("pred_hit_prob", "mean"),
            avg_pred_ev=("pred_ev_per_stake", "mean"),
            avg_selector_score=("selector_score", "mean"),
            avg_line_gap_net=("line_gap_support_net", "mean"),
            avg_abs_line_gap=("avg_abs_line_gap", "mean"),
            avg_ll_bad=("ll_bad_count", "mean"),
            avg_ll_good=("ll_good_count", "mean"),
            avg_q=("avg_q_score", "mean"),
            avg_conf=("avg_conf_weight", "mean"),
            selected_stake=("selected_stake_units", "sum"),
        )
        for issue, row in stats.iterrows():
            out[str(issue)].update({prefix + key: fnum(value, math.nan) for key, value in row.to_dict().items()})
    return dict(out)


def aggregate_protection_features(path: Path, arms: tuple[str, ...]) -> dict[str, dict[str, object]]:
    rows = pd.read_csv(path)
    rows["issue"] = rows["issue"].astype(str)
    rows = rows[rows["strategy"].isin(arms)].copy()
    numeric_cols = [
        "source_pred_ev_per_stake",
        "source_pred_hit_prob",
        "source_selector_score",
        "source_line_gap_support_net",
        "source_avg_abs_line_gap",
        "source_ll_bad_count",
        "raw_stake_units",
        "stake_units",
    ]
    for col in numeric_cols:
        rows[col] = pd.to_numeric(rows[col], errors="coerce")
    out: dict[str, dict[str, object]] = defaultdict(dict)
    for arm, sub in rows.groupby("strategy", sort=False):
        short = arm.removesuffix("__budget256_fractional").removeprefix("n7prot_")
        grouped = sub.groupby("issue", sort=False).agg(
            ticket_count=("ticket_idx", "count"),
            avg_source_pred_hit=("source_pred_hit_prob", "mean"),
            avg_source_pred_ev=("source_pred_ev_per_stake", "mean"),
            avg_source_score=("source_selector_score", "mean"),
            avg_source_line_gap=("source_line_gap_support_net", "mean"),
            avg_source_ll_bad=("source_ll_bad_count", "mean"),
            raw_stake=("raw_stake_units", "sum"),
        )
        for issue, row in grouped.iterrows():
            out[str(issue)].update({f"{short}_{key}": fnum(value, math.nan) for key, value in row.to_dict().items()})
    return dict(out)


def issue_feature_rows(
    *,
    issues: list[str],
    selected_rows: dict[str, dict[str, object]],
    ticket_features: dict[str, dict[str, object]],
    protection_features: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for issue in issues:
        base = selected_rows[issue]
        row: dict[str, object] = {
            "issue": issue,
            "issue_order": base.get("issue_order", ""),
            "calendar_year": base.get("calendar_year", ""),
            "selected_profit_units": fnum(base.get("profit_units")),
            "selected_full_loss": int(full_loss(base)),
            "selected_win": int(fnum(base.get("profit_units")) > 0),
        }
        row.update(ticket_features.get(issue, {}))
        row.update(protection_features.get(issue, {}))
        if not math.isfinite(fnum(row.get("core_ticket_count"), math.nan)):
            row["core_ticket_count"] = 0.0
        if not math.isfinite(fnum(row.get("exact_ticket_count"), math.nan)):
            row["exact_ticket_count"] = 0.0
        row["core_exact_ticket_ratio"] = fnum(row.get("exact_ticket_count")) / max(fnum(row.get("core_ticket_count")), 1.0)
        row["core_avg_good_minus_bad"] = fnum(row.get("core_avg_ll_good")) - fnum(row.get("core_avg_ll_bad"))
        row["core_linegap_x_tickets"] = fnum(row.get("core_avg_line_gap_net")) * fnum(row.get("core_ticket_count"))
        out.append(row)
    return out


def feature_window_diffs(feature_rows: list[dict[str, object]], window_issues: set[str]) -> list[dict[str, object]]:
    df = pd.DataFrame(feature_rows)
    skip = {"issue", "issue_order", "calendar_year", "selected_profit_units", "selected_full_loss", "selected_win"}
    out = []
    for col in df.columns:
        if col in skip:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        if vals.notna().sum() < 30:
            continue
        in_vals = vals[df["issue"].astype(str).isin(window_issues)]
        out_vals = vals[~df["issue"].astype(str).isin(window_issues)]
        if in_vals.notna().sum() < 5 or out_vals.notna().sum() < 20:
            continue
        all_std = vals.std()
        diff = in_vals.mean() - out_vals.mean()
        out.append(
            {
                "feature": col,
                "window_mean": in_vals.mean(),
                "outside_mean": out_vals.mean(),
                "diff": diff,
                "std_diff": diff / all_std if all_std and math.isfinite(all_std) else math.nan,
                "window_median": in_vals.median(),
                "outside_median": out_vals.median(),
                "window_n": int(in_vals.notna().sum()),
                "outside_n": int(out_vals.notna().sum()),
            }
        )
    out.sort(key=lambda row: abs(fnum(row.get("std_diff"))), reverse=True)
    return out


def percentile(values: list[float], q: float) -> float:
    clean = sorted(v for v in values if math.isfinite(v))
    if not clean:
        return math.nan
    if len(clean) == 1:
        return clean[0]
    pos = (len(clean) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return clean[lo]
    return clean[lo] * (hi - pos) + clean[hi] * (pos - lo)


def feature_value(row: dict[str, object], feature: str) -> float:
    return fnum(row.get(feature), math.nan)


def dynamic_decisions(
    *,
    issues: list[str],
    features_by_issue: dict[str, dict[str, object]],
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    feature: str,
    bad_side: str,
    low_q: float,
    high_q: float,
    defensive_portfolio: str,
    aggressive_portfolio: str,
    selected_portfolio: str,
    history: int,
    min_history: int,
) -> list[dict[str, object]]:
    selected_rows = rows_by_portfolio[selected_portfolio]
    out: list[dict[str, object]] = []
    hist_values: list[float] = []
    for issue in issues:
        cur = feature_value(features_by_issue.get(issue, {}), feature)
        recent = hist_values[-history:]
        chosen = selected_portfolio
        state = "neutral"
        low = math.nan
        high = math.nan
        if len(recent) >= min_history and math.isfinite(cur):
            low = percentile(recent, low_q)
            high = percentile(recent, high_q)
            is_bad = cur <= low if bad_side == "low" else cur >= high
            is_good = cur >= high if bad_side == "low" else cur <= low
            if is_bad and defensive_portfolio in rows_by_portfolio:
                chosen = defensive_portfolio
                state = "defensive"
            elif aggressive_portfolio != selected_portfolio and is_good and aggressive_portfolio in rows_by_portfolio:
                chosen = aggressive_portfolio
                state = "aggressive"
        source = rows_by_portfolio.get(chosen, {}).get(issue) or selected_rows[issue]
        row = dict(source)
        row["portfolio"] = (
            f"dyn_{feature}_{bad_side}_l{int(low_q * 100)}_h{int(high_q * 100)}__"
            f"def_{defensive_portfolio}__agg_{aggressive_portfolio}"
        )
        row["chosen_portfolio"] = chosen
        row["state"] = state
        row["quality_feature"] = feature
        row["quality_value"] = cur if math.isfinite(cur) else ""
        row["quality_low_threshold"] = low if math.isfinite(low) else ""
        row["quality_high_threshold"] = high if math.isfinite(high) else ""
        row["quality_history_n"] = len(recent)
        out.append(row)
        if math.isfinite(cur):
            hist_values.append(cur)
    return out


def evaluate_dynamic_grid(
    *,
    issues: list[str],
    feature_rows: list[dict[str, object]],
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    selected_portfolio: str,
    args: argparse.Namespace,
) -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    features_by_issue = {str(row["issue"]): row for row in feature_rows}
    feature_specs = [
        ("core_ticket_count", "low"),
        ("core_avg_pred_hit", "low"),
        ("core_avg_pred_ev", "low"),
        ("core_avg_selector_score", "low"),
        ("core_avg_line_gap_net", "low"),
        ("core_avg_good_minus_bad", "low"),
        ("core_linegap_x_tickets", "low"),
        ("exact_ticket_count", "low"),
        ("core_exact_ticket_ratio", "low"),
        ("core_avg_ll_bad", "high"),
        ("same_ticket4_full_risk_avg_source_pred_hit", "low"),
        ("same_ticket4_full_risk_avg_source_line_gap", "low"),
        ("same_ticket2_draw_risk_avg_source_pred_hit", "low"),
    ]
    defensive_ports = [
        "b384_dd32_smooth100",
        "b384_dd64_smooth100",
        "b384_dd32_smooth80_wideconvex19",
    ]
    aggressive_ports = [
        selected_portfolio,
        "b384_dd32_safe80_convex19",
        "b384_dd32_smooth50_convex50",
        "b384_dd32_smooth35_convex65",
        "b384_dd32_safe35_convex65",
    ]
    summaries: list[dict[str, object]] = []
    series_by_name: dict[str, list[dict[str, object]]] = {}
    for feature, bad_side in feature_specs:
        if all(not math.isfinite(feature_value(row, feature)) for row in feature_rows):
            continue
        for defensive in defensive_ports:
            for aggressive in aggressive_ports:
                for low_q in (0.20, 0.30, 0.40):
                    for high_q in (0.60, 0.70, 0.80):
                        if low_q >= high_q:
                            continue
                        rows = dynamic_decisions(
                            issues=issues,
                            features_by_issue=features_by_issue,
                            rows_by_portfolio=rows_by_portfolio,
                            feature=feature,
                            bad_side=bad_side,
                            low_q=low_q,
                            high_q=high_q,
                            defensive_portfolio=defensive,
                            aggressive_portfolio=aggressive,
                            selected_portfolio=selected_portfolio,
                            history=args.history_issues,
                            min_history=args.min_history_issues,
                        )
                        name = str(rows[0]["portfolio"]) if rows else ""
                        summary = summarize_issue_rows(rows, portfolio=name, budget=384.0)
                        states = Counter(str(row.get("state", "")) for row in rows)
                        chosen = Counter(str(row.get("chosen_portfolio", "")) for row in rows)
                        summary.update(
                            {
                                "feature": feature,
                                "bad_side": bad_side,
                                "low_q": low_q,
                                "high_q": high_q,
                                "defensive_portfolio": defensive,
                                "aggressive_portfolio": aggressive,
                                "state_mix": ";".join(f"{k}:{v}" for k, v in sorted(states.items())),
                                "chosen_mix": ";".join(f"{k}:{v}" for k, v in chosen.most_common()),
                            }
                        )
                        summaries.append(summary)
                        series_by_name[name] = rows
    return summaries, series_by_name


def equity_svg(path: Path, series_rows: dict[str, list[dict[str, object]]]) -> None:
    width, height = 1180, 620
    left, right, top, bottom = 72, 24, 32, 72
    plot_w, plot_h = width - left - right, height - top - bottom
    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf"]

    def points(rows: list[dict[str, object]]) -> list[tuple[int, float, int]]:
        equity = 0.0
        out = []
        for idx, row in enumerate(sorted(rows, key=row_order)):
            equity += fnum(row.get("profit_units"))
            out.append((idx, equity, row_year(row)))
        return out

    points_by_name = {name: points(rows) for name, rows in series_rows.items()}
    all_points = [p for pts in points_by_name.values() for p in pts]
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
    year_marks = {}
    base_points = next(iter(points_by_name.values()))
    for x, _y, year in base_points:
        if year and year not in year_marks:
            year_marks[year] = x
    for year, x0 in sorted(year_marks.items()):
        if year % 2 == 0 or year in (2014, 2025):
            x = sx(x0)
            elems.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_h}" stroke="#f3f4f6"/>')
            elems.append(f'<text x="{x:.2f}" y="{height - 36}" text-anchor="middle" font-size="12" fill="#374151">{year}</text>')
    zero = sy(0)
    elems.append(f'<line x1="{left}" y1="{zero:.2f}" x2="{left + plot_w}" y2="{zero:.2f}" stroke="#9ca3af" stroke-dasharray="4 4"/>')
    for idx, (name, pts) in enumerate(points_by_name.items()):
        color = colors[idx % len(colors)]
        coords = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y, _year in pts)
        elems.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.2"/>')
        lx, ly = left + 12 + (idx % 2) * 430, top + 18 + (idx // 2) * 22
        label = name[:78]
        elems.append(f'<line x1="{lx}" y1="{ly - 5}" x2="{lx + 26}" y2="{ly - 5}" stroke="{color}" stroke-width="3"/>')
        elems.append(f'<text x="{lx + 34}" y="{ly}" font-size="13" fill="#111827">{label}</text>')
    elems.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(elems), encoding="utf-8")


def compact_summary(rows: list[dict[str, object]], limit: int = 20) -> list[dict[str, object]]:
    cols = [
        "portfolio",
        "feature",
        "bad_side",
        "low_q",
        "high_q",
        "defensive_portfolio",
        "aggressive_portfolio",
        "profit_per_256",
        "roi",
        "non_full_loss_rate",
        "max_drawdown_units",
        "max_drawdown_per_256",
        "max_dead_streak",
        "recent_profit_per_256",
        "state_mix",
    ]
    return [{col: row.get(col, "") for col in cols} for row in rows[:limit]]


def run(args: argparse.Namespace) -> None:
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    rows_by_portfolio = load_portfolio_issue_rows(args.sleeve_issue_profit)
    selected_rows = rows_by_portfolio[SELECTED_PORTFOLIO]
    current_rows = rows_by_portfolio[CURRENT_PORTFOLIO]
    arm_rows = load_strategy_issue_rows(args.arm_issue_profit)
    issues = sorted(selected_rows, key=lambda issue: int(float(str(selected_rows[issue].get("issue_order", 10**9)))))
    selected_series = [selected_rows[issue] for issue in issues]
    dd = drawdown_window(selected_series)
    window_rows = selected_series[int(dd["start_idx"]) : int(dd["end_idx"]) + 1]
    window_issues = {str(row["issue"]) for row in window_rows}

    component_rows = selected_component_rows(
        issues=issues,
        selected_rows=selected_rows,
        current_rows=current_rows,
        arm_rows=arm_rows,
    )
    component_summary = summarize_components(component_rows, window_issues)

    ticket_features = aggregate_ticket_features(args.selected_tickets)
    protection_features = aggregate_protection_features(
        args.protection_tickets,
        arms=(DD_ARM, SMOOTH_ARM, SMOOTH_SAFE_ARM, CONVEX_ARM),
    )
    features = issue_feature_rows(
        issues=issues,
        selected_rows=selected_rows,
        ticket_features=ticket_features,
        protection_features=protection_features,
    )
    feature_diffs = feature_window_diffs(features, window_issues)

    same_budget_ports = [
        SELECTED_PORTFOLIO,
        "b384_dd32_smooth100",
        "b384_dd32_safe80_convex19",
        "b384_dd32_smooth50_convex50",
        "b384_dd32_smooth35_convex65",
        "b384_dd32_safe35_convex65",
        "b384_dd64_smooth100",
        "b384_dd64_smooth80_convex19",
    ]
    window_portfolio_rows: list[dict[str, object]] = []
    for port in same_budget_ports:
        if port not in rows_by_portfolio:
            continue
        rows = [rows_by_portfolio[port][issue] for issue in issues if issue in rows_by_portfolio[port]]
        win_rows = [row for row in rows if str(row["issue"]) in window_issues]
        full = summarize_issue_rows(rows, portfolio=port, budget=384.0)
        win = summarize_issue_rows(win_rows, portfolio=port, budget=384.0)
        window_portfolio_rows.append(
            {
                "portfolio": port,
                "window_profit_units": win["profit_units"],
                "window_roi": win["roi"],
                "window_win_rate": win["issue_win_rate"],
                "window_full_loss_rate": win["full_loss_rate"],
                "full_profit_per_256": full["profit_per_256"],
                "full_roi": full["roi"],
                "full_maxdd_units": full["max_drawdown_units"],
                "full_recent_profit_per_256": full["recent_profit_per_256"],
            }
        )
    window_portfolio_rows.sort(key=lambda row: fnum(row["window_profit_units"]), reverse=True)

    dynamic_summaries, dynamic_series = evaluate_dynamic_grid(
        issues=issues,
        feature_rows=features,
        rows_by_portfolio=rows_by_portfolio,
        selected_portfolio=SELECTED_PORTFOLIO,
        args=args,
    )
    baseline = summarize_issue_rows(selected_series, portfolio=SELECTED_PORTFOLIO, budget=384.0)
    for row in dynamic_summaries:
        row["profit_per_256_delta_vs_base"] = fnum(row.get("profit_per_256")) - fnum(baseline.get("profit_per_256"))
        row["maxdd_delta_vs_base"] = fnum(row.get("max_drawdown_units")) - fnum(baseline.get("max_drawdown_units"))
        row["recent_profit_per_256_delta_vs_base"] = fnum(row.get("recent_profit_per_256")) - fnum(
            baseline.get("recent_profit_per_256")
        )
    top_by_dd = sorted(dynamic_summaries, key=lambda row: (fnum(row["maxdd_delta_vs_base"]), fnum(row["profit_per_256"])), reverse=True)
    top_by_profit = sorted(dynamic_summaries, key=lambda row: fnum(row["profit_per_256"]), reverse=True)
    balanced = [
        row
        for row in dynamic_summaries
        if fnum(row["maxdd_delta_vs_base"]) > 0 and fnum(row["profit_per_256"]) >= fnum(baseline["profit_per_256"]) * 0.95
    ]
    balanced.sort(key=lambda row: (fnum(row["maxdd_delta_vs_base"]), fnum(row["profit_per_256"])), reverse=True)
    positive_pareto = [
        row
        for row in dynamic_summaries
        if fnum(row["maxdd_delta_vs_base"]) > 0 and fnum(row["profit_per_256_delta_vs_base"]) > 0
    ]
    positive_pareto.sort(
        key=lambda row: (fnum(row["maxdd_delta_vs_base"]), fnum(row["profit_per_256_delta_vs_base"])),
        reverse=True,
    )

    selected_dynamic_names = [SELECTED_PORTFOLIO]
    for row in (balanced[:2] or top_by_dd[:2]) + top_by_profit[:1]:
        name = str(row["portfolio"])
        if name not in selected_dynamic_names:
            selected_dynamic_names.append(name)
    selected_issue_rows = []
    series_for_svg = {SELECTED_PORTFOLIO: selected_series}
    for name in selected_dynamic_names[1:]:
        rows = dynamic_series.get(name, [])
        if rows:
            selected_issue_rows.extend(rows)
            series_for_svg[name] = rows
    figure_path = out / "n7_384_dynamic_allocator_equity.svg"
    equity_svg(figure_path, series_for_svg)

    write_csv(out / "maxdd_window_issues.csv", window_rows)
    write_csv(out / "component_attribution.csv", component_summary)
    write_csv(out / "issue_prebet_features.csv", features)
    write_csv(out / "feature_window_diffs.csv", feature_diffs)
    write_csv(out / "same_budget_window_portfolios.csv", window_portfolio_rows)
    write_csv(out / "dynamic_allocator_summary.csv", dynamic_summaries)
    write_csv(out / "dynamic_allocator_selected_issue_profit.csv", selected_issue_rows)

    feature_cols = [
        "feature",
        "window_mean",
        "outside_mean",
        "diff",
        "std_diff",
        "window_median",
        "outside_median",
        "window_n",
        "outside_n",
    ]
    component_cols = [
        "component",
        "segment",
        "issues",
        "stake_units",
        "profit_units",
        "roi",
        "win_issues",
        "full_loss_issues",
        "avg_profit_per_issue",
    ]
    window_port_cols = [
        "portfolio",
        "window_profit_units",
        "window_roi",
        "window_win_rate",
        "window_full_loss_rate",
        "full_profit_per_256",
        "full_maxdd_units",
        "full_recent_profit_per_256",
    ]
    report = [
        "# N7 384 Drawdown Diagnostics And Dynamic Allocator",
        "",
        "## Scope",
        "",
        f"- Base profile: `{SELECTED_PORTFOLIO}`.",
        f"- MaxDD window: peak issue `{dd['peak_issue']}` to trough issue `{dd['trough_issue']}`, segment issues `{dd['issues']}`, drawdown `{dd['maxdd_units']:.1f}` units.",
        "- Dynamic allocator uses current-issue pre-bet features and rolling thresholds from prior issues only.",
        "",
        "## Baseline",
        "",
        md_table([baseline]),
        "",
        "## Component Attribution",
        "",
        md_table([{col: row.get(col, "") for col in component_cols} for row in component_summary], limit=60),
        "",
        "## Same-Budget 384 Portfolios Inside MaxDD Window",
        "",
        md_table([{col: row.get(col, "") for col in window_port_cols} for row in window_portfolio_rows], limit=40),
        "",
        "## Pre-Bet Feature Differences In MaxDD Window",
        "",
        md_table([{col: row.get(col, "") for col in feature_cols} for row in feature_diffs[:24]], limit=30),
        "",
        "## Dynamic Allocator: Balanced Candidates",
        "",
        md_table(compact_summary(balanced, limit=20), limit=20),
        "",
        "## Dynamic Allocator: Profit And MaxDD Both Improve",
        "",
        md_table(compact_summary(positive_pareto, limit=20), limit=20),
        "",
        "## Dynamic Allocator: Best MaxDD Improvement",
        "",
        md_table(compact_summary(top_by_dd, limit=20), limit=20),
        "",
        "## Dynamic Allocator: Best Profit",
        "",
        md_table(compact_summary(top_by_profit, limit=20), limit=20),
        "",
        "## Interpretation",
        "",
    ]
    if balanced:
        best = balanced[0]
        report.extend(
            [
                f"- Best balanced dynamic candidate improves maxDD by `{fnum(best['maxdd_delta_vs_base']):.1f}` units while keeping profit/256 at `{fnum(best['profit_per_256']):.1f}`.",
            ]
        )
        if positive_pareto:
            best_positive = positive_pareto[0]
            report.append(
                f"- Best profit-positive candidate improves profit/256 by `{fnum(best_positive['profit_per_256_delta_vs_base']):.1f}` and maxDD by `{fnum(best_positive['maxdd_delta_vs_base']):.1f}` units."
            )
        report.append(
            "- The maxDD improvement is still modest; use this as a regime-signal lead, not an operating replacement yet."
        )
    else:
        report.extend(
            [
                "- No dynamic allocator candidate simultaneously improved maxDD and retained at least 95% of baseline profit/256.",
                "- In this grid, dynamic sleeve switching should not replace the current static 384 profile without a stronger regime signal.",
            ]
        )
    report.extend(
        [
            "",
            "## Files",
            "",
            f"- `{out / 'maxdd_window_issues.csv'}`",
            f"- `{out / 'component_attribution.csv'}`",
            f"- `{out / 'feature_window_diffs.csv'}`",
            f"- `{out / 'same_budget_window_portfolios.csv'}`",
            f"- `{out / 'dynamic_allocator_summary.csv'}`",
            f"- `{out / 'dynamic_allocator_selected_issue_profit.csv'}`",
            f"- `{figure_path}`",
            "",
        ]
    )
    report_text = "\n".join(report)
    (out / "n7_384_drawdown_dynamic_report.md").write_text(report_text, encoding="utf-8")
    docs_path = Path("docs/research/n7_384_drawdown_dynamic_allocator_2026-06-29.md")
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text(report_text, encoding="utf-8")
    print(f"Wrote {out / 'n7_384_drawdown_dynamic_report.md'}")
    print(f"Wrote {docs_path}")
    print(f"Wrote {figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sleeve-issue-profit", type=Path, default=Path("results/n7_sleeve_mix_capital_20260629/sleeve_mix_issue_profit.csv"))
    parser.add_argument("--arm-issue-profit", type=Path, default=Path("results/n7_multi_leg_protection_overlay_large_20260629/multi_leg_protection_issue_profit.csv"))
    parser.add_argument("--selected-tickets", type=Path, default=Path("results/high_n_selector_20260628/high_n_selector_selected_tickets.csv"))
    parser.add_argument("--protection-tickets", type=Path, default=Path("results/n7_multi_leg_protection_overlay_large_20260629/multi_leg_protection_budgeted_tickets.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_384_drawdown_dynamic_20260629"))
    parser.add_argument("--history-issues", type=int, default=80)
    parser.add_argument("--min-history-issues", type=int, default=40)
    args = parser.parse_args()
    for path in (args.sleeve_issue_profit, args.arm_issue_profit, args.selected_tickets, args.protection_tickets):
        if not path.exists():
            raise SystemExit(f"missing input: {path}")
    run(args)


if __name__ == "__main__":
    main()
