#!/usr/bin/env python3
"""Combine N7 rotating coverage arms with N5 smoothing sleeves."""
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_same_ticket_leg_coverage import fnum, max_dead_streak, max_drawdown_units
from scripts.evaluate_n_dynamic_issue_depth import issue_year, loss_streak
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv

N7_ARMS = {
    "current": "prod_current_main__budget512",
    "rot_draw05_tail": "prod_rot_t30_mix05_tail_draw_k1__budget512_fractional",
    "rot_draw20_tail": "prod_rot_t30_mix20_tail_draw_k1__budget512_fractional",
    "rot_full05_head": "prod_rot_t30_mix05_head_full_k1__budget512_fractional",
    "rot_alt05_head_k2": "prod_rot_t30_mix05_head_alt_k2__budget512_fractional",
    "rot_unc10_head_k2": "prod_rot_t30_mix10_head_uncertain_k2__budget512_fractional",
}

ALLOCATIONS = {
    "512main": {"main": 512},
    "384main_128op05": {"main": 384, "op05": 128},
    "384main_64op05_64n5x90": {"main": 384, "op05": 64, "n5x90": 64},
    "384main_64op05_64n3x180": {"main": 384, "op05": 64, "n3x180": 64},
    "384main_64n5x90_64n3x180": {"main": 384, "n5x90": 64, "n3x180": 64},
    "256main_128op05_128n3x180": {"main": 256, "op05": 128, "n3x180": 128},
    "307main_205op05": {"main": 307, "op05": 205},
    "256main_256op05": {"main": 256, "op05": 256},
}

