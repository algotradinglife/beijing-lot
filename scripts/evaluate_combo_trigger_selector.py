#!/usr/bin/env python3
"""Rolling selector for main-vs-cold-tail trigger rules.

The selector chooses a rule for issue T using only issue rows before T. This is
intended as a light overfit check for trigger filters discovered in sensitivity
runs, not as a final production policy.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_combo_main_cold_tail import max_drawdown, max_loss_streak
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


DEFAULT_RULES = (
    "cold_q180=results/combo_trigger_cand15_q180_t{train}",
    "cold_q100_pmax10=results/combo_trigger_cand15_q100_pmax10_t{train}",
)


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def parse_rule(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("rule must be NAME=PATH_TEMPLATE")
    name, template = raw.split("=", 1)
    name = name.strip()
    template = template.strip()
    if not name or not template:
        raise argparse.ArgumentTypeError("rule must be NAME=PATH_TEMPLATE")
    return name, template


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


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


def normalize_issue_row(row: dict[str, str], *, train_window: int, rule: str, source: Path) -> dict[str, object]:
    budget = as_float(row, "budget")
    profit = as_float(row, "profit")
    return {
        "train_window": train_window,
        "rule": rule,
        "issue": str(row["issue"]),
        "budget": budget,
        "deployed_stake": as_float(row, "deployed_stake", budget),
        "profit": profit,
        "budget_roi": profit / budget if budget else float("nan"),
        "main_profit": as_float(row, "main_profit", profit),
        "cold_profit": as_float(row, "cold_profit"),
        "cold_stake": as_float(row, "cold_stake"),
        "triggered": as_int(row, "triggered"),
        "cold_tickets": as_int(row, "cold_tickets"),
        "cold_hits": as_int(row, "cold_hits"),
        "n_cold_candidate_matches": as_int(row, "n_cold_candidate_matches"),
        "n_q_legs": as_int(row, "n_q_legs"),
        "source": str(source),
    }


def load_main_rows(result_dir: Path, train_window: int) -> dict[str, dict[str, object]]:
    path = result_dir / "allocation_issue_profit.csv"
    rows = read_csv_rows(path)
    out: dict[str, dict[str, object]] = {}
    for row in rows:
        if row.get("allocation") != "main_100%_cold_0%":
            continue
        normalized = normalize_issue_row(row, train_window=train_window, rule="main_only", source=path)
        out[str(normalized["issue"])] = normalized
    return out


def load_conditional_rows(result_dir: Path, train_window: int, rule: str) -> dict[str, dict[str, object]]:
    path = result_dir / "conditional_allocation_issue_profit.csv"
    rows = read_csv_rows(path)
    out: dict[str, dict[str, object]] = {}
    for row in rows:
        normalized = normalize_issue_row(row, train_window=train_window, rule=rule, source=path)
        out[str(normalized["issue"])] = normalized
    return out


def trailing_score(
    rows_by_issue: dict[str, dict[str, object]],
    history: list[str],
    *,
    metric: str,
    dd_penalty: float,
) -> tuple[float, dict[str, float]]:
    vals = [rows_by_issue[i] for i in history if i in rows_by_issue]
    budget = sum(as_float(r, "budget") for r in vals)
    profit = sum(as_float(r, "profit") for r in vals)
    profits = [as_float(r, "profit") for r in vals]
    roi = profit / budget if budget else float("-inf")
    dd = max_drawdown(profits)
    if metric == "profit":
        raw = profit
        penalty_base = budget if budget else 1.0
        score = raw - dd_penalty * dd / penalty_base
    elif metric == "roi":
        score = roi - dd_penalty * (dd / budget if budget else 0.0)
    else:
        raise ValueError(f"unsupported selector metric: {metric}")
    return score, {"trailing_budget": budget, "trailing_profit": profit, "trailing_roi": roi, "trailing_dd": dd}


def summarize(rows: list[dict[str, object]], group_keys: list[str]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(k, "") for k in group_keys)].append(row)
    out: list[dict[str, object]] = []
    for key, vals in sorted(grouped.items()):
        vals = sorted(vals, key=lambda r: (int(r.get("train_window", 0)), str(r.get("issue", ""))))
        profits = [as_float(r, "profit") for r in vals]
        budget = sum(as_float(r, "budget") for r in vals)
        profit = sum(profits)
        selected_counts = Counter(str(r.get("selected_rule", r.get("rule", ""))) for r in vals)
        row = {k: v for k, v in zip(group_keys, key)}
        row.update(
            {
                "issues": len(vals),
                "triggered_issues": sum(1 for r in vals if as_int(r, "triggered") > 0),
                "budget": budget,
                "profit": profit,
                "budget_roi": profit / budget if budget else float("nan"),
                "profitable_issues": sum(1 for p in profits if p > 0),
                "max_issue_profit": max(profits) if profits else 0.0,
                "min_issue_profit": min(profits) if profits else 0.0,
                "max_issue_loss_streak": max_loss_streak(profits),
                "max_drawdown_units": max_drawdown(profits),
                "selected_rule_counts": ";".join(f"{name}:{count}" for name, count in selected_counts.most_common()),
            }
        )
        out.append(row)
    return out


def run(args: argparse.Namespace) -> None:
    train_windows = parse_ints(args.train_windows)
    rule_specs = [parse_rule(raw) for raw in (args.rule or DEFAULT_RULES)]

    selector_rows: list[dict[str, object]] = []
    fixed_rows: list[dict[str, object]] = []

    for train_window in train_windows:
        rule_maps: dict[str, dict[str, dict[str, object]]] = {}
        first_rule_dir = Path(rule_specs[0][1].format(train=train_window))
        main_rows = load_main_rows(first_rule_dir, train_window)
        rule_maps["main_only"] = main_rows

        for rule_name, template in rule_specs:
            result_dir = Path(template.format(train=train_window))
            rule_maps[rule_name] = load_conditional_rows(result_dir, train_window, rule_name)

        issues = sorted(main_rows)
        for rule_name, issue_map in rule_maps.items():
            for issue in issues:
                row = issue_map.get(issue, main_rows[issue]).copy()
                row["fixed_rule"] = rule_name
                fixed_rows.append(row)

        for idx, issue in enumerate(issues):
            history = issues[max(0, idx - args.trailing_issues) : idx]
            if len(history) < args.warmup_issues:
                selected_rule = args.default_rule
                score_details = {"trailing_budget": 0.0, "trailing_profit": 0.0, "trailing_roi": float("nan"), "trailing_dd": 0.0}
                selected_score = float("nan")
            else:
                scored: list[tuple[float, str, dict[str, float]]] = []
                for rule_name, issue_map in rule_maps.items():
                    score, details = trailing_score(
                        issue_map,
                        history,
                        metric=args.metric,
                        dd_penalty=args.dd_penalty,
                    )
                    scored.append((score, rule_name, details))
                scored.sort(key=lambda x: (x[0], x[1] == args.default_rule), reverse=True)
                selected_score, selected_rule, score_details = scored[0]

            issue_map = rule_maps.get(selected_rule, main_rows)
            selected_row = issue_map.get(issue, main_rows[issue]).copy()
            selected_row.update(
                {
                    "selector": args.selector_name,
                    "selected_rule": selected_rule,
                    "selected_score": selected_score,
                    "history_issues": len(history),
                    **score_details,
                }
            )
            selector_rows.append(selected_row)

    selector_summary = summarize(selector_rows, ["selector", "train_window"])
    selector_summary.extend(summarize(selector_rows, ["selector"]))
    fixed_summary = summarize(fixed_rows, ["fixed_rule", "train_window"])
    fixed_summary.extend(summarize(fixed_rows, ["fixed_rule"]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "selector_issue_profit.csv", selector_rows)
    write_csv(args.output_dir / "selector_summary.csv", selector_summary)
    write_csv(args.output_dir / "fixed_rule_issue_profit.csv", fixed_rows)
    write_csv(args.output_dir / "fixed_rule_summary.csv", fixed_summary)

    report = [
        "# Combo Trigger Rolling Selector",
        "",
        "The selector chooses each issue using only previous issues in the same train-window sensitivity run.",
        "",
        f"- Train windows: `{args.train_windows}`",
        f"- Warmup issues: `{args.warmup_issues}`",
        f"- Trailing issues: `{args.trailing_issues}`",
        f"- Metric: `{args.metric}`",
        f"- Drawdown penalty: `{args.dd_penalty}`",
        f"- Default rule before warmup: `{args.default_rule}`",
        "",
        "## Selector Summary",
        md_table(selector_summary),
        "## Fixed Rule Summary",
        md_table(fixed_summary),
        "",
        "## Files",
        "",
        "- `selector_issue_profit.csv`",
        "- `selector_summary.csv`",
        "- `fixed_rule_issue_profit.csv`",
        "- `fixed_rule_summary.csv`",
        "",
    ]
    (args.output_dir / "selector_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'selector_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("results/combo_trigger_selector"))
    parser.add_argument("--train-windows", default="8,12,16,20")
    parser.add_argument("--rule", action="append", help="Rule spec NAME=PATH_TEMPLATE, where {train} is replaced.")
    parser.add_argument("--selector-name", default="rolling_trailing_roi")
    parser.add_argument("--metric", choices=("roi", "profit"), default="roi")
    parser.add_argument("--warmup-issues", type=int, default=12)
    parser.add_argument("--trailing-issues", type=int, default=20)
    parser.add_argument("--dd-penalty", type=float, default=0.0)
    parser.add_argument("--default-rule", default="main_only")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
