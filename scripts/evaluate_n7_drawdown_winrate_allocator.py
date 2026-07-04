#!/usr/bin/env python3
"""Allocate more capital to high win-rate sleeves as drawdown deepens."""
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

from scripts.evaluate_issue_cooldown import max_underwater
from scripts.evaluate_n7_dynamic_sleeve_allocator import max_drawdown_units, row_order, row_year
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv

BASE_MODEL = "core512_none0"


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


def load_model_rows(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    out: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in read_csv(path):
        out[str(row["model"])][str(row["issue"])] = row
    return dict(out)


def ordered_issues(model_rows: dict[str, dict[str, dict[str, str]]]) -> list[str]:
    base = model_rows.get(BASE_MODEL, {})
    if not base:
        raise SystemExit(f"missing base model: {BASE_MODEL}")
    return [str(row["issue"]) for row in sorted(base.values(), key=row_order)]


def full_loss(row: dict[str, object]) -> bool:
    stake = fnum(row.get("stake_units"))
    return stake > 0 and fnum(row.get("profit_units")) <= -0.999 * stake


def allocator_specs() -> list[dict[str, object]]:
    """Stage maps are ordered from deepest to shallowest drawdown depth."""
    return [
        {
            "allocator": "fixed_base",
            "stages": [(0.0, BASE_MODEL)],
        },
        {
            "allocator": "fixed_448_dyn64",
            "stages": [(0.0, "core448_n3_n5_dynamic64")],
        },
        {
            "allocator": "fixed_384_n5ov128",
            "stages": [(0.0, "core384_n5_static_overlap50128")],
        },
        {
            "allocator": "dd5_10_15_dyn",
            "stages": [
                (15000.0, "core320_n3_n5_dynamic192"),
                (10000.0, "core384_n3_n5_dynamic128"),
                (5000.0, "core448_n3_n5_dynamic64"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd5_10_15_n5",
            "stages": [
                (15000.0, "core320_n5_static192"),
                (10000.0, "core384_n5_static128"),
                (5000.0, "core448_n5_static64"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd5_10_15_n5ov",
            "stages": [
                (15000.0, "core320_n5_static_overlap50192"),
                (10000.0, "core384_n5_static_overlap50128"),
                (5000.0, "core448_n5_static_overlap5064"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd5_10_15_mixed",
            "stages": [
                (15000.0, "core320_n5_static_overlap50192"),
                (10000.0, "core384_n5_static_overlap50128"),
                (5000.0, "core448_n3_n5_dynamic64"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd5_10_15_20_dyn",
            "stages": [
                (20000.0, "core256_n3_n5_dynamic256"),
                (15000.0, "core320_n3_n5_dynamic192"),
                (10000.0, "core384_n3_n5_dynamic128"),
                (5000.0, "core448_n3_n5_dynamic64"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd5_10_15_20_n5",
            "stages": [
                (20000.0, "core256_n5_static256"),
                (15000.0, "core320_n5_static192"),
                (10000.0, "core384_n5_static128"),
                (5000.0, "core448_n5_static64"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd5_10_15_20_n5ov",
            "stages": [
                (20000.0, "core256_n5_static_overlap50256"),
                (15000.0, "core320_n5_static_overlap50192"),
                (10000.0, "core384_n5_static_overlap50128"),
                (5000.0, "core448_n5_static_overlap5064"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd8_12_16_20_mixed",
            "stages": [
                (20000.0, "core256_n5_static_overlap50256"),
                (16000.0, "core320_n5_static_overlap50192"),
                (12000.0, "core384_n5_static_overlap50128"),
                (8000.0, "core448_n3_n5_dynamic64"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd10_15_20_mixed",
            "stages": [
                (20000.0, "core256_n5_static_overlap50256"),
                (15000.0, "core320_n5_static_overlap50192"),
                (10000.0, "core384_n5_static_overlap50128"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd5_10_15_20_safe",
            "stages": [
                (20000.0, "core256_n3_static_high_win256"),
                (15000.0, "core320_n3_static_high_win192"),
                (10000.0, "core384_n5_static_overlap50128"),
                (5000.0, "core448_n3_n5_dynamic64"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd8_12_16_20_safe",
            "stages": [
                (20000.0, "core256_n3_static_high_win256"),
                (16000.0, "core320_n3_static_high_win192"),
                (12000.0, "core384_n5_static_overlap50128"),
                (8000.0, "core448_n3_n5_dynamic64"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd10_15_20_safe",
            "stages": [
                (20000.0, "core256_n3_static_high_win256"),
                (15000.0, "core320_n3_static_high_win192"),
                (10000.0, "core384_n5_static_overlap50128"),
                (0.0, BASE_MODEL),
            ],
        },
        {
            "allocator": "dd5_10_15_full_safe",
            "stages": [
                (15000.0, "core256_n3_static_high_win256"),
                (10000.0, "core320_n3_static_high_win192"),
                (5000.0, "core384_n5_static_overlap50128"),
                (0.0, BASE_MODEL),
            ],
        },
    ]


def choose_stage(stages: list[tuple[float, str]], drawdown_depth: float) -> tuple[float, str]:
    for threshold, model in sorted(stages, key=lambda item: item[0], reverse=True):
        if drawdown_depth >= threshold:
            return threshold, model
    return 0.0, BASE_MODEL


def replay_allocator(
    *,
    spec: dict[str, object],
    model_rows: dict[str, dict[str, dict[str, str]]],
    issues: list[str],
) -> list[dict[str, object]]:
    equity = 0.0
    peak = 0.0
    out: list[dict[str, object]] = []
    stages = [(float(threshold), str(model)) for threshold, model in spec["stages"]]  # type: ignore[index]
    for issue in issues:
        drawdown_before = equity - peak
        drawdown_depth = peak - equity
        threshold, model = choose_stage(stages, drawdown_depth)
        source = model_rows.get(model, {}).get(issue)
        if source is None:
            raise SystemExit(f"missing issue {issue} for model {model}")
        before = equity
        profit = fnum(source.get("profit_units"))
        equity += profit
        peak = max(peak, equity)
        copied = dict(source)
        copied.update(
            {
                "allocator": spec["allocator"],
                "selected_model": model,
                "stage_threshold_units": threshold,
                "equity_before": before,
                "drawdown_before_units": drawdown_before,
                "drawdown_depth_before_units": drawdown_depth,
                "profit_units": profit,
                "equity_after": equity,
                "drawdown_after_units": equity - peak,
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
    stage_counts = Counter(str(row.get("selected_model", "")) for row in rows)
    stage_mix = ";".join(f"{model}:{count}" for model, count in sorted(stage_counts.items()))
    out = {
        "allocator": str(rows[0]["allocator"]) if rows else "",
        "n_issues": len(rows),
        "stake_units": stake,
        "profit_units": profit,
        "roi_on_deployed_stake": profit / stake if stake else math.nan,
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
        "roi_ex_best_on_deployed_stake": (profit - best) / stake if stake else math.nan,
        "recent_profit_units": recent_profit,
        "recent_roi_on_deployed_stake": recent_profit / recent_stake if recent_stake else math.nan,
        "recent_roi_ex_best_on_deployed_stake": (recent_profit - recent_best) / recent_stake
        if recent_stake
        else math.nan,
        "stage_mix": stage_mix,
    }
    out.update(max_underwater(rows))
    return out


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["allocator"]), row_year(row))].append(row)
    out = []
    for (allocator, year), vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "allocator": allocator,
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
    model_rows = load_model_rows(args.high_win_issue_profit)
    issues = ordered_issues(model_rows)
    all_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for spec in allocator_specs():
        rows = replay_allocator(spec=spec, model_rows=model_rows, issues=issues)
        all_rows.extend(rows)
        summaries.append(summarize(rows, recent_min_year=args.recent_min_year, recent_max_year=args.recent_max_year))
    summaries.sort(
        key=lambda row: (
            fnum(row["max_drawdown_units"]),
            fnum(row["profit_units"]),
            fnum(row["issue_win_rate"]),
        ),
        reverse=True,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "drawdown_winrate_allocator_issue_profit.csv", all_rows)
    write_csv(args.output_dir / "drawdown_winrate_allocator_summary.csv", summaries)
    write_csv(args.output_dir / "drawdown_winrate_allocator_annual.csv", annual_rows(all_rows))
    report = [
        "# Drawdown-stage win-rate allocator",
        "",
        "- Selection is based on drawdown before the issue is played.",
        "- Deeper drawdown increases allocation to lower-N high win-rate sleeves.",
        "- If equity recovers, the allocator can move back toward the N7 core.",
        "",
        "## Summary Sorted By MaxDD",
        "",
        md_table(summaries, limit=80),
        "",
    ]
    (args.output_dir / "drawdown_winrate_allocator_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'drawdown_winrate_allocator_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--high-win-issue-profit",
        type=Path,
        default=Path("results/n7_high_win_sleeve_20260628/high_win_sleeve_issue_profit.csv"),
    )
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_drawdown_winrate_allocator_20260628"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
