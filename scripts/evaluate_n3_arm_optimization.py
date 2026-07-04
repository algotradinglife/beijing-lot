#!/usr/bin/env python3
"""Search standalone N3 quality gates using only pre-bet ticket features."""
from __future__ import annotations

import argparse
import csv
import itertools
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_issue_cooldown import max_underwater
from scripts.evaluate_n3_independent_selector import fnum, plot_equity, write_csv_all
from scripts.evaluate_n7_dynamic_sleeve_allocator import row_order, row_year
from scripts.evaluate_n7_same_ticket_leg_coverage import max_dead_streak, max_drawdown_units
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


SOURCE_SETS = [
    {
        "family": "soft_overlap",
        "raw": Path("results/n3_independent_selector_20260628/n3_independent_raw_tickets.csv"),
        "issue": Path("results/n3_independent_selector_20260628/n3_independent_issue_profit.csv"),
    },
    {
        "family": "combo_sample",
        "raw": Path("results/n3_independent_combo_sample_selector_20260628/n3_combo_sample_raw_tickets.csv"),
        "issue": Path("results/n3_independent_combo_sample_selector_20260628/n3_combo_sample_issue_profit.csv"),
    },
    {
        "family": "coverage_round",
        "raw": Path("results/n3_independent_coverage_round_selector_20260628/n3_coverage_round_raw_tickets.csv"),
        "issue": Path("results/n3_independent_coverage_round_selector_20260628/n3_coverage_round_issue_profit.csv"),
    },
]

FEATURE_DIRECTIONS = {
    "n_raw_tickets": ("high", "low"),
    "n_unique_legs": ("high", "low"),
    "effective_legs": ("high", "low"),
    "top_leg_use_rate": ("low", "high"),
    "avg_pair_overlap": ("low", "high"),
    "avg_pred_hit_prob": ("high", "low"),
    "p50_pred_hit_prob": ("high", "low"),
    "p75_pred_hit_prob": ("high", "low"),
    "p90_pred_hit_prob": ("high", "low"),
    "max_pred_hit_prob": ("high", "low"),
    "avg_pred_ev": ("high", "low"),
    "p50_pred_ev": ("high", "low"),
    "p75_pred_ev": ("high", "low"),
    "p90_pred_ev": ("high", "low"),
    "max_pred_ev": ("high", "low"),
    "avg_pred_factor_product": ("high", "low"),
    "p90_pred_factor_product": ("high", "low"),
    "frac_action_3": ("high", "low"),
    "frac_action_1": ("high", "low"),
    "frac_action_0": ("high", "low"),
}

PAIR_FEATURES = [
    ("avg_pred_hit_prob", "high"),
    ("p75_pred_hit_prob", "high"),
    ("p90_pred_hit_prob", "high"),
    ("avg_pred_ev", "high"),
    ("p75_pred_ev", "high"),
    ("n_unique_legs", "high"),
    ("effective_legs", "high"),
    ("top_leg_use_rate", "low"),
    ("avg_pair_overlap", "low"),
]


@dataclass(frozen=True)
class Gate:
    gate_id: str
    feature_a: str
    direction_a: str
    quantile_a: float
    threshold_a: float
    feature_b: str = ""
    direction_b: str = ""
    quantile_b: float = math.nan
    threshold_b: float = math.nan


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def percentile(vals: list[float], q: float) -> float:
    vals = sorted(val for val in vals if math.isfinite(val))
    if not vals:
        return math.nan
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def mean(vals: list[float]) -> float:
    vals = [val for val in vals if math.isfinite(val)]
    return sum(vals) / len(vals) if vals else math.nan


def parse_leg(leg: str) -> tuple[str, str]:
    match_part, rest = leg.split(":", 1)
    action = rest.split("@", 1)[0]
    return match_part, action


def budget_strategy_name(raw_strategy: str) -> str:
    return f"{raw_strategy}__budget256_fractional"


def load_issue_rows(path: Path, family: str) -> dict[tuple[str, str], dict[str, object]]:
    out = {}
    for row in read_csv(path):
        copied: dict[str, object] = dict(row)
        copied["family"] = family
        out[(str(row["strategy"]), str(row["issue"]))] = copied
    return out


