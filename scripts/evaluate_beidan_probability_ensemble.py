#!/usr/bin/env python3
"""Walk-forward probability ensembles for Beidan result and draw prediction."""
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

from scripts.evaluate_beidan_draw_binary import (
    DRAW_INDEX,
    average_precision,
    binary_logloss,
    brier as binary_brier,
    feature_matrix as draw_feature_matrix,
    fit_logistic as fit_draw_logistic,
    load_team_form_extras,
    merge_extras,
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
)
from scripts.walkforward_beidan_strategy_eval import default_db_path, load_action_rows, md_table, write_csv


def parse_source_models(raw: str) -> list[tuple[str, float]]:
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"source model must be feature_set:l2, got {part!r}")
        feature_set, l2 = part.split(":", 1)
        out.append((feature_set.strip(), float(l2)))
    return out


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def normalize_probs(probs: np.ndarray) -> np.ndarray:
    probs = np.clip(np.asarray(probs, dtype=float), 1e-9, 1.0)
    return probs / probs.sum(axis=1, keepdims=True)


def multiclass_brier(probs: np.ndarray, y: np.ndarray) -> float:
    one_hot = np.zeros_like(probs)
    one_hot[np.arange(len(y)), y] = 1.0
    return float(np.mean(np.sum((probs - one_hot) ** 2, axis=1)))


def top2_accuracy(probs: np.ndarray, y: np.ndarray) -> float:
    ranked = np.argsort(-probs, axis=1)[:, :2]
    return float(np.mean([int(y_i in ranked_i) for y_i, ranked_i in zip(y, ranked)]))


def entropy(row: np.ndarray) -> float:
    row = np.clip(row, 1e-12, 1.0)
    return float(-np.sum(row * np.log(row)))


def safe_extra(sample, key: str, default: float = 0.0) -> float:
    try:
        value = float(sample.extras.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def simplex_weights(n: int, step: float) -> list[np.ndarray]:
    units = int(round(1.0 / step))
    out: list[np.ndarray] = []

    def rec(prefix: list[int], remaining: int, slots: int) -> None:
        if slots == 1:
            out.append(np.asarray(prefix + [remaining], dtype=float) / units)
            return
        for value in range(remaining + 1):
            rec(prefix + [value], remaining - value, slots - 1)

    rec([], units, n)
    return out


def weighted_probs(source_probs: list[np.ndarray], weights: np.ndarray) -> np.ndarray:
    out = np.zeros_like(source_probs[0])
    for weight, probs in zip(weights, source_probs):
        out += float(weight) * probs
    return normalize_probs(out)


def best_train_weights(source_probs: list[np.ndarray], y: np.ndarray, grid: list[np.ndarray]) -> np.ndarray:
    best_w = grid[0]
    best_loss = float("inf")
    for weights in grid:
        loss = logloss(weighted_probs(source_probs, weights), y)
        if loss < best_loss:
            best_loss = loss
            best_w = weights
    return best_w


def best_train_draw_weights(source_probs: list[np.ndarray], y: np.ndarray, grid: list[np.ndarray], *, metric: str) -> np.ndarray:
    best_w = grid[0]
    best_score = float("inf") if metric == "logloss" else -float("inf")
    for weights in grid:
        p = np.zeros_like(source_probs[0])
        for weight, probs in zip(weights, source_probs):
            p += float(weight) * probs
        p = np.clip(p, 1e-9, 1 - 1e-9)
        if metric == "logloss":
            score = binary_logloss(p, y)
            if score < best_score:
                best_score = score
                best_w = weights
        elif metric == "ap":
            score = average_precision(p, y)
            if score > best_score:
                best_score = score
                best_w = weights
        else:
            raise ValueError(f"unsupported draw weight metric: {metric}")
    return best_w


def weighted_draw_probs(source_probs: list[np.ndarray], weights: np.ndarray) -> np.ndarray:
    out = np.zeros_like(source_probs[0])
    for weight, probs in zip(weights, source_probs):
        out += float(weight) * probs
    return np.clip(out, 1e-9, 1 - 1e-9)


def result_summary(config: str, probs: np.ndarray, y: np.ndarray) -> dict[str, object]:
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
    }


