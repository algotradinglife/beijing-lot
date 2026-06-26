#!/usr/bin/env python3
"""Validation gate for combo strategy candidates.

The gate reruns a candidate across decision snapshots, then checks whether
positive PnL survives realistic-entry and concentration tests. The `final`
snapshot is kept as a diagnostic only; pass/fail is based on non-final snapshots.
"""
from __future__ import annotations

import argparse
import csv
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_combo_main_cold_tail import max_drawdown, max_loss_streak
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


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


def run_dir(args: argparse.Namespace, snapshot: str, train_issues: int) -> Path:
    return args.output_dir / "runs" / f"{args.candidate_name}_{snapshot}_t{train_issues}"


def evaluator_command(
    args: argparse.Namespace,
    unknown_args: list[str],
    *,
    snapshot: str,
    train_issues: int,
    out_dir: Path,
) -> list[str]:
    cmd = [
        args.python_exe,
        str(args.evaluator),
        "--train-issues",
        str(train_issues),
        "--main-snapshot",
        snapshot,
        "--cold-snapshot",
        args.cold_snapshot,
        "--cold-overlap-filter",
        args.cold_overlap_filter,
        "--trigger-min-cold-candidate-matches",
        str(args.trigger_min_cold_candidate_matches),
        "--trigger-min-q-legs",
        str(args.trigger_min_q_legs),
        "--output-dir",
        str(out_dir),
    ]
    return cmd + unknown_args


def run_evaluations(args: argparse.Namespace, unknown_args: list[str]) -> list[dict[str, object]]:
    command_rows: list[dict[str, object]] = []
    for train_issues in parse_ints(args.train_windows):
        for snapshot in parse_strings(args.snapshots):
            out_dir = run_dir(args, snapshot, train_issues)
            report = out_dir / "combo_report.md"
            cmd = evaluator_command(args, unknown_args, snapshot=snapshot, train_issues=train_issues, out_dir=out_dir)
            command_rows.append(
                {
                    "candidate": args.candidate_name,
                    "train_issues": train_issues,
                    "snapshot": snapshot,
                    "output_dir": str(out_dir),
                    "command": " ".join(cmd),
                    "executed": int((args.force or not report.exists()) and not args.skip_run),
                }
            )
            if args.skip_run:
                continue
            if report.exists() and not args.force:
                continue
            subprocess.run(cmd, cwd=ROOT, check=True)
    return command_rows


def issue_rows_from_allocation(result_dir: Path) -> list[dict[str, object]]:
    path = result_dir / "allocation_issue_profit.csv"
    out: list[dict[str, object]] = []
    if not path.exists():
        return out
    for row in read_csv_rows(path):
        if row.get("allocation") != "main_100%_cold_0%":
            continue
        out.append(
            {
                "portfolio": "main_only",
                "issue": row["issue"],
                "stake": as_float(row, "budget"),
                "profit": as_float(row, "profit"),
                "triggered": 0,
            }
        )
    return out


def issue_rows_from_conditional(result_dir: Path) -> list[dict[str, object]]:
    path = result_dir / "conditional_allocation_issue_profit.csv"
    out: list[dict[str, object]] = []
    if not path.exists():
        return out
    for row in read_csv_rows(path):
        out.append(
            {
                "portfolio": "conditional",
                "issue": row["issue"],
                "stake": as_float(row, "budget"),
                "profit": as_float(row, "profit"),
                "triggered": as_int(row, "triggered"),
            }
        )
    return out


