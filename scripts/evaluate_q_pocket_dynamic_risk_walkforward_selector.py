#!/usr/bin/env python3
"""Walk-forward select dynamic risk policies using only prior issue PnL."""
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


@dataclass(frozen=True)
class PolicySpec:
    label: str
    selector: str
    allocation_policy: str


def as_float(row: dict[str, object], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, default)
        if value == "":
            return default
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def parse_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def parse_policy(raw: str) -> PolicySpec:
    parts = raw.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("policy must be LABEL:SELECTOR:ALLOCATION_POLICY")
    label, selector, allocation_policy = (part.strip() for part in parts)
    if not label or not selector or not allocation_policy:
        raise argparse.ArgumentTypeError("policy must be LABEL:SELECTOR:ALLOCATION_POLICY")
    return PolicySpec(label=label, selector=selector, allocation_policy=allocation_policy)


def parse_period(raw: str) -> tuple[str, int, int]:
    parts = raw.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("period must be LABEL:START_YEAR:END_YEAR")
    label, start, end = parts
    return label, int(start), int(end)


def issue_year(issue: str) -> int | None:
    text = issue.strip()
    if len(text) < 2 or not text[:2].isdigit():
        return None
    return 2000 + int(text[:2])


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


def load_policy_rows(path: Path, policies: list[PolicySpec]) -> tuple[list[str], dict[str, dict[str, dict[str, object]]]]:
    if not path.exists():
        raise FileNotFoundError(path)
    wanted = {(policy.selector, policy.allocation_policy): policy.label for policy in policies}
    rows_by_policy: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    issues: set[str] = set()
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (str(row.get("selector", "")), str(row.get("allocation_policy", "")))
            label = wanted.get(key)
            if label is None:
                continue
            issue = str(row["issue"])
            issues.add(issue)
            converted = dict(row)
            converted["candidate_policy"] = label
            rows_by_policy[label][issue] = converted

    issue_list = sorted(issues)
    missing: list[str] = []
    for policy in policies:
        for issue in issue_list:
            if issue not in rows_by_policy[policy.label]:
                missing.append(f"{policy.label}:{issue}")
                if len(missing) >= 5:
                    break
        if len(missing) >= 5:
            break
    if missing:
        raise RuntimeError(f"Missing policy issue rows, examples: {', '.join(missing)}")
    return issue_list, rows_by_policy


def trailing_stats(rows_by_issue: dict[str, dict[str, object]], history: list[str]) -> dict[str, float]:
    vals = [rows_by_issue[issue] for issue in history]
    stake = sum(as_float(row, "stake_units") for row in vals)
    profit = sum(as_float(row, "profit_units") for row in vals)
    profits = [as_float(row, "profit_units") for row in vals]
    ranked = sorted(vals, key=lambda row: as_float(row, "profit_units"), reverse=True)
    ex1 = ranked[1:]
    ex2 = ranked[2:]
    ex1_stake = sum(as_float(row, "stake_units") for row in ex1)
    ex1_profit = sum(as_float(row, "profit_units") for row in ex1)
    ex2_stake = sum(as_float(row, "stake_units") for row in ex2)
    ex2_profit = sum(as_float(row, "profit_units") for row in ex2)
    return {
        "stake": stake,
        "profit": profit,
        "roi": profit / stake if stake > 0 else float("-inf"),
        "profit_per_100": profit / len(history) * 100 if history else float("-inf"),
        "ex_top1_roi": ex1_profit / ex1_stake if ex1_stake > 0 else float("-inf"),
        "ex_top2_roi": ex2_profit / ex2_stake if ex2_stake > 0 else float("-inf"),
        "drawdown_pct": max_drawdown(profits),
    }


def score_stats(stats: dict[str, float], metric: str, dd_penalty: float) -> float:
    if metric == "profit_per_100":
        base = stats["profit_per_100"]
    elif metric == "roi":
        base = stats["roi"]
    elif metric == "ex_top1_roi":
        base = stats["ex_top1_roi"]
    elif metric == "ex_top2_roi":
        base = stats["ex_top2_roi"]
    else:
        raise ValueError(f"unsupported metric: {metric}")
    if not math.isfinite(base):
        return float("-inf")
    return base - dd_penalty * abs(stats["drawdown_pct"])


