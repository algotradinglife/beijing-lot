#!/usr/bin/env python3
"""Blend the current N7 core with lower-N high win-rate sleeves."""
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

from scripts.evaluate_issue_cooldown import max_underwater
from scripts.evaluate_n7_dynamic_sleeve_allocator import max_drawdown_units, row_order, row_year
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv

BASE_POLICY = "reference::draw_tail_to_n3::w5::dd2::ls4"

SLEEVES = [
    {
        "label": "n5_static",
        "path": Path("results/n_dynamic_issue_smoothing_optional_budget256_20260628/n_dynamic_issue_depth_issue_profit.csv"),
        "strategy": "dynamic_static_n5x90__budget256_fractional",
    },
    {
        "label": "n5_static_overlap50",
        "path": Path(
            "results/n_dynamic_issue_smoothing_optional_budget256_overlap050_20260628/"
            "n_dynamic_issue_depth_issue_profit.csv"
        ),
        "strategy": "dynamic_static_n5x90__budget256_fractional",
    },
    {
        "label": "n3_n5_dynamic",
        "path": Path("results/n_dynamic_issue_depth_n3_sweep_20260628/n_dynamic_issue_depth_issue_profit.csv"),
        "strategy": "dynamic_low3_mid5_high7x30__budget256_fractional",
    },
    {
        "label": "n3_static_high_win",
        "path": Path("results/n_dynamic_issue_depth_n3_sweep_20260628/n_dynamic_issue_depth_issue_profit.csv"),
        "strategy": "dynamic_static_n3x360__budget256_fractional",
    },
]


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv_all(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    first_keys = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(first_keys))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=first_keys + extra)
        writer.writeheader()
        writer.writerows(rows)


def load_base(path: Path, policy: str) -> list[dict[str, object]]:
    rows = [dict(row) for row in read_csv(path) if row.get("policy") == policy]
    if not rows:
        raise SystemExit(f"base policy has no rows: {policy}")
    rows.sort(key=row_order)
    return rows


def load_sleeve(path: Path, strategy: str) -> dict[str, dict[str, str]]:
    rows = {str(row["issue"]): row for row in read_csv(path) if row.get("strategy") == strategy}
    if not rows:
        raise SystemExit(f"sleeve strategy has no rows: {strategy} in {path}")
    return rows


def full_loss(row: dict[str, object]) -> bool:
    stake = fnum(row.get("stake_units"))
    return stake > 0 and fnum(row.get("profit_units")) <= -0.999 * stake


def model_name(core_units: float, sleeve_label: str, sleeve_units: float) -> str:
    return f"core{core_units:g}_{sleeve_label}{sleeve_units:g}".replace(".", "p")


def replay(
    *,
    base_rows: list[dict[str, object]],
    sleeve_rows: dict[str, dict[str, str]],
    sleeve_label: str,
    sleeve_strategy: str,
    core_units: float,
    sleeve_units: float,
) -> list[dict[str, object]]:
    base_scale = core_units / 512.0
    sleeve_scale = sleeve_units / 256.0
    model = model_name(core_units, sleeve_label, sleeve_units)
    out: list[dict[str, object]] = []
    for row in base_rows:
        issue = str(row["issue"])
        sleeve = sleeve_rows.get(issue)
        if sleeve is None:
            raise SystemExit(f"missing sleeve issue {issue}: {sleeve_label}")
        base_profit = fnum(row.get("profit_units")) * base_scale
        base_stake = fnum(row.get("stake_units")) * base_scale
        sleeve_profit = fnum(sleeve.get("profit_units")) * sleeve_scale
        sleeve_stake = fnum(sleeve.get("stake_units")) * sleeve_scale
        profit = base_profit + sleeve_profit
        stake = base_stake + sleeve_stake
        copied = dict(row)
        copied.update(
            {
                "model": model,
                "core_units": core_units,
                "sleeve_label": sleeve_label,
                "sleeve_strategy": sleeve_strategy,
                "sleeve_units": sleeve_units,
                "base_profit_units": base_profit,
                "base_stake_units": base_stake,
                "sleeve_profit_units": sleeve_profit,
                "sleeve_stake_units": sleeve_stake,
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "tickets": fnum(row.get("tickets")) * base_scale + fnum(sleeve.get("tickets")) * sleeve_scale,
                "hits": fnum(row.get("hits")) * base_scale + fnum(sleeve.get("hits")) * sleeve_scale,
            }
        )
        out.append(copied)
    return out


