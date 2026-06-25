#!/usr/bin/env python3
"""Analyze W/D/L proportion stability and prior-based probability adjustment."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_result_model_eval import OUTCOMES
from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_configs(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def prob_array(rows: list[dict[str, str]]) -> np.ndarray:
    return np.asarray([[float(r[f"p_{code}"]) for code in OUTCOMES] for r in rows], dtype=float)


def y_array(rows: list[dict[str, str]]) -> np.ndarray:
    return np.asarray([OUTCOMES.index(str(r["actual"])) for r in rows], dtype=int)


def normalize(p: np.ndarray) -> np.ndarray:
    p = np.maximum(p, 1e-12)
    return p / p.sum(axis=-1, keepdims=True)


def logloss(p: np.ndarray, y: np.ndarray) -> float:
    return float(-np.log(np.maximum(p[np.arange(len(y)), y], 1e-12)).mean())


def accuracy(p: np.ndarray, y: np.ndarray) -> float:
    return float((p.argmax(axis=1) == y).mean())


def class_rates(y: np.ndarray) -> np.ndarray:
    counts = np.asarray([(y == i).sum() for i in range(len(OUTCOMES))], dtype=float)
    return counts / counts.sum() if counts.sum() else np.ones(len(OUTCOMES)) / len(OUTCOMES)


def issue_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    out = defaultdict(list)
    for row in rows:
        out[str(row["test_issue"])].append(row)
    return dict(out)


def proportion_error(actual: np.ndarray, predicted: np.ndarray) -> tuple[float, float]:
    diff = predicted - actual
    return float(np.mean(np.abs(diff))), float(np.sqrt(np.mean(diff * diff)))


def train_prior_for_issue(
    all_by_issue: dict[str, list[dict[str, str]]],
    issues: list[str],
    issue_idx: int,
    train_issues: int,
) -> np.ndarray:
    start = max(0, issue_idx - train_issues)
    train_rows = [r for issue in issues[start:issue_idx] for r in all_by_issue[issue]]
    if not train_rows:
        return np.ones(len(OUTCOMES)) / len(OUTCOMES)
    return class_rates(y_array(train_rows))


def blend_with_prior(p: np.ndarray, prior: np.ndarray, weight: float) -> np.ndarray:
    return normalize((1.0 - weight) * p + weight * prior.reshape(1, -1))


def match_issue_prior(p: np.ndarray, target_prior: np.ndarray, max_iter: int = 80) -> np.ndarray:
    """Multiplicatively adjust per-match probabilities to match target issue prior."""
    adjusted = normalize(p.copy())
    target = np.asarray(target_prior, dtype=float)
    target = target / target.sum()
    for _ in range(max_iter):
        current = adjusted.mean(axis=0)
        factors = target / np.maximum(current, 1e-9)
        adjusted = normalize(adjusted * factors.reshape(1, -1))
    return adjusted


def evaluate_adjustments(
    rows: list[dict[str, str]],
    *,
    train_issues: int,
    blend_weights: list[float],
) -> list[dict[str, object]]:
    by_issue = issue_rows(rows)
    issues = sorted(by_issue)
    baseline_probs = []
    prior_only_probs = []
    matched_probs = []
    blend_probs = {w: [] for w in blend_weights}
    ys = []

    for idx, issue in enumerate(issues):
        rs = by_issue[issue]
        p = prob_array(rs)
        y = y_array(rs)
        prior = train_prior_for_issue(by_issue, issues, idx, train_issues)
        baseline_probs.append(p)
        prior_only_probs.append(np.tile(prior.reshape(1, -1), (len(rs), 1)))
        matched_probs.append(match_issue_prior(p, prior))
        for w in blend_weights:
            blend_probs[w].append(blend_with_prior(p, prior, w))
        ys.append(y)

    y_all = np.concatenate(ys)
    out = []
    candidates = {
        "model_raw": np.vstack(baseline_probs),
        "rolling_prior_only": np.vstack(prior_only_probs),
        "issue_prior_matched": np.vstack(matched_probs),
    }
    for w, parts in blend_probs.items():
        candidates[f"blend_prior_{w:g}"] = np.vstack(parts)

    for name, p_all in candidates.items():
        out.append(
            {
                "adjustment": name,
                "n_matches": len(y_all),
                "logloss": logloss(p_all, y_all),
                "accuracy": accuracy(p_all, y_all),
                "mean_p_3": float(p_all[:, 0].mean()),
                "mean_p_1": float(p_all[:, 1].mean()),
                "mean_p_0": float(p_all[:, 2].mean()),
            }
        )
    return sorted(out, key=lambda r: float(r["logloss"]))


def analyze_config(rows: list[dict[str, str]], config: str, train_issues: int) -> tuple[list[dict[str, object]], dict[str, object]]:
    by_issue = issue_rows(rows)
    issue_out = []
    for issue, rs in sorted(by_issue.items()):
        p = prob_array(rs)
        y = y_array(rs)
        actual = class_rates(y)
        mean_prob = p.mean(axis=0)
        top_counts = np.asarray([(p.argmax(axis=1) == i).sum() for i in range(len(OUTCOMES))], dtype=float)
        top_rate = top_counts / top_counts.sum()
        prior = train_prior_for_issue(by_issue, sorted(by_issue), sorted(by_issue).index(issue), train_issues)
        mean_prob_mae, mean_prob_rmse = proportion_error(actual, mean_prob)
        top_mae, top_rmse = proportion_error(actual, top_rate)
        prior_mae, prior_rmse = proportion_error(actual, prior)
        issue_out.append(
            {
                "config": config,
                "issue": issue,
                "n_matches": len(rs),
                "actual_3": actual[0],
                "actual_1": actual[1],
                "actual_0": actual[2],
                "mean_p_3": mean_prob[0],
                "mean_p_1": mean_prob[1],
                "mean_p_0": mean_prob[2],
                "top_pred_3": top_rate[0],
                "top_pred_1": top_rate[1],
                "top_pred_0": top_rate[2],
                "rolling_prior_3": prior[0],
                "rolling_prior_1": prior[1],
                "rolling_prior_0": prior[2],
                "mean_prob_mae": mean_prob_mae,
                "mean_prob_rmse": mean_prob_rmse,
                "top_pred_mae": top_mae,
                "top_pred_rmse": top_rmse,
                "rolling_prior_mae": prior_mae,
                "rolling_prior_rmse": prior_rmse,
            }
        )

    def avg(key: str) -> float:
        return sum(float(r[key]) for r in issue_out) / len(issue_out) if issue_out else float("nan")

    def std(key: str) -> float:
        values = np.asarray([float(r[key]) for r in issue_out], dtype=float)
        return float(values.std(ddof=1)) if len(values) > 1 else float("nan")

    y_all = y_array(rows)
    p_all = prob_array(rows)
    actual_all = class_rates(y_all)
    summary = {
        "config": config,
        "n_issues": len(issue_out),
        "n_matches": len(rows),
        "actual_all_3": actual_all[0],
        "actual_all_1": actual_all[1],
        "actual_all_0": actual_all[2],
        "mean_p_all_3": float(p_all[:, 0].mean()),
        "mean_p_all_1": float(p_all[:, 1].mean()),
        "mean_p_all_0": float(p_all[:, 2].mean()),
        "top_pred_all_3": float((p_all.argmax(axis=1) == 0).mean()),
        "top_pred_all_1": float((p_all.argmax(axis=1) == 1).mean()),
        "top_pred_all_0": float((p_all.argmax(axis=1) == 2).mean()),
        "actual_issue_std_3": std("actual_3"),
        "actual_issue_std_1": std("actual_1"),
        "actual_issue_std_0": std("actual_0"),
        "mean_prob_issue_mae": avg("mean_prob_mae"),
        "top_pred_issue_mae": avg("top_pred_mae"),
        "rolling_prior_issue_mae": avg("rolling_prior_mae"),
        "mean_prob_issue_rmse": avg("mean_prob_rmse"),
        "top_pred_issue_rmse": avg("top_pred_rmse"),
        "rolling_prior_issue_rmse": avg("rolling_prior_rmse"),
    }
    return issue_out, summary


def run(args: argparse.Namespace) -> None:
    rows = load_rows(args.prediction_rows)
    configs = parse_configs(args.configs)
    blend_weights = [float(x) for x in args.blend_weights.split(",") if x.strip()]
    all_issue_rows = []
    summaries = []
    adjustment_rows = []

    for config in configs:
        cfg_rows = [r for r in rows if r["config"] == config]
        if not cfg_rows:
            continue
        issue_out, summary = analyze_config(cfg_rows, config, args.train_issues)
        all_issue_rows.extend(issue_out)
        summaries.append(summary)
        for row in evaluate_adjustments(cfg_rows, train_issues=args.train_issues, blend_weights=blend_weights):
            row["config"] = config
            adjustment_rows.append(row)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "wdl_issue_proportions.csv", all_issue_rows)
    write_csv(out / "wdl_proportion_summary.csv", summaries)
    write_csv(out / "wdl_prior_adjustment_summary.csv", adjustment_rows)

    report = [
        "# W/D/L proportion stability and prior adjustment",
        "",
        f"- Prediction rows: `{args.prediction_rows}`",
        f"- Configs: `{args.configs}`",
        f"- Rolling train issues: `{args.train_issues}`",
        "",
        "## Proportion Summary",
        md_table(summaries),
        "## Prior Adjustment Summary",
        md_table(adjustment_rows),
        "",
        "## Files",
        "",
        "- `wdl_issue_proportions.csv`",
        "- `wdl_proportion_summary.csv`",
        "- `wdl_prior_adjustment_summary.csv`",
        "",
    ]
    (out / "wdl_proportion_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'wdl_proportion_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prediction-rows",
        type=Path,
        default=Path("results/beidan_prediction_accuracy_l2_calibration/prediction_rows.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("results/wdl_proportion_stability"))
    parser.add_argument("--configs", default="base_l20.01_blend0,kelly_l20.03_blend0,market")
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--blend-weights", default="0.05,0.1,0.2,0.3,0.5")
    args = parser.parse_args()
    if not args.prediction_rows.exists():
        raise SystemExit(f"missing prediction rows: {args.prediction_rows}")
    run(args)


if __name__ == "__main__":
    main()