def select_rows(
    issues: list[str],
    rows_by_policy: dict[str, dict[str, dict[str, object]]],
    *,
    windows: list[int],
    metrics: list[str],
    dd_penalties: list[float],
    warmup_issues: int,
    min_trailing_stake: float,
    default_policy: str,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    policy_names = sorted(rows_by_policy)
    for window in windows:
        for metric in metrics:
            for dd_penalty in dd_penalties:
                wf_selector = f"wf_{metric}_w{window}_dd{dd_penalty:g}"
                for idx, issue in enumerate(issues):
                    history = issues[max(0, idx - window) : idx]
                    selected_policy = default_policy
                    selected_score = float("nan")
                    selected_stats = {
                        "wf_history_issues": len(history),
                        "wf_trailing_stake": 0.0,
                        "wf_trailing_profit": 0.0,
                        "wf_trailing_roi": float("nan"),
                        "wf_trailing_profit_per_100": float("nan"),
                        "wf_trailing_ex_top1_roi": float("nan"),
                        "wf_trailing_ex_top2_roi": float("nan"),
                        "wf_trailing_drawdown_pct": 0.0,
                    }
                    if len(history) >= warmup_issues:
                        scored: list[tuple[float, str, dict[str, float]]] = []
                        for policy in policy_names:
                            stats = trailing_stats(rows_by_policy[policy], history)
                            score = (
                                score_stats(stats, metric, dd_penalty)
                                if stats["stake"] >= min_trailing_stake
                                else float("-inf")
                            )
                            scored.append((score, policy, stats))
                        scored.sort(key=lambda item: (item[0], item[1] == default_policy), reverse=True)
                        selected_score, selected_policy, stats = scored[0]
                        selected_stats = {
                            "wf_history_issues": len(history),
                            "wf_trailing_stake": stats["stake"],
                            "wf_trailing_profit": stats["profit"],
                            "wf_trailing_roi": stats["roi"],
                            "wf_trailing_profit_per_100": stats["profit_per_100"],
                            "wf_trailing_ex_top1_roi": stats["ex_top1_roi"],
                            "wf_trailing_ex_top2_roi": stats["ex_top2_roi"],
                            "wf_trailing_drawdown_pct": stats["drawdown_pct"],
                        }
                    base = dict(rows_by_policy[selected_policy][issue])
                    base["wf_selector"] = wf_selector
                    base["wf_selected_policy"] = selected_policy
                    base["wf_selected_score"] = selected_score
                    base.update(selected_stats)
                    out.append(base)
    return out


def summarize(rows: list[dict[str, object]], group_keys: list[str]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(key, "") for key in group_keys)].append(row)
    out: list[dict[str, object]] = []
    for key, vals in sorted(grouped.items()):
        vals = sorted(vals, key=lambda row: str(row["issue"]))
        stake = sum(as_float(row, "stake_units") for row in vals)
        profit = sum(as_float(row, "profit_units") for row in vals)
        tickets = sum(as_float(row, "tickets") for row in vals)
        hits = sum(as_float(row, "hits") for row in vals)
        deployed = [row for row in vals if as_float(row, "stake_units") > 0]
        profits = [as_float(row, "profit_units") for row in vals]
        ranked = sorted(vals, key=lambda row: as_float(row, "profit_units"), reverse=True)
        best_profit = as_float(ranked[0], "profit_units") if ranked else 0.0
        second_profit = as_float(ranked[1], "profit_units") if len(ranked) > 1 else 0.0
        years = sorted({issue_year(str(row["issue"])) for row in vals if issue_year(str(row["issue"])) is not None})
        span_years = max(1, max(years) - min(years) + 1) if years else 1

        annual_profit: dict[int, float] = defaultdict(float)
        for row in vals:
            year = issue_year(str(row["issue"]))
            if year is not None:
                annual_profit[year] += as_float(row, "profit_units")
        losing_years = sum(1 for year in years if annual_profit[year] < 0)

        result = {group_key: value for group_key, value in zip(group_keys, key)}
        result.update(
            {
                "issues": len(vals),
                "deployed_issues": len(deployed),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake > 0 else float("nan"),
                "profit_per_100_issues": profit / len(vals) * 100 if vals else float("nan"),
                "profit_per_year": profit / span_years,
                "hit_rate": hits / tickets if tickets > 0 else float("nan"),
                "issue_win_rate": (
                    sum(1 for row in deployed if as_float(row, "profit_units") > 0) / len(deployed)
                    if deployed
                    else float("nan")
                ),
                "losing_years": losing_years,
                "max_drawdown_pct_on_10000": max_drawdown(profits),
                "max_loss_streak_issues": max_loss_streak(profits),
                "best_issue": ranked[0]["issue"] if ranked else "",
                "best_issue_profit_units": best_profit,
                "best_issue_profit_share": best_profit / profit if profit > 0 and best_profit > 0 else "",
                "top2_issue_profit_share": (
                    (best_profit + max(0.0, second_profit)) / profit
                    if profit > 0 and best_profit > 0
                    else ""
                ),
                "wf_selected_policy_counts": ";".join(
                    f"{policy}:{count}"
                    for policy, count in Counter(str(row.get("wf_selected_policy", "")) for row in vals).most_common()
                ),
            }
        )
        out.append(result)
    out.sort(key=lambda row: as_float(row, "profit_per_100_issues"), reverse=True)
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
        "wf_selector",
        "period",
        "issues",
        "stake_units",
        "profit_units",
        "roi",
        "profit_per_100_issues",
        "profit_per_year",
        "losing_years",
        "max_drawdown_pct_on_10000",
        "wf_selected_policy_counts",
    ]
    return [{key: row.get(key, "") for key in keep if key in row} for row in rows]