def build_feature_rows(source_sets: list[dict[str, object]]) -> list[dict[str, object]]:
    all_rows: list[dict[str, object]] = []
    for spec in source_sets:
        family = str(spec["family"])
        raw_path = Path(spec["raw"])
        issue_path = Path(spec["issue"])
        if not raw_path.exists() or not issue_path.exists():
            continue
        issue_map = load_issue_rows(issue_path, family)
        grouped: dict[tuple[str, str], dict[str, object]] = {}
        for row in read_csv(raw_path):
            strategy = str(row["strategy"])
            issue = str(row["issue"])
            key = (strategy, issue)
            vals = grouped.setdefault(
                key,
                {
                    "family": family,
                    "raw_strategy": strategy,
                    "strategy": budget_strategy_name(strategy),
                    "issue": issue,
                    "pred_hit_probs": [],
                    "pred_evs": [],
                    "pred_factors": [],
                    "leg_counts": Counter(),
                    "action_counts": Counter(),
                    "n_raw_tickets": 0,
                },
            )
            vals["n_raw_tickets"] = int(vals["n_raw_tickets"]) + 1
            vals["pred_hit_probs"].append(fnum(row.get("pred_hit_prob"), math.nan))
            vals["pred_evs"].append(fnum(row.get("pred_ev_per_stake"), math.nan))
            vals["pred_factors"].append(fnum(row.get("pred_factor_product"), math.nan))
            for leg in str(row.get("legs", "")).split(";"):
                if not leg:
                    continue
                match_id, action = parse_leg(leg)
                leg_id = f"{match_id}:{action}"
                vals["leg_counts"][leg_id] += 1
                vals["action_counts"][action] += 1

        for (raw_strategy, issue), vals in grouped.items():
            strategy = budget_strategy_name(raw_strategy)
            issue_row = issue_map.get((strategy, issue))
            if issue_row is None:
                continue
            n_tickets = int(vals["n_raw_tickets"])
            leg_counts: Counter[str] = vals["leg_counts"]
            total_legs = sum(leg_counts.values())
            action_counts: Counter[str] = vals["action_counts"]
            shares = [count / total_legs for count in leg_counts.values()] if total_legs else []
            pair_den = n_tickets * (n_tickets - 1) / 2
            shared_pairs = sum(count * (count - 1) / 2 for count in leg_counts.values())
            row_out = {
                "family": vals["family"],
                "raw_strategy": raw_strategy,
                "strategy": strategy,
                "issue": issue,
                "n_raw_tickets": n_tickets,
                "n_unique_legs": len(leg_counts),
                "effective_legs": 1.0 / sum(share * share for share in shares) if shares else math.nan,
                "top_leg_use_rate": max(leg_counts.values()) / n_tickets if leg_counts and n_tickets else math.nan,
                "avg_pair_overlap": shared_pairs / pair_den if pair_den > 0 else math.nan,
                "avg_pred_hit_prob": mean(vals["pred_hit_probs"]),
                "p50_pred_hit_prob": percentile(vals["pred_hit_probs"], 0.50),
                "p75_pred_hit_prob": percentile(vals["pred_hit_probs"], 0.75),
                "p90_pred_hit_prob": percentile(vals["pred_hit_probs"], 0.90),
                "max_pred_hit_prob": max(vals["pred_hit_probs"]) if vals["pred_hit_probs"] else math.nan,
                "avg_pred_ev": mean(vals["pred_evs"]),
                "p50_pred_ev": percentile(vals["pred_evs"], 0.50),
                "p75_pred_ev": percentile(vals["pred_evs"], 0.75),
                "p90_pred_ev": percentile(vals["pred_evs"], 0.90),
                "max_pred_ev": max(vals["pred_evs"]) if vals["pred_evs"] else math.nan,
                "avg_pred_factor_product": mean(vals["pred_factors"]),
                "p90_pred_factor_product": percentile(vals["pred_factors"], 0.90),
                "frac_action_3": action_counts["3"] / total_legs if total_legs else math.nan,
                "frac_action_1": action_counts["1"] / total_legs if total_legs else math.nan,
                "frac_action_0": action_counts["0"] / total_legs if total_legs else math.nan,
            }
            for key, value in issue_row.items():
                if key not in row_out:
                    row_out[key] = value
            all_rows.append(row_out)
    return all_rows


def pass_one(value: float, direction: str, threshold: float) -> bool:
    if not math.isfinite(value) or not math.isfinite(threshold):
        return False
    if direction == "high":
        return value >= threshold
    if direction == "low":
        return value <= threshold
    raise ValueError(direction)


