#!/usr/bin/env python3
"""Replay convexity-triggered depth overlays on the current N7/N5/N3 policy."""
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
from scripts.evaluate_n7_dynamic_sleeve_allocator import full_loss, max_drawdown_units, row_order, row_year
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv

BASE_POLICY = "reference::draw_tail_to_n3::w5::dd2::ls4"
N3_STRATEGY = "dynamic_static_n3x180__budget256_fractional"
N5_STRATEGY = "dynamic_static_n5x90__budget256_fractional"


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_strategy_rows(path: Path, strategy: str) -> dict[str, dict[str, str]]:
    out = {}
    for row in read_csv(path):
        if row.get("strategy") == strategy:
            out[str(row["issue"])] = row
    if not out:
        raise SystemExit(f"strategy has no rows: {strategy} in {path}")
    return out


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


def is_bad_regime(row: dict[str, object]) -> bool:
    return str(row.get("state")) in {"defensive", "severe"}


def is_convex(row: dict[str, object], gate: str) -> bool:
    tickets = fnum(row.get("tickets"))
    if gate == "none":
        return False
    if gate == "low30":
        return tickets <= 30
    if gate == "ge100":
        return tickets >= 100
    if gate == "low30_or_ge100":
        return tickets <= 30 or tickets >= 100
    if gate == "low45_def":
        return tickets <= 45 and str(row.get("state")) == "defensive"
    raise ValueError(f"unknown gate: {gate}")


def gate_match(row: dict[str, object], gate: str, scope: str) -> bool:
    if not is_convex(row, gate):
        return False
    if scope == "all":
        return True
    if scope == "bad":
        return is_bad_regime(row)
    raise ValueError(f"unknown scope: {scope}")


def overlay_specs() -> list[dict[str, object]]:
    specs: list[dict[str, object]] = [
        {
            "model": "base",
            "gate": "none",
            "scope": "all",
            "base_scale_on_gate": 1.0,
            "base_scale_off_bad": 1.0,
            "n3_units_on_gate": 0.0,
            "n5op_units_on_gate": 0.0,
            "n5std_units_on_gate": 0.0,
        }
    ]
    for gate in ("low30", "ge100", "low30_or_ge100", "low45_def"):
        for scope in ("bad", "all"):
            for base_scale in (1.25, 1.5, 2.0):
                specs.append(
                    {
                        "model": f"{scope}_{gate}_scale{base_scale:g}".replace(".", "p"),
                        "gate": gate,
                        "scope": scope,
                        "base_scale_on_gate": base_scale,
                        "base_scale_off_bad": 1.0,
                        "n3_units_on_gate": 0.0,
                        "n5op_units_on_gate": 0.0,
                        "n5std_units_on_gate": 0.0,
                    }
                )
            for n3_units in (64.0, 128.0, 256.0):
                specs.append(
                    {
                        "model": f"{scope}_{gate}_add_n3_{n3_units:g}",
                        "gate": gate,
                        "scope": scope,
                        "base_scale_on_gate": 1.0,
                        "base_scale_off_bad": 1.0,
                        "n3_units_on_gate": n3_units,
                        "n5op_units_on_gate": 0.0,
                        "n5std_units_on_gate": 0.0,
                    }
                )
            specs.append(
                {
                    "model": f"{scope}_{gate}_add_n3_64_n5op_64",
                    "gate": gate,
                    "scope": scope,
                    "base_scale_on_gate": 1.0,
                    "base_scale_off_bad": 1.0,
                    "n3_units_on_gate": 64.0,
                    "n5op_units_on_gate": 64.0,
                    "n5std_units_on_gate": 0.0,
                }
            )
            specs.append(
                {
                    "model": f"{scope}_{gate}_reduce_lowconv_bad_0p5_add_n3_128",
                    "gate": gate,
                    "scope": scope,
                    "base_scale_on_gate": 1.0,
                    "base_scale_off_bad": 0.5,
                    "n3_units_on_gate": 128.0,
                    "n5op_units_on_gate": 0.0,
                    "n5std_units_on_gate": 0.0,
                }
            )
    return specs


def apply_overlay_piece(
    *,
    issue: str,
    source: dict[str, dict[str, str]],
    units: float,
) -> tuple[float, float, float, float]:
    if units <= 0:
        return 0.0, 0.0, 0.0, 0.0
    row = source.get(issue)
    if row is None:
        raise SystemExit(f"missing overlay issue {issue}")
    scale = units / 256.0
    return (
        fnum(row.get("stake_units")) * scale,
        fnum(row.get("profit_units")) * scale,
        fnum(row.get("tickets")) * scale,
        fnum(row.get("hits")) * scale,
    )


