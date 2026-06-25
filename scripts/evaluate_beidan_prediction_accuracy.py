#!/usr/bin/env python3
"""Compare Beidan single-match result prediction models walk-forward.

This script focuses on prediction quality only. It evaluates model feature
sets, regularization strengths, and optional blending with market probabilities
on the same rolling issue windows used by the betting strategy backtests.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_result_model_eval import (
    OUTCOMES,
    accuracy,
    build_samples,
    feature_tensor,
    fit_model,
    load_match_extras,
    logloss,
    market_probs,
    predict_proba,
)
from scripts.walkforward_beidan_strategy_eval import (
    default_db_path,
    load_action_rows,
    md_table,
    write_csv,
)


def parse_csv_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def parse_csv_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def prediction_rows(
    *,
    config: str,
    feature_set: str,
    l2: float,
    blend_market_weight: float,
    test_issue: str,
    train_start_issue: str,
    train_end_issue: str,
    samples,
    probs: np.ndarray,
    market: np.ndarray,
) -> list[dict[str, object]]:
    rows = []
    for sample, p_row, m_row in zip(samples, probs, market):
        y = int(sample.y)
        ranked = sorted(range(3), key=lambda i: float(p_row[i]), reverse=True)
        market_ranked = sorted(range(3), key=lambda i: float(m_row[i]), reverse=True)
        top = ranked[0]
        second = ranked[1]
        top2_hit = int(y in ranked[:2])
        rows.append(
            {
                "config": config,
                "feature_set": feature_set,
                "l2": l2,
                "blend_market_weight": blend_market_weight,
                "test_issue": test_issue,
                "train_start_issue": train_start_issue,
                "train_end_issue": train_end_issue,
                "match_id": sample.match_id,
                "match_idx": sample.rows["3"].match_idx,
                "league": sample.rows["3"].league,
                "hcp": sample.rows["3"].hcp,
                "actual": OUTCOMES[y],
                "pred": OUTCOMES[top],
                "hit": int(top == y),
                "top2_hit": top2_hit,
                "top_p": float(p_row[top]),
                "second_p": float(p_row[second]),
                "margin": float(p_row[top] - p_row[second]),
                "p_3": float(p_row[0]),
                "p_1": float(p_row[1]),
                "p_0": float(p_row[2]),
                "market_pred": OUTCOMES[market_ranked[0]],
                "market_hit": int(market_ranked[0] == y),
                "market_top_p": float(m_row[market_ranked[0]]),
                "market_margin": float(m_row[market_ranked[0]] - m_row[market_ranked[1]]),
            }
        )
    return rows


def summarize_predictions(rows: list[dict[str, object]]) -> dict[str, object]:
    n = len(rows)
    if n == 0:
        return {}
    y = np.asarray([OUTCOMES.index(str(r["actual"])) for r in rows], dtype=int)
    probs = np.asarray([[float(r[f"p_{code}"]) for code in OUTCOMES] for r in rows], dtype=float)
    hits = sum(int(r["hit"]) for r in rows)
    top2_hits = sum(int(r["top2_hit"]) for r in rows)
    one_hot = np.zeros_like(probs)
    one_hot[np.arange(n), y] = 1.0
    brier = float(np.mean(np.sum((probs - one_hot) ** 2, axis=1)))
    by_issue = defaultdict(lambda: [0, 0])
    for r in rows:
        by_issue[str(r["test_issue"])][0] += int(r["hit"])
        by_issue[str(r["test_issue"])][1] += 1
    issue_accs = [hit / total for hit, total in by_issue.values() if total]
    first = rows[0]
    return {
        "config": first["config"],
        "feature_set": first["feature_set"],
        "l2": first["l2"],
        "blend_market_weight": first["blend_market_weight"],
        "n_matches": n,
        "logloss": logloss(probs, y),
        "brier": brier,
        "accuracy": hits / n,
        "top2_accuracy": top2_hits / n,
        "avg_top_p": sum(float(r["top_p"]) for r in rows) / n,
        "avg_margin": sum(float(r["margin"]) for r in rows) / n,
        "issue_accuracy_mean": sum(issue_accs) / len(issue_accs) if issue_accs else float("nan"),
    }


def calibration_summary(rows: list[dict[str, object]], bin_width: float = 0.1) -> list[dict[str, object]]:
    first = rows[0]
    bins = []
    start = 0.0
    while start < 1.0:
        end = min(1.0, start + bin_width)
        bins.append((start, end))
        start = end

    out = []
    for lo, hi in bins:
        selected = []
        for r in rows:
            actual = str(r["actual"])
            for code in OUTCOMES:
                p = float(r[f"p_{code}"])
                if p >= lo and (p < hi or (hi == 1.0 and p <= hi)):
                    selected.append((p, int(actual == code)))
        n = len(selected)
        if n:
            avg_p = sum(p for p, _ in selected) / n
            obs = sum(hit for _, hit in selected) / n
        else:
            avg_p = float("nan")
            obs = float("nan")
        out.append(
            {
                "config": first["config"],
                "view": "all_outcome_probs",
                "bin": f"{lo:.1f}-{hi:.1f}",
                "n": n,
                "avg_p": avg_p,
                "observed_rate": obs,
                "calibration_error": obs - avg_p if n else float("nan"),
            }
        )

    for lo, hi in bins:
        selected = [
            (float(r["top_p"]), int(r["hit"]))
            for r in rows
            if float(r["top_p"]) >= lo and (float(r["top_p"]) < hi or (hi == 1.0 and float(r["top_p"]) <= hi))
        ]
        n = len(selected)
        if n:
            avg_p = sum(p for p, _ in selected) / n
            obs = sum(hit for _, hit in selected) / n
        else:
            avg_p = float("nan")
            obs = float("nan")
        out.append(
            {
                "config": first["config"],
                "view": "top_pred_probs",
                "bin": f"{lo:.1f}-{hi:.1f}",
                "n": n,
                "avg_p": avg_p,
                "observed_rate": obs,
                "calibration_error": obs - avg_p if n else float("nan"),
            }
        )
    return out


def confidence_summary(rows: list[dict[str, object]], top_p_thresholds: list[float], margin_thresholds: list[float]) -> list[dict[str, object]]:
    out = []
    for threshold in top_p_thresholds:
        selected = [r for r in rows if float(r["top_p"]) >= threshold]
        out.append(confidence_row(rows, selected, f"top_p>={threshold:g}"))
    for threshold in margin_thresholds:
        selected = [r for r in rows if float(r["margin"]) >= threshold]
        out.append(confidence_row(rows, selected, f"margin>={threshold:g}"))
    return out


def confidence_row(all_rows: list[dict[str, object]], selected: list[dict[str, object]], rule: str) -> dict[str, object]:
    first = all_rows[0]
    n_all = len(all_rows)
    n = len(selected)
    hits = sum(int(r["hit"]) for r in selected)
    top2_hits = sum(int(r["top2_hit"]) for r in selected)
    return {
        "config": first["config"],
        "rule": rule,
        "n_selected": n,
        "coverage": n / n_all if n_all else float("nan"),
        "accuracy": hits / n if n else float("nan"),
        "top2_accuracy": top2_hits / n if n else float("nan"),
        "avg_top_p": sum(float(r["top_p"]) for r in selected) / n if n else float("nan"),
        "avg_margin": sum(float(r["margin"]) for r in selected) / n if n else float("nan"),
    }


def deletion_summary(rows: list[dict[str, object]], thresholds: list[float]) -> list[dict[str, object]]:
    out = []
    first = rows[0]
    n_matches = len(rows)
    for threshold in thresholds:
        n_deleted = 0
        false_delete = 0
        by_outcome = defaultdict(lambda: [0, 0])
        for r in rows:
            actual = str(r["actual"])
            for code in OUTCOMES:
                if float(r[f"p_{code}"]) <= threshold:
                    n_deleted += 1
                    by_outcome[code][1] += 1
                    if actual == code:
                        false_delete += 1
                        by_outcome[code][0] += 1
        out.append(
            {
                "config": first["config"],
                "rule": f"p_outcome<={threshold:g}",
                "n_deleted_outcomes": n_deleted,
                "deleted_outcomes_per_match": n_deleted / n_matches if n_matches else float("nan"),
                "false_delete_rate": false_delete / n_deleted if n_deleted else float("nan"),
                "false_deletes": false_delete,
                "false_delete_3": by_outcome["3"][0] / by_outcome["3"][1] if by_outcome["3"][1] else float("nan"),
                "false_delete_1": by_outcome["1"][0] / by_outcome["1"][1] if by_outcome["1"][1] else float("nan"),
                "false_delete_0": by_outcome["0"][0] / by_outcome["0"][1] if by_outcome["0"][1] else float("nan"),
            }
        )
    return out


def outcome_accuracy(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    first = rows[0]
    out = []
    for pred_code in OUTCOMES:
        selected = [r for r in rows if str(r["pred"]) == pred_code]
        n = len(selected)
        out.append(
            {
                "config": first["config"],
                "pred": pred_code,
                "n_pred": n,
                "coverage": n / len(rows) if rows else float("nan"),
                "accuracy": sum(int(r["hit"]) for r in selected) / n if n else float("nan"),
                "avg_top_p": sum(float(r["top_p"]) for r in selected) / n if n else float("nan"),
                "actual_3_rate": sum(1 for r in selected if r["actual"] == "3") / n if n else float("nan"),
                "actual_1_rate": sum(1 for r in selected if r["actual"] == "1") / n if n else float("nan"),
                "actual_0_rate": sum(1 for r in selected if r["actual"] == "0") / n if n else float("nan"),
            }
        )
    return out


def compact_top(rows: list[dict[str, object]], key: str, n: int = 12, reverse: bool = True) -> list[dict[str, object]]:
    return sorted(rows, key=lambda r: float(r[key]) if str(r[key]) else float("nan"), reverse=reverse)[:n]


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    extras = load_match_extras(args.db, args.min_year)
    samples = build_samples(action_rows, extras)
    by_issue = group_samples_by_issue(samples)
    issues = sorted(by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    feature_sets = parse_csv_strings(args.feature_sets)
    l2_values = parse_csv_floats(args.l2_values)
    blend_weights = parse_csv_floats(args.blend_market_weights)
    top_p_thresholds = parse_csv_floats(args.top_p_thresholds)
    margin_thresholds = parse_csv_floats(args.margin_thresholds)
    deletion_thresholds = parse_csv_floats(args.deletion_thresholds)

    rows_by_config: dict[str, list[dict[str, object]]] = defaultdict(list)
    window_rows: list[dict[str, object]] = []

    for feature_set in feature_sets:
        for l2 in l2_values:
            model_config = f"{feature_set}_l2{l2:g}"
            for issue_idx in range(args.train_issues, len(issues)):
                test_issue = issues[issue_idx]
                train_issues = issues[issue_idx - args.train_issues:issue_idx]
                train_samples = [s for issue in train_issues for s in by_issue[issue]]
                test_samples = by_issue[test_issue]
                if len(train_samples) < args.min_train_matches:
                    continue
                model = fit_model(train_samples, l2=l2, maxiter=args.maxiter, feature_set=feature_set)
                model_probs = predict_proba(test_samples, model)
                market = market_probs(test_samples)
                _, y_test = feature_tensor(test_samples, model.ctx, model.feature_set)
                window_rows.append(
                    {
                        "model_config": model_config,
                        "test_issue": test_issue,
                        "train_start_issue": train_issues[0],
                        "train_end_issue": train_issues[-1],
                        "n_train_matches": len(train_samples),
                        "n_test_matches": len(test_samples),
                        "train_logloss": model.train_logloss,
                        "train_accuracy": model.train_accuracy,
                        "model_logloss": logloss(model_probs, y_test),
                        "market_logloss": logloss(market, y_test),
                        "model_accuracy": accuracy(model_probs, y_test),
                        "market_accuracy": accuracy(market, y_test),
                    }
                )
                for blend in blend_weights:
                    probs = (1.0 - blend) * model_probs + blend * market
                    probs = probs / probs.sum(axis=1, keepdims=True)
                    config = f"{feature_set}_l2{l2:g}_blend{blend:g}"
                    rows_by_config[config].extend(
                        prediction_rows(
                            config=config,
                            feature_set=feature_set,
                            l2=l2,
                            blend_market_weight=blend,
                            test_issue=test_issue,
                            train_start_issue=train_issues[0],
                            train_end_issue=train_issues[-1],
                            samples=test_samples,
                            probs=probs,
                            market=market,
                        )
                    )

    if args.include_market_baseline and rows_by_config:
        market_rows = []
        # Reuse the train/test issue structure so the market baseline has the
        # same eligible sample set as the model configs.
        for issue_idx in range(args.train_issues, len(issues)):
            test_issue = issues[issue_idx]
            train_issues = issues[issue_idx - args.train_issues:issue_idx]
            train_samples = [s for issue in train_issues for s in by_issue[issue]]
            if len(train_samples) < args.min_train_matches:
                continue
            test_samples = by_issue[test_issue]
            market = market_probs(test_samples)
            market_rows.extend(
                prediction_rows(
                    config="market",
                    feature_set="market",
                    l2=0.0,
                    blend_market_weight=1.0,
                    test_issue=test_issue,
                    train_start_issue=train_issues[0],
                    train_end_issue=train_issues[-1],
                    samples=test_samples,
                    probs=market,
                    market=market,
                )
            )
        rows_by_config["market"] = market_rows

    prediction_all = [row for rows in rows_by_config.values() for row in rows]
    summary_rows = [summarize_predictions(rows) for rows in rows_by_config.values() if rows]
    summary_rows.sort(key=lambda r: (float(r["accuracy"]), -float(r["logloss"])), reverse=True)

    confidence_rows = []
    deletion_rows = []
    outcome_rows = []
    calibration_rows = []
    for _, rows in sorted(rows_by_config.items()):
        confidence_rows.extend(confidence_summary(rows, top_p_thresholds, margin_thresholds))
        deletion_rows.extend(deletion_summary(rows, deletion_thresholds))
        outcome_rows.extend(outcome_accuracy(rows))
        calibration_rows.extend(calibration_summary(rows))

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "prediction_rows.csv", prediction_all)
    write_csv(out / "prediction_summary.csv", summary_rows)
    write_csv(out / "confidence_summary.csv", confidence_rows)
    write_csv(out / "deletion_summary.csv", deletion_rows)
    write_csv(out / "outcome_accuracy.csv", outcome_rows)
    write_csv(out / "calibration_summary.csv", calibration_rows)
    write_csv(out / "window_metrics.csv", window_rows)

    best_config = summary_rows[0]["config"] if summary_rows else ""
    best_conf = [r for r in confidence_rows if r["config"] == best_config]
    best_delete = [r for r in deletion_rows if r["config"] == best_config]
    best_calibration = [r for r in calibration_rows if r["config"] == best_config]
    report = [
        "# Beidan result prediction accuracy",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Feature sets: `{args.feature_sets}`",
        f"- L2 values: `{args.l2_values}`",
        f"- Blend market weights: `{args.blend_market_weights}`",
        f"- Max iterations: `{args.maxiter}`",
        "",
        "## Overall Summary",
        md_table(summary_rows),
        "## Best Config Confidence",
        md_table(best_conf),
        "## Best Config Deletion",
        md_table(best_delete),
        "## Best Config Calibration",
        md_table(best_calibration),
        "## Outcome Accuracy",
        md_table([r for r in outcome_rows if r["config"] == best_config]),
        "",
        "## Files",
        "",
        "- `prediction_summary.csv`",
        "- `confidence_summary.csv`",
        "- `deletion_summary.csv`",
        "- `calibration_summary.csv`",
        "- `outcome_accuracy.csv`",
        "- `prediction_rows.csv`",
        "- `window_metrics.csv`",
        "",
    ]
    (out / "prediction_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'prediction_report.md'}")
    print(f"Wrote {len(prediction_all)} prediction rows across {len(rows_by_config)} configs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/beidan_prediction_accuracy"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--feature-sets", default="base,kelly,priors,rich")
    parser.add_argument("--l2-values", default="0.03")
    parser.add_argument("--blend-market-weights", default="0,0.15,0.3")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--top-p-thresholds", default="0.38,0.42,0.46,0.5,0.55,0.6")
    parser.add_argument("--margin-thresholds", default="0.03,0.06,0.1,0.15,0.2")
    parser.add_argument("--deletion-thresholds", default="0.08,0.1,0.12,0.15,0.2")
    parser.add_argument("--include-market-baseline", action="store_true", default=True)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