def draw_summary(config: str, p_draw: np.ndarray, y: np.ndarray) -> dict[str, object]:
    draw_y = (y == DRAW_INDEX).astype(int)
    return {
        "config": config,
        "n_matches": len(y),
        "draw_rate": float(draw_y.mean()),
        "logloss": binary_logloss(p_draw, draw_y),
        "brier": binary_brier(p_draw, draw_y),
        "roc_auc": rank_auc(p_draw, draw_y),
        "average_precision": average_precision(p_draw, draw_y),
        "avg_p_draw": float(np.mean(p_draw)),
        "precision_at_p30": precision_at_threshold(p_draw, draw_y, 0.30),
        "recall_at_p30": recall_at_threshold(p_draw, draw_y, 0.30),
        "precision_at_p35": precision_at_threshold(p_draw, draw_y, 0.35),
        "recall_at_p35": recall_at_threshold(p_draw, draw_y, 0.35),
    }


def precision_at_threshold(p: np.ndarray, y: np.ndarray, threshold: float) -> float:
    mask = p >= threshold
    return float(y[mask].mean()) if mask.any() else float("nan")


def recall_at_threshold(p: np.ndarray, y: np.ndarray, threshold: float) -> float:
    positives = y.sum()
    if positives <= 0:
        return float("nan")
    return float(y[p >= threshold].sum() / positives)


def draw_meta_features(samples, source_probs: dict[str, np.ndarray], binary_draw: np.ndarray) -> np.ndarray:
    market = source_probs["market"]
    columns = [
        market[:, DRAW_INDEX],
        np.abs(market[:, 0] - market[:, 2]),
        np.asarray([entropy(row) for row in market], dtype=float),
        binary_draw,
    ]
    for name, probs in sorted(source_probs.items()):
        columns.append(probs[:, DRAW_INDEX])
        columns.append(probs[:, DRAW_INDEX] / np.maximum(probs[:, 0] + probs[:, 2], 1e-9))
    columns.extend(
        [
            np.asarray([safe_extra(s, "is_cup_like", 0.0) for s in samples], dtype=float),
            np.asarray([safe_extra(s, "combined_recent_draw_rate_10", 0.276) for s in samples], dtype=float),
            np.asarray([safe_extra(s, "combined_recent_low_total_rate_10", 0.50) for s in samples], dtype=float),
            np.asarray([safe_extra(s, "combined_recent_avg_abs_gd_10", 1.25) for s in samples], dtype=float),
            np.asarray([safe_extra(s, "league_prior_draw_rate", 0.276) for s in samples], dtype=float),
        ]
    )
    return np.vstack(columns).T


