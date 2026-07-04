#!/usr/bin/env python3
"""Generate focused no-locking live-equity curves for the profit-tier rule."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_384_drawdown_dynamic import fnum, row_order
from scripts.evaluate_n7_384_weak_quality_dynamic import write_equity_svg


FOCUSED_SERIES = ("fixed_256", "profit_live_equity")


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


def delta_rows(rows: list[dict[str, str]], *, rule: str, field: str, start: float) -> list[dict[str, object]]:
    previous = start
    out: list[dict[str, object]] = []
    for row in sorted((r for r in rows if r.get("rule") == rule), key=row_order):
        value = fnum(row.get(field), previous)
        out.append(
            {
                "issue": row.get("issue", ""),
                "issue_order": row.get("issue_order", ""),
                "calendar_year": row.get("calendar_year", ""),
                "profit_units": value - previous,
            }
        )
        previous = value
    return out


def curve_csv_rows(rows: list[dict[str, str]], *, start: float) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for rule in FOCUSED_SERIES:
        for row in sorted((r for r in rows if r.get("rule") == rule), key=row_order):
            out.append(
                {
                    "rule": rule,
                    "issue": row.get("issue", ""),
                    "calendar_year": row.get("calendar_year", ""),
                    "issue_order": row.get("issue_order", ""),
                    "issue_close_ts": row.get("issue_close_ts", ""),
                    "issue_cap": fnum(row.get("issue_cap")),
                    "equity_after": fnum(row.get("equity_after"), start),
                    "total_wealth_after": fnum(row.get("total_wealth_after"), start),
                    "drawdown_after": fnum(row.get("drawdown_after")),
                    "profit_units": fnum(row.get("profit_units")),
                }
            )
    return out


def run(args: argparse.Namespace) -> None:
    rows = read_rows(args.ledger)
    focused = {
        "fixed_256": delta_rows(rows, rule="fixed_256", field="equity_after", start=args.starting_equity),
        "profit_live_equity": delta_rows(
            rows, rule="profit_live_equity", field="equity_after", start=args.starting_equity
        ),
    }
    write_equity_svg(args.focused_svg, focused)
    write_csv_all(args.focused_csv, curve_csv_rows(rows, start=args.starting_equity))

    total_vs_live = {
        "profit_live_equity_total_wealth": delta_rows(
            rows, rule="profit_live_equity", field="total_wealth_after", start=args.starting_equity
        ),
        "profit_live_equity_live_equity": delta_rows(
            rows, rule="profit_live_equity", field="equity_after", start=args.starting_equity
        ),
    }
    write_equity_svg(args.total_vs_live_svg, total_vs_live)
    print(f"Wrote {args.focused_svg}")
    print(f"Wrote {args.total_vs_live_svg}")
    print(f"Wrote {args.focused_csv}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("results/live_position_management_rules_20260629/position_rule_single_path_ledger.csv"),
    )
    parser.add_argument(
        "--focused-svg",
        type=Path,
        default=Path("docs/research/figures/live_equity_profit_tier_focused_curve_2026-06-29.svg"),
    )
    parser.add_argument(
        "--total-vs-live-svg",
        type=Path,
        default=Path("docs/research/figures/live_equity_profit_tier_total_vs_live_curve_2026-06-29.svg"),
    )
    parser.add_argument(
        "--focused-csv",
        type=Path,
        default=Path("docs/research/figures/live_equity_profit_tier_focused_curve_2026-06-29.csv"),
    )
    parser.add_argument("--starting-equity", type=float, default=10000.0)
    args = parser.parse_args()
    if not args.ledger.exists():
        raise SystemExit(f"missing ledger: {args.ledger}")
    run(args)


if __name__ == "__main__":
    main()
