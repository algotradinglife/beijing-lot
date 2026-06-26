#!/usr/bin/env python3
"""Evaluate rolling gate selectors over q-pocket strategy outputs.

Each issue's gate is selected using only prior issue-level PnL from already
generated q-pocket walk-forward outputs. This is a first-pass regime selector
benchmark, not a production policy.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


DEFAULT_GATES = (
    "whitelist=q_pocket_whitelist_open__budget20_whole",
    "core30=q_pocket_core_issue_gate30__budget20_whole",
    "keyed=q_pocket_keyed_pockets__budget20_whole",
)
DEFAULT_PERIODS = (
    "2014-2017:2014:2017",
    "2018-2020:2018:2020",
    "2021-2023:2021:2023",
    "2024-2025:2024:2025",
)


@dataclass(frozen=True)
class GateSpec:
    label: str
    strategy: str


def as_float(row: dict[str, object], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, default)
        if value == "":
            return default
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def as_int(row: dict[str, object], key: str, default: int = 0) -> int:
    try:
        value = row.get(key, default)
        if value == "":
            return default
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def parse_gate(raw: str) -> GateSpec:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("gate must be LABEL=STRATEGY_NAME")
    label, strategy = raw.split("=", 1)
    label = label.strip()
    strategy = strategy.strip()
    if not label or not strategy:
        raise argparse.ArgumentTypeError("gate must be LABEL=STRATEGY_NAME")
    return GateSpec(label=label, strategy=strategy)


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def parse_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def parse_period(raw: str) -> tuple[str, int, int]:
    parts = raw.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("period must be LABEL:START_YEAR:END_YEAR")
    label, start, end = parts
    return label, int(start), int(end)


def issue_year(issue: str) -> int | None:
    if len(issue) < 2 or not issue[:2].isdigit():
        return None
    return 2000 + int(issue[:2])


def with_periods(rows: list[dict[str, object]], periods: list[tuple[str, int, int]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in rows:
        year = issue_year(str(row["issue"]))
        if year is None:
            continue
        for label, start, end in periods:
            if start <= year <= end:
                converted = dict(row)
                converted["period"] = label
                out.append(converted)
                break
    return out


def max_drawdown(profits: list[float], initial_equity: float = 10_000.0) -> float:
    equity = initial_equity
    peak = equity
    max_dd = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        if peak > 0:
            max_dd = min(max_dd, (equity - peak) / peak)
    return max_dd


def max_loss_streak(profits: list[float]) -> int:
    current = 0
    worst = 0
    for profit in profits:
        if profit > 0:
            current = 0
        else:
            current += 1
            worst = max(worst, current)
    return worst


def load_issue_rows(result_dir: Path, gates: list[GateSpec]) -> tuple[list[str], dict[str, dict[str, dict[str, object]]]]:
    path = result_dir / "q_pocket_budget_rows.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    strategy_to_label = {gate.strategy: gate.label for gate in gates}
    grouped: dict[str, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: {"stake": 0.0, "profit": 0.0, "hits": 0.0, "tickets": 0.0})
    )
    issues: set[str] = set()
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            strategy = str(row["strategy"])
            label = strategy_to_label.get(strategy)
            if label is None:
                continue
            issue = str(row["issue"])
            issues.add(issue)
            vals = grouped[label][issue]
            vals["stake"] += as_float(row, "stake_units")
            vals["profit"] += as_float(row, "profit_units")
            vals["hits"] += as_float(row, "hit")
            vals["tickets"] += 1.0

    issue_list = sorted(issues)
    rows_by_gate: dict[str, dict[str, dict[str, object]]] = {}
    for gate in gates:
        by_issue: dict[str, dict[str, object]] = {}
        for issue in issue_list:
            vals = grouped[gate.label].get(issue, {"stake": 0.0, "profit": 0.0, "hits": 0.0, "tickets": 0.0})
            stake = float(vals["stake"])
            profit = float(vals["profit"])
            by_issue[issue] = {
                "gate": gate.label,
                "strategy": gate.strategy,
                "issue": issue,
                "stake_units": stake,
                "profit_units": profit,
                "hits": float(vals["hits"]),
                "tickets": float(vals["tickets"]),
                "roi": profit / stake if stake > 0 else float("nan"),
                "deployed": 1 if stake > 0 else 0,
            }
        rows_by_gate[gate.label] = by_issue
    return issue_list, rows_by_gate


def trailing_stats(rows_by_issue: dict[str, dict[str, object]], history: list[str]) -> dict[str, float]:
    vals = [rows_by_issue[issue] for issue in history]
    stake = sum(as_float(row, "stake_units") for row in vals)
    profit = sum(as_float(row, "profit_units") for row in vals)
    profits = [as_float(row, "profit_units") for row in vals]
    issue_rows = sorted(vals, key=lambda row: as_float(row, "profit_units"), reverse=True)
    ex1 = issue_rows[1:]
    ex2 = issue_rows[2:]
    ex1_stake = sum(as_float(row, "stake_units") for row in ex1)
    ex1_profit = sum(as_float(row, "profit_units") for row in ex1)
    ex2_stake = sum(as_float(row, "stake_units") for row in ex2)
    ex2_profit = sum(as_float(row, "profit_units") for row in ex2)
    deployed = [row for row in vals if as_float(row, "stake_units") > 0]
    return {
        "stake": stake,
        "profit": profit,
        "roi": profit / stake if stake > 0 else float("-inf"),
        "ex_top1_roi": ex1_profit / ex1_stake if ex1_stake > 0 else float("-inf"),
        "ex_top2_roi": ex2_profit / ex2_stake if ex2_stake > 0 else float("-inf"),
        "drawdown_pct": max_drawdown(profits),
        "deployed_issues": float(len(deployed)),
        "issue_win_rate": (
            sum(1 for row in deployed if as_float(row, "profit_units") > 0) / len(deployed)
            if deployed
            else 0.0
        ),
    }


def score_stats(stats: dict[str, float], metric: str, dd_penalty: float) -> float:
    if metric == "roi":
        base = stats["roi"]
    elif metric == "ex_top1_roi":
        base = stats["ex_top1_roi"]
    elif metric == "ex_top2_roi":
        base = stats["ex_top2_roi"]
    elif metric == "profit":
        base = stats["profit"]
    else:
        raise ValueError(f"unsupported metric: {metric}")
    if not math.isfinite(base):
        return float("-inf")
    return base - dd_penalty * abs(stats["drawdown_pct"])


def summarize_issue_rows(rows: list[dict[str, object]], group_keys: list[str]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(key, "") for key in group_keys)].append(row)
    out: list[dict[str, object]] = []
    for key, vals in sorted(grouped.items()):
        vals = sorted(vals, key=lambda row: str(row["issue"]))
        deployed = [row for row in vals if as_float(row, "stake_units") > 0]
        stake = sum(as_float(row, "stake_units") for row in vals)
        profit = sum(as_float(row, "profit_units") for row in vals)
        hits = sum(as_float(row, "hits") for row in vals)
        tickets = sum(as_float(row, "tickets") for row in vals)
        issue_profits = [as_float(row, "profit_units") for row in vals]
        ranked = sorted(vals, key=lambda row: as_float(row, "profit_units"), reverse=True)
        best_profit = as_float(ranked[0], "profit_units") if ranked else 0.0
        second_profit = as_float(ranked[1], "profit_units") if len(ranked) > 1 else 0.0

        def ex_top(k: int) -> float:
            kept = ranked[k:]
            kept_stake = sum(as_float(row, "stake_units") for row in kept)
            kept_profit = sum(as_float(row, "profit_units") for row in kept)
            return kept_profit / kept_stake if kept_stake > 0 else float("nan")

        verdict = "negative"
        ex1 = ex_top(1)
        ex2 = ex_top(2)
        if profit > 0 and ex1 > 0 and ex2 > 0:
            verdict = "robust"
        elif profit > 0 and ex1 > 0:
            verdict = "top2_sensitive_positive"
        elif profit > 0:
            verdict = "jackpot_dependent"

        row = {group_key: value for group_key, value in zip(group_keys, key)}
        row.update(
            {
                "issues": len(vals),
                "deployed_issues": len(deployed),
                "tickets": tickets,
                "hits": hits,
                "hit_rate": hits / tickets if tickets > 0 else float("nan"),
                "issue_win_rate": (
                    sum(1 for row_ in deployed if as_float(row_, "profit_units") > 0) / len(deployed)
                    if deployed
                    else float("nan")
                ),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake > 0 else float("nan"),
                "best_issue": ranked[0]["issue"] if ranked else "",
                "best_issue_profit_units": best_profit,
                "best_issue_profit_share": best_profit / profit if profit > 0 and best_profit > 0 else "",
                "top2_issue_profit_share": (
                    (best_profit + max(0.0, second_profit)) / profit
                    if profit > 0 and best_profit > 0
                    else ""
                ),
                "ex_top1_roi": ex1,
                "ex_top2_roi": ex2,
                "max_drawdown_pct_on_10000": max_drawdown(issue_profits),
                "max_loss_streak_issues": max_loss_streak(issue_profits),
                "selected_gate_counts": ";".join(
                    f"{gate}:{count}" for gate, count in Counter(str(v.get("selected_gate", v.get("gate", ""))) for v in vals).most_common()
                ),
                "verdict": verdict,
            }
        )
        out.append(row)
    return out


def fixed_rows(rows_by_gate: dict[str, dict[str, dict[str, object]]], issues: list[str]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for gate, by_issue in rows_by_gate.items():
        for issue in issues:
            row = dict(by_issue[issue])
            row["mode"] = "fixed"
            row["selector"] = gate
            row["selected_gate"] = gate
            row["selected_score"] = ""
            out.append(row)
    return out


def selector_rows(
    rows_by_gate: dict[str, dict[str, dict[str, object]]],
    issues: list[str],
    *,
    windows: list[int],
    metrics: list[str],
    dd_penalties: list[float],
    warmup_issues: int,
    min_trailing_stake: float,
    min_score: float,
    default_gate: str,
    allow_skip: bool,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    gate_names = sorted(rows_by_gate)
    for window in windows:
        for metric in metrics:
            for dd_penalty in dd_penalties:
                selector = f"rolling_{metric}_w{window}_dd{dd_penalty:g}"
                for idx, issue in enumerate(issues):
                    history = issues[max(0, idx - window) : idx]
                    selected_gate = default_gate
                    selected_score = float("nan")
                    selected_stats = {
                        "trailing_stake": 0.0,
                        "trailing_profit": 0.0,
                        "trailing_roi": float("nan"),
                        "trailing_ex_top1_roi": float("nan"),
                        "trailing_ex_top2_roi": float("nan"),
                        "trailing_drawdown_pct": 0.0,
                    }
                    if len(history) >= warmup_issues:
                        scored: list[tuple[float, str, dict[str, float]]] = []
                        for gate in gate_names:
                            stats = trailing_stats(rows_by_gate[gate], history)
                            if stats["stake"] < min_trailing_stake:
                                score = float("-inf")
                            else:
                                score = score_stats(stats, metric, dd_penalty)
                            scored.append((score, gate, stats))
                        scored.sort(key=lambda item: (item[0], item[1] == default_gate), reverse=True)
                        selected_score, selected_gate, stats = scored[0]
                        selected_stats = {
                            "trailing_stake": stats["stake"],
                            "trailing_profit": stats["profit"],
                            "trailing_roi": stats["roi"],
                            "trailing_ex_top1_roi": stats["ex_top1_roi"],
                            "trailing_ex_top2_roi": stats["ex_top2_roi"],
                            "trailing_drawdown_pct": stats["drawdown_pct"],
                        }
                        if allow_skip and (not math.isfinite(selected_score) or selected_score <= min_score):
                            selected_gate = "SKIP"
                    if selected_gate == "SKIP":
                        base = {
                            "gate": "SKIP",
                            "strategy": "SKIP",
                            "issue": issue,
                            "stake_units": 0.0,
                            "profit_units": 0.0,
                            "hits": 0.0,
                            "tickets": 0.0,
                            "roi": float("nan"),
                            "deployed": 0,
                        }
                    else:
                        base = dict(rows_by_gate[selected_gate][issue])
                    base.update(
                        {
                            "mode": "selector",
                            "selector": selector,
                            "selected_gate": selected_gate,
                            "selected_score": selected_score,
                            "history_issues": len(history),
                            **selected_stats,
                        }
                    )
                    out.append(base)
    return out


def compact_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "mode",
        "selector",
        "issues",
        "deployed_issues",
        "hit_rate",
        "issue_win_rate",
        "stake_units",
        "profit_units",
        "roi",
        "best_issue_profit_share",
        "ex_top1_roi",
        "ex_top2_roi",
        "max_drawdown_pct_on_10000",
        "selected_gate_counts",
        "verdict",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows]


def run(args: argparse.Namespace) -> None:
    gates = [parse_gate(raw) for raw in (args.gate or DEFAULT_GATES)]
    issues, rows_by_gate = load_issue_rows(args.result_dir, gates)
    fixed = fixed_rows(rows_by_gate, issues)
    selected = selector_rows(
        rows_by_gate,
        issues,
        windows=parse_ints(args.windows),
        metrics=[x.strip() for x in args.metrics.split(",") if x.strip()],
        dd_penalties=parse_floats(args.dd_penalties),
        warmup_issues=args.warmup_issues,
        min_trailing_stake=args.min_trailing_stake,
        min_score=args.min_score,
        default_gate=args.default_gate,
        allow_skip=not args.no_skip,
    )
    periods = [parse_period(raw) for raw in args.period]
    fixed_period = summarize_issue_rows(with_periods(fixed, periods), ["mode", "selector", "period"])
    selector_period = summarize_issue_rows(with_periods(selected, periods), ["mode", "selector", "period"])

    summary = summarize_issue_rows(fixed, ["mode", "selector"])
    selector_summary = summarize_issue_rows(selected, ["mode", "selector"])
    summary.extend(selector_summary)
    summary.sort(key=lambda row: (str(row["mode"]), float(row["roi"]) if str(row["roi"]) != "nan" else -999), reverse=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "gate_selector_issue_profit.csv", selected)
    write_csv(args.output_dir / "gate_fixed_issue_profit.csv", fixed)
    write_csv(args.output_dir / "gate_selector_summary.csv", selector_summary)
    write_csv(args.output_dir / "gate_fixed_summary.csv", summarize_issue_rows(fixed, ["mode", "selector"]))
    write_csv(args.output_dir / "gate_selector_combined_summary.csv", summary)
    write_csv(args.output_dir / "gate_selector_period_summary.csv", selector_period)
    write_csv(args.output_dir / "gate_fixed_period_summary.csv", fixed_period)

    top_selector_rows = [row for row in selector_summary if as_float(row, "stake_units") > 0]
    top_selector_rows.sort(key=lambda row: as_float(row, "roi"), reverse=True)
    report = [
        "# Q-pocket rolling gate selector",
        "",
        "The selector chooses a gate for issue T using only issue-level PnL from issues before T.",
        "",
        f"- Result dir: `{args.result_dir}`",
        f"- Gates: `{', '.join(f'{gate.label}={gate.strategy}' for gate in gates)}`",
        f"- Windows: `{args.windows}`",
        f"- Metrics: `{args.metrics}`",
        f"- DD penalties: `{args.dd_penalties}`",
        f"- Warmup issues: `{args.warmup_issues}`",
        f"- Min trailing stake: `{args.min_trailing_stake}`",
        f"- Skip threshold: `{args.min_score}`",
        "",
        "## Fixed Gates",
        md_table(summarize_issue_rows(fixed, ["mode", "selector"])),
        "## Top Selectors",
        md_table(compact_summary(top_selector_rows[:20])),
        "## Top Selector Periods",
        md_table(
            compact_summary(
                [
                    row
                    for row in selector_period
                    if row["selector"] in {str(top["selector"]) for top in top_selector_rows[:5]}
                ]
            )
        ),
        "",
        "## Files",
        "",
        "- `gate_selector_issue_profit.csv`",
        "- `gate_fixed_issue_profit.csv`",
        "- `gate_selector_summary.csv`",
        "- `gate_fixed_summary.csv`",
        "- `gate_selector_combined_summary.csv`",
        "- `gate_selector_period_summary.csv`",
        "- `gate_fixed_period_summary.csv`",
        "",
    ]
    (args.output_dir / "gate_selector_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'gate_selector_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gate", action="append", help="Gate spec LABEL=STRATEGY_NAME. May be repeated.")
    parser.add_argument("--windows", default="24,48,72")
    parser.add_argument("--metrics", default="roi,ex_top1_roi,ex_top2_roi")
    parser.add_argument("--dd-penalties", default="0,1")
    parser.add_argument("--warmup-issues", type=int, default=24)
    parser.add_argument("--min-trailing-stake", type=float, default=200.0)
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--default-gate", default="core30")
    parser.add_argument("--no-skip", action="store_true")
    parser.add_argument("--period", action="append", default=list(DEFAULT_PERIODS), help="Period spec LABEL:START_YEAR:END_YEAR")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
