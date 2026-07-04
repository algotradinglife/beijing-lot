#!/usr/bin/env python3
"""Two-layer dynamic allocator over N7/N5/N3 ratio-grid portfolios."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_dynamic_sleeve_allocator import (
    fnum,
    history_state,
    load_issue_rows,
    row_order,
    summarize,
    annual_rows,
)
from scripts.evaluate_n7_n5_n3_ratio_grid import portfolio_name
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


def parse_ints(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def arm(n7_label: str, n7: int, n5op: int, n5std: int, n3: int) -> str:
    return portfolio_name(n7_label, {"n7": n7, "n5op": n5op, "n5std": n5std, "n3": n3})


def valid_arm(n7_label: str, n7: int, n5op: int, n5std: int, n3: int) -> str:
    total = n7 + n5op + n5std + n3
    if total != 512 or min(n7, n5op, n5std, n3) < 0:
        return ""
    return arm(n7_label, n7, n5op, n5std, n3)


def is_defensive(state: dict[str, object], *, dead: int, loss: int, profit_units: float) -> bool:
    return (
        int(state["dead_streak"]) >= dead
        or int(state["loss_streak"]) >= loss
        or fnum(state["rolling_profit"]) <= profit_units
    )


def is_hot(fast_state: dict[str, object], slow_state: dict[str, object]) -> bool:
    return (
        fnum(fast_state["rolling_profit"]) >= 512
        and fnum(slow_state["rolling_profit"]) >= 512
        and int(fast_state["dead_streak"]) == 0
        and int(slow_state["dead_streak"]) == 0
        and int(fast_state["rolling_dead_count"]) == 0
        and int(slow_state["rolling_dead_count"]) == 0
        and int(fast_state["loss_streak"]) <= 1
        and int(slow_state["loss_streak"]) <= 1
    )


def policy_specs(args: argparse.Namespace) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for fast_window in parse_ints(args.fast_windows):
        for slow_window in parse_ints(args.slow_windows):
            for fast_n3 in parse_ints(args.fast_n3_units):
                for slow_n3 in parse_ints(args.slow_n3_units):
                    for severe_n3 in parse_ints(args.severe_n3_units):
                        for slow_signal in ("played", "reference"):
                            normal_n7 = args.normal_n7_units
                            fast_n7 = args.fast_n7_units
                            slow_n7 = args.slow_n7_units
                            severe_n7 = args.severe_n7_units
                            normal = valid_arm(args.main_n7_arm, normal_n7, 512 - normal_n7, 0, 0)
                            hot = arm(args.main_n7_arm, 512, 0, 0, 0)
                            fast = valid_arm(
                                args.main_n7_arm,
                                fast_n7,
                                512 - fast_n7 - fast_n3,
                                0,
                                fast_n3,
                            )
                            slow = valid_arm(
                                args.main_n7_arm,
                                slow_n7,
                                512 - slow_n7 - slow_n3 - 64,
                                64,
                                slow_n3,
                            )
                            severe = valid_arm(
                                args.severe_n7_arm,
                                severe_n7,
                                512 - severe_n7 - severe_n3,
                                0,
                                severe_n3,
                            )
                            if not all([normal, hot, fast, slow, severe]):
                                continue
                            specs.append(
                                {
                                    "policy": (
                                        "two_layer"
                                        f"::fw{fast_window}sw{slow_window}"
                                        f"::n{normal_n7}f{fast_n7}s{slow_n7}x{severe_n7}"
                                        f"::fn3{fast_n3}sn3{slow_n3}x{severe_n3}"
                                        f"::{('fast_only' if args.disable_slow else 'slow_on')}"
                                        f"::{slow_signal}"
                                    ),
                                    "fast_window": fast_window,
                                    "slow_window": slow_window,
                                    "slow_signal": slow_signal,
                                    "normal_arm": normal,
                                    "hot_arm": hot,
                                    "fast_arm": fast,
                                    "slow_arm": slow,
                                    "severe_arm": severe,
                                    "fast_n3_units": fast_n3,
                                    "slow_n3_units": slow_n3,
                                    "severe_n3_units": severe_n3,
                                    "normal_n7_units": normal_n7,
                                    "fast_n7_units": fast_n7,
                                    "slow_n7_units": slow_n7,
                                    "severe_n7_units": severe_n7,
                                    "disable_slow": args.disable_slow,
                                }
                            )
    return specs


def choose_arm(
    spec: dict[str, object],
    *,
    fast_state: dict[str, object],
    slow_state: dict[str, object],
) -> tuple[str, str]:
    min_history = max(int(spec["fast_window"]), int(spec["slow_window"]))
    if spec.get("disable_slow"):
        min_history = int(spec["fast_window"])
    if int(slow_state["history_n"]) < min_history:
        return str(spec["normal_arm"]), "warmup"
    if spec.get("disable_slow"):
        if is_defensive(fast_state, dead=3, loss=8, profit_units=-3.0 * 512):
            return str(spec["severe_arm"]), "fast_severe"
        if is_defensive(fast_state, dead=2, loss=4, profit_units=-1.0 * 512):
            return str(spec["fast_arm"]), "fast_defensive"
        if is_hot(fast_state, fast_state):
            return str(spec["hot_arm"]), "hot"
        return str(spec["normal_arm"]), "normal"
    if is_defensive(slow_state, dead=3, loss=8, profit_units=-3.0 * 512):
        return str(spec["severe_arm"]), "slow_severe"
    if is_defensive(slow_state, dead=2, loss=5, profit_units=-1.5 * 512):
        return str(spec["slow_arm"]), "slow_defensive"
    if is_defensive(fast_state, dead=2, loss=4, profit_units=-1.0 * 512):
        return str(spec["fast_arm"]), "fast_defensive"
    if is_hot(fast_state, slow_state):
        return str(spec["hot_arm"]), "hot"
    return str(spec["normal_arm"]), "normal"


def simulate(
    spec: dict[str, object],
    issue_maps: dict[str, dict[str, dict[str, str]]],
    issues: list[str],
) -> tuple[list[dict[str, object]], Counter[str], Counter[str]]:
    played_history: list[dict[str, object]] = []
    reference_history: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    arm_use: Counter[str] = Counter()
    state_use: Counter[str] = Counter()
    reference_arm = str(spec["normal_arm"])

    for issue in issues:
        fast_state = history_state(reference_history, int(spec["fast_window"]))
        slow_history = played_history if spec["slow_signal"] == "played" else reference_history
        slow_state = history_state(slow_history, int(spec["slow_window"]))
        selected_arm, state = choose_arm(spec, fast_state=fast_state, slow_state=slow_state)
        chosen = dict(issue_maps[selected_arm][issue])
        chosen.update(
            {
                "policy": spec["policy"],
                "chosen_arm": selected_arm,
                "state": state,
                "fast_window": spec["fast_window"],
                "slow_window": spec["slow_window"],
                "slow_signal": spec["slow_signal"],
                "fast_rolling_profit": fast_state.get("rolling_profit", ""),
                "slow_rolling_profit": slow_state.get("rolling_profit", ""),
                "fast_dead_streak_before": fast_state.get("dead_streak", ""),
                "slow_dead_streak_before": slow_state.get("dead_streak", ""),
                "fast_loss_streak_before": fast_state.get("loss_streak", ""),
                "slow_loss_streak_before": slow_state.get("loss_streak", ""),
            }
        )
        rows.append(chosen)
        played_history.append(chosen)
        reference_history.append(dict(issue_maps[reference_arm][issue]))
        arm_use[selected_arm] += 1
        state_use[state] += 1
    return rows, arm_use, state_use


def run(args: argparse.Namespace) -> None:
    issue_maps = load_issue_rows(args.ratio_issue_profit)
    reference_arm = arm(args.main_n7_arm, 384, 128, 0, 0)
    if reference_arm not in issue_maps:
        raise SystemExit(f"missing reference arm: {reference_arm}")
    issues = [row["issue"] for row in sorted(issue_maps[reference_arm].values(), key=row_order)]

    all_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    usage_rows: list[dict[str, object]] = []
    for spec in policy_specs(args):
        required = [
            str(spec[key])
            for key in ("normal_arm", "hot_arm", "fast_arm", "slow_arm", "severe_arm")
        ]
        if any(item not in issue_maps for item in required):
            continue
        rows, arm_use, state_use = simulate(spec, issue_maps, issues)
        all_rows.extend(rows)
        summary = summarize(rows, args.recent_min_year, args.recent_max_year)
        summary.update(
            {
                "fast_window": spec["fast_window"],
                "slow_window": spec["slow_window"],
                "slow_signal": spec["slow_signal"],
                "normal_arm": spec["normal_arm"],
                "hot_arm": spec["hot_arm"],
                "fast_arm": spec["fast_arm"],
                "slow_arm": spec["slow_arm"],
                "severe_arm": spec["severe_arm"],
                "fast_n3_units": spec["fast_n3_units"],
                "slow_n3_units": spec["slow_n3_units"],
                "severe_n3_units": spec["severe_n3_units"],
                "normal_n7_units": spec["normal_n7_units"],
                "fast_n7_units": spec["fast_n7_units"],
                "slow_n7_units": spec["slow_n7_units"],
                "severe_n7_units": spec["severe_n7_units"],
                "disable_slow": spec["disable_slow"],
                "arm_usage": ";".join(f"{key}:{value}" for key, value in sorted(arm_use.items())),
                "state_usage": ";".join(f"{key}:{value}" for key, value in sorted(state_use.items())),
            }
        )
        summaries.append(summary)
        for key, value in sorted(arm_use.items()):
            usage_rows.append({"policy": spec["policy"], "type": "arm", "name": key, "count": value})
        for key, value in sorted(state_use.items()):
            usage_rows.append({"policy": spec["policy"], "type": "state", "name": key, "count": value})

    summaries.sort(key=lambda row: (fnum(row["profit_units"]), fnum(row["non_full_loss_rate"])), reverse=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "n7_n5_n3_ratio_dynamic_issue_profit.csv", all_rows)
    write_csv(args.output_dir / "n7_n5_n3_ratio_dynamic_summary.csv", summaries)
    write_csv(args.output_dir / "n7_n5_n3_ratio_dynamic_usage.csv", usage_rows)
    write_csv(args.output_dir / "n7_n5_n3_ratio_dynamic_annual.csv", annual_rows(all_rows))
    report = [
        "# N7/N5/N3 two-layer dynamic ratio allocator",
        "",
        f"- Ratio source: `{args.ratio_issue_profit}`",
        f"- Main N7 arm: `{args.main_n7_arm}`",
        f"- Severe N7 arm: `{args.severe_n7_arm}`",
        "",
        "## Top Profit",
        "",
        md_table(summaries, limit=30),
        "",
        "## High Non-Full-Loss With ROI >= 0.85",
        "",
        md_table(
            [
                row
                for row in sorted(summaries, key=lambda item: fnum(item["non_full_loss_rate"]), reverse=True)
                if fnum(row["roi"]) >= 0.85
            ],
            limit=30,
        ),
        "",
    ]
    (args.output_dir / "n7_n5_n3_ratio_dynamic_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'n7_n5_n3_ratio_dynamic_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ratio-issue-profit",
        type=Path,
        default=Path("results/n7_n5_n3_ratio_grid_20260628_timefix/n7_n5_n3_ratio_issue_profit.csv"),
    )
    parser.add_argument("--main-n7-arm", default="rot_draw20_tail")
    parser.add_argument("--severe-n7-arm", default="rot_full05_head")
    parser.add_argument("--normal-n7-units", type=int, default=384)
    parser.add_argument("--fast-n7-units", type=int, default=384)
    parser.add_argument("--slow-n7-units", type=int, default=384)
    parser.add_argument("--severe-n7-units", type=int, default=384)
    parser.add_argument("--disable-slow", action="store_true")
    parser.add_argument("--fast-windows", default="3,5,8")
    parser.add_argument("--slow-windows", default="13,21,34")
    parser.add_argument("--fast-n3-units", default="32,64,96,128")
    parser.add_argument("--slow-n3-units", default="32,64")
    parser.add_argument("--severe-n3-units", default="64,96,128")
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_n5_n3_ratio_dynamic_20260628_timefix"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