def append_prediction_rows(rows: list[dict[str, object]], config: str, samples, probs: np.ndarray) -> None:
    for sample, row in zip(samples, probs):
        pred = int(np.argmax(row))
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
                "p_3": float(row[0]),
                "p_1": float(row[1]),
                "p_0": float(row[2]),
            }
        )


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    base_extras = load_match_extras(args.db, args.min_year)
    form_extras = load_team_form_extras(args.db, args.min_year)
    samples = build_samples(action_rows, merge_extras(base_extras, form_extras))
    by_issue = group_samples_by_issue(samples)
    issues = sorted(by_issue)
    source_models = parse_source_models(args.source_models)
    weight_grid = simplex_weights(1 + len(source_models), args.weight_step)
    draw_weight_grid = simplex_weights(2 + len(source_models), args.weight_step)

    result_probs_by_config: dict[str, list[np.ndarray]] = defaultdict(list)
    result_y: list[np.ndarray] = []
    draw_probs_by_config: dict[str, list[np.ndarray]] = defaultdict(list)
    draw_stack_probs: list[np.ndarray] = []
    prediction_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues:issue_idx]
        train_samples = [s for issue in train_issues for s in by_issue[issue]]
        test_samples = by_issue[test_issue]
        if len(train_samples) < args.min_train_matches:
            continue

        train_y = np.asarray([s.y for s in train_samples], dtype=int)
        test_y = np.asarray([s.y for s in test_samples], dtype=int)
        result_y.append(test_y)

        train_sources: dict[str, np.ndarray] = {"market": market_probs(train_samples)}
        test_sources: dict[str, np.ndarray] = {"market": market_probs(test_samples)}

        for feature_set, l2 in source_models:
            model = fit_model(train_samples, l2=l2, maxiter=args.maxiter, feature_set=feature_set)
            name = f"{feature_set}_l2{l2:g}"
            train_sources[name] = predict_proba(train_samples, model)
            test_sources[name] = predict_proba(test_samples, model)

        source_names = list(train_sources)
        train_source_list = [train_sources[name] for name in source_names]
        test_source_list = [test_sources[name] for name in source_names]
        best_w = best_train_weights(train_source_list, train_y, weight_grid)

        fixed_configs: dict[str, np.ndarray] = {}
        for name in source_names:
            fixed_configs[name] = test_sources[name]
        model_names = [name for name in source_names if name != "market"]
        fixed_configs["avg_models"] = weighted_probs(
            [test_sources[name] for name in model_names],
            np.ones(len(model_names), dtype=float) / len(model_names),
        )
        fixed_configs["avg_market_models"] = weighted_probs(
            test_source_list,
            np.ones(len(test_source_list), dtype=float) / len(test_source_list),
        )
        fixed_configs["tuned_simplex"] = weighted_probs(test_source_list, best_w)

        ctx = build_feature_context(train_samples)
        x_train, y_train_draw = draw_feature_matrix(train_samples, ctx, args.draw_feature_set)
        x_test, _ = draw_feature_matrix(test_samples, ctx, args.draw_feature_set)
        _, train_binary_draw, test_binary_draw = fit_draw_logistic(
            x_train,
            y_train_draw,
            x_test,
            l2=args.draw_l2,
            class_weight=args.draw_class_weight,
        )
        fixed_configs["draw_binary_pseudo3way"] = pseudo_three_way(test_binary_draw, test_sources["market"])

        draw_train_sources = {name: probs[:, DRAW_INDEX] for name, probs in train_sources.items()}
        draw_test_sources = {name: probs[:, DRAW_INDEX] for name, probs in test_sources.items()}
        draw_train_sources["binary_logistic"] = train_binary_draw
        draw_test_sources["binary_logistic"] = test_binary_draw
        draw_source_names = list(draw_train_sources)
        train_draw_list = [draw_train_sources[name] for name in draw_source_names]
        test_draw_list = [draw_test_sources[name] for name in draw_source_names]
        train_draw_y = (train_y == DRAW_INDEX).astype(int)
        draw_w_logloss = best_train_draw_weights(train_draw_list, train_draw_y, draw_weight_grid, metric="logloss")
        draw_w_ap = best_train_draw_weights(train_draw_list, train_draw_y, draw_weight_grid, metric="ap")
        draw_probs_by_config["draw_avg_all"].append(
            weighted_draw_probs(test_draw_list, np.ones(len(test_draw_list), dtype=float) / len(test_draw_list))
        )
        draw_probs_by_config["draw_tuned_logloss"].append(weighted_draw_probs(test_draw_list, draw_w_logloss))
        draw_probs_by_config["draw_tuned_ap"].append(weighted_draw_probs(test_draw_list, draw_w_ap))

        train_meta = draw_meta_features(train_samples, train_sources, train_binary_draw)
        test_meta = draw_meta_features(test_samples, test_sources, test_binary_draw)
        _, _, test_stack_draw = fit_draw_logistic(
            train_meta,
            y_train_draw,
            test_meta,
            l2=args.draw_stack_l2,
            class_weight="none",
        )
        draw_stack_probs.append(test_stack_draw)

        for config, probs in fixed_configs.items():
            probs = normalize_probs(probs)
            result_probs_by_config[config].append(probs)
            draw_probs_by_config[config].append(probs[:, DRAW_INDEX])
            append_prediction_rows(prediction_rows, config, test_samples, probs)
        draw_probs_by_config["draw_stack_logistic"].append(test_stack_draw)

        window_row = {
            "test_issue": test_issue,
            "train_start_issue": train_issues[0],
            "train_end_issue": train_issues[-1],
            "n_train_matches": len(train_samples),
            "n_test_matches": len(test_samples),
            "tuned_weights": ";".join(f"{name}={weight:.2f}" for name, weight in zip(source_names, best_w)),
            "draw_logloss_weights": ";".join(f"{name}={weight:.2f}" for name, weight in zip(draw_source_names, draw_w_logloss)),
            "draw_ap_weights": ";".join(f"{name}={weight:.2f}" for name, weight in zip(draw_source_names, draw_w_ap)),
            "tuned_train_logloss": logloss(weighted_probs(train_source_list, best_w), train_y),
            "tuned_test_logloss": logloss(fixed_configs["tuned_simplex"], test_y),
        }
        window_rows.append(window_row)

    y_all = np.concatenate(result_y) if result_y else np.asarray([], dtype=int)
    result_summary_rows = []
    for config, chunks in result_probs_by_config.items():
        probs = normalize_probs(np.vstack(chunks))
        result_summary_rows.append(result_summary(config, probs, y_all))
    result_summary_rows.sort(key=lambda r: (float(r["accuracy"]), -float(r["logloss"])), reverse=True)

    draw_summary_rows = []
    for config, chunks in draw_probs_by_config.items():
        p_draw = np.concatenate(chunks)
        draw_summary_rows.append(draw_summary(config, p_draw, y_all))
    draw_summary_rows.sort(key=lambda r: (float(r["average_precision"]), float(r["roc_auc"])), reverse=True)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "prediction_rows.csv", prediction_rows)
    write_csv(out / "prediction_summary.csv", result_summary_rows)
    write_csv(out / "draw_summary.csv", draw_summary_rows)
    write_csv(out / "ensemble_windows.csv", window_rows)

    report = [
        "# Beidan probability ensemble evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Source models: `{args.source_models}`",
        f"- Draw feature set: `{args.draw_feature_set}`",
        f"- Simplex weight step: `{args.weight_step}`",
        "",
        "## Result Prediction",
        md_table(result_summary_rows),
        "## Draw Prediction",
        md_table(draw_summary_rows),
        "## Windows",
        md_table(window_rows[:40]),
        "",
        "## Files",
        "",
        "- `prediction_summary.csv`",
        "- `draw_summary.csv`",
        "- `prediction_rows.csv`",
        "- `ensemble_windows.csv`",
        "",
    ]
    (out / "ensemble_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'ensemble_report.md'}")


def pseudo_three_way(p_draw: np.ndarray, market: np.ndarray) -> np.ndarray:
    p_draw = np.clip(np.asarray(p_draw, dtype=float), 1e-6, 1 - 1e-6)
    market = normalize_probs(market)
    non_draw = 1.0 - p_draw
    home_away = np.maximum(market[:, 0] + market[:, 2], 1e-9)
    return normalize_probs(
        np.vstack(
            [
                non_draw * market[:, 0] / home_away,
                p_draw,
                non_draw * market[:, 2] / home_away,
            ]
        ).T
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/beidan_probability_ensemble"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--source-models", default="base:0.01,kelly:0.03,rich:0.03")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--weight-step", type=float, default=0.1)
    parser.add_argument("--draw-feature-set", default="form_kelly")
    parser.add_argument("--draw-l2", type=float, default=0.01)
    parser.add_argument("--draw-class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--draw-stack-l2", type=float, default=0.03)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
