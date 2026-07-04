#!/usr/bin/env python3
"""Dynamic issue-level allocation between N7 tail protection and N5 sleeves.

The allocator treats each fixed portfolio as an arm, then chooses the next issue's
arm using only prior settled issue results. This is a K-line style position
allocator, not a match-result model.
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

from scripts.evaluate_n7_same_ticket_leg_coverage import fnum, max_dead_streak, max_drawdown_units
from scripts.evaluate_n_dynamic_issue_depth import issue_year, loss_streak
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv

HOT_ARM = "rot_draw20_tail__512main"
NORMAL_ARM = "rot_draw20_tail__384main_128op05"
SPLIT_N5_ARM = "rot_draw20_tail__384main_64op05_64n5x90"
SPLIT_N3_ARM = "rot_draw20_tail__384main_64op05_64n3x180"
SPLIT_N5_N3_ARM = "rot_draw20_tail__384main_64n5x90_64n3x180"
FULL_PROTECT_ARM = "rot_full05_head__384main_128op05"
FULL_SPLIT_ARM = "rot_full05_head__384main_64op05_64n5x90"
FULL_N3_ARM = "rot_full05_head__384main_64op05_64n3x180"
UNCERTAIN_SPLIT_ARM = "rot_unc10_head_k2__384main_64op05_64n5x90"
N5_205_ARM = "rot_draw20_tail__307main_205op05"
N5_256_ARM = "rot_draw20_tail__256main_256op05"

FIXED_ARMS = [
    "current__512main",
    HOT_ARM,
    NORMAL_ARM,
    SPLIT_N5_ARM,
    SPLIT_N3_ARM,
    SPLIT_N5_N3_ARM,
    FULL_PROTECT_ARM,
    FULL_SPLIT_ARM,
    FULL_N3_ARM,
    UNCERTAIN_SPLIT_ARM,
    N5_205_ARM,
    N5_256_ARM,
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_ints(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def load_issue_rows(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    out: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in read_csv(path):
        out[str(row["portfolio"])][str(row["issue"])] = row
    return dict(out)


def full_loss(row: dict[str, object]) -> bool:
    return fnum(row.get("stake_units")) > 0 and fnum(row.get("profit_units")) <= -0.999 * fnum(row.get("stake_units"))


def row_order(row: dict[str, object]) -> tuple[object, str]:
    return row.get("issue_close_ts", ""), str(row.get("issue", ""))


def row_year(row: dict[str, object]) -> int:
    if row.get("calendar_year") not in (None, ""):
        return int(str(row["calendar_year"]))
    close_ts = str(row.get("issue_close_ts", ""))
    if len(close_ts) >= 4 and close_ts[:4].isdigit():
        return int(close_ts[:4])
    return issue_year(str(row["issue"]))


def consecutive(rows: list[dict[str, object]], predicate) -> int:
    total = 0
    for row in reversed(rows):
        if predicate(row):
            total += 1
            continue
        break
    return total


def history_state(history: list[dict[str, object]], window: int) -> dict[str, object]:
    recent = history[-window:] if window > 0 else history
    stake = sum(fnum(row.get("stake_units")) for row in recent)
    profit = sum(fnum(row.get("profit_units")) for row in recent)
    dead_count = sum(1 for row in recent if full_loss(row))
    loss_count = sum(1 for row in recent if fnum(row.get("profit_units")) <= 0)
    return {
        "history_n": len(history),
        "window": window,
        "rolling_stake": stake,
        "rolling_profit": profit,
        "rolling_roi": profit / stake if stake else math.nan,
        "rolling_dead_count": dead_count,
        "rolling_loss_count": loss_count,
        "dead_streak": consecutive(history, full_loss),
        "loss_streak": consecutive(history, lambda row: fnum(row.get("profit_units")) <= 0),
    }


def policy_specs(windows: list[int]) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for arm in FIXED_ARMS:
        specs.append(
            {
                "policy": f"fixed::{arm}",
                "kind": "fixed",
                "normal_arm": arm,
            }
        )

    arm_sets = [
        {
            "name": "draw_tail_to_split",
            "normal_arm": NORMAL_ARM,
            "hot_arm": HOT_ARM,
            "defensive_arm": SPLIT_N5_ARM,
            "severe_arm": FULL_SPLIT_ARM,
        },
        {
            "name": "draw_tail_to_full",
            "normal_arm": NORMAL_ARM,
            "hot_arm": HOT_ARM,
            "defensive_arm": FULL_PROTECT_ARM,
            "severe_arm": UNCERTAIN_SPLIT_ARM,
        },
        {
            "name": "split_base_to_full",
            "normal_arm": SPLIT_N5_ARM,
            "hot_arm": NORMAL_ARM,
            "defensive_arm": FULL_SPLIT_ARM,
            "severe_arm": UNCERTAIN_SPLIT_ARM,
        },
        {
            "name": "draw_tail_to_n3",
            "normal_arm": NORMAL_ARM,
            "hot_arm": HOT_ARM,
            "defensive_arm": SPLIT_N3_ARM,
            "severe_arm": FULL_N3_ARM,
        },
        {
            "name": "split_base_to_n3",
            "normal_arm": SPLIT_N5_ARM,
            "hot_arm": NORMAL_ARM,
            "defensive_arm": SPLIT_N5_N3_ARM,
            "severe_arm": FULL_N3_ARM,
        },
        {
            "name": "n5_ratio_step",
            "normal_arm": NORMAL_ARM,
            "hot_arm": HOT_ARM,
            "defensive_arm": N5_205_ARM,
            "severe_arm": N5_256_ARM,
        },
    ]

    for signal_mode in ("played", "reference"):
        for arms in arm_sets:
            for window in windows:
                for defensive_dead in (2, 3):
                    for defensive_loss in (4, 6):
                        specs.append(
                            {
                                "policy": (
                                    f"{signal_mode}::{arms['name']}::w{window}"
                                    f"::dd{defensive_dead}::ls{defensive_loss}"
                                ),
                                "kind": "dynamic",
                                "signal_mode": signal_mode,
                                "window": window,
                                "min_history": window,
                                "normal_arm": arms["normal_arm"],
                                "hot_arm": arms["hot_arm"],
                                "defensive_arm": arms["defensive_arm"],
                                "severe_arm": arms["severe_arm"],
                                "defensive_dead": defensive_dead,
                                "defensive_loss": defensive_loss,
                                "defensive_profit": -1.5 * 512,
                                "severe_dead": max(defensive_dead + 1, 4),
                                "severe_loss": max(defensive_loss + 2, 8),
                                "severe_profit": -3.0 * 512,
                                "hot_profit": 1.0 * 512,
                            }
                        )
    return specs


def choose_arm(spec: dict[str, object], state: dict[str, object]) -> tuple[str, str]:
    if spec["kind"] == "fixed":
        return str(spec["normal_arm"]), "fixed"
    if int(state["history_n"]) < int(spec["min_history"]):
        return str(spec["normal_arm"]), "warmup"

    if (
        int(state["dead_streak"]) >= int(spec["severe_dead"])
        or int(state["loss_streak"]) >= int(spec["severe_loss"])
        or fnum(state["rolling_profit"]) <= fnum(spec["severe_profit"])
    ):
        return str(spec["severe_arm"]), "severe"
    if (
        int(state["dead_streak"]) >= int(spec["defensive_dead"])
        or int(state["loss_streak"]) >= int(spec["defensive_loss"])
        or fnum(state["rolling_profit"]) <= fnum(spec["defensive_profit"])
    ):
        return str(spec["defensive_arm"]), "defensive"
    if (
        fnum(state["rolling_profit"]) >= fnum(spec["hot_profit"])
        and int(state["dead_streak"]) == 0
        and int(state["rolling_dead_count"]) == 0
        and int(state["loss_streak"]) <= 1
    ):
        return str(spec["hot_arm"]), "hot"
    return str(spec["normal_arm"]), "normal"


def max_underwater(rows: list[dict[str, object]]) -> dict[str, object]:
    rows = sorted(rows, key=row_order)
    equity = 0.0
    peak = 0.0
    peak_date = ""
    current_start = ""
    current_len = 0
    current_peak = 0.0
    current_trough = 0.0
    best = {
        "max_underwater_issues": 0,
        "max_underwater_start_ts": "",
        "max_underwater_end_ts": "",
        "max_underwater_peak_units": 0.0,
        "max_underwater_trough_units": 0.0,
        "max_underwater_dd_units": 0.0,
    }
    for row in rows:
        equity += fnum(row.get("profit_units"))
        date = str(row.get("issue_close_ts", row.get("issue", "")))
        if equity >= peak:
            if current_len > int(best["max_underwater_issues"]):
                best = {
                    "max_underwater_issues": current_len,
                    "max_underwater_start_ts": current_start,
                    "max_underwater_end_ts": date,
                    "max_underwater_peak_units": current_peak,
                    "max_underwater_trough_units": current_trough,
                    "max_underwater_dd_units": current_trough - current_peak,
                }
            peak = equity
            peak_date = date
            current_start = ""
            current_len = 0
            current_peak = peak
            current_trough = equity
            continue
        if not current_start:
            current_start = peak_date
            current_peak = peak
            current_trough = equity
            current_len = 1
        else:
            current_len += 1
            current_trough = min(current_trough, equity)

    if current_len > int(best["max_underwater_issues"]):
        best = {
            "max_underwater_issues": current_len,
            "max_underwater_start_ts": current_start,
            "max_underwater_end_ts": str(rows[-1].get("issue_close_ts", rows[-1].get("issue", ""))) if rows else "",
            "max_underwater_peak_units": current_peak,
            "max_underwater_trough_units": current_trough,
            "max_underwater_dd_units": current_trough - current_peak,
        }
    return best


def summarize(rows: list[dict[str, object]], recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    rows = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in rows)
    profit = sum(fnum(row.get("profit_units")) for row in rows)
    best = max((fnum(row.get("profit_units")) for row in rows), default=0.0)
    recent = [row for row in rows if recent_min_year <= row_year(row) <= recent_max_year]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    recent_best = max((fnum(row.get("profit_units")) for row in recent), default=0.0)
    out = {
        "policy": str(rows[0]["policy"]) if rows else "",
        "n_issues": len(rows),
        "stake_units": stake,
        "profit_units": profit,
        "roi": profit / stake if stake else math.nan,
        "issue_win_rate": sum(1 for row in rows if fnum(row.get("profit_units")) > 0) / len(rows),
        "non_full_loss_rate": sum(1 for row in rows if not full_loss(row)) / len(rows),
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
    }
    out.update(max_underwater(rows))
    return out


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["policy"]), row_year(row))].append(row)
    out = []
    for (policy, year), vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "policy": policy,
                "year": year,
                "n_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals),
                "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals),
            }
        )
    return out


def simulate_policy(
    spec: dict[str, object],
    issue_maps: dict[str, dict[str, dict[str, str]]],
    issues: list[str],
    reference_arm: str,
) -> tuple[list[dict[str, object]], Counter[str], Counter[str]]:
    played_history: list[dict[str, object]] = []
    reference_history: list[dict[str, object]] = []
    chosen_rows: list[dict[str, object]] = []
    arm_use: Counter[str] = Counter()
    state_use: Counter[str] = Counter()

    for issue in issues:
        source_history = played_history
        if spec.get("signal_mode") == "reference":
            source_history = reference_history
        state = history_state(source_history, int(spec.get("window", 0)))
        arm, state_name = choose_arm(spec, state)
        if issue not in issue_maps[arm]:
            raise SystemExit(f"missing issue {issue} for arm {arm}")
        chosen = dict(issue_maps[arm][issue])
        chosen.update(
            {
                "policy": spec["policy"],
                "chosen_arm": arm,
                "state": state_name,
                "signal_mode": spec.get("signal_mode", "fixed"),
                "rolling_profit": state.get("rolling_profit", ""),
                "rolling_roi": state.get("rolling_roi", ""),
                "rolling_dead_count": state.get("rolling_dead_count", ""),
                "rolling_loss_count": state.get("rolling_loss_count", ""),
                "dead_streak_before": state.get("dead_streak", ""),
                "loss_streak_before": state.get("loss_streak", ""),
                "history_n": state.get("history_n", ""),
            }
        )
        chosen_rows.append(chosen)
        played_history.append(chosen)
        reference_history.append(dict(issue_maps[reference_arm][issue]))
        arm_use[arm] += 1
        state_use[state_name] += 1
    return chosen_rows, arm_use, state_use


def run(args: argparse.Namespace) -> None:
    issue_maps = load_issue_rows(args.combo_issue_profit)
    for arm in set(FIXED_ARMS + [args.reference_arm]):
        if arm not in issue_maps:
            raise SystemExit(f"missing required arm: {arm}")
    issues = [
        row["issue"]
        for row in sorted(issue_maps[args.reference_arm].values(), key=row_order)
    ]

    all_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    usage_rows: list[dict[str, object]] = []
    for spec in policy_specs(parse_ints(args.windows)):
        rows, arm_use, state_use = simulate_policy(spec, issue_maps, issues, args.reference_arm)
        all_rows.extend(rows)
        summary = summarize(rows, args.recent_min_year, args.recent_max_year)
        summary.update(
            {
                "kind": spec["kind"],
                "signal_mode": spec.get("signal_mode", "fixed"),
                "window": spec.get("window", ""),
                "normal_arm": spec["normal_arm"],
                "hot_arm": spec.get("hot_arm", ""),
                "defensive_arm": spec.get("defensive_arm", ""),
                "severe_arm": spec.get("severe_arm", ""),
                "arm_usage": ";".join(f"{arm}:{count}" for arm, count in sorted(arm_use.items())),
                "state_usage": ";".join(f"{state}:{count}" for state, count in sorted(state_use.items())),
            }
        )
        summaries.append(summary)
        for arm, count in sorted(arm_use.items()):
            usage_rows.append({"policy": spec["policy"], "type": "arm", "name": arm, "count": count})
        for state, count in sorted(state_use.items()):
            usage_rows.append({"policy": spec["policy"], "type": "state", "name": state, "count": count})

    summaries.sort(key=lambda row: (fnum(row["profit_units"]), fnum(row["non_full_loss_rate"])), reverse=True)
    selected_names = {
        "fixed::current__512main",
        f"fixed::{HOT_ARM}",
        f"fixed::{NORMAL_ARM}",
        f"fixed::{SPLIT_N5_ARM}",
        f"fixed::{FULL_SPLIT_ARM}",
    }
    selected_names.update(str(row["policy"]) for row in summaries[:15])
    selected = [row for row in summaries if row["policy"] in selected_names]
    selected.sort(key=lambda row: (str(row["kind"]) != "fixed", -fnum(row["profit_units"])))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "dynamic_sleeve_issue_profit.csv", all_rows)
    write_csv(args.output_dir / "dynamic_sleeve_summary.csv", summaries)
    write_csv(args.output_dir / "dynamic_sleeve_selected.csv", selected)
    write_csv(args.output_dir / "dynamic_sleeve_usage.csv", usage_rows)
    write_csv(args.output_dir / "dynamic_sleeve_annual.csv", annual_rows(all_rows))

    report = [
        "# Dynamic N7/N5 sleeve allocator",
        "",
        f"- Combo source: `{args.combo_issue_profit}`",
        f"- Reference arm: `{args.reference_arm}`",
        "",
        "## Selected",
        "",
        md_table(selected, limit=60),
        "",
        "## Top policies",
        "",
        md_table(summaries[:30], limit=30),
        "",
    ]
    (args.output_dir / "dynamic_sleeve_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'dynamic_sleeve_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--combo-issue-profit",
        type=Path,
        default=Path("results/n7_rotating_n5_sleeve_combo_20260628/rotating_n5_combo_issue_profit.csv"),
    )
    parser.add_argument("--reference-arm", default=NORMAL_ARM)
    parser.add_argument("--windows", default="3,5,8,13")
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_dynamic_sleeve_allocator_20260628"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