def pass_gate(row: dict[str, object], gate: Gate) -> bool:
    if not pass_one(fnum(row.get(gate.feature_a), math.nan), gate.direction_a, gate.threshold_a):
        return False
    if gate.feature_b:
        return pass_one(fnum(row.get(gate.feature_b), math.nan), gate.direction_b, gate.threshold_b)
    return True


def full_loss(row: dict[str, object]) -> bool:
    stake = fnum(row.get("stake_units"))
    return stake > 0 and fnum(row.get("profit_units")) <= -0.999 * stake


def summarize_active(rows: list[dict[str, object]], label: str) -> dict[str, object]:
    rows = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in rows)
    profit = sum(fnum(row.get("profit_units")) for row in rows)
    best = max((fnum(row.get("profit_units")) for row in rows), default=0.0)
    out = {
        f"{label}_active_issues": len(rows),
        f"{label}_stake_units": stake,
        f"{label}_profit_units": profit,
        f"{label}_roi": profit / stake if stake else math.nan,
        f"{label}_issue_win_rate": sum(1 for row in rows if fnum(row.get("profit_units")) > 0) / len(rows)
        if rows
        else math.nan,
        f"{label}_non_full_loss_rate": sum(1 for row in rows if not full_loss(row)) / len(rows) if rows else math.nan,
        f"{label}_max_drawdown_units": max_drawdown_units(rows),
        f"{label}_max_dead_streak": max_dead_streak(rows),
        f"{label}_best_issue_profit_units": best,
        f"{label}_roi_ex_best": (profit - best) / stake if stake else math.nan,
    }
    out.update({f"{label}_{key}": value for key, value in max_underwater(rows).items()})
    return out


def rows_for_years(rows: list[dict[str, object]], min_year: int, max_year: int) -> list[dict[str, object]]:
    return [row for row in rows if min_year <= row_year(row) <= max_year]


def gate_id(gate: Gate) -> str:
    if gate.feature_b:
        return (
            f"{gate.feature_a}_{gate.direction_a}_q{gate.quantile_a:g}"
            f"__{gate.feature_b}_{gate.direction_b}_q{gate.quantile_b:g}"
        )
    return f"{gate.feature_a}_{gate.direction_a}_q{gate.quantile_a:g}"


def build_single_gates(train_rows: list[dict[str, object]], quantiles: list[float]) -> list[Gate]:
    gates = []
    for feature, directions in FEATURE_DIRECTIONS.items():
        vals = [fnum(row.get(feature), math.nan) for row in train_rows]
        if sum(1 for val in vals if math.isfinite(val)) < 20:
            continue
        for direction in directions:
            for q in quantiles:
                threshold = percentile(vals, q)
                gate = Gate(
                    gate_id=f"{feature}_{direction}_q{q:g}",
                    feature_a=feature,
                    direction_a=direction,
                    quantile_a=q,
                    threshold_a=threshold,
                )
                gates.append(gate)
    return gates


def build_pair_gates(train_rows: list[dict[str, object]], quantiles: list[float]) -> list[Gate]:
    gates = []
    for (feature_a, direction_a), (feature_b, direction_b) in itertools.combinations(PAIR_FEATURES, 2):
        vals_a = [fnum(row.get(feature_a), math.nan) for row in train_rows]
        vals_b = [fnum(row.get(feature_b), math.nan) for row in train_rows]
        if sum(1 for val in vals_a if math.isfinite(val)) < 20 or sum(1 for val in vals_b if math.isfinite(val)) < 20:
            continue
        for qa in quantiles:
            for qb in quantiles:
                gates.append(
                    Gate(
                        gate_id=f"{feature_a}_{direction_a}_q{qa:g}__{feature_b}_{direction_b}_q{qb:g}",
                        feature_a=feature_a,
                        direction_a=direction_a,
                        quantile_a=qa,
                        threshold_a=percentile(vals_a, qa),
                        feature_b=feature_b,
                        direction_b=direction_b,
                        quantile_b=qb,
                        threshold_b=percentile(vals_b, qb),
                    )
                )
    return gates


