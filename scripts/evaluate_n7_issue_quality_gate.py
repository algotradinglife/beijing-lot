#!/usr/bin/env python3
"""Replay fixed-stake N=7 strategies with walk-forward issue-quality gates.

The gate is evaluated after tickets are built but before staking the issue.
Current issue features are observable at that time; thresholds are estimated
only from prior issue features.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_fixed_loss_streaks import (
    build_issue_features,
    issue_sort_key,
    issue_year,
    read_csv,
    select_strategy,
    strip_budget_suffix,
)
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


@dataclass(frozen=True)
class GateSpec:
    name: str
    features: tuple[str, ...]
    quantile: float
    mode: str


def write_csv_union(path: Path, rows: list[dict[str, object]]) -> None:
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


def parse_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def fnum(value: object, default: float = float("nan")) -> float:
    if value == "":
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def percentile(values: list[float], q: float) -> float:
    values = sorted(v for v in values if math.isfinite(v))
    if not values:
        return float("nan")
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def quantile_label(q: float) -> str:
    return f"q{q:g}".replace(".", "p")


def make_gate_specs(features: list[str], quantiles: list[float], combined: list[str]) -> list[GateSpec]:
    specs = [GateSpec("no_gate", tuple(), 0.0, "none")]
    for feature in features:
        for q in quantiles:
            specs.append(GateSpec(f"gate_{feature}_{quantile_label(q)}", (feature,), q, "all"))
    for raw in combined:
        parts = tuple(part.strip() for part in raw.split("+") if part.strip())
        if len(parts) < 2:
            continue
        for q in quantiles:
            specs.append(GateSpec(f"gate_{'_and_'.join(parts)}_{quantile_label(q)}", parts, q, "all"))
    return specs


def load_strategy_context(result_dir: Path, strategy_regex: str, min_streak: int):
    issue_rows_all = read_csv(result_dir / "ev_framework_issue_profit.csv")
    strategy = select_strategy(issue_rows_all, strategy_regex)
    base_strategy = strip_budget_suffix(strategy)
    issue_rows = sorted(
        [row for row in issue_rows_all if row["strategy"] == strategy],
        key=lambda row: issue_sort_key(row["issue"]),
    )
    ticket_rows = read_csv(result_dir / "ev_framework_budget_fractional_tickets.csv")
    decision_rows = read_csv(result_dir / "ev_framework_decisions.csv")
    features, _streaks, selected_decisions = build_issue_features(
        strategy=strategy,
        base_strategy=base_strategy,
        issue_rows=issue_rows,
        ticket_rows=ticket_rows,
        decision_rows=decision_rows,
        min_streak=min_streak,
    )
    by_issue = {str(row["issue"]): row for row in issue_rows}
    return strategy, base_strategy, issue_rows, features, by_issue, selected_decisions


def gate_passes(
    *,
    spec: GateSpec,
    row: dict[str, object],
    history: list[dict[str, object]],
    rolling_window: int,
    min_history: int,
) -> tuple[bool, dict[str, object]]:
    if spec.mode == "none":
        return True, {}
    recent_history = history[-rolling_window:] if rolling_window > 0 else history
    if len(recent_history) < min_history:
        return True, {"gate_reason": "insufficient_history", "history_n": len(recent_history)}

    details: dict[str, object] = {"history_n": len(recent_history)}
    passes = []
    for feature in spec.features:
        current = fnum(row.get(feature))
        threshold = percentile([fnum(prev.get(feature)) for prev in recent_history], spec.quantile)
        ok = math.isfinite(current) and math.isfinite(threshold) and current >= threshold
        details[f"{feature}_value"] = current
        details[f"{feature}_threshold"] = threshold
        details[f"{feature}_pass"] = 1 if ok else 0
        passes.append(ok)
    return all(passes), details


def max_drawdown(issue_rows: list[dict[str, object]], *, initial: float = 10_000.0) -> float:
    equity = initial
    peak = equity
    max_dd = 0.0
    for row in issue_rows:
        equity += fnum(row.get("profit_units"), 0.0)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = min(max_dd, (equity - peak) / peak)
    return max_dd


def loss_streak_stats(issue_rows: list[dict[str, object]]) -> tuple[int, int, int]:
    current = 0
    max_streak = 0
    streaks_ge5 = 0
    issues_in_ge5 = 0
    for row in issue_rows:
        if int(row.get("active", 0)) == 1 and fnum(row.get("profit_units"), 0.0) < 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            if current >= 5:
                streaks_ge5 += 1
                issues_in_ge5 += current
            current = 0
    if current >= 5:
        streaks_ge5 += 1
        issues_in_ge5 += current
    return max_streak, streaks_ge5, issues_in_ge5


def summarize_rows(
    *,
    run: str,
    source_strategy: str,
    gate: str,
    rows: list[dict[str, object]],
    recent_start: int = 2023,
    recent_end: int = 2025,
) -> dict[str, object]:
    active_rows = [row for row in rows if int(row.get("active", 0)) == 1]
    signal_rows = [row for row in rows if int(row.get("signal", 0)) == 1]
    stake = sum(fnum(row.get("stake_units"), 0.0) for row in active_rows)
    profit = sum(fnum(row.get("profit_units"), 0.0) for row in active_rows)
    best = max((fnum(row.get("profit_units"), 0.0) for row in active_rows), default=0.0)
    max_loss_streak, streaks_ge5, issues_in_ge5 = loss_streak_stats(rows)
    recent_rows = [
        row
        for row in rows
        if recent_start <= int(row["year"]) <= recent_end and int(row.get("active", 0)) == 1
    ]
    recent_stake = sum(fnum(row.get("stake_units"), 0.0) for row in recent_rows)
    recent_profit = sum(fnum(row.get("profit_units"), 0.0) for row in recent_rows)
    recent_best = max((fnum(row.get("profit_units"), 0.0) for row in recent_rows), default=0.0)
    return {
        "run": run,
        "source_strategy": source_strategy,
        "gate": gate,
        "calendar_issues": len(rows),
        "signal_issues": len(signal_rows),
        "active_issues": len(active_rows),
        "skipped_issues": len(signal_rows) - len(active_rows),
        "deployment_rate_vs_signal": len(active_rows) / len(signal_rows) if signal_rows else float("nan"),
        "stake_units": stake,
        "profit_units": profit,
        "roi_on_deployed_stake": profit / stake if stake > 0 else float("nan"),
        "roi_on_signal_budget": profit / sum(fnum(row.get("original_stake_units"), 0.0) for row in signal_rows)
        if signal_rows
        else float("nan"),
        "issue_win_rate": sum(1 for row in active_rows if fnum(row.get("profit_units"), 0.0) > 0) / len(active_rows)
        if active_rows
        else float("nan"),
        "profitable_issues": sum(1 for row in active_rows if fnum(row.get("profit_units"), 0.0) > 0),
        "best_issue_profit_units": best,
        "best_issue_profit_share": best / profit if profit > 0 and best > 0 else "",
        "profit_ex_best_issue": profit - best,
        "roi_ex_best_issue": (profit - best) / (stake - fnum(active_rows[0].get("stake_units"), 0.0))
        if len(active_rows) > 1 and stake > fnum(active_rows[0].get("stake_units"), 0.0)
        else float("nan"),
        "max_drawdown_pct_on_10000": max_drawdown(rows),
        "max_active_loss_streak": max_loss_streak,
        "n_loss_streaks_ge5": streaks_ge5,
        "issues_in_loss_streaks_ge5": issues_in_ge5,
        "recent_active_issues": len(recent_rows),
        "recent_profit_units": recent_profit,
        "recent_roi": recent_profit / recent_stake if recent_stake > 0 else float("nan"),
        "recent_best_issue_profit_units": recent_best,
        "recent_profit_ex_best_issue": recent_profit - recent_best,
        "recent_roi_ex_best_issue": (recent_profit - recent_best) / (recent_stake - 256.0)
        if recent_stake > 256.0
        else float("nan"),
    }


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["source_strategy"]), str(row["gate"]), int(row["year"]))].append(row)
    out = []
    for (strategy, gate, year), vals in sorted(grouped.items()):
        active = [row for row in vals if int(row.get("active", 0)) == 1]
        stake = sum(fnum(row.get("stake_units"), 0.0) for row in active)
        profit = sum(fnum(row.get("profit_units"), 0.0) for row in active)
        out.append(
            {
                "source_strategy": strategy,
                "gate": gate,
                "year": year,
                "calendar_issues": len(vals),
                "active_issues": len(active),
                "skipped_issues": sum(1 for row in vals if int(row.get("signal", 0)) == 1 and int(row.get("active", 0)) == 0),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake > 0 else float("nan"),
            }
        )
    return out


def replay_gates(
    *,
    result_dir: Path,
    strategy_regex: str,
    specs: list[GateSpec],
    rolling_window: int,
    min_history: int,
    min_streak: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], str]:
    strategy, _base_strategy, issue_rows, features, issue_by_id, _selected = load_strategy_context(
        result_dir, strategy_regex, min_streak
    )
    feature_rows = sorted(features, key=lambda row: issue_sort_key(str(row["issue"])))
    all_issue_rows: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []

    for spec in specs:
        history: list[dict[str, object]] = []
        replay_rows: list[dict[str, object]] = []
        for feature_row in feature_rows:
            issue = str(feature_row["issue"])
            original = issue_by_id.get(issue)
            if original is None:
                continue
            passed, details = gate_passes(
                spec=spec,
                row=feature_row,
                history=history,
                rolling_window=rolling_window,
                min_history=min_history,
            )
            active = 1 if passed else 0
            stake = fnum(original.get("stake_units"), 0.0) if active else 0.0
            profit = fnum(original.get("profit_units"), 0.0) if active else 0.0
            replay_row = {
                "run": result_dir.name,
                "source_strategy": strategy,
                "gate": spec.name,
                "issue": issue,
                "year": issue_year(issue),
                "signal": 1,
                "active": active,
                "skipped": 0 if active else 1,
                "original_stake_units": fnum(original.get("stake_units"), 0.0),
                "original_profit_units": fnum(original.get("profit_units"), 0.0),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake > 0 else 0.0,
                **{feature: fnum(feature_row.get(feature)) for feature in spec.features},
                **details,
            }
            replay_rows.append(replay_row)
            history.append(feature_row)
        all_issue_rows.extend(replay_rows)
        summary.append(
            summarize_rows(
                run=result_dir.name,
                source_strategy=strategy,
                gate=spec.name,
                rows=replay_rows,
            )
        )
    return summary, all_issue_rows, annual_rows(all_issue_rows), strategy


def compact_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "run",
        "source_strategy",
        "gate",
        "active_issues",
        "skipped_issues",
        "profit_units",
        "roi_on_deployed_stake",
        "roi_on_signal_budget",
        "best_issue_profit_share",
        "roi_ex_best_issue",
        "max_drawdown_pct_on_10000",
        "max_active_loss_streak",
        "n_loss_streaks_ge5",
        "issues_in_loss_streaks_ge5",
        "recent_active_issues",
        "recent_profit_units",
        "recent_roi",
        "recent_roi_ex_best_issue",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows]


def run(args: argparse.Namespace) -> None:
    specs = make_gate_specs(
        parse_strings(args.gate_features),
        parse_floats(args.quantiles),
        parse_strings(args.combined_gates),
    )
    summary, issue_rows, annual, strategy = replay_gates(
        result_dir=args.result_dir.resolve(),
        strategy_regex=args.strategy_regex,
        specs=specs,
        rolling_window=args.rolling_window,
        min_history=args.min_history,
        min_streak=args.min_streak,
    )
    summary.sort(
        key=lambda row: (
            -fnum(row.get("profit_units"), -1e18),
            fnum(row.get("max_drawdown_pct_on_10000"), -1e18),
        )
    )

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "issue_quality_gate_summary.csv", summary)
    write_csv_union(out / "issue_quality_gate_issue_rows.csv", issue_rows)
    write_csv(out / "issue_quality_gate_annual_summary.csv", annual)

    report = [
        "# N=7 rolling issue-quality gate replay",
        "",
        f"- Result dir: `{args.result_dir}`",
        f"- Strategy: `{strategy}`",
        f"- Rolling window: `{args.rolling_window}`",
        f"- Min history: `{args.min_history}`",
        f"- Features: `{args.gate_features}`",
        f"- Quantiles: `{args.quantiles}`",
        f"- Combined gates: `{args.combined_gates}`",
        "",
        "## Summary",
        "",
        md_table(compact_summary(summary), limit=100),
        "## Files",
        "",
        "- `issue_quality_gate_summary.csv`",
        "- `issue_quality_gate_issue_rows.csv`",
        "- `issue_quality_gate_annual_summary.csv`",
        "",
    ]
    (out / "issue_quality_gate_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'issue_quality_gate_report.md'}")
    print(f"Wrote {len(summary)} summary rows and {len(issue_rows)} issue rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_issue_quality_gate"))
    parser.add_argument("--strategy-regex", default=r"7s0p__budget")
    parser.add_argument("--gate-features", default="avg_p_hat,avg_ticket_pred_hit,avg_score")
    parser.add_argument("--combined-gates", default="avg_p_hat+avg_ticket_pred_hit")
    parser.add_argument("--quantiles", default="0.1,0.2,0.3")
    parser.add_argument("--rolling-window", type=int, default=96)
    parser.add_argument("--min-history", type=int, default=48)
    parser.add_argument("--min-streak", type=int, default=5)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