def replay(
    *,
    base_rows: list[dict[str, object]],
    n3_rows: dict[str, dict[str, str]],
    n5op_rows: dict[str, dict[str, str]],
    n5std_rows: dict[str, dict[str, str]],
    spec: dict[str, object],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in base_rows:
        issue = str(row["issue"])
        match = gate_match(row, str(spec["gate"]), str(spec["scope"]))
        bad = is_bad_regime(row)
        base_scale = fnum(spec["base_scale_on_gate"]) if match else 1.0
        if bad and not match:
            base_scale = fnum(spec["base_scale_off_bad"])
        base_stake = fnum(row.get("stake_units")) * base_scale
        base_profit = fnum(row.get("profit_units")) * base_scale
        base_tickets = fnum(row.get("tickets")) * base_scale
        base_hits = fnum(row.get("hits")) * base_scale

        n3_stake = n3_profit = n3_tickets = n3_hits = 0.0
        n5op_stake = n5op_profit = n5op_tickets = n5op_hits = 0.0
        n5std_stake = n5std_profit = n5std_tickets = n5std_hits = 0.0
        if match:
            n3_stake, n3_profit, n3_tickets, n3_hits = apply_overlay_piece(
                issue=issue, source=n3_rows, units=fnum(spec["n3_units_on_gate"])
            )
            n5op_stake, n5op_profit, n5op_tickets, n5op_hits = apply_overlay_piece(
                issue=issue, source=n5op_rows, units=fnum(spec["n5op_units_on_gate"])
            )
            n5std_stake, n5std_profit, n5std_tickets, n5std_hits = apply_overlay_piece(
                issue=issue, source=n5std_rows, units=fnum(spec["n5std_units_on_gate"])
            )

        stake = base_stake + n3_stake + n5op_stake + n5std_stake
        profit = base_profit + n3_profit + n5op_profit + n5std_profit
        copied = dict(row)
        copied.update(
            {
                "model": spec["model"],
                "gate": spec["gate"],
                "scope": spec["scope"],
                "gate_match": int(match),
                "bad_regime": int(bad),
                "base_scale": base_scale,
                "base_stake_units": base_stake,
                "base_profit_units": base_profit,
                "n3_overlay_units": fnum(spec["n3_units_on_gate"]) if match else 0.0,
                "n3_overlay_stake_units": n3_stake,
                "n3_overlay_profit_units": n3_profit,
                "n5op_overlay_units": fnum(spec["n5op_units_on_gate"]) if match else 0.0,
                "n5op_overlay_stake_units": n5op_stake,
                "n5op_overlay_profit_units": n5op_profit,
                "n5std_overlay_units": fnum(spec["n5std_units_on_gate"]) if match else 0.0,
                "n5std_overlay_stake_units": n5std_stake,
                "n5std_overlay_profit_units": n5std_profit,
                "stake_units": stake,
                "profit_units": profit,
                "tickets": base_tickets + n3_tickets + n5op_tickets + n5std_tickets,
                "hits": base_hits + n3_hits + n5op_hits + n5std_hits,
                "roi": profit / stake if stake else math.nan,
            }
        )
        out.append(copied)
    return out


def summarize(rows: list[dict[str, object]], *, recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    rows = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in rows)
    base_stake = sum(fnum(row.get("base_stake_units")) for row in rows)
    profit = sum(fnum(row.get("profit_units")) for row in rows)
    best = max((fnum(row.get("profit_units")) for row in rows), default=0.0)
    recent = [row for row in rows if recent_min_year <= row_year(row) <= recent_max_year]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    recent_best = max((fnum(row.get("profit_units")) for row in recent), default=0.0)
    out = {
        "model": str(rows[0]["model"]) if rows else "",
        "gate": str(rows[0].get("gate", "")) if rows else "",
        "scope": str(rows[0].get("scope", "")) if rows else "",
        "n_issues": len(rows),
        "trigger_issues": sum(int(fnum(row.get("gate_match"))) for row in rows),
        "bad_regime_issues": sum(int(fnum(row.get("bad_regime"))) for row in rows),
        "stake_units": stake,
        "base_stake_units": base_stake,
        "extra_stake_units": stake - base_stake,
        "profit_units": profit,
        "profit_delta_vs_base": profit
        - sum(fnum(row.get("original_base_profit_units", row.get("profit_units"))) for row in rows),
        "roi_on_deployed_stake": profit / stake if stake else math.nan,
        "roi_on_base_512_budget": profit / (len(rows) * 512.0) if rows else math.nan,
        "issue_win_rate": sum(1 for row in rows if fnum(row.get("profit_units")) > 0) / len(rows) if rows else math.nan,
        "non_full_loss_rate": sum(1 for row in rows if not full_loss(row)) / len(rows) if rows else math.nan,
        "max_drawdown_units": max_drawdown_units(rows),
        "best_issue_profit_units": best,
        "roi_ex_best_on_deployed_stake": (profit - best) / stake if stake else math.nan,
        "recent_profit_units": recent_profit,
        "recent_roi_on_deployed_stake": recent_profit / recent_stake if recent_stake else math.nan,
        "recent_roi_ex_best_on_base_budget": (recent_profit - recent_best) / (len(recent) * 512.0)
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
                "trigger_issues": sum(int(fnum(row.get("gate_match"))) for row in vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi_on_deployed_stake": profit / stake if stake else math.nan,
                "roi_on_base_512_budget": profit / (len(vals) * 512.0) if vals else math.nan,
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    base_rows = [
        dict(row, original_base_profit_units=row["profit_units"])
        for row in read_csv(args.base_issue_profit)
        if row.get("policy") == args.base_policy
    ]
    if not base_rows:
        raise SystemExit(f"base policy has no rows: {args.base_policy}")
    base_rows.sort(key=row_order)
    n3_rows = read_strategy_rows(args.n3_issue_profit, args.n3_strategy)
    n5op_rows = read_strategy_rows(args.n5op_issue_profit, args.n5_strategy)
    n5std_rows = read_strategy_rows(args.n5std_issue_profit, args.n5_strategy)

    all_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for spec in overlay_specs():
        rows = replay(base_rows=base_rows, n3_rows=n3_rows, n5op_rows=n5op_rows, n5std_rows=n5std_rows, spec=spec)
        all_rows.extend(rows)
        summaries.append(summarize(rows, recent_min_year=args.recent_min_year, recent_max_year=args.recent_max_year))
    summaries.sort(
        key=lambda row: (
            fnum(row["profit_units"]),
            fnum(row["max_drawdown_units"]),
            fnum(row["non_full_loss_rate"]),
        ),
        reverse=True,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "convexity_depth_issue_profit.csv", all_rows)
    write_csv(args.output_dir / "convexity_depth_summary.csv", summaries)
    write_csv(args.output_dir / "convexity_depth_annual.csv", annual_rows(all_rows))
    report = [
        "# N7 convexity depth overlay",
        "",
        "- Base policy: `reference::draw_tail_to_n3::w5::dd2::ls4`.",
        "- Gates use only pre-bet issue fields from the selected policy: `state`, `tickets`, and chosen arm.",
        "- Overlay actions either scale the selected book or add extra N3/N5 coverage on trigger issues.",
        "- This is not a cooldown test: bad regimes are allowed to keep or increase risk when the convexity proxy is present.",
        "",
        "## Top Models",
        "",
        md_table(summaries, limit=40),
        "",
    ]
    (args.output_dir / "convexity_depth_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'convexity_depth_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-issue-profit",
        type=Path,
        default=Path("results/n7_dynamic_sleeve_allocator_n3_20260628_timefix/dynamic_sleeve_issue_profit.csv"),
    )
    parser.add_argument("--base-policy", default=BASE_POLICY)
    parser.add_argument(
        "--n3-issue-profit",
        type=Path,
        default=Path("results/n_dynamic_issue_depth_n3_sweep_20260628/n_dynamic_issue_depth_issue_profit.csv"),
    )
    parser.add_argument(
        "--n5op-issue-profit",
        type=Path,
        default=Path("results/n_dynamic_issue_smoothing_optional_budget256_overlap050_20260628/n_dynamic_issue_depth_issue_profit.csv"),
    )
    parser.add_argument(
        "--n5std-issue-profit",
        type=Path,
        default=Path("results/n_dynamic_issue_smoothing_optional_budget256_20260628/n_dynamic_issue_depth_issue_profit.csv"),
    )
    parser.add_argument("--n3-strategy", default=N3_STRATEGY)
    parser.add_argument("--n5-strategy", default=N5_STRATEGY)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_convexity_depth_overlay_20260628"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