def run(args: argparse.Namespace) -> None:
    policies = [parse_policy(raw) for raw in args.policy]
    periods = [parse_period(raw) for raw in args.period]
    issues, rows_by_policy = load_policy_rows(args.policy_rows, policies)
    selected = select_rows(
        issues,
        rows_by_policy,
        windows=parse_ints(args.windows),
        metrics=[metric.strip() for metric in args.metrics.split(",") if metric.strip()],
        dd_penalties=parse_floats(args.dd_penalties),
        warmup_issues=args.warmup_issues,
        min_trailing_stake=args.min_trailing_stake,
        default_policy=args.default_policy,
    )
    summary = summarize(selected, ["wf_selector"])
    period_summary = summarize(with_periods(selected, periods), ["wf_selector", "period"])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "dynamic_risk_wf_issue_profit.csv", selected)
    write_csv(args.output_dir / "dynamic_risk_wf_summary.csv", summary)
    write_csv(args.output_dir / "dynamic_risk_wf_period_summary.csv", period_summary)

    report = [
        "# Dynamic Risk Walk-forward Selector",
        "",
        "Each issue's risk policy is selected using only policy PnL from prior issues.",
        "",
        f"- Policy rows: `{args.policy_rows}`",
        f"- Policies: `{', '.join(f'{p.label}:{p.selector}:{p.allocation_policy}' for p in policies)}`",
        f"- Windows: `{args.windows}`",
        f"- Metrics: `{args.metrics}`",
        f"- DD penalties: `{args.dd_penalties}`",
        f"- Warmup issues: `{args.warmup_issues}`",
        f"- Min trailing stake: `{args.min_trailing_stake}`",
        f"- Default policy: `{args.default_policy}`",
        "",
        "## Top Walk-forward Selectors",
        md_table(compact(summary[:20])),
        "## Period Summary",
        md_table(compact(period_summary)),
        "",
        "## Files",
        "",
        "- `dynamic_risk_wf_issue_profit.csv`",
        "- `dynamic_risk_wf_summary.csv`",
        "- `dynamic_risk_wf_period_summary.csv`",
        "",
    ]
    (args.output_dir / "dynamic_risk_wf_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'dynamic_risk_wf_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-rows", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--policy", action="append", required=True, help="LABEL:SELECTOR:ALLOCATION_POLICY")
    parser.add_argument("--windows", default="52,104")
    parser.add_argument("--metrics", default="profit_per_100,roi,ex_top1_roi")
    parser.add_argument("--dd-penalties", default="0,250")
    parser.add_argument("--warmup-issues", type=int, default=52)
    parser.add_argument("--min-trailing-stake", type=float, default=500.0)
    parser.add_argument("--default-policy", default="full")
    parser.add_argument(
        "--period",
        action="append",
        default=[
            "2014-2017:2014:2017",
            "2018-2020:2018:2020",
            "2021-2024:2021:2024",
            "2025:2025:2025",
            "2014-2024:2014:2024",
        ],
        help="Period spec LABEL:START_YEAR:END_YEAR",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