def evaluate_gate(
    strategy: str,
    family: str,
    gate: Gate,
    all_strategy_rows: list[dict[str, object]],
    *,
    train_min_year: int,
    train_max_year: int,
    test_min_year: int,
    test_max_year: int,
) -> dict[str, object]:
    active = [row for row in all_strategy_rows if pass_gate(row, gate)]
    train_active = rows_for_years(active, train_min_year, train_max_year)
    test_active = rows_for_years(active, test_min_year, test_max_year)
    result = {
        "candidate": f"{strategy}::{gate_id(gate)}",
        "family": family,
        "strategy": strategy,
        "gate_id": gate_id(gate),
        "feature_a": gate.feature_a,
        "direction_a": gate.direction_a,
        "quantile_a": gate.quantile_a,
        "threshold_a": gate.threshold_a,
        "feature_b": gate.feature_b,
        "direction_b": gate.direction_b,
        "quantile_b": gate.quantile_b,
        "threshold_b": gate.threshold_b,
        "train_years": f"{train_min_year}-{train_max_year}",
        "test_years": f"{test_min_year}-{test_max_year}",
        "all_available_issues": len(all_strategy_rows),
    }
    result.update(summarize_active(train_active, "train"))
    result.update(summarize_active(test_active, "test"))
    result.update(summarize_active(active, "full"))
    return result


