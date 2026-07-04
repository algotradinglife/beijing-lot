#!/usr/bin/env python3
"""No-lookahead issue-quality selector for the main 384-unit strategy.

The selector keeps budget fixed at 384 units and chooses per issue between:

- baseline_384_hybrid
- defensive_smooth90_convex10

Signals are restricted to issue-level pre-bet features plus prior realized
strategy equity state. Rolling feature thresholds use prior issues only.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.render_main_strategy_leg_ev_depth_html as html_base


BASELINE = "baseline_384_hybrid"
DEFENSIVE = "defensive_smooth90_convex10"
BUDGET = 384.0

FEATURE_PATH = Path("results/n7_384_drawdown_dynamic_20260629/issue_prebet_features.csv")
ISSUE_PROFIT_PATH = Path("results/main_strategy_defensive_next_round_20260629/fine_grid_issue_profit.csv")
OUT_DIR = Path("results/main_strategy_issue_quality_selector_v2_20260629")
OUT_HTML = Path("docs/research/main_strategy_issue_quality_selector_v2_2026-06-29.html")

FEATURE_SPECS: list[tuple[str, str, str]] = [
    ("core_avg_pred_ev", "low", "core predEV"),
    ("core_avg_selector_score", "low", "core selector"),
    ("core_avg_q", "low", "core q"),
    ("core_avg_conf", "low", "core confidence"),
    ("core_ticket_count", "low", "core count"),
    ("core_avg_pred_hit", "low", "core pred hit"),
    ("core_avg_line_gap_net", "low", "core line-gap support"),
    ("same_ticket4_full_risk_avg_source_line_gap", "low", "smooth source line-gap"),
    ("all_avg_abs_line_gap", "high", "all abs line-gap"),
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def row_order(row: dict[str, object]) -> tuple[int, str]:
    return (int(fnum(row.get("issue_order"), 10**9)), str(row.get("issue", "")))


def row_year(row: dict[str, object]) -> int:
    year = row.get("calendar_year")
    if year not in ("", None):
        return int(fnum(year))
    issue = str(row.get("issue", ""))
    if len(issue) >= 2 and issue[:2].isdigit():
        yy = int(issue[:2])
        return 2000 + yy if yy < 80 else 1900 + yy
    return 0


def full_loss(row: dict[str, object]) -> bool:
    stake = fnum(row.get("stake_units"), BUDGET)
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
        if fnum(row.get("profit_units")) < 0:
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


def percentile(values: list[float], q: float) -> float:
    vals = sorted(v for v in values if math.isfinite(v))
    if not vals:
        return math.nan
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def q_label(value: float) -> str:
    return f"q{value:g}".replace(".", "p")


def load_portfolios(path: Path) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in read_rows(path):
        out[str(row["portfolio"])][str(row["issue"])] = dict(row)
    return dict(out)


def load_features(path: Path) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for row in read_rows(path):
        copied: dict[str, object] = dict(row)
        for key, value in row.items():
            if key == "issue":
                continue
            try:
                copied[key] = float(value)
            except (TypeError, ValueError):
                copied[key] = value
        out[str(row["issue"])] = copied
    return out


def ordered_issues(portfolios: dict[str, dict[str, dict[str, object]]]) -> list[str]:
    if BASELINE not in portfolios:
        raise SystemExit(f"missing portfolio: {BASELINE}")
    if DEFENSIVE not in portfolios:
        raise SystemExit(f"missing portfolio: {DEFENSIVE}")
    return sorted(portfolios[BASELINE], key=lambda issue: row_order(portfolios[BASELINE][issue]))


class FeatureContext:
    def __init__(
        self,
        *,
        issues: list[str],
        features_by_issue: dict[str, dict[str, object]],
        q: float,
        history: int,
        min_history: int,
    ) -> None:
        self.q = q
        self.history = history
        self.min_history = min_history
        self.flags: dict[str, dict[str, object]] = {}
        histories: dict[str, list[float]] = {feature: [] for feature, _side, _label in FEATURE_SPECS}
        for issue in issues:
            feature_row = features_by_issue.get(issue, {})
            out: dict[str, object] = {
                "weak_count": 0,
                "weak_score": 0.0,
                "quality_history_n": 0,
            }
            valid_histories = []
            for feature, side, label in FEATURE_SPECS:
                value = fnum(feature_row.get(feature), math.nan)
                recent = histories[feature][-history:]
                valid_histories.append(len(recent))
                threshold = math.nan
                weak = False
                severity = 0.0
                if len(recent) >= min_history and math.isfinite(value):
                    threshold = percentile(recent, q if side == "low" else 1.0 - q)
                    if math.isfinite(threshold):
                        if side == "low":
                            weak = value <= threshold
                            median = percentile(recent, 0.5)
                            denom = abs(threshold) + abs(median) + 1e-9
                            severity = max(0.0, (threshold - value) / denom)
                        else:
                            weak = value >= threshold
                            median = percentile(recent, 0.5)
                            denom = abs(threshold) + abs(median) + 1e-9
                            severity = max(0.0, (value - threshold) / denom)
                safe = feature.replace("_", "")
                out[f"{safe}_value"] = value if math.isfinite(value) else ""
                out[f"{safe}_threshold"] = threshold if math.isfinite(threshold) else ""
                out[f"{safe}_weak"] = int(weak)
                out[f"{safe}_severity"] = severity
                if weak:
                    out["weak_count"] = int(out["weak_count"]) + 1
                    out["weak_score"] = fnum(out["weak_score"]) + severity
                if math.isfinite(value):
                    histories[feature].append(value)
            out["quality_history_n"] = min(valid_histories) if valid_histories else 0
            self.flags[issue] = out

    def weak_feature(self, issue: str, feature: str) -> bool:
        return int(fnum(self.flags.get(issue, {}).get(f"{feature.replace('_', '')}_weak"))) == 1

    def weak_count(self, issue: str) -> int:
        return int(fnum(self.flags.get(issue, {}).get("weak_count")))

    def weak_score(self, issue: str) -> float:
        return fnum(self.flags.get(issue, {}).get("weak_score"))

    def history_n(self, issue: str) -> int:
        return int(fnum(self.flags.get(issue, {}).get("quality_history_n")))


QualityFn = Callable[[str, FeatureContext], tuple[bool, str]]


def make_feature_rule(feature: str, label: str) -> QualityFn:
    def fn(issue: str, ctx: FeatureContext) -> tuple[bool, str]:
        return ctx.weak_feature(issue, feature), label

    return fn


def make_count_rule(cutoff: int) -> QualityFn:
    def fn(issue: str, ctx: FeatureContext) -> tuple[bool, str]:
        return ctx.weak_count(issue) >= cutoff, f"weak_count>={cutoff}"

    return fn


def make_score_rule(cutoff: float) -> QualityFn:
    def fn(issue: str, ctx: FeatureContext) -> tuple[bool, str]:
        return ctx.weak_score(issue) >= cutoff, f"weak_score>={cutoff:g}"

    return fn


def clone_choice(
    *,
    issue: str,
    portfolio_name: str,
    chosen: dict[str, object],
    base: dict[str, object],
    defensive: dict[str, object],
    state: str,
    quality_signal: bool,
    state_signal: bool,
    reason: str,
    ctx: FeatureContext | None,
    features: dict[str, object],
) -> dict[str, object]:
    base_profit = fnum(base.get("profit_units"))
    defensive_profit = fnum(defensive.get("profit_units"))
    row = dict(chosen)
    row.update(
        {
            "portfolio": portfolio_name,
            "issue": issue,
            "stake_units": BUDGET,
            "profit_units": fnum(chosen.get("profit_units")),
            "roi": fnum(chosen.get("profit_units")) / BUDGET,
            "chosen_portfolio": DEFENSIVE if state == "defensive" else BASELINE,
            "state": state,
            "quality_signal": int(quality_signal),
            "state_signal": int(state_signal),
            "switch_reason": reason,
            "base_profit_units": base_profit,
            "defensive_profit_units": defensive_profit,
            "delta_vs_base_units": fnum(chosen.get("profit_units")) - base_profit,
            "base_full_loss": int(full_loss(base)),
            "defensive_full_loss": int(full_loss(defensive)),
            "dynamic_full_loss": int(full_loss({"stake_units": BUDGET, "profit_units": fnum(chosen.get("profit_units"))})),
            "base_win": int(base_profit > 0),
            "defensive_win": int(defensive_profit > 0),
            "dynamic_win": int(fnum(chosen.get("profit_units")) > 0),
            "weak_count": ctx.weak_count(issue) if ctx else "",
            "weak_score": ctx.weak_score(issue) if ctx else "",
            "quality_history_n": ctx.history_n(issue) if ctx else "",
        }
    )
    for feature, _side, _label in FEATURE_SPECS:
        row[feature] = features.get(feature, "")
    return row


def replay_selector(
    *,
    name: str,
    issues: list[str],
    base_by_issue: dict[str, dict[str, object]],
    defensive_by_issue: dict[str, dict[str, object]],
    features_by_issue: dict[str, dict[str, object]],
    ctx: FeatureContext | None,
    quality_fn: QualityFn | None,
    state_loss_trigger: int | None = None,
    state_dd_trigger: float | None = None,
    combine_mode: str = "quality",
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    equity = 0.0
    peak = 0.0
    loss_streak = 0
    for issue in issues:
        base = base_by_issue[issue]
        defensive = defensive_by_issue[issue]
        features = features_by_issue.get(issue, {})
        quality_signal = False
        reason_parts: list[str] = []
        if quality_fn and ctx:
            quality_signal, reason = quality_fn(issue, ctx)
            if quality_signal:
                reason_parts.append(reason)
        current_dd = peak - equity
        state_signal = False
        if state_loss_trigger is not None and loss_streak >= state_loss_trigger:
            state_signal = True
            reason_parts.append(f"loss_streak>={state_loss_trigger}")
        if state_dd_trigger is not None and current_dd >= state_dd_trigger:
            state_signal = True
            reason_parts.append(f"drawdown>={state_dd_trigger:g}")

        if combine_mode == "state":
            use_defensive = state_signal
        elif combine_mode == "or":
            use_defensive = quality_signal or state_signal
        elif combine_mode == "and":
            use_defensive = quality_signal and state_signal
        else:
            use_defensive = quality_signal

        chosen = defensive if use_defensive else base
        state = "defensive" if use_defensive else "base"
        row = clone_choice(
            issue=issue,
            portfolio_name=name,
            chosen=chosen,
            base=base,
            defensive=defensive,
            state=state,
            quality_signal=quality_signal,
            state_signal=state_signal,
            reason=";".join(reason_parts),
            ctx=ctx,
            features=features,
        )
        rows.append(row)

        profit = fnum(row.get("profit_units"))
        equity += profit
        peak = max(peak, equity)
        loss_streak = loss_streak + 1 if profit < 0 else 0
    return rows


def summarize(rows: list[dict[str, object]], *, portfolio: str) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units"), BUDGET) for row in ordered)
    profit = sum(fnum(row.get("profit_units")) for row in ordered)
    best = max((fnum(row.get("profit_units")) for row in ordered), default=0.0)
    recent = [row for row in ordered if 2023 <= row_year(row) <= 2025]
    recent_stake = sum(fnum(row.get("stake_units"), BUDGET) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    defensive_count = sum(1 for row in ordered if row.get("state") == "defensive")
    switched = [row for row in ordered if row.get("state") == "defensive"]
    out = {
        "portfolio": portfolio,
        "issues": len(ordered),
        "stake_units": stake,
        "profit_units": profit,
        "profit_per_256": profit / (BUDGET / 256.0),
        "roi": profit / stake if stake else math.nan,
        "issue_win_rate": sum(1 for row in ordered if fnum(row.get("profit_units")) > 0) / len(ordered),
        "non_full_loss_rate": sum(1 for row in ordered if not full_loss(row)) / len(ordered),
        "full_loss_rate": sum(1 for row in ordered if full_loss(row)) / len(ordered),
        "max_drawdown_units": max_drawdown_units(ordered),
        "max_drawdown_per_256": max_drawdown_units(ordered) / (BUDGET / 256.0),
        "max_loss_streak": max_loss_streak(ordered),
        "max_dead_streak": max_dead_streak(ordered),
        "best_issue_profit_units": best,
        "roi_ex_best_issue": (profit - best) / (stake - BUDGET) if stake > BUDGET else math.nan,
        "recent_profit_units": recent_profit,
        "recent_profit_per_256": recent_profit / (BUDGET / 256.0),
        "recent_roi": recent_profit / recent_stake if recent_stake else math.nan,
        "defensive_issue_count": defensive_count,
        "defensive_issue_share": defensive_count / len(ordered) if ordered else math.nan,
        "switch_delta_units": sum(fnum(row.get("delta_vs_base_units")) for row in switched),
        "switch_helped_count": sum(1 for row in switched if fnum(row.get("delta_vs_base_units")) > 1e-9),
        "switch_hurt_count": sum(1 for row in switched if fnum(row.get("delta_vs_base_units")) < -1e-9),
        "switch_flat_count": sum(1 for row in switched if abs(fnum(row.get("delta_vs_base_units"))) <= 1e-9),
    }
    return out


def add_delta(summary_rows: list[dict[str, object]]) -> None:
    base = next(row for row in summary_rows if row["portfolio"] == BASELINE)
    for row in summary_rows:
        row["delta_profit_per_256_vs_base"] = fnum(row.get("profit_per_256")) - fnum(base.get("profit_per_256"))
        row["delta_roi_vs_base"] = fnum(row.get("roi")) - fnum(base.get("roi"))
        row["delta_maxdd_units_vs_base"] = fnum(row.get("max_drawdown_units")) - fnum(base.get("max_drawdown_units"))
        row["delta_loss_streak_vs_base"] = fnum(row.get("max_loss_streak")) - fnum(base.get("max_loss_streak"))
        row["delta_issue_win_pp_vs_base"] = (fnum(row.get("issue_win_rate")) - fnum(base.get("issue_win_rate"))) * 100.0
        row["delta_full_loss_pp_vs_base"] = (fnum(row.get("full_loss_rate")) - fnum(base.get("full_loss_rate"))) * 100.0
        row["delta_recent_profit_per_256_vs_base"] = fnum(row.get("recent_profit_per_256")) - fnum(
            base.get("recent_profit_per_256")
        )
        row["risk_utility"] = (
            fnum(row.get("delta_profit_per_256_vs_base"))
            + 2.5 * fnum(row.get("delta_maxdd_units_vs_base"))
            - 850.0 * max(0.0, fnum(row.get("delta_loss_streak_vs_base")))
            + 500.0 * fnum(row.get("delta_issue_win_pp_vs_base"))
            - 500.0 * max(0.0, fnum(row.get("delta_full_loss_pp_vs_base")))
        )


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["portfolio"]), row_year(row))].append(row)
    out: list[dict[str, object]] = []
    for (portfolio, year), vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units"), BUDGET) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "portfolio": portfolio,
                "year": year,
                "n_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "profit_per_256": profit / (BUDGET / 256.0),
                "roi": profit / stake if stake else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals),
                "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals),
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def period_rows(
    *,
    issues: list[str],
    series: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    periods = [
        ("all", lambda row: True),
        ("train_like_2014_2022", lambda row: 2014 <= row_year(row) <= 2022),
        ("recent_2023_2025", lambda row: 2023 <= row_year(row) <= 2025),
        ("weak_recent_2024_2025", lambda row: 2024 <= row_year(row) <= 2025),
    ]
    out: list[dict[str, object]] = []
    baseline_rows = series[BASELINE]
    for portfolio, rows in series.items():
        if portfolio == BASELINE:
            continue
        for name, predicate in periods:
            base = [row for row in baseline_rows if predicate(row)]
            sub = [row for row in rows if predicate(row)]
            base_profit = sum(fnum(row.get("profit_units")) for row in base)
            profit = sum(fnum(row.get("profit_units")) for row in sub)
            stake = len(sub) * BUDGET
            out.append(
                {
                    "portfolio": portfolio,
                    "period": name,
                    "n_issues": len(sub),
                    "profit_units": profit,
                    "profit_per_256": profit / (BUDGET / 256.0),
                    "roi": profit / stake if stake else math.nan,
                    "delta_vs_base": profit - base_profit,
                    "max_drawdown_units": max_drawdown_units(sub),
                    "base_max_drawdown_units": max_drawdown_units(base),
                    "maxdd_delta_vs_base": max_drawdown_units(sub) - max_drawdown_units(base),
                    "issue_win_rate": sum(1 for row in sub if fnum(row.get("profit_units")) > 0) / len(sub)
                    if sub
                    else math.nan,
                    "full_loss_rate": sum(1 for row in sub if full_loss(row)) / len(sub) if sub else math.nan,
                }
            )
    return out


def pareto_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    candidates = [r for r in rows if r["portfolio"] not in {BASELINE, DEFENSIVE}]
    out: list[dict[str, object]] = []
    for row in candidates:
        dominated = False
        for other in candidates:
            if other is row:
                continue
            better_or_equal = (
                fnum(other.get("roi")) >= fnum(row.get("roi"))
                and fnum(other.get("max_drawdown_units")) >= fnum(row.get("max_drawdown_units"))
                and fnum(other.get("max_loss_streak")) <= fnum(row.get("max_loss_streak"))
                and fnum(other.get("issue_win_rate")) >= fnum(row.get("issue_win_rate"))
            )
            strict = (
                fnum(other.get("roi")) > fnum(row.get("roi"))
                or fnum(other.get("max_drawdown_units")) > fnum(row.get("max_drawdown_units"))
                or fnum(other.get("max_loss_streak")) < fnum(row.get("max_loss_streak"))
                or fnum(other.get("issue_win_rate")) > fnum(row.get("issue_win_rate"))
            )
            if better_or_equal and strict:
                dominated = True
                break
        if not dominated:
            copied = dict(row)
            copied["pareto_front"] = 1
            out.append(copied)
    out.sort(key=lambda row: (fnum(row.get("risk_utility")), fnum(row.get("roi"))), reverse=True)
    return out


def normalized_issue_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in rows:
        copied = dict(row)
        scale = fnum(row.get("stake_units"), BUDGET) / 256.0
        if scale > 0:
            copied["profit_units"] = fnum(row.get("profit_units")) / scale
            copied["stake_units"] = 256.0
        out.append(copied)
    return out


def make_html(
    *,
    output: Path,
    summary_rows: list[dict[str, object]],
    issue_rows: list[dict[str, object]],
    annual: list[dict[str, object]],
    periods: list[dict[str, object]],
    pareto: list[dict[str, object]],
    focused: list[str],
) -> None:
    html_base.FOCUSED = focused
    html_base.COLORS = {
        BASELINE: "#2f855a",
        DEFENSIVE: "#e45756",
        "state_L6_DD9000": "#4c78a8",
        "state_L4_DD3000": "#72b7b2",
        focused[-1] if focused else "": "#f58518",
    }
    palette = ["#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#bcbd22", "#111827"]
    for idx, name in enumerate(focused):
        html_base.COLORS.setdefault(name, palette[idx % len(palette)])

    summary_map = {str(row["portfolio"]): row for row in summary_rows}
    focused_summary = [summary_map[name] for name in focused if name in summary_map]
    focused_issue = [row for row in issue_rows if row.get("portfolio") in set(focused)]
    focused_annual = [row for row in annual if row.get("portfolio") in set(focused)]
    recent_annual = [row for row in focused_annual if int(fnum(row.get("year"))) >= 2023]
    recent_annual.sort(key=lambda row: (focused.index(str(row["portfolio"])), int(fnum(row.get("year")))))

    eq, dd = html_base.build_series([{k: str(v) for k, v in row.items()} for row in focused_issue])
    eq_norm, _ = html_base.build_series([{k: str(v) for k, v in row.items()} for row in normalized_issue_rows(focused_issue)])
    equity_svg = html_base.line_svg(eq, title="Issue quality selector v2: total profit curve", y_label="cumulative total profit")
    norm_svg = html_base.line_svg(eq_norm, title="Issue quality selector v2: profit/256 normalized curve", y_label="cumulative profit/256")
    dd_svg = html_base.line_svg(dd, title="Issue quality selector v2: drawdown curve", y_label="equity - running peak")
    annual_svg = html_base.annual_profit_svg([{k: str(v) for k, v in row.items()} for row in focused_annual])

    top_rows = sorted(
        [row for row in summary_rows if row["portfolio"] not in {BASELINE, DEFENSIVE}],
        key=lambda row: (fnum(row.get("risk_utility")), fnum(row.get("roi"))),
        reverse=True,
    )[:20]
    maxdd_rows = sorted(
        [row for row in summary_rows if row["portfolio"] not in {BASELINE, DEFENSIVE}],
        key=lambda row: (fnum(row.get("max_drawdown_units")), fnum(row.get("roi"))),
        reverse=True,
    )[:20]
    period_focus = [
        row
        for row in periods
        if row.get("portfolio") in set(focused) and row.get("period") in {"recent_2023_2025", "weak_recent_2024_2025"}
    ]

    cols = [
        ("portfolio", "portfolio", "text"),
        ("profit_per_256", "profit/256", "num"),
        ("roi", "ROI", "roi"),
        ("delta_profit_per_256_vs_base", "profit/256 Δ", "num"),
        ("max_drawdown_units", "maxDD", "num"),
        ("delta_maxdd_units_vs_base", "maxDD Δ", "num"),
        ("max_loss_streak", "loss streak", "num"),
        ("delta_loss_streak_vs_base", "loss streak Δ", "num"),
        ("issue_win_rate", "issue win", "pct"),
        ("delta_issue_win_pp_vs_base", "issue win Δ pp", "num2"),
        ("full_loss_rate", "full loss", "pct"),
        ("defensive_issue_share", "def share", "pct"),
        ("recent_profit_per_256", "2023-25 profit/256", "num"),
        ("risk_utility", "utility", "num"),
    ]

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Issue Quality Selector v2</title>
<style>
:root {{ --bg:#f7f7f4; --fg:#171717; --muted:#666; --border:#d8d2c7; --panel:#fff; --head:#eef2ef; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Arial,sans-serif; line-height:1.62; }}
main {{ max-width:1240px; margin:0 auto; padding:28px 28px 72px; }}
h1 {{ margin:0 0 8px; font-size:30px; }}
h2 {{ margin:34px 0 12px; padding-bottom:6px; border-bottom:1px solid var(--border); font-size:21px; }}
.meta {{ color:var(--muted); font-size:14px; }}
.callout {{ background:#fff7e6; border-left:4px solid #9a6500; padding:12px 16px; border-radius:0 6px 6px 0; margin:18px 0; }}
.chart-wrap {{ background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:14px; overflow-x:auto; margin:14px 0; }}
.chart {{ width:100%; min-width:980px; height:auto; display:block; background:#fff; }}
.chart-title {{ font-size:18px; font-weight:700; fill:#222; }}
.axis-label,.tick,.legend {{ fill:#555; font-size:12px; }}
.axis {{ stroke:#8d887f; stroke-width:1; }}
.grid {{ stroke:#e5e1d8; stroke-width:1; }}
.zero {{ stroke:#888; stroke-width:1.3; stroke-dasharray:4 4; }}
table {{ width:100%; border-collapse:collapse; background:var(--panel); font-size:13px; margin:10px 0 18px; }}
th,td {{ border:1px solid var(--border); padding:7px 9px; text-align:left; vertical-align:top; }}
th {{ background:var(--head); font-weight:700; }}
tbody tr:nth-child(even) {{ background:rgba(0,0,0,.025); }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
code {{ background:#ece8df; padding:1px 5px; border-radius:4px; }}
</style>
</head>
<body>
<main>
<h1>Issue Quality Selector v2</h1>
<p class="meta">生成日期：2026-06-29。固定 384/期，不空仓；每期只在 <code>{BASELINE}</code> 与 <code>{DEFENSIVE}</code> 之间切换。</p>
<div class="callout">
所有质量阈值都只用当前期之前的 issue feature 历史；账户状态规则只用已经发生的策略权益曲线。
因此这里是 no-lookahead 回放，不使用当期或未来赛果来决定当期动作。
</div>

<h2>Focused Candidates</h2>
{html_base.table_html(focused_summary, cols)}

<h2>Equity And Drawdown</h2>
<div class="chart-wrap">{equity_svg}</div>
<div class="chart-wrap">{norm_svg}</div>
<div class="chart-wrap">{dd_svg}</div>
<div class="chart-wrap">{annual_svg}</div>

<h2>Top Risk-Utility Candidates</h2>
{html_base.table_html(top_rows, cols)}

<h2>Best MaxDD Candidates</h2>
{html_base.table_html(maxdd_rows, cols)}

<h2>Pareto Front</h2>
{html_base.table_html(pareto[:30], cols)}

<h2>Recent Periods</h2>
{html_base.table_html(period_focus, [
    ("portfolio", "portfolio", "text"),
    ("period", "period", "text"),
    ("n_issues", "n", "num"),
    ("profit_per_256", "profit/256", "num"),
    ("roi", "ROI", "roi"),
    ("delta_vs_base", "profit Δ vs base", "num"),
    ("max_drawdown_units", "maxDD", "num"),
    ("maxdd_delta_vs_base", "maxDD Δ", "num"),
    ("issue_win_rate", "issue win", "pct"),
    ("full_loss_rate", "full loss", "pct"),
])}

<h2>2023-2025 Annual</h2>
{html_base.table_html(recent_annual, [
    ("portfolio", "portfolio", "text"),
    ("year", "year", "text"),
    ("n_issues", "n", "num"),
    ("profit_per_256", "profit/256", "num"),
    ("roi", "ROI", "roi"),
    ("issue_win_rate", "issue win", "pct"),
    ("non_full_loss_rate", "non-full-loss", "pct"),
    ("max_drawdown_units", "maxDD", "num"),
])}
</main>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


def build_selectors(args: argparse.Namespace) -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    portfolios = load_portfolios(args.issue_profit)
    features = load_features(args.features)
    issues = ordered_issues(portfolios)
    base_by_issue = portfolios[BASELINE]
    defensive_by_issue = portfolios[DEFENSIVE]

    series: dict[str, list[dict[str, object]]] = {
        BASELINE: [
            clone_choice(
                issue=issue,
                portfolio_name=BASELINE,
                chosen=base_by_issue[issue],
                base=base_by_issue[issue],
                defensive=defensive_by_issue[issue],
                state="base",
                quality_signal=False,
                state_signal=False,
                reason="static",
                ctx=None,
                features=features.get(issue, {}),
            )
            for issue in issues
        ],
        DEFENSIVE: [
            clone_choice(
                issue=issue,
                portfolio_name=DEFENSIVE,
                chosen=defensive_by_issue[issue],
                base=base_by_issue[issue],
                defensive=defensive_by_issue[issue],
                state="defensive",
                quality_signal=True,
                state_signal=False,
                reason="static",
                ctx=None,
                features=features.get(issue, {}),
            )
            for issue in issues
        ],
    }

    # Account-state references. These do not use pre-bet quality features.
    for loss_trigger, dd_trigger in ((4, 3000.0), (6, 9000.0), (10, 12000.0)):
        name = f"state_L{loss_trigger}_DD{int(dd_trigger)}"
        series[name] = replay_selector(
            name=name,
            issues=issues,
            base_by_issue=base_by_issue,
            defensive_by_issue=defensive_by_issue,
            features_by_issue=features,
            ctx=None,
            quality_fn=None,
            state_loss_trigger=loss_trigger,
            state_dd_trigger=dd_trigger,
            combine_mode="state",
        )

    contexts: dict[tuple[float, int], FeatureContext] = {}
    for q in args.quantiles:
        for history in args.histories:
            ctx = FeatureContext(
                issues=issues,
                features_by_issue=features,
                q=q,
                history=history,
                min_history=args.min_history,
            )
            contexts[(q, history)] = ctx
            qtxt = q_label(q)
            for feature, side, label in FEATURE_SPECS:
                name = f"quality_{feature}_{side}_{qtxt}_h{history}"
                series[name] = replay_selector(
                    name=name,
                    issues=issues,
                    base_by_issue=base_by_issue,
                    defensive_by_issue=defensive_by_issue,
                    features_by_issue=features,
                    ctx=ctx,
                    quality_fn=make_feature_rule(feature, f"{label} {side} {qtxt}"),
                    combine_mode="quality",
                )
            for cutoff in args.weak_count_cutoffs:
                name = f"quality_weakcount_ge{cutoff}_{qtxt}_h{history}"
                quality_fn = make_count_rule(cutoff)
                series[name] = replay_selector(
                    name=name,
                    issues=issues,
                    base_by_issue=base_by_issue,
                    defensive_by_issue=defensive_by_issue,
                    features_by_issue=features,
                    ctx=ctx,
                    quality_fn=quality_fn,
                    combine_mode="quality",
                )
                for loss_trigger, dd_trigger in ((6, 9000.0), (10, 12000.0)):
                    combo_name = f"state_L{loss_trigger}_DD{int(dd_trigger)}_OR_weakcount_ge{cutoff}_{qtxt}_h{history}"
                    series[combo_name] = replay_selector(
                        name=combo_name,
                        issues=issues,
                        base_by_issue=base_by_issue,
                        defensive_by_issue=defensive_by_issue,
                        features_by_issue=features,
                        ctx=ctx,
                        quality_fn=quality_fn,
                        state_loss_trigger=loss_trigger,
                        state_dd_trigger=dd_trigger,
                        combine_mode="or",
                    )
            for score_cutoff in args.weak_score_cutoffs:
                name = f"quality_weakscore_ge{str(score_cutoff).replace('.', 'p')}_{qtxt}_h{history}"
                series[name] = replay_selector(
                    name=name,
                    issues=issues,
                    base_by_issue=base_by_issue,
                    defensive_by_issue=defensive_by_issue,
                    features_by_issue=features,
                    ctx=ctx,
                    quality_fn=make_score_rule(score_cutoff),
                    combine_mode="quality",
                )

    summaries = [summarize(rows, portfolio=name) for name, rows in series.items()]
    add_delta(summaries)
    return summaries, series


def run(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries, series = build_selectors(args)
    issue_rows = [row for rows in series.values() for row in rows]
    annual = annual_rows(issue_rows)
    periods = period_rows(issues=[], series=series)
    pareto = pareto_rows(summaries)

    summaries_sorted = sorted(summaries, key=lambda row: (fnum(row.get("risk_utility")), fnum(row.get("roi"))), reverse=True)
    write_rows(args.output_dir / "quality_selector_summary.csv", summaries_sorted)
    write_rows(args.output_dir / "quality_selector_issue_profit.csv", issue_rows)
    write_rows(args.output_dir / "quality_selector_annual.csv", annual)
    write_rows(args.output_dir / "quality_selector_periods.csv", periods)
    write_rows(args.output_dir / "quality_selector_pareto.csv", pareto)

    focused = [BASELINE, DEFENSIVE, "state_L6_DD9000", "state_L4_DD3000"]
    for row in summaries_sorted:
        name = str(row["portfolio"])
        if name not in focused and name not in {BASELINE, DEFENSIVE}:
            focused.append(name)
        if len(focused) >= 7:
            break
    for row in sorted(summaries, key=lambda r: (fnum(r.get("max_drawdown_units")), fnum(r.get("roi"))), reverse=True):
        name = str(row["portfolio"])
        if name not in focused and name not in {BASELINE, DEFENSIVE}:
            focused.append(name)
        if len(focused) >= 9:
            break

    make_html(
        output=args.output,
        summary_rows=summaries,
        issue_rows=issue_rows,
        annual=annual,
        periods=periods,
        pareto=pareto,
        focused=focused,
    )
    print(f"Wrote {args.output_dir}")
    print(f"Wrote {args.output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, default=FEATURE_PATH)
    parser.add_argument("--issue-profit", type=Path, default=ISSUE_PROFIT_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--output", type=Path, default=OUT_HTML)
    parser.add_argument("--histories", type=int, nargs="+", default=[60, 80, 120])
    parser.add_argument("--quantiles", type=float, nargs="+", default=[0.10, 0.15, 0.20, 0.25])
    parser.add_argument("--min-history", type=int, default=40)
    parser.add_argument("--weak-count-cutoffs", type=int, nargs="+", default=[1, 2, 3, 4])
    parser.add_argument("--weak-score-cutoffs", type=float, nargs="+", default=[0.02, 0.05, 0.10, 0.20])
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