def summarize_issue_rows(
    rows: list[dict[str, object]],
    *,
    args: argparse.Namespace,
    snapshot: str,
    train_issues: int,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["portfolio"])].append(row)

    out: list[dict[str, object]] = []
    for portfolio, vals in sorted(grouped.items()):
        vals = sorted(vals, key=lambda r: str(r["issue"]))
        profits = [as_float(r, "profit") for r in vals]
        stakes = [as_float(r, "stake") for r in vals]
        stake = sum(stakes)
        profit = sum(profits)
        roi = profit / stake if stake else float("nan")
        if vals:
            best = max(vals, key=lambda r: as_float(r, "profit"))
            worst = min(vals, key=lambda r: as_float(r, "profit"))
            best_profit = as_float(best, "profit")
            best_stake = as_float(best, "stake")
            loo_profit = profit - best_profit
            loo_stake = stake - best_stake
        else:
            best = worst = {"issue": ""}
            best_profit = best_stake = loo_profit = loo_stake = 0.0
        best_share = best_profit / profit if profit > 0 and best_profit > 0 else float("inf")
        loo_roi = loo_profit / loo_stake if loo_stake else float("nan")
        profitable = sum(1 for p in profits if p > 0)
        profitable_rate = profitable / len(vals) if vals else float("nan")
        dd = max_drawdown(profits)
        dd_to_profit = dd / profit if profit > 0 else float("inf")

        is_real_snapshot = snapshot != "final"
        pass_min_issues = len(vals) >= args.min_issues
        pass_roi = math.isfinite(roi) and roi >= args.min_roi
        pass_loo = math.isfinite(loo_roi) and loo_roi >= args.min_loo_roi
        pass_best_share = math.isfinite(best_share) and best_share <= args.max_best_issue_share
        pass_profitable_rate = math.isfinite(profitable_rate) and profitable_rate >= args.min_profitable_issue_rate
        pass_dd = math.isfinite(dd_to_profit) and dd_to_profit <= args.max_dd_to_profit
        pass_snapshot = (
            is_real_snapshot
            and pass_min_issues
            and pass_roi
            and pass_loo
            and pass_best_share
            and pass_profitable_rate
            and pass_dd
        )
        out.append(
            {
                "candidate": args.candidate_name,
                "train_issues": train_issues,
                "snapshot": snapshot,
                "portfolio": portfolio,
                "is_real_snapshot": int(is_real_snapshot),
                "issues": len(vals),
                "triggered_issues": sum(1 for r in vals if as_int(r, "triggered") > 0),
                "stake": stake,
                "profit": profit,
                "roi": roi,
                "profitable_issues": profitable,
                "profitable_issue_rate": profitable_rate,
                "best_issue": str(best.get("issue", "")),
                "best_issue_profit": best_profit,
                "best_issue_profit_share": best_share,
                "loo_profit": loo_profit,
                "loo_roi": loo_roi,
                "worst_issue": str(worst.get("issue", "")),
                "min_issue_profit": min(profits) if profits else 0.0,
                "max_drawdown_units": dd,
                "max_dd_to_profit": dd_to_profit,
                "max_issue_loss_streak": max_loss_streak(profits),
                "pass_min_issues": int(pass_min_issues),
                "pass_roi": int(pass_roi),
                "pass_loo": int(pass_loo),
                "pass_best_share": int(pass_best_share),
                "pass_profitable_rate": int(pass_profitable_rate),
                "pass_dd": int(pass_dd),
                "pass_snapshot": int(pass_snapshot),
            }
        )
    return out


def collect_metrics(args: argparse.Namespace) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for train_issues in parse_ints(args.train_windows):
        for snapshot in parse_strings(args.snapshots):
            result_dir = run_dir(args, snapshot, train_issues)
            issue_rows = issue_rows_from_allocation(result_dir)
            if args.include_conditional:
                issue_rows.extend(issue_rows_from_conditional(result_dir))
            rows.extend(summarize_issue_rows(issue_rows, args=args, snapshot=snapshot, train_issues=train_issues))
    return rows


def verdict_rows(metrics: list[dict[str, object]], args: argparse.Namespace) -> list[dict[str, object]]:
    grouped: dict[tuple[int, str], list[dict[str, object]]] = defaultdict(list)
    for row in metrics:
        grouped[(as_int(row, "train_issues"), str(row["portfolio"]))].append(row)
    out: list[dict[str, object]] = []
    real_snapshots = [s for s in parse_strings(args.snapshots) if s != "final"]
    for (train_issues, portfolio), vals in sorted(grouped.items()):
        by_snapshot = {str(r["snapshot"]): r for r in vals}
        missing = [s for s in real_snapshots if s not in by_snapshot]
        failed = [s for s in real_snapshots if s in by_snapshot and as_int(by_snapshot[s], "pass_snapshot") == 0]
        passed = [s for s in real_snapshots if s in by_snapshot and as_int(by_snapshot[s], "pass_snapshot") == 1]
        verdict = "pass" if not missing and not failed and passed else "fail"
        reasons: list[str] = []
        if missing:
            reasons.append(f"missing real snapshots: {','.join(missing)}")
        for s in failed:
            row = by_snapshot[s]
            checks = []
            for key in (
                "pass_min_issues",
                "pass_roi",
                "pass_loo",
                "pass_best_share",
                "pass_profitable_rate",
                "pass_dd",
            ):
                if as_int(row, key) == 0:
                    checks.append(key.replace("pass_", ""))
            reasons.append(f"{s} failed {','.join(checks)}")
        out.append(
            {
                "candidate": args.candidate_name,
                "train_issues": train_issues,
                "portfolio": portfolio,
                "verdict": verdict,
                "real_snapshots_required": ",".join(real_snapshots),
                "real_snapshots_passed": ",".join(passed),
                "reason": "; ".join(reasons) if reasons else "all real snapshots passed",
            }
        )
    return out