SELECTED = [
    "current__512main",
    "rot_draw20_tail__512main",
    "current__384main_128op05",
    "rot_draw05_tail__384main_128op05",
    "rot_draw20_tail__384main_128op05",
    "current__384main_64op05_64n5x90",
    "rot_draw20_tail__384main_64op05_64n5x90",
    "rot_draw20_tail__384main_64op05_64n3x180",
    "rot_draw20_tail__384main_64n5x90_64n3x180",
    "rot_full05_head__384main_128op05",
    "rot_full05_head__384main_64op05_64n5x90",
    "rot_full05_head__384main_64op05_64n3x180",
    "rot_unc10_head_k2__384main_64op05_64n5x90",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def rows_by_strategy(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    out: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in read_csv(path):
        out[str(row["strategy"])][str(row["issue"])] = row
    return dict(out)


def load_issue_calendar(db_path: Path) -> dict[str, dict[str, object]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = list(
        conn.execute(
            """
            SELECT
                issue,
                MIN(kickoff_ts) AS start_ts,
                MAX(kickoff_ts) AS close_ts,
                MAX(season_year) AS season_year
            FROM action_candidates
            WHERE has_winning_sp = 1
              AND kickoff_ts IS NOT NULL
            GROUP BY issue
            ORDER BY close_ts, issue
            """
        )
    )
    conn.close()
    return {
        str(row["issue"]): {
            "issue_start_ts": str(row["start_ts"]),
            "issue_close_ts": str(row["close_ts"]),
            "issue_order": idx,
            "calendar_year": int(str(row["close_ts"])[:4]),
            "season_year": int(row["season_year"]) if row["season_year"] is not None else issue_year(str(row["issue"])),
        }
        for idx, row in enumerate(rows)
    }


def issue_order(issue: str, calendar: dict[str, dict[str, object]]) -> tuple[object, str]:
    meta = calendar.get(issue)
    if meta:
        return meta["issue_close_ts"], issue
    return issue_year(issue), issue


def row_order(row: dict[str, object]) -> tuple[object, str]:
    return row.get("issue_close_ts", ""), str(row.get("issue", ""))


def combine_issue_rows(
    portfolio: str,
    legs: list[tuple[dict[str, dict[str, str]], str, float, str]],
    calendar: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    issues = sorted(
        set().union(*(set(source[strategy]) for source, strategy, _scale, _label in legs)),
        key=lambda issue: issue_order(issue, calendar),
    )
    out: list[dict[str, object]] = []
    for issue in issues:
        stake = 0.0
        profit = 0.0
        tickets = 0.0
        hits = 0.0
        parts = []
        for source, strategy, scale, label in legs:
            row = source[strategy].get(issue)
            if row is None:
                continue
            stake += fnum(row.get("stake_units")) * scale
            profit += fnum(row.get("profit_units")) * scale
            tickets += fnum(row.get("tickets")) * scale
            hits += fnum(row.get("hits")) * scale
            parts.append(label)
        row = {
            "portfolio": portfolio,
            "issue": issue,
            "stake_units": stake,
            "profit_units": profit,
            "roi": profit / stake if stake else math.nan,
            "tickets": tickets,
            "hits": hits,
            "parts": "+".join(parts),
        }
        row.update(calendar.get(issue, {}))
        out.append(row)
    return out


def summarize(rows: list[dict[str, object]], recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    rows = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in rows)
    profit = sum(fnum(row.get("profit_units")) for row in rows)
    best = max((fnum(row.get("profit_units")) for row in rows), default=0.0)
    recent = [
        row
        for row in rows
        if recent_min_year <= int(row.get("calendar_year", issue_year(str(row["issue"])))) <= recent_max_year
    ]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    recent_best = max((fnum(row.get("profit_units")) for row in recent), default=0.0)
    full_loss = [
        fnum(row.get("stake_units")) > 0 and fnum(row.get("profit_units")) <= -0.999 * fnum(row.get("stake_units"))
        for row in rows
    ]
    return {
        "portfolio": str(rows[0]["portfolio"]) if rows else "",
        "n_issues": len(rows),
        "stake_units": stake,
        "profit_units": profit,
        "roi": profit / stake if stake else math.nan,
        "issue_win_rate": sum(1 for row in rows if fnum(row.get("profit_units")) > 0) / len(rows),
        "non_full_loss_rate": sum(1 for dead in full_loss if not dead) / len(rows),
        "small_loss_rate": sum(
            1 for row in rows if -fnum(row.get("stake_units")) < fnum(row.get("profit_units")) <= 0
        )
        / len(rows),
        "max_dead_streak": max_dead_streak(rows),
        "max_loss_streak": loss_streak(rows),
        "max_drawdown_units": max_drawdown_units(rows),
        "best_issue_profit_units": best,
        "roi_ex_best_issue": (profit - best) / stake if stake else math.nan,
        "recent_profit_units": recent_profit,
        "recent_roi": recent_profit / recent_stake if recent_stake else math.nan,
        "recent_roi_ex_best_issue": (recent_profit - recent_best) / recent_stake if recent_stake else math.nan,
        "avg_tickets": sum(fnum(row.get("tickets")) for row in rows) / len(rows),
    }


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = (str(row["portfolio"]), int(row.get("calendar_year", issue_year(str(row["issue"])))))
        grouped[key].append(row)
    out = []
    for (portfolio, year), vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "portfolio": portfolio,
                "year": year,
                "n_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals),
                "non_full_loss_rate": sum(
                    1
                    for row in vals
                    if not (
                        fnum(row.get("stake_units")) > 0
                        and fnum(row.get("profit_units")) <= -0.999 * fnum(row.get("stake_units"))
                    )
                )
                / len(vals),
            }
        )
    return out


def build_portfolios(args: argparse.Namespace) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    n7 = rows_by_strategy(args.n7_issue_profit)
    n5op = rows_by_strategy(args.n5_op05_issue_profit)
    n5std = rows_by_strategy(args.n5_standard_issue_profit)
    n3std = rows_by_strategy(args.n3_standard_issue_profit)
    calendar = load_issue_calendar(args.db)

    issue_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for n7_label, n7_strategy in N7_ARMS.items():
        if n7_strategy not in n7:
            raise SystemExit(f"missing N7 strategy: {n7_strategy}")
        for allocation_label, allocation in ALLOCATIONS.items():
            legs: list[tuple[dict[str, dict[str, str]], str, float, str]] = [
                (n7, n7_strategy, allocation["main"] / 512.0, n7_label)
            ]
            if allocation.get("op05", 0) > 0:
                legs.append(
                    (
                        n5op,
                        "dynamic_static_n5x90__budget256_fractional",
                        allocation["op05"] / 256.0,
                        "N5op05",
                    )
                )
            if allocation.get("n5x90", 0) > 0:
                legs.append(
                    (
                        n5std,
                        "dynamic_static_n5x90__budget256_fractional",
                        allocation["n5x90"] / 256.0,
                        "N5x90",
                    )
                )
            if allocation.get("n3x180", 0) > 0:
                legs.append(
                    (
                        n3std,
                        "dynamic_static_n3x180__budget256_fractional",
                        allocation["n3x180"] / 256.0,
                        "N3x180",
                    )
                )
            portfolio = f"{n7_label}__{allocation_label}"
            rows = combine_issue_rows(portfolio, legs, calendar)
            issue_rows.extend(rows)
            summary = summarize(rows, args.recent_min_year, args.recent_max_year)
            summary.update(
                {
                    "n7_arm": n7_label,
                    "allocation": allocation_label,
                    "main_budget_units": allocation["main"],
                    "n5op05_budget_units": allocation.get("op05", 0),
                    "n5x90_budget_units": allocation.get("n5x90", 0),
                    "n3x180_budget_units": allocation.get("n3x180", 0),
                }
            )
            summary_rows.append(summary)
    summary_rows.sort(key=lambda row: (fnum(row["profit_units"]), fnum(row["non_full_loss_rate"])), reverse=True)
    return issue_rows, summary_rows


def run(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    issue_rows, summary_rows = build_portfolios(args)
    annual = annual_rows(issue_rows)
    selected = [row for row in summary_rows if row["portfolio"] in SELECTED]
    selected.sort(key=lambda row: SELECTED.index(str(row["portfolio"])))

    write_csv(args.output_dir / "rotating_n5_combo_issue_profit.csv", issue_rows)
    write_csv(args.output_dir / "rotating_n5_combo_summary.csv", summary_rows)
    write_csv(args.output_dir / "rotating_n5_combo_annual.csv", annual)
    write_csv(args.output_dir / "rotating_n5_combo_selected.csv", selected)

    report = [
        "# N7 rotating coverage + N5 sleeve combo",
        "",
        "## Selected",
        "",
        md_table(selected, limit=40),
        "",
        "## Top profit",
        "",
        md_table(summary_rows, limit=20),
        "",
    ]
    (args.output_dir / "rotating_n5_combo_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'rotating_n5_combo_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n7-issue-profit",
        type=Path,
        default=Path("results/n7_rotating_leg_coverage_t30_20260628/rotating_cover_production_budget512_issue_profit.csv"),
    )
    parser.add_argument(
        "--n5-op05-issue-profit",
        type=Path,
        default=Path("results/n_dynamic_issue_smoothing_optional_budget256_overlap050_20260628/n_dynamic_issue_depth_issue_profit.csv"),
    )
    parser.add_argument(
        "--n5-standard-issue-profit",
        type=Path,
        default=Path("results/n_dynamic_issue_smoothing_optional_budget256_20260628/n_dynamic_issue_depth_issue_profit.csv"),
    )
    parser.add_argument(
        "--n3-standard-issue-profit",
        type=Path,
        default=Path("results/n_dynamic_issue_depth_n3_sweep_20260628/n_dynamic_issue_depth_issue_profit.csv"),
    )
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_rotating_n5_sleeve_combo_20260628"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