def annual_rows_for_candidate(rows: list[dict[str, object]], candidate: str) -> list[dict[str, object]]:
    grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[row_year(row)].append(row)
    out = []
    for year, vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "candidate": candidate,
                "year": year,
                "active_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals)
                if vals
                else math.nan,
                "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals) if vals else math.nan,
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def curve_rows_for_candidates(
    *,
    selected: list[dict[str, object]],
    rows_by_strategy: dict[str, list[dict[str, object]]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    issue_rows = []
    curves = []
    for item in selected:
        gate = Gate(
            gate_id=str(item["gate_id"]),
            feature_a=str(item["feature_a"]),
            direction_a=str(item["direction_a"]),
            quantile_a=fnum(item["quantile_a"]),
            threshold_a=fnum(item["threshold_a"]),
            feature_b=str(item.get("feature_b", "")),
            direction_b=str(item.get("direction_b", "")),
            quantile_b=fnum(item.get("quantile_b"), math.nan),
            threshold_b=fnum(item.get("threshold_b"), math.nan),
        )
        candidate = str(item["candidate"])
        rows = [row for row in rows_by_strategy[str(item["strategy"])] if pass_gate(row, gate)]
        rows = sorted(rows, key=row_order)
        cum_profit = 0.0
        cum_roi = 0.0
        for idx, row in enumerate(rows, start=1):
            copied = dict(row)
            copied["candidate"] = candidate
            copied["strategy"] = candidate
            issue_rows.append(copied)
            profit = fnum(row.get("profit_units"))
            stake = fnum(row.get("stake_units"))
            cum_profit += profit
            cum_roi += profit / stake if stake else 0.0
            curves.append(
                {
                    "strategy": candidate,
                    "issue": row.get("issue", ""),
                    "issue_close_ts": row.get("issue_close_ts", ""),
                    "issue_order": row.get("issue_order", ""),
                    "calendar_year": row_year(row),
                    "cum_profit_units": cum_profit,
                    "cum_issue_roi_units": cum_roi,
                    "n_points": idx,
                }
            )
    return issue_rows, curves


def compact(rows: list[dict[str, object]], limit: int = 20) -> list[dict[str, object]]:
    keep = [
        "candidate",
        "family",
        "train_active_issues",
        "train_roi",
        "train_profit_units",
        "test_active_issues",
        "test_roi",
        "test_profit_units",
        "full_active_issues",
        "full_roi",
        "full_profit_units",
        "full_issue_win_rate",
        "full_non_full_loss_rate",
        "full_max_drawdown_units",
        "full_roi_ex_best",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows[:limit]]


def run(args: argparse.Namespace) -> None:
    feature_rows = build_feature_rows(SOURCE_SETS)
    rows_by_strategy: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in feature_rows:
        rows_by_strategy[str(row["strategy"])].append(row)
    for rows in rows_by_strategy.values():
        rows.sort(key=row_order)

    quantiles = [float(part) for part in args.quantiles.split(",") if part.strip()]
    pair_quantiles = [float(part) for part in args.pair_quantiles.split(",") if part.strip()]
    candidates = []
    for strategy, rows in sorted(rows_by_strategy.items()):
        train_rows = rows_for_years(rows, args.train_min_year, args.train_max_year)
        if len(train_rows) < args.min_train_available:
            continue
        family = str(rows[0].get("family", ""))
        gates = build_single_gates(train_rows, quantiles)
        gates.extend(build_pair_gates(train_rows, pair_quantiles))
        for gate in gates:
            evaluated = evaluate_gate(
                strategy,
                family,
                gate,
                rows,
                train_min_year=args.train_min_year,
                train_max_year=args.train_max_year,
                test_min_year=args.test_min_year,
                test_max_year=args.test_max_year,
            )
            if (
                int(evaluated["train_active_issues"]) >= args.min_train_active
                and int(evaluated["test_active_issues"]) >= args.min_test_active
            ):
                candidates.append(evaluated)

    candidates.sort(
        key=lambda row: (
            fnum(row.get("test_roi")),
            fnum(row.get("test_profit_units")),
            fnum(row.get("full_roi")),
            -fnum(row.get("full_max_drawdown_units")),
        ),
        reverse=True,
    )
    robust = [
        row
        for row in candidates
        if fnum(row.get("train_roi")) > 0
        and fnum(row.get("test_roi")) > 0
        and fnum(row.get("full_roi")) > 0
        and fnum(row.get("full_roi_ex_best")) > 0
        and int(row.get("full_active_issues", 0)) >= args.min_full_active
    ]
    robust.sort(
        key=lambda row: (
            fnum(row.get("full_roi_ex_best")),
            fnum(row.get("full_roi")),
            fnum(row.get("test_roi")),
        ),
        reverse=True,
    )
    selected = robust[: args.plot_top_n]
    if len(selected) < args.plot_top_n:
        for row in candidates:
            if row not in selected:
                selected.append(row)
            if len(selected) >= args.plot_top_n:
                break

    selected_issue_rows, curve_rows = curve_rows_for_candidates(selected=selected, rows_by_strategy=rows_by_strategy)
    annual = []
    for item in selected:
        candidate_rows = [row for row in selected_issue_rows if row["candidate"] == item["candidate"]]
        annual.extend(annual_rows_for_candidate(candidate_rows, str(item["candidate"])))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "n3_arm_feature_rows.csv", feature_rows)
    write_csv_all(args.output_dir / "n3_arm_gate_candidates.csv", candidates)
    write_csv_all(args.output_dir / "n3_arm_gate_robust.csv", robust)
    write_csv_all(args.output_dir / "n3_arm_gate_selected_issue_profit.csv", selected_issue_rows)
    write_csv_all(args.output_dir / "n3_arm_gate_selected_annual.csv", annual)
    write_csv_all(args.output_dir / "n3_arm_gate_selected_curve.csv", curve_rows)
    plot_equity(curve_rows, args.figure_path)

    report = [
        "# N3 standalone arm optimization",
        "",
        "- Goal: find positive standalone N3 arms by adding pre-bet issue gates.",
        f"- Gate thresholds are fit on `{args.train_min_year}-{args.train_max_year}` and tested on `{args.test_min_year}-{args.test_max_year}`.",
        "- Features are built only from generated N3 ticket rows before settlement: predicted hit probability, predicted EV proxy, leg diversity, and action mix.",
        "",
        "## Robust Positive Candidates",
        "",
        md_table(compact(robust, limit=30)),
        "",
        "## Top Test ROI Candidates",
        "",
        md_table(compact(candidates, limit=30)),
        "",
        f"Equity curve SVG: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-min-year", type=int, default=2014)
    parser.add_argument("--train-max-year", type=int, default=2022)
    parser.add_argument("--test-min-year", type=int, default=2023)
    parser.add_argument("--test-max-year", type=int, default=2025)
    parser.add_argument("--quantiles", default="0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9")
    parser.add_argument("--pair-quantiles", default="0.4,0.5,0.6,0.7,0.8")
    parser.add_argument("--min-train-available", type=int, default=250)
    parser.add_argument("--min-train-active", type=int, default=80)
    parser.add_argument("--min-test-active", type=int, default=12)
    parser.add_argument("--min-full-active", type=int, default=100)
    parser.add_argument("--plot-top-n", type=int, default=8)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n3_arm_optimization_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n3_arm_optimization_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n3_arm_optimization_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
