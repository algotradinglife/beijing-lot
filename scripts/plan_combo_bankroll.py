#!/usr/bin/env python3
"""Convert combo backtest unit PnL into RMB bankroll/risk numbers."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_combo_main_cold_tail import max_drawdown, max_loss_streak
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


def parse_input(raw: str) -> tuple[str, Path]:
    if "=" in raw:
        name, path = raw.split("=", 1)
        return name.strip(), Path(path.strip())
    path = Path(raw)
    return path.parent.name or path.stem, path


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


def group_key(row: dict[str, str]) -> str:
    if row.get("allocation"):
        return str(row["allocation"])
    if row.get("selector"):
        return str(row["selector"])
    if row.get("fixed_rule"):
        return str(row["fixed_rule"])
    if row.get("portfolio"):
        return str(row["portfolio"])
    return "all"


def normalize_rows(name: str, path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in read_csv_rows(path):
        budget = as_float(raw, "budget", as_float(raw, "stake"))
        profit = as_float(raw, "profit")
        rows.append(
            {
                "source": name,
                "group": group_key(raw),
                "issue": str(raw.get("issue", "")),
                "triggered": as_int(raw, "triggered"),
                "budget_units": budget,
                "deployed_units": as_float(raw, "deployed_stake", budget),
                "profit_units": profit,
                "main_profit_units": as_float(raw, "main_profit", profit),
                "cold_profit_units": as_float(raw, "cold_profit"),
                "cold_stake_units": as_float(raw, "cold_stake"),
            }
        )
    return rows


def summarize(rows: list[dict[str, object]], *, unit_yuan: float, bankroll_yuan: float, max_dd_pct: float, max_issue_loss_pct: float) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["source"]), str(row["group"]))].append(row)

    out: list[dict[str, object]] = []
    for (source, group), vals in sorted(grouped.items()):
        vals = sorted(vals, key=lambda r: str(r["issue"]))
        profits = [as_float(r, "profit_units") for r in vals]
        budgets = [as_float(r, "budget_units") for r in vals]
        budget_units = sum(budgets)
        profit_units = sum(profits)
        max_dd_units = max_drawdown(profits)
        worst_issue_loss_units = abs(min(profits)) if profits else 0.0
        dd_unit_cap = bankroll_yuan * max_dd_pct / max_dd_units if max_dd_units > 0 else float("inf")
        issue_loss_unit_cap = (
            bankroll_yuan * max_issue_loss_pct / worst_issue_loss_units if worst_issue_loss_units > 0 else float("inf")
        )
        capped_unit = min(unit_yuan, dd_unit_cap, issue_loss_unit_cap)
        out.append(
            {
                "source": source,
                "group": group,
                "issues": len(vals),
                "triggered_issues": sum(1 for r in vals if as_int(r, "triggered") > 0),
                "budget_units": budget_units,
                "budget_yuan": budget_units * unit_yuan,
                "profit_units": profit_units,
                "profit_yuan": profit_units * unit_yuan,
                "roi": profit_units / budget_units if budget_units else float("nan"),
                "avg_issue_budget_units": sum(budgets) / len(budgets) if budgets else 0.0,
                "max_issue_budget_units": max(budgets) if budgets else 0.0,
                "min_issue_profit_units": min(profits) if profits else 0.0,
                "min_issue_profit_yuan": (min(profits) if profits else 0.0) * unit_yuan,
                "max_drawdown_units": max_dd_units,
                "max_drawdown_yuan": max_dd_units * unit_yuan,
                "max_drawdown_pct_bankroll": max_dd_units * unit_yuan / bankroll_yuan if bankroll_yuan else "",
                "max_loss_streak": max_loss_streak(profits),
                "unit_yuan": unit_yuan,
                "unit_cap_by_dd_yuan": dd_unit_cap,
                "unit_cap_by_issue_loss_yuan": issue_loss_unit_cap,
                "risk_capped_unit_yuan": capped_unit,
                "risk_capped_profit_yuan": profit_units * capped_unit,
                "risk_capped_max_drawdown_yuan": max_dd_units * capped_unit,
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    input_specs = args.input or [
        "conservative_t8=results/combo_trigger_cand15_q180_t8/conditional_allocation_issue_profit.csv",
        "conservative_t12=results/combo_trigger_cand15_q180_t12/conditional_allocation_issue_profit.csv",
        "conservative_t16=results/combo_trigger_cand15_q180_t16/conditional_allocation_issue_profit.csv",
        "conservative_t20=results/combo_trigger_cand15_q180_t20/conditional_allocation_issue_profit.csv",
        "aggressive_t8=results/combo_trigger_cand15_q100_pmax10_t8/conditional_allocation_issue_profit.csv",
        "aggressive_t12=results/combo_trigger_cand15_q100_pmax10_t12/conditional_allocation_issue_profit.csv",
        "aggressive_t16=results/combo_trigger_cand15_q100_pmax10_t16/conditional_allocation_issue_profit.csv",
        "aggressive_t20=results/combo_trigger_cand15_q100_pmax10_t20/conditional_allocation_issue_profit.csv",
    ]

    issue_rows: list[dict[str, object]] = []
    for raw in input_specs:
        name, path = parse_input(raw)
        if not path.exists():
            raise SystemExit(f"input not found: {path}")
        issue_rows.extend(normalize_rows(name, path))

    summary = summarize(
        issue_rows,
        unit_yuan=args.unit_yuan,
        bankroll_yuan=args.bankroll_yuan,
        max_dd_pct=args.max_dd_pct,
        max_issue_loss_pct=args.max_issue_loss_pct,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "bankroll_issue_profit.csv", issue_rows)
    write_csv(args.output_dir / "bankroll_summary.csv", summary)
    report = [
        "# Combo Bankroll Plan",
        "",
        f"- Unit: `{args.unit_yuan}` RMB per simulated stake unit",
        f"- Bankroll: `{args.bankroll_yuan}` RMB",
        f"- Max drawdown cap: `{args.max_dd_pct:.2%}` of bankroll",
        f"- Worst issue loss cap: `{args.max_issue_loss_pct:.2%}` of bankroll",
        "",
        "The cap columns answer how large one simulated stake unit can be before the historical drawdown or worst issue loss breaches the configured risk limit.",
        "",
        "## Summary",
        md_table(summary),
        "",
        "## Files",
        "",
        "- `bankroll_issue_profit.csv`",
        "- `bankroll_summary.csv`",
        "",
    ]
    (args.output_dir / "bankroll_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'bankroll_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", help="Input spec NAME=CSV_PATH. May be repeated.")
    parser.add_argument("--output-dir", type=Path, default=Path("results/combo_bankroll_plan"))
    parser.add_argument("--unit-yuan", type=float, default=2.0)
    parser.add_argument("--bankroll-yuan", type=float, default=10000.0)
    parser.add_argument("--max-dd-pct", type=float, default=0.15)
    parser.add_argument("--max-issue-loss-pct", type=float, default=0.03)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
