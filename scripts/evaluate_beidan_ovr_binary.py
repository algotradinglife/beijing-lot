#!/usr/bin/env python3
"""Evaluate one-vs-rest binary result models against multinomial baselines."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_beidan_draw_binary import (
    average_precision,
    binary_logloss,
    brier as binary_brier,
    fit_logistic,
    rank_auc,
)
from scripts.walkforward_beidan_result_model_eval import (
    OUTCOMES,
    accuracy,
    build_feature_context,
    build_samples,
    feature_tensor,
    fit_model,
    load_match_extras,
    logloss,
    market_probs,
    predict_proba,
    row_features,
)
from scripts.walkforward_beidan_strategy_eval import default_db_path, load_action_rows, md_table, write_csv


def parse_csv_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def parse_csv_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def normalize(probs: np.ndarray) -> np.ndarray:
    probs = np.clip(np.asarray(probs, dtype=float), 1e-9, 1.0)
    return probs / probs.sum(axis=1, keepdims=True)


def multiclass_brier(probs: np.ndarray, y: np.ndarray) -> float:
    one_hot = np.zeros_like(probs)
    one_hot[np.arange(len(y)), y] = 1.0
    return float(np.mean(np.sum((probs - one_hot) ** 2, axis=1)))


def top2_accuracy(probs: np.ndarray, y: np.ndarray) -> float:
    ranked = np.argsort(-probs, axis=1)[:, :2]
    return float(np.mean([int(y_i in ranked_i) for y_i, ranked_i in zip(y, ranked)]))


def action_matrix(samples, ctx, feature_set: str, outcome_idx: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    x_rows = []
    y_rows = []
    for sample in samples:
        indexes = range(len(OUTCOMES)) if outcome_idx is None else [outcome_idx]
        for idx in indexes:
            code = OUTCOMES[idx]
            x_rows.append(row_features(sample.rows[code], idx, sample, ctx, feature_set))
            y_rows.append(1 if sample.y == idx else 0)
    return np.asarray(x_rows, dtype=float), np.asarray(y_rows, dtype=int)


def fit_ovr_shared(train_samples, test_samples, ctx, feature_set: str, l2: float, class_weight: str) -> tuple[np.ndarray, np.ndarray]:
    x_train, y_train = action_matrix(train_samples, ctx, feature_set)
    x_test, _ = action_matrix(test_samples, ctx, feature_set)
    _, train_p_flat, test_p_flat = fit_logistic(x_train, y_train, x_test, l2=l2, class_weight=class_weight)
    return train_p_flat.reshape(len(train_samples), 3), test_p_flat.reshape(len(test_samples), 3)


def fit_ovr_separate(train_samples, test_samples, ctx, feature_set: str, l2: float, class_weight: str) -> tuple[np.ndarray, np.ndarray]:
    train_cols = []
    test_cols = []
    for idx in range(3):
        x_train, y_train = action_matrix(train_samples, ctx, feature_set, outcome_idx=idx)
        x_test, _ = action_matrix(test_samples, ctx, feature_set, outcome_idx=idx)
        _, train_p, test_p = fit_logistic(x_train, y_train, x_test, l2=l2, class_weight=class_weight)
        train_cols.append(train_p)
        test_cols.append(test_p)
    return np.vstack(train_cols).T, np.vstack(test_cols).T


def result_summary(config: str, probs: np.ndarray, y: np.ndarray, raw_probs: np.ndarray | None = None) -> dict[str, object]:
    raw = raw_probs if raw_probs is not None else probs
    return {
        "config": config,
        "n_matches": len(y),
        "logloss": logloss(probs, y),
        "brier": multiclass_brier(probs, y),
        "accuracy": accuracy(probs, y),
        "top2_accuracy": top2_accuracy(probs, y),
        "pred_3_rate": float(np.mean(probs.argmax(axis=1) == 0)),
        "pred_1_rate": float(np.mean(probs.argmax(axis=1) == 1)),
        "pred_0_rate": float(np.mean(probs.argmax(axis=1) == 2)),
        "avg_p_3": float(probs[:, 0].mean()),
        "avg_p_1": float(probs[:, 1].mean()),
        "avg_p_0": float(probs[:, 2].mean()),
        "avg_raw_sum": float(raw.sum(axis=1).mean()),
    }


def outcome_binary_rows(config: str, probs: np.ndarray, y: np.ndarray) -> list[dict[str, object]]:
    out = []
    for idx, code in enumerate(OUTCOMES):
        labels = (y == idx).astype(int)
        p = np.clip(probs[:, idx], 1e-9, 1 - 1e-9)
        out.append(
            {
                "config": config,
                "outcome": code,
                "base_rate": float(labels.mean()),
                "logloss": binary_logloss(p, labels),
                "brier": binary_brier(p, labels),
                "roc_auc": rank_auc(p, labels),
                "average_precision": average_precision(p, labels),
                "avg_p": float(p.mean()),
                "precision_at_p40": precision_at(p, labels, 0.40),
                "recall_at_p40": recall_at(p, labels, 0.40),
                "precision_at_p50": precision_at(p, labels, 0.50),
                "recall_at_p50": recall_at(p, labels, 0.50),
            }
        )
    return out


def action_binary_summary(config: str, raw_probs: np.ndarray, y: np.ndarray) -> dict[str, object]:
    labels = np.zeros_like(raw_probs, dtype=int)
    labels[np.arange(len(y)), y] = 1
    p = np.clip(raw_probs.reshape(-1), 1e-9, 1 - 1e-9)
    yy = labels.reshape(-1)
    return {
        "config": config,
        "n_actions": len(yy),
        "hit_rate": float(yy.mean()),
        "logloss": binary_logloss(p, yy),
        "brier": binary_brier(p, yy),
        "roc_auc": rank_auc(p, yy),
        "average_precision": average_precision(p, yy),
        "avg_p": float(p.mean()),
    }


def precision_at(p: np.ndarray, y: np.ndarray, threshold: float) -> float:
    mask = p >= threshold
    return float(y[mask].mean()) if mask.any() else float("nan")


def recall_at(p: np.ndarray, y: np.ndarray, threshold: float) -> float:
    positives = y.sum()
    return float(y[p >= threshold].sum() / positives) if positives else float("nan")


def append_prediction_rows(rows: list[dict[str, object]], config: str, samples, probs: np.ndarray, raw_probs: np.ndarray | None = None) -> None:
    raw = raw_probs if raw_probs is not None else probs
    for sample, p, raw_p in zip(samples, probs, raw):
        pred = int(np.argmax(p))
        rows.append(
            {
                "config": config,
                "issue": sample.issue,
                "match_id": sample.match_id,
                "match_idx": sample.rows["3"].match_idx,
                "league": sample.rows["3"].league,
                "hcp": sample.rows["3"].hcp,
                "actual": OUTCOMES[sample.y],
                "pred": OUTCOMES[pred],
                "hit": int(pred == sample.y),
                "p_3": float(p[0]),
                "p_1": float(p[1]),
                "p_0": float(p[2]),
                "raw_p_3": float(raw_p[0]),
                "raw_p_1": float(raw_p[1]),
                "raw_p_0": float(raw_p[2]),
                "raw_sum": float(raw_p.sum()),
            }
        )


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    by_issue = group_samples_by_issue(samples)
    issues = sorted(by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    feature_sets = parse_csv_strings(args.feature_sets)
    l2_values = parse_csv_floats(args.l2_values)
    modes = parse_csv_strings(args.modes)

    probs_by_config: dict[str, list[np.ndarray]] = defaultdict(list)
    raw_by_config: dict[str, list[np.ndarray]] = defaultdict(list)
    y_chunks: list[np.ndarray] = []
    prediction_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues:issue_idx]
        train_samples = [s for issue in train_issues for s in by_issue[issue]]
        test_samples = by_issue[test_issue]
        if len(train_samples) < args.min_train_matches:
            continue
        y_test = np.asarray([s.y for s in test_samples], dtype=int)
        y_chunks.append(y_test)

        market = market_probs(test_samples)
        probs_by_config["market"].append(market)
        raw_by_config["market"].append(market)
        append_prediction_rows(prediction_rows, "market", test_samples, market)

        ctx = build_feature_context(train_samples)
        for feature_set in feature_sets:
            for l2 in l2_values:
                multinomial = fit_model(train_samples, l2=l2, maxiter=args.maxiter, feature_set=feature_set)
                m_probs = predict_proba(test_samples, multinomial)
                m_config = f"multinomial_{feature_set}_l2{l2:g}"
                probs_by_config[m_config].append(m_probs)
                raw_by_config[m_config].append(m_probs)
                append_prediction_rows(prediction_rows, m_config, test_samples, m_probs)

                for mode in modes:
                    if mode == "shared":
                        train_raw, test_raw = fit_ovr_shared(
                            train_samples,
                            test_samples,
                            ctx,
                            feature_set,
                            l2,
                            args.class_weight,
                        )
                    elif mode == "separate":
                        train_raw, test_raw = fit_ovr_separate(
                            train_samples,
                            test_samples,
                            ctx,
                            feature_set,
                            l2,
                            args.class_weight,
                        )
                    else:
                        raise ValueError(f"unsupported mode: {mode}")
                    probs = normalize(test_raw)
                    config = f"ovr_{mode}_{feature_set}_l2{l2:g}_{args.class_weight}"
                    probs_by_config[config].append(probs)
                    raw_by_config[config].append(test_raw)
                    append_prediction_rows(prediction_rows, config, test_samples, probs, test_raw)

                    window_rows.append(
                        {
                            "config": config,
                            "test_issue": test_issue,
                            "train_start_issue": train_issues[0],
                            "train_end_issue": train_issues[-1],
                            "n_train_matches": len(train_samples),
                            "n_test_matches": len(test_samples),
                            "train_raw_sum": float(train_raw.sum(axis=1).mean()),
                            "test_raw_sum": float(test_raw.sum(axis=1).mean()),
                        }
                    )

    y_all = np.concatenate(y_chunks)
    result_rows = []
    outcome_rows = []
    action_rows_out = []
    for config in sorted(probs_by_config):
        probs = normalize(np.vstack(probs_by_config[config]))
        raw = np.vstack(raw_by_config[config])
        result_rows.append(result_summary(config, probs, y_all, raw))
        outcome_rows.extend(outcome_binary_rows(config, probs, y_all))
        action_rows_out.append(action_binary_summary(config, raw, y_all))

    result_rows.sort(key=lambda r: (float(r["accuracy"]), -float(r["logloss"])), reverse=True)
    outcome_rows.sort(key=lambda r: (str(r["outcome"]), float(r["average_precision"])), reverse=True)
    action_rows_out.sort(key=lambda r: (float(r["average_precision"]), -float(r["logloss"])), reverse=True)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "ovr_prediction_rows.csv", prediction_rows)
    write_csv(out / "ovr_result_summary.csv", result_rows)
    write_csv(out / "ovr_outcome_binary_summary.csv", outcome_rows)
    write_csv(out / "ovr_action_binary_summary.csv", action_rows_out)
    write_csv(out / "ovr_windows.csv", window_rows)

    report = [
        "# Beidan one-vs-rest binary result evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Feature sets: `{args.feature_sets}`",
        f"- L2 values: `{args.l2_values}`",
        f"- Modes: `{args.modes}`",
        f"- Class weight: `{args.class_weight}`",
        "",
        "## Result Summary",
        md_table(result_rows),
        "## Action-Level Binary Summary",
        md_table(action_rows_out),
        "## Outcome Binary Summary",
        md_table(outcome_rows),
        "",
        "## Files",
        "",
        "- `ovr_result_summary.csv`",
        "- `ovr_outcome_binary_summary.csv`",
        "- `ovr_action_binary_summary.csv`",
        "- `ovr_prediction_rows.csv`",
        "- `ovr_windows.csv`",
        "",
    ]
    (out / "ovr_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'ovr_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/beidan_ovr_binary"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--feature-sets", default="base,kelly")
    parser.add_argument("--l2-values", default="0.01,0.03")
    parser.add_argument("--modes", default="shared,separate")
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--maxiter", type=int, default=120)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
