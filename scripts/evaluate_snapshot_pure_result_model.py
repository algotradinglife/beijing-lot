#!/usr/bin/env python3
"""Evaluate snapshot-pure result probability models.

The output is model-level only: logloss, top-1 accuracy, top-2 coverage and
prediction distribution.  Ticket-level use is evaluated by
``evaluate_n7_joint_uncertainty_depth.py``.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.snapshot_pure_result_model import fit_predict_snapshot_pure, snapshot_market_probabilities
from scripts.walkforward_beidan_result_model_eval import OUTCOMES, build_samples, load_match_extras, logloss
from scripts.walkforward_beidan_strategy_eval import default_db_path, load_action_rows, md_table, write_csv


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def prediction_metrics(probs: np.ndarray, y: np.ndarray) -> dict[str, object]:
    pred = np.argmax(probs, axis=1)
    top2 = np.argsort(-probs, axis=1)[:, :2]
    pred_counts = Counter(int(x) for x in pred)
    actual_counts = Counter(int(x) for x in y)
    return {
        "n_matches": int(len(y)),
        "logloss": logloss(probs, y),
        "top1_accuracy": float(np.mean(pred == y)) if len(y) else float("nan"),
        "top2_coverage": float(np.mean([int(y[i]) in set(top2[i]) for i in range(len(y))])) if len(y) else float("nan"),
        "pred_3": pred_counts.get(0, 0),
        "pred_1": pred_counts.get(1, 0),
        "pred_0": pred_counts.get(2, 0),
        "actual_3": actual_counts.get(0, 0),
        "actual_1": actual_counts.get(1, 0),
        "actual_0": actual_counts.get(2, 0),
    }


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    snapshots = parse_strings(args.snapshots)
    feature_sets = parse_strings(args.feature_sets)

    summary_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    for snapshot in snapshots:
        accum: dict[str, list[np.ndarray]] = defaultdict(list)
        y_all: list[int] = []
        for issue_idx in range(args.train_issues, len(issues)):
            test_issue = issues[issue_idx]
            train_issues = issues[issue_idx - args.train_issues : issue_idx]
            train_samples = [sample for issue in train_issues for sample in samples_by_issue.get(issue, [])]
            test_samples = samples_by_issue.get(test_issue, [])
            if len(train_samples) < args.min_train_matches or not test_samples:
                continue
            y = np.asarray([sample.y for sample in test_samples], dtype=int)
            y_all.extend(int(v) for v in y)
            market = snapshot_market_probabilities(test_samples, snapshot)
            accum[f"{snapshot_market_name(snapshot)}"].append(market)
            window_metric = prediction_metrics(market, y)
            window_metric.update(
                {
                    "snapshot": snapshot,
                    "model": snapshot_market_name(snapshot),
                    "test_issue": test_issue,
                    "train_start_issue": train_issues[0],
                    "train_end_issue": train_issues[-1],
                    "n_train_matches": len(train_samples),
                    "train_logloss": "",
                    "train_accuracy": "",
                }
            )
            window_rows.append(window_metric)

            for feature_set in feature_sets:
                probs, model = fit_predict_snapshot_pure(
                    train_samples,
                    test_samples,
                    snapshot=snapshot,
                    feature_set=feature_set,
                    l2=args.l2,
                    maxiter=args.maxiter,
                )
                name = f"{snapshot}_snapshot_pure_{feature_set}"
                accum[name].append(probs)
                window_metric = prediction_metrics(probs, y)
                window_metric.update(
                    {
                        "snapshot": snapshot,
                        "model": name,
                        "test_issue": test_issue,
                        "train_start_issue": train_issues[0],
                        "train_end_issue": train_issues[-1],
                        "n_train_matches": len(train_samples),
                        "train_logloss": model.train_logloss,
                        "train_accuracy": model.train_accuracy,
                    }
                )
                window_rows.append(window_metric)

        y_arr = np.asarray(y_all, dtype=int)
        if len(y_arr) == 0:
            continue
        for name, prob_chunks in sorted(accum.items()):
            probs = np.vstack(prob_chunks)
            row = prediction_metrics(probs, y_arr)
            row.update({"snapshot": snapshot, "model": name})
            summary_rows.append(row)

    summary_rows.sort(key=lambda r: (str(r["snapshot"]), float(r["logloss"])))
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "snapshot_pure_model_summary.csv", summary_rows)
    write_csv(out / "snapshot_pure_model_windows.csv", window_rows)
    report = [
        "# Snapshot-pure result model evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Snapshots: `{args.snapshots}`",
        f"- Feature sets: `{args.feature_sets}`",
        "",
        "## Summary",
        md_table(summary_rows),
        "",
        "## Files",
        "",
        "- `snapshot_pure_model_summary.csv`",
        "- `snapshot_pure_model_windows.csv`",
        "",
    ]
    (out / "snapshot_pure_model_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'snapshot_pure_model_report.md'}")


def snapshot_market_name(snapshot: str) -> str:
    return f"{snapshot}_snapshot_market"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/snapshot_pure_result_model"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--snapshots", default="10h,1h")
    parser.add_argument("--feature-sets", default="snapshot_priors")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--maxiter", type=int, default=120)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
