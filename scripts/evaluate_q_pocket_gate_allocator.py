#!/usr/bin/env python3
"""Apply conservative stake allocation to q-pocket gate selector issue rows."""
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


DEFAULT_POLICIES = (
    "ex1_full_else_half=ex1_full_else_half",
    "ex1_full_raw_half_floor_quarter=ex1_full_raw_half_floor_quarter",
    "ex1_full_raw_half_else_skip=ex1_full_raw_half_else_skip",
    "raw_full_ex1_half_floor_quarter=raw_full_ex1_half_floor_quarter",
)
DEFAULT_PERIODS = (
    "2014-2017:2014:2017",
    "2018-2020:2018:2020",
    "2021-2023:2021:2023",
    "2024-2025:2024:2025",
)


@dataclass(frozen=True)
class PolicySpec:
    label: str
    kind: str


def as_float(row: dict[str, object], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, default)
        if value == "":
            return default
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def parse_policy(raw: str) -> PolicySpec:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("policy must be LABEL=KIND")
    label, kind = raw.split("=", 1)
    label = label.strip()
    kind = kind.strip()
    if not label or not kind:
        raise argparse.ArgumentTypeError("policy must be LABEL=KIND")
    return PolicySpec(label=label, kind=kind)


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


def load_rows(path: Path, selectors: set[str]) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(path)
    out: list[dict[str, object]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if selectors and str(row["selector"]) not in selectors:
                continue
            out.append(dict(row))
    return out


def scale_for_policy(row: dict[str, object], spec: PolicySpec) -> tuple[float, str]:
    history_issues = as_float(row, "history_issues")
    if history_issues <= 0:
        return 1.0, "warmup_full"

    raw_roi = as_float(row, "trailing_roi", float("nan"))
    ex1_roi = as_float(row, "trailing_ex_top1_roi", float("nan"))

    ex1_positive = math.isfinite(ex1_roi) and ex1_roi > 0
    raw_positive = math.isfinite(raw_roi) and raw_roi > 0

    if spec.kind == "ex1_full_else_half":
        return (1.0, "ex1_full") if ex1_positive else (0.5, "else_half")
    if spec.kind == "ex1_full_raw_half_floor_quarter":
        if ex1_positive:
            return 1.0, "ex1_full"
        if raw_positive:
            return 0.5, "raw_half"
        return 0.25, "floor_quarter"
    if spec.kind == "ex1_full_raw_half_else_skip":
        if ex1_positive:
            return 1.0, "ex1_full"
        if raw_positive:
            return 0.5, "raw_half"
        return 0.0, "else_skip"
    if spec.kind == "raw_full_ex1_half_floor_quarter":
        if raw_positive:
            return 1.0, "raw_full"
        if ex1_positive:
            return 0.5, "ex1_half"
        return 0.25, "floor_quarter"
    raise ValueError(f"unknown policy kind: {spec.kind}")


def apply_policies(rows: list[dict[str, object]], policies: list[PolicySpec]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in rows:
        base_stake = as_float(row, "stake_units")
        base_profit = as_float(row, "profit_units")
        base_hits = as_float(row, "hits")
        base_tickets = as_float(row, "tickets")
        for policy in policies:
            scale, reason = scale_for_policy(row, policy)
            converted = dict(row)
            converted["allocation_policy"] = policy.label
            converted["allocation_kind"] = policy.kind
            converted["allocation_scale"] = scale
            converted["allocation_reason"] = reason
            converted["base_stake_units"] = base_stake
            converted["base_profit_units"] = base_profit
            converted["stake_units"] = base_stake * scale
            converted["profit_units"] = base_profit * scale
            converted["hits"] = base_hits if scale > 0 else 0.0
            converted["tickets"] = base_tickets if scale > 0 else 0.0
            converted["deployed"] = 1 if base_stake * scale > 0 else 0
            converted["roi"] = (
                converted["profit_units"] / converted["stake_units"]
                if converted["stake_units"] > 0
                else float("nan")
            )
            out.append(converted)
    return out


def summarize(rows: list[dict[str, object]], group_keys: list[str]) -> list[dict[str, object]]:
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

        ex1 = ex_top(1)
        ex2 = ex_top(2)
        verdict = "negative"
        if profit > 0 and ex1 > 0 and ex2 > 0:
            verdict = "robust"
        elif profit > 0 and ex1 > 0:
            verdict = "top2_sensitive_positive"
        elif profit > 0:
            verdict = "jackpot_dependent"

        result = {group_key: value for group_key, value in zip(group_keys, key)}
        result.update(
            {
                "issues": len(vals),
                "deployed_issues": len(deployed),
                "tickets": tickets,
                "hits": hits,
                "hit_rate": hits / tickets if tickets > 0 else float("nan"),
                "issue_win_rate": (
                    sum(1 for row in deployed if as_float(row, "profit_units") > 0) / len(deployed)
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
                "allocation_reason_counts": ";".join(
                    f"{reason}:{count}" for reason, count in Counter(str(v.get("allocation_reason", "")) for v in vals).most_common()
                ),
                "selected_gate_counts": ";".join(
                    f"{gate}:{count}" for gate, count in Counter(str(v.get("selected_gate", "")) for v in vals).most_common()
                ),
                "verdict": verdict,
            }
        )
        out.append(result)
    return out


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


def compact(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "selector",
        "allocation_policy",
        "period",
        "issues",
        "deployed_issues",
        "hit_rate",
        "issue_win_rate",
        "stake_units",
        "profit_units",
        "roi",
        "ex_top1_roi",
        "ex_top2_roi",
        "max_drawdown_pct_on_10000",
        "allocation_reason_counts",
        "verdict",
    ]
    return [{key: row.get(key, "") for key in keep if key in row} for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selector-rows", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--selector", action="append", required=True)
    parser.add_argument("--policy", action="append", default=list(DEFAULT_POLICIES), help="Policy spec LABEL=KIND")
    parser.add_argument("--period", action="append", default=list(DEFAULT_PERIODS), help="Period spec LABEL:START_YEAR:END_YEAR")
    args = parser.parse_args()

    policies = [parse_policy(raw) for raw in args.policy]
    periods = [parse_period(raw) for raw in args.period]
    rows = load_rows(args.selector_rows, set(args.selector))
    allocated = apply_policies(rows, policies)
    summary = summarize(allocated, ["selector", "allocation_policy"])
    summary.sort(key=lambda row: as_float(row, "profit_units"), reverse=True)
    period_summary = summarize(with_periods(allocated, periods), ["selector", "allocation_policy", "period"])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "allocator_issue_profit.csv", allocated)
    write_csv(args.output_dir / "allocator_summary.csv", summary)
    write_csv(args.output_dir / "allocator_period_summary.csv", period_summary)

    report = [
        "# Q-pocket gate allocator",
        "",
        f"- Selector rows: `{args.selector_rows}`",
        f"- Selectors: `{', '.join(args.selector)}`",
        f"- Policies: `{', '.join(f'{policy.label}={policy.kind}' for policy in policies)}`",
        "",
        "## Summary",
        md_table(compact(summary)),
        "## Period Summary",
        md_table(compact(period_summary)),
        "",
        "## Files",
        "",
        "- `allocator_issue_profit.csv`",
        "- `allocator_summary.csv`",
        "- `allocator_period_summary.csv`",
        "",
    ]
    (args.output_dir / "allocator_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'allocator_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