def summarize(rows: list[dict[str, object]], *, recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    rows = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in rows)
    profit = sum(fnum(row.get("profit_units")) for row in rows)
    best = max((fnum(row.get("profit_units")) for row in rows), default=0.0)
    recent = [row for row in rows if recent_min_year <= row_year(row) <= recent_max_year]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    recent_best = max((fnum(row.get("profit_units")) for row in recent), default=0.0)
    out = {
        "model": str(rows[0]["model"]) if rows else "",
        "core_units": rows[0].get("core_units", "") if rows else "",
        "sleeve_label": rows[0].get("sleeve_label", "") if rows else "",
        "sleeve_units": rows[0].get("sleeve_units", "") if rows else "",
        "n_issues": len(rows),
        "stake_units": stake,
        "profit_units": profit,
        "profit_per_issue": profit / len(rows) if rows else math.nan,
        "roi_on_deployed_stake": profit / stake if stake else math.nan,
        "roi_on_512_budget": profit / (len(rows) * 512.0) if rows else math.nan,
        "issue_win_rate": sum(1 for row in rows if fnum(row.get("profit_units")) > 0) / len(rows) if rows else math.nan,
        "non_full_loss_rate": sum(1 for row in rows if not full_loss(row)) / len(rows) if rows else math.nan,
        "small_loss_rate": sum(
            1 for row in rows if -fnum(row.get("stake_units")) < fnum(row.get("profit_units")) <= 0
        )
        / len(rows)
        if rows
        else math.nan,
        "max_drawdown_units": max_drawdown_units(rows),
        "best_issue_profit_units": best,
        "roi_ex_best_on_512_budget": (profit - best) / (len(rows) * 512.0) if rows else math.nan,
        "recent_profit_units": recent_profit,
        "recent_roi_on_deployed_stake": recent_profit / recent_stake if recent_stake else math.nan,
        "recent_roi_ex_best_on_512_budget": (recent_profit - recent_best) / (len(recent) * 512.0)
        if recent
        else math.nan,
    }
    out.update(max_underwater(rows))
    return out


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["model"]), row_year(row))].append(row)
    out = []
    for (model, year), vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "model": model,
                "year": year,
                "n_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi_on_deployed_stake": profit / stake if stake else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals)
                if vals
                else math.nan,
                "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals) if vals else math.nan,
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    base_rows = load_base(args.base_issue_profit, args.base_policy)
    sleeve_maps = [
        (str(spec["label"]), str(spec["strategy"]), load_sleeve(Path(spec["path"]), str(spec["strategy"])))
        for spec in SLEEVES
    ]
    core_units_list = [float(part.strip()) for part in args.core_units.split(",") if part.strip()]
    all_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []

    base_model_rows = replay(
        base_rows=base_rows,
        sleeve_rows=sleeve_maps[0][2],
        sleeve_label="none",
        sleeve_strategy="none",
        core_units=512.0,
        sleeve_units=0.0,
    )
    all_rows.extend(base_model_rows)
    summaries.append(summarize(base_model_rows, recent_min_year=args.recent_min_year, recent_max_year=args.recent_max_year))

    for core_units in core_units_list:
        sleeve_units = 512.0 - core_units
        if sleeve_units <= 0:
            continue
        for label, strategy, sleeve_rows in sleeve_maps:
            rows = replay(
                base_rows=base_rows,
                sleeve_rows=sleeve_rows,
                sleeve_label=label,
                sleeve_strategy=strategy,
                core_units=core_units,
                sleeve_units=sleeve_units,
            )
            all_rows.extend(rows)
            summaries.append(summarize(rows, recent_min_year=args.recent_min_year, recent_max_year=args.recent_max_year))

    summaries.sort(
        key=lambda row: (
            fnum(row["issue_win_rate"]),
            fnum(row["profit_units"]),
            fnum(row["max_drawdown_units"]),
        ),
        reverse=True,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "high_win_sleeve_issue_profit.csv", all_rows)
    write_csv(args.output_dir / "high_win_sleeve_summary.csv", summaries)
    write_csv(args.output_dir / "high_win_sleeve_annual.csv", annual_rows(all_rows))
    report = [
        "# N7 core + high win-rate sleeve",
        "",
        f"- Base policy: `{args.base_policy}`",
        "- Same 512-unit per-issue budget: core units + sleeve units = 512.",
        "- Sleeve win rate is evaluated at issue level, because the goal is fewer all-loss issues.",
        "",
        "## Summary Sorted By Issue Win Rate",
        "",
        md_table(summaries, limit=80),
        "",
    ]
    (args.output_dir / "high_win_sleeve_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'high_win_sleeve_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-issue-profit",
        type=Path,
        default=Path("results/n7_dynamic_sleeve_allocator_n3_20260628_timefix/dynamic_sleeve_issue_profit.csv"),
    )
    parser.add_argument("--base-policy", default=BASE_POLICY)
    parser.add_argument("--core-units", default="448,384,320,256")
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_high_win_sleeve_20260628"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