def compact_metrics(metrics: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "train_issues",
        "snapshot",
        "portfolio",
        "issues",
        "triggered_issues",
        "roi",
        "loo_roi",
        "profit",
        "loo_profit",
        "profitable_issue_rate",
        "best_issue",
        "best_issue_profit_share",
        "max_drawdown_units",
        "max_dd_to_profit",
        "pass_snapshot",
    ]
    return [{k: row[k] for k in keep} for row in metrics]


def write_report(args: argparse.Namespace, commands: list[dict[str, object]], metrics: list[dict[str, object]], verdicts: list[dict[str, object]]) -> None:
    report = [
        f"# Strategy Candidate Validation Gate: {args.candidate_name}",
        "",
        "The `final` snapshot is diagnostic only. A candidate passes only if every non-final snapshot passes the hard gates.",
        "",
        "## Hard Gates",
        "",
        f"- Minimum issues: `{args.min_issues}`",
        f"- Minimum ROI: `{args.min_roi:.2%}`",
        f"- Minimum leave-one-out ROI: `{args.min_loo_roi:.2%}`",
        f"- Maximum best issue profit share: `{args.max_best_issue_share:.2f}`",
        f"- Minimum profitable issue rate: `{args.min_profitable_issue_rate:.2%}`",
        f"- Maximum maxDD/profit: `{args.max_dd_to_profit:.2f}`",
        "",
        "## Verdict",
        md_table(verdicts),
        "## Metrics",
        md_table(compact_metrics(metrics)),
        "## Commands",
        md_table(commands),
        "",
        "## Output Files",
        "",
        "- `gate_metrics.csv`",
        "- `gate_verdict.csv`",
        "- `gate_commands.csv`",
        "- `validation_gate_report.md`",
        "",
    ]
    (args.output_dir / "validation_gate_report.md").write_text("\n".join(report), encoding="utf-8")


def run(args: argparse.Namespace, unknown_args: list[str]) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    commands = run_evaluations(args, unknown_args)
    metrics = collect_metrics(args)
    verdicts = verdict_rows(metrics, args)
    write_csv(args.output_dir / "gate_commands.csv", commands)
    write_csv(args.output_dir / "gate_metrics.csv", metrics)
    write_csv(args.output_dir / "gate_verdict.csv", verdicts)
    write_report(args, commands, metrics, verdicts)
    print(f"Wrote {args.output_dir / 'validation_gate_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-name", default="n7_combo_cold_tail")
    parser.add_argument("--output-dir", type=Path, default=Path("results/combo_candidate_validation_gate"))
    parser.add_argument("--evaluator", type=Path, default=Path("scripts/evaluate_combo_main_cold_tail.py"))
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--train-windows", default="12")
    parser.add_argument("--snapshots", default="final,1h,10h")
    parser.add_argument("--cold-snapshot", choices=("final", "1h", "10h"), default="1h")
    parser.add_argument("--cold-overlap-filter", choices=("none", "exact", "covered", "match"), default="match")
    parser.add_argument("--trigger-min-cold-candidate-matches", type=int, default=15)
    parser.add_argument("--trigger-min-q-legs", type=int, default=180)
    parser.set_defaults(include_conditional=True)
    parser.add_argument("--include-conditional", dest="include_conditional", action="store_true")
    parser.add_argument("--no-conditional", dest="include_conditional", action="store_false")
    parser.add_argument("--skip-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--min-issues", type=int, default=60)
    parser.add_argument("--min-roi", type=float, default=0.0)
    parser.add_argument("--min-loo-roi", type=float, default=0.0)
    parser.add_argument("--max-best-issue-share", type=float, default=0.50)
    parser.add_argument("--min-profitable-issue-rate", type=float, default=0.20)
    parser.add_argument("--max-dd-to-profit", type=float, default=1.50)
    args, unknown_args = parser.parse_known_args()
    run(args, unknown_args)


if __name__ == "__main__":
    main()
