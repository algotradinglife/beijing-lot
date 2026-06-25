#!/usr/bin/env python3
"""Walk-forward draw vs non-draw prediction for Beidan matches.

The environment does not include sklearn, so this script implements two small
models with numpy/scipy:

- binary logistic regression
- a shallow random-forest-style ensemble using bootstrap samples and Gini trees

The evaluation focuses on draw precision/recall and low-probability draw
deletion safety, not raw accuracy.
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_result_model_eval import (
    EXTRA_FEATURE_KEYS,
    OUTCOMES,
    build_feature_context,
    build_samples,
    load_match_extras,
    market_probs,
    prior_key_hcp,
    safe_log,
    val,
)
from scripts.walkforward_beidan_strategy_eval import default_db_path, load_action_rows, md_table, write_csv


DRAW_INDEX = OUTCOMES.index("1")
CUP_KEYWORDS = ("杯", "欧冠", "欧联", "亚冠", "解放者", "南球杯", "世俱", "锦标", "附加")
FORM_WINDOWS = (5, 10)
FORM_FEATURE_KEYS = [
    "is_cup_like",
    "league_prior_draw_rate",
    "league_prior_low_total_rate",
    "league_prior_avg_total_goals",
    "home_recent_draw_rate_5",
    "home_recent_draw_rate_10",
    "away_recent_draw_rate_5",
    "away_recent_draw_rate_10",
    "home_recent_low_total_rate_5",
    "home_recent_low_total_rate_10",
    "away_recent_low_total_rate_5",
    "away_recent_low_total_rate_10",
    "home_recent_avg_total_goals_5",
    "home_recent_avg_total_goals_10",
    "away_recent_avg_total_goals_5",
    "away_recent_avg_total_goals_10",
    "home_recent_avg_abs_gd_5",
    "home_recent_avg_abs_gd_10",
    "away_recent_avg_abs_gd_5",
    "away_recent_avg_abs_gd_10",
    "home_recent_avg_gf_5",
    "home_recent_avg_gf_10",
    "away_recent_avg_gf_5",
    "away_recent_avg_gf_10",
    "home_recent_avg_ga_5",
    "home_recent_avg_ga_10",
    "away_recent_avg_ga_5",
    "away_recent_avg_ga_10",
    "combined_recent_draw_rate_5",
    "combined_recent_draw_rate_10",
    "combined_recent_low_total_rate_5",
    "combined_recent_low_total_rate_10",
    "combined_recent_avg_total_goals_5",
    "combined_recent_avg_total_goals_10",
    "combined_recent_avg_abs_gd_5",
    "combined_recent_avg_abs_gd_10",
    "team_recent_draw_rate_gap_5",
    "team_recent_draw_rate_gap_10",
    "team_recent_avg_total_gap_5",
    "team_recent_avg_total_gap_10",
    "h2h_prior_draw_rate",
    "h2h_prior_low_total_rate",
    "h2h_prior_avg_total_goals",
]


def parse_csv_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def parse_csv_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def parse_score(score: str | None) -> tuple[int, int] | None:
    if not score or "-" not in str(score):
        return None
    left, right = str(score).split("-", 1)
    try:
        return int(left.strip()), int(right.strip())
    except ValueError:
        return None


def is_cup_like(league: str | None) -> float:
    league = str(league or "")
    return 1.0 if any(keyword in league for keyword in CUP_KEYWORDS) else 0.0


def metric_from_history(history: list[dict[str, float]], key: str, window: int, default: float = 0.0) -> float:
    part = history[-window:]
    if not part:
        return default
    return float(sum(float(x[key]) for x in part) / len(part))


def rate_from_counts(counts: Counter[str], key: str, default: float) -> float:
    n = counts.get("n", 0)
    if n <= 0:
        return default
    return float(counts.get(key, 0.0) / n)


def load_team_form_extras(db_path: Path, min_year: int) -> dict[int, dict[str, float]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = list(
        conn.execute(
            """
            SELECT match_id, issue, match_idx, kickoff_ts, season_year, league, home, away,
                   score, fthg, ftag, result_code, has_winning_sp
            FROM match_features
            WHERE season_year >= ?
              AND home IS NOT NULL
              AND away IS NOT NULL
              AND kickoff_ts IS NOT NULL
            ORDER BY kickoff_ts, match_id
            """,
            (min_year,),
        )
    )
    conn.close()

    team_history: dict[str, list[dict[str, float]]] = defaultdict(list)
    league_counts: dict[str, Counter[str]] = defaultdict(Counter)
    pair_history: dict[tuple[str, str], list[dict[str, float]]] = defaultdict(list)
    extras: dict[int, dict[str, float]] = {}
    global_counts: Counter[str] = Counter()

    for row in rows:
        home = str(row["home"])
        away = str(row["away"])
        league = str(row["league"] or "")
        pair = tuple(sorted((home, away)))
        league_prior_draw = rate_from_counts(league_counts[league], "draws", rate_from_counts(global_counts, "draws", 0.276))
        league_prior_low = rate_from_counts(league_counts[league], "low_totals", rate_from_counts(global_counts, "low_totals", 0.50))
        league_prior_goals = rate_from_counts(league_counts[league], "total_goals", rate_from_counts(global_counts, "total_goals", 2.50))
        e: dict[str, float] = {
            "is_cup_like": is_cup_like(league),
            "league_prior_draw_rate": league_prior_draw,
            "league_prior_low_total_rate": league_prior_low,
            "league_prior_avg_total_goals": league_prior_goals,
        }
        for window in FORM_WINDOWS:
            home_draw = metric_from_history(team_history[home], "draw", window, league_prior_draw)
            away_draw = metric_from_history(team_history[away], "draw", window, league_prior_draw)
            home_low = metric_from_history(team_history[home], "low_total", window, league_prior_low)
            away_low = metric_from_history(team_history[away], "low_total", window, league_prior_low)
            home_total = metric_from_history(team_history[home], "total_goals", window, league_prior_goals)
            away_total = metric_from_history(team_history[away], "total_goals", window, league_prior_goals)
            home_abs_gd = metric_from_history(team_history[home], "abs_gd", window, 1.25)
            away_abs_gd = metric_from_history(team_history[away], "abs_gd", window, 1.25)
            home_gf = metric_from_history(team_history[home], "gf", window, 1.25)
            away_gf = metric_from_history(team_history[away], "gf", window, 1.25)
            home_ga = metric_from_history(team_history[home], "ga", window, 1.25)
            away_ga = metric_from_history(team_history[away], "ga", window, 1.25)
            e[f"home_recent_draw_rate_{window}"] = home_draw
            e[f"away_recent_draw_rate_{window}"] = away_draw
            e[f"home_recent_low_total_rate_{window}"] = home_low
            e[f"away_recent_low_total_rate_{window}"] = away_low
            e[f"home_recent_avg_total_goals_{window}"] = home_total
            e[f"away_recent_avg_total_goals_{window}"] = away_total
            e[f"home_recent_avg_abs_gd_{window}"] = home_abs_gd
            e[f"away_recent_avg_abs_gd_{window}"] = away_abs_gd
            e[f"home_recent_avg_gf_{window}"] = home_gf
            e[f"away_recent_avg_gf_{window}"] = away_gf
            e[f"home_recent_avg_ga_{window}"] = home_ga
            e[f"away_recent_avg_ga_{window}"] = away_ga
            e[f"combined_recent_draw_rate_{window}"] = (home_draw + away_draw) / 2.0
            e[f"combined_recent_low_total_rate_{window}"] = (home_low + away_low) / 2.0
            e[f"combined_recent_avg_total_goals_{window}"] = (home_total + away_total) / 2.0
            e[f"combined_recent_avg_abs_gd_{window}"] = (home_abs_gd + away_abs_gd) / 2.0
            e[f"team_recent_draw_rate_gap_{window}"] = abs(home_draw - away_draw)
            e[f"team_recent_avg_total_gap_{window}"] = abs(home_total - away_total)

        h2h = pair_history[pair]
        e["h2h_prior_draw_rate"] = metric_from_history(h2h, "draw", 5, league_prior_draw)
        e["h2h_prior_low_total_rate"] = metric_from_history(h2h, "low_total", 5, league_prior_low)
        e["h2h_prior_avg_total_goals"] = metric_from_history(h2h, "total_goals", 5, league_prior_goals)
        extras[int(row["match_id"])] = e

        score = None
        if row["fthg"] is not None and row["ftag"] is not None:
            score = (int(row["fthg"]), int(row["ftag"]))
        else:
            score = parse_score(row["score"])
        result = str(row["result_code"]) if row["result_code"] is not None else ""
        if score is None or result not in {"3", "1", "0"}:
            continue
        fthg, ftag = score
        total_goals = fthg + ftag
        draw = 1.0 if result == "1" else 0.0
        low_total = 1.0 if total_goals <= 2 else 0.0
        abs_gd = float(abs(fthg - ftag))
        home_rec = {"draw": draw, "low_total": low_total, "total_goals": float(total_goals), "abs_gd": abs_gd, "gf": float(fthg), "ga": float(ftag)}
        away_rec = {"draw": draw, "low_total": low_total, "total_goals": float(total_goals), "abs_gd": abs_gd, "gf": float(ftag), "ga": float(fthg)}
        team_history[home].append(home_rec)
        team_history[away].append(away_rec)
        pair_history[pair].append({"draw": draw, "low_total": low_total, "total_goals": float(total_goals), "abs_gd": abs_gd, "gf": 0.0, "ga": 0.0})
        for counts in (league_counts[league], global_counts):
            counts["n"] += 1
            counts["draws"] += draw
            counts["low_totals"] += low_total
            counts["total_goals"] += float(total_goals)
    return extras


def merge_extras(*sources: dict[int, dict[str, float]]) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = defaultdict(dict)
    for source in sources:
        for match_id, values in source.items():
            out[match_id].update(values)
    return dict(out)


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40.0, 40.0)))


def binary_logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def rank_auc(scores: np.ndarray, y: np.ndarray) -> float:
    pos = int(y.sum())
    neg = int(len(y) - pos)
    if pos == 0 or neg == 0:
        return float("nan")
    order = np.argsort(scores)
    ranks = np.empty(len(scores), dtype=float)
    i = 0
    while i < len(scores):
        j = i + 1
        while j < len(scores) and scores[order[j]] == scores[order[i]]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        ranks[order[i:j]] = avg_rank
        i = j
    rank_sum_pos = float(ranks[y == 1].sum())
    return (rank_sum_pos - pos * (pos + 1) / 2.0) / (pos * neg)


def average_precision(scores: np.ndarray, y: np.ndarray) -> float:
    pos = int(y.sum())
    if pos == 0:
        return float("nan")
    order = np.argsort(-scores)
    y_sorted = y[order]
    tp = 0
    total = 0
    precision_sum = 0.0
    for label in y_sorted:
        total += 1
        if label == 1:
            tp += 1
            precision_sum += tp / total
    return precision_sum / pos


def standardize_train_test(x_train: np.ndarray, x_test: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    std[std < 1e-8] = 1.0
    return (x_train - mean) / std, (x_test - mean) / std, mean, std


def entropy(probs: list[float]) -> float:
    return -sum(p * math.log(max(p, 1e-12)) for p in probs)


def sample_feature_vector(sample, ctx, feature_set: str) -> list[float]:
    rows = sample.rows
    p_raw = [val(rows[code].euro_final_p) for code in OUTCOMES]
    total = sum(p_raw)
    p = [x / total for x in p_raw] if total > 0 else [1 / 3, 1 / 3, 1 / 3]
    odds = [val(rows[code].euro_final_odds) for code in OUTCOMES]
    odds_1h = [val(rows[code].euro_1h_odds) for code in OUTCOMES]
    odds_10h = [val(rows[code].euro_10h_odds) for code in OUTCOMES]
    p_1h_raw = [val(rows[code].euro_1h_p) for code in OUTCOMES]
    p_10h_raw = [val(rows[code].euro_10h_p) for code in OUTCOMES]
    p_1h_total = sum(p_1h_raw)
    p_10h_total = sum(p_10h_raw)
    p_1h = [x / p_1h_total for x in p_1h_raw] if p_1h_total > 0 else [0.0, 0.0, 0.0]
    p_10h = [x / p_10h_total for x in p_10h_raw] if p_10h_total > 0 else [0.0, 0.0, 0.0]
    row3 = rows["3"]
    hcp = val(row3.hcp)
    abs_hcp = abs(hcp)
    hkey = prior_key_hcp(hcp)
    league_prior = ctx.league_prior.get(row3.league or "", ctx.global_prior)
    hcp_prior = ctx.hcp_prior.get(hkey, ctx.global_prior)
    league_hcp_prior = ctx.league_hcp_prior.get((row3.league or "", hkey), ctx.global_prior)
    fav_idx = int(np.argmax(p))
    home_away_gap = p[0] - p[2]
    fav_gap = sorted(p, reverse=True)[0] - sorted(p, reverse=True)[1]

    base = [
        *p,
        p[DRAW_INDEX],
        p[DRAW_INDEX] - max(p[0], p[2]),
        p[DRAW_INDEX] - min(p[0], p[2]),
        abs(home_away_gap),
        home_away_gap,
        fav_gap,
        entropy(p),
        *[safe_log(x) for x in odds],
        safe_log(odds[DRAW_INDEX]),
        odds[DRAW_INDEX] / odds[0] - 1.0 if odds[0] else 0.0,
        odds[DRAW_INDEX] / odds[2] - 1.0 if odds[2] else 0.0,
        float(rows["1"].euro_final_rank or 0),
        1.0 if rows["1"].euro_final_rank == 1 else 0.0,
        1.0 if rows["1"].euro_final_rank == 2 else 0.0,
        1.0 if rows["1"].euro_final_rank == 3 else 0.0,
        hcp,
        abs_hcp,
        1.0 if hcp <= -2 else 0.0,
        1.0 if hcp == -1 else 0.0,
        1.0 if hcp == 0 else 0.0,
        1.0 if hcp == 1 else 0.0,
        1.0 if hcp >= 2 else 0.0,
        float(fav_idx == DRAW_INDEX),
        *(p[i] - p_1h[i] if p_1h[i] else 0.0 for i in range(3)),
        *(p[i] - p_10h[i] if p_10h[i] else 0.0 for i in range(3)),
        *(odds[i] / odds_1h[i] - 1.0 if odds_1h[i] else 0.0 for i in range(3)),
        *(odds[i] / odds_10h[i] - 1.0 if odds_10h[i] else 0.0 for i in range(3)),
    ]
    kelly = [
        *(val(rows[code].kelly_final, 1.0) for code in OUTCOMES),
        *(val(rows[code].kelly_1h, 1.0) for code in OUTCOMES),
        *(val(rows[code].kelly_10h, 1.0) for code in OUTCOMES),
        *(val(rows[code].kelly_move_10h_final) for code in OUTCOMES),
    ]
    priors = [
        ctx.global_prior[DRAW_INDEX],
        league_prior[DRAW_INDEX],
        hcp_prior[DRAW_INDEX],
        league_hcp_prior[DRAW_INDEX],
        league_prior[DRAW_INDEX] - p[DRAW_INDEX],
        hcp_prior[DRAW_INDEX] - p[DRAW_INDEX],
        league_hcp_prior[DRAW_INDEX] - p[DRAW_INDEX],
    ]
    extras = [val(sample.extras.get(k)) for k in EXTRA_FEATURE_KEYS]
    form = [val(sample.extras.get(k)) for k in FORM_FEATURE_KEYS]
    if feature_set == "base":
        return base
    if feature_set == "kelly":
        return base + kelly
    if feature_set == "priors":
        return base + priors
    if feature_set == "extras":
        return base + extras
    if feature_set == "rich":
        return base + kelly + priors + extras
    if feature_set == "form":
        return base + form
    if feature_set == "form_kelly":
        return base + kelly + form
    if feature_set == "form_rich":
        return base + kelly + priors + extras + form
    raise ValueError(f"unsupported feature set: {feature_set}")


def feature_matrix(samples, ctx, feature_set: str) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray([sample_feature_vector(s, ctx, feature_set) for s in samples], dtype=float)
    y = np.asarray([1 if s.y == DRAW_INDEX else 0 for s in samples], dtype=int)
    return x, y


@dataclass(frozen=True)
class LogisticModel:
    beta: np.ndarray
    mean: np.ndarray
    std: np.ndarray


def fit_logistic(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray, *, l2: float, class_weight: str) -> tuple[LogisticModel, np.ndarray, np.ndarray]:
    x_train_s, x_test_s, mean, std = standardize_train_test(x_train, x_test)
    x_train_i = np.concatenate([np.ones((x_train_s.shape[0], 1)), x_train_s], axis=1)
    x_test_i = np.concatenate([np.ones((x_test_s.shape[0], 1)), x_test_s], axis=1)
    if class_weight == "balanced":
        pos = max(1, int(y_train.sum()))
        neg = max(1, int(len(y_train) - pos))
        weights = np.where(y_train == 1, len(y_train) / (2 * pos), len(y_train) / (2 * neg)).astype(float)
    else:
        weights = np.ones(len(y_train), dtype=float)

    def loss_grad(beta: np.ndarray) -> tuple[float, np.ndarray]:
        z = x_train_i @ beta
        p = sigmoid(z)
        ce = -(y_train * np.log(np.maximum(p, 1e-12)) + (1 - y_train) * np.log(np.maximum(1 - p, 1e-12)))
        loss = float(np.mean(weights * ce)) + 0.5 * l2 * float(beta[1:] @ beta[1:])
        grad = (x_train_i.T @ (weights * (p - y_train))) / len(y_train)
        grad[1:] += l2 * beta[1:]
        return loss, grad

    opt = minimize(loss_grad, np.zeros(x_train_i.shape[1]), method="L-BFGS-B", jac=True, options={"maxiter": 120, "ftol": 1e-8})
    beta = np.asarray(opt.x, dtype=float)
    return LogisticModel(beta=beta, mean=mean, std=std), sigmoid(x_train_i @ beta), sigmoid(x_test_i @ beta)


@dataclass
class TreeNode:
    prob: float
    feature: int = -1
    threshold: float = 0.0
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None


def gini_from_counts(pos: int, n: int) -> float:
    if n <= 0:
        return 0.0
    p = pos / n
    return 1.0 - p * p - (1 - p) * (1 - p)


def fit_tree(
    x: np.ndarray,
    y: np.ndarray,
    rng: np.random.Generator,
    *,
    depth: int,
    max_depth: int,
    min_leaf: int,
    max_features: int,
    n_thresholds: int,
) -> TreeNode:
    n = len(y)
    pos = int(y.sum())
    prob = (pos + 1.0) / (n + 2.0)
    if depth >= max_depth or n < min_leaf * 2 or pos == 0 or pos == n:
        return TreeNode(prob=prob)

    features = rng.choice(x.shape[1], size=min(max_features, x.shape[1]), replace=False)
    parent_gini = gini_from_counts(pos, n)
    best_gain = 0.0
    best_feature = -1
    best_threshold = 0.0
    best_mask = None
    for feature in features:
        col = x[:, feature]
        finite = col[np.isfinite(col)]
        if len(finite) < min_leaf * 2:
            continue
        qs = np.linspace(0.05, 0.95, n_thresholds)
        thresholds = np.unique(np.quantile(finite, qs))
        for threshold in thresholds:
            mask = col <= threshold
            left_n = int(mask.sum())
            right_n = n - left_n
            if left_n < min_leaf or right_n < min_leaf:
                continue
            left_pos = int(y[mask].sum())
            right_pos = pos - left_pos
            weighted_gini = (left_n * gini_from_counts(left_pos, left_n) + right_n * gini_from_counts(right_pos, right_n)) / n
            gain = parent_gini - weighted_gini
            if gain > best_gain:
                best_gain = gain
                best_feature = int(feature)
                best_threshold = float(threshold)
                best_mask = mask
    if best_feature < 0 or best_mask is None:
        return TreeNode(prob=prob)
    return TreeNode(
        prob=prob,
        feature=best_feature,
        threshold=best_threshold,
        left=fit_tree(
            x[best_mask],
            y[best_mask],
            rng,
            depth=depth + 1,
            max_depth=max_depth,
            min_leaf=min_leaf,
            max_features=max_features,
            n_thresholds=n_thresholds,
        ),
        right=fit_tree(
            x[~best_mask],
            y[~best_mask],
            rng,
            depth=depth + 1,
            max_depth=max_depth,
            min_leaf=min_leaf,
            max_features=max_features,
            n_thresholds=n_thresholds,
        ),
    )


def predict_tree_one(node: TreeNode, row: np.ndarray) -> float:
    cur = node
    while cur.feature >= 0 and cur.left is not None and cur.right is not None:
        cur = cur.left if row[cur.feature] <= cur.threshold else cur.right
    return cur.prob


def fit_forest(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
    *,
    n_estimators: int,
    max_depth: int,
    min_leaf: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    max_features = max(1, int(math.sqrt(x_train.shape[1])))
    train_preds = np.zeros(len(y_train), dtype=float)
    test_preds = np.zeros(len(x_test), dtype=float)
    for _ in range(n_estimators):
        idx = rng.integers(0, len(y_train), size=len(y_train))
        tree = fit_tree(
            x_train[idx],
            y_train[idx],
            rng,
            depth=0,
            max_depth=max_depth,
            min_leaf=min_leaf,
            max_features=max_features,
            n_thresholds=12,
        )
        train_preds += np.asarray([predict_tree_one(tree, row) for row in x_train], dtype=float)
        test_preds += np.asarray([predict_tree_one(tree, row) for row in x_test], dtype=float)
    return train_preds / n_estimators, test_preds / n_estimators


def threshold_rows(rows: list[dict[str, object]], thresholds: list[float]) -> list[dict[str, object]]:
    out = []
    total_draws = sum(int(r["is_draw"]) for r in rows)
    for threshold in thresholds:
        tp = fp = tn = fn = 0
        for r in rows:
            pred = float(r["p_draw"]) >= threshold
            actual = int(r["is_draw"]) == 1
            if pred and actual:
                tp += 1
            elif pred and not actual:
                fp += 1
            elif not pred and actual:
                fn += 1
            else:
                tn += 1
        precision = tp / (tp + fp) if tp + fp else float("nan")
        recall = tp / (tp + fn) if tp + fn else float("nan")
        f1 = 2 * precision * recall / (precision + recall) if precision + recall and math.isfinite(precision) else float("nan")
        out.append(
            {
                "config": rows[0]["config"],
                "threshold": threshold,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
                "pred_draws": tp + fp,
                "pred_draw_rate": (tp + fp) / len(rows) if rows else float("nan"),
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "accuracy": (tp + tn) / len(rows) if rows else float("nan"),
                "draw_retention": recall,
                "draws_deleted": fn,
                "non_draws_deleted_with_draw": fp,
                "total_draws": total_draws,
            }
        )
    return out


def delete_rows(rows: list[dict[str, object]], thresholds: list[float]) -> list[dict[str, object]]:
    out = []
    for threshold in thresholds:
        deleted = [r for r in rows if float(r["p_draw"]) <= threshold]
        false_delete = sum(int(r["is_draw"]) for r in deleted)
        out.append(
            {
                "config": rows[0]["config"],
                "delete_rule": f"p_draw<={threshold:g}",
                "n_deleted_draw_options": len(deleted),
                "match_coverage": len(deleted) / len(rows) if rows else float("nan"),
                "false_delete_draws": false_delete,
                "false_delete_rate": false_delete / len(deleted) if deleted else float("nan"),
                "draw_recall_lost": false_delete / sum(int(r["is_draw"]) for r in rows) if rows else float("nan"),
            }
        )
    return out


def calibration_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for lo in np.arange(0.0, 1.0, 0.1):
        hi = min(1.0, lo + 0.1)
        selected = [r for r in rows if float(r["p_draw"]) >= lo and (float(r["p_draw"]) < hi or hi == 1.0)]
        n = len(selected)
        avg_p = sum(float(r["p_draw"]) for r in selected) / n if n else float("nan")
        obs = sum(int(r["is_draw"]) for r in selected) / n if n else float("nan")
        out.append(
            {
                "config": rows[0]["config"],
                "bin": f"{lo:.1f}-{hi:.1f}",
                "n": n,
                "avg_p_draw": avg_p,
                "observed_draw_rate": obs,
                "calibration_error": obs - avg_p if n else float("nan"),
            }
        )
    return out


def summary_row(config: str, rows: list[dict[str, object]]) -> dict[str, object]:
    y = np.asarray([int(r["is_draw"]) for r in rows], dtype=int)
    p = np.asarray([float(r["p_draw"]) for r in rows], dtype=float)
    base = float(y.mean()) if len(y) else float("nan")
    return {
        "config": config,
        "model_type": rows[0]["model_type"],
        "feature_set": rows[0]["feature_set"],
        "n_matches": len(rows),
        "draw_rate": base,
        "logloss": binary_logloss(p, y),
        "brier": brier(p, y),
        "roc_auc": rank_auc(p, y),
        "average_precision": average_precision(p, y),
        "lift_ap_vs_base": average_precision(p, y) / base if base > 0 else float("nan"),
        "avg_p_draw": float(p.mean()),
    }


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    base_extras = load_match_extras(args.db, args.min_year)
    form_extras = load_team_form_extras(args.db, args.min_year) if args.include_form_extras else {}
    extras = merge_extras(base_extras, form_extras)
    samples = build_samples(action_rows, extras)
    by_issue = group_samples_by_issue(samples)
    issues = sorted(by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    feature_sets = parse_csv_strings(args.feature_sets)
    model_types = parse_csv_strings(args.model_types)
    thresholds = parse_csv_floats(args.thresholds)
    delete_thresholds = parse_csv_floats(args.delete_thresholds)
    rows_by_config: dict[str, list[dict[str, object]]] = defaultdict(list)
    window_rows: list[dict[str, object]] = []

    for feature_set in feature_sets:
        for model_type in model_types:
            config = f"{model_type}_{feature_set}"
            if model_type.startswith("logistic"):
                config += f"_l2{args.l2:g}"
                if model_type == "logistic_balanced":
                    config += "_balanced"
            elif model_type == "forest":
                config += f"_t{args.n_estimators}_d{args.max_depth}"
            for issue_idx in range(args.train_issues, len(issues)):
                test_issue = issues[issue_idx]
                train_issues = issues[issue_idx - args.train_issues:issue_idx]
                train_samples = [s for issue in train_issues for s in by_issue[issue]]
                test_samples = by_issue[test_issue]
                if len(train_samples) < args.min_train_matches:
                    continue
                ctx = build_feature_context(train_samples)
                x_train, y_train = feature_matrix(train_samples, ctx, feature_set)
                x_test, y_test = feature_matrix(test_samples, ctx, feature_set)
                if model_type == "market":
                    train_probs = market_probs(train_samples)[:, DRAW_INDEX]
                    test_probs = market_probs(test_samples)[:, DRAW_INDEX]
                elif model_type in {"logistic", "logistic_balanced"}:
                    _, train_probs, test_probs = fit_logistic(
                        x_train,
                        y_train,
                        x_test,
                        l2=args.l2,
                        class_weight="balanced" if model_type == "logistic_balanced" else "none",
                    )
                elif model_type == "forest":
                    train_probs, test_probs = fit_forest(
                        x_train,
                        y_train,
                        x_test,
                        n_estimators=args.n_estimators,
                        max_depth=args.max_depth,
                        min_leaf=args.min_leaf,
                        seed=args.seed + issue_idx,
                    )
                else:
                    raise ValueError(f"unsupported model type: {model_type}")
                window_rows.append(
                    {
                        "config": config,
                        "test_issue": test_issue,
                        "train_start_issue": train_issues[0],
                        "train_end_issue": train_issues[-1],
                        "n_train_matches": len(train_samples),
                        "n_test_matches": len(test_samples),
                        "train_draw_rate": float(y_train.mean()),
                        "test_draw_rate": float(y_test.mean()),
                        "train_logloss": binary_logloss(train_probs, y_train),
                        "test_logloss": binary_logloss(test_probs, y_test),
                        "test_average_precision": average_precision(test_probs, y_test),
                    }
                )
                for sample, p_draw, is_draw in zip(test_samples, test_probs, y_test):
                    rows_by_config[config].append(
                        {
                            "config": config,
                            "model_type": model_type,
                            "feature_set": feature_set,
                            "issue": test_issue,
                            "match_id": sample.match_id,
                            "match_idx": sample.rows["3"].match_idx,
                            "league": sample.rows["3"].league,
                            "hcp": sample.rows["3"].hcp,
                            "is_draw": int(is_draw),
                            "actual": sample.rows["3"].result_code,
                            "p_draw": float(p_draw),
                            "market_p_draw": float(market_probs([sample])[0, DRAW_INDEX]),
                        }
                    )

    summary = [summary_row(config, rows) for config, rows in rows_by_config.items()]
    summary.sort(key=lambda r: (float(r["average_precision"]), -float(r["logloss"])), reverse=True)
    threshold_summary = []
    delete_summary = []
    calibration_summary = []
    for config, rows in sorted(rows_by_config.items()):
        threshold_summary.extend(threshold_rows(rows, thresholds))
        delete_summary.extend(delete_rows(rows, delete_thresholds))
        calibration_summary.extend(calibration_rows(rows))

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "draw_prediction_rows.csv", [r for rows in rows_by_config.values() for r in rows])
    write_csv(out / "draw_model_summary.csv", summary)
    write_csv(out / "draw_threshold_summary.csv", threshold_summary)
    write_csv(out / "draw_delete_summary.csv", delete_summary)
    write_csv(out / "draw_calibration_summary.csv", calibration_summary)
    write_csv(out / "draw_window_metrics.csv", window_rows)

    best = summary[0]["config"] if summary else ""
    report = [
        "# Beidan draw vs non-draw prediction",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Feature sets: `{args.feature_sets}`",
        f"- Model types: `{args.model_types}`",
        f"- L2: `{args.l2}`",
        f"- Forest trees/depth/min_leaf: `{args.n_estimators}` / `{args.max_depth}` / `{args.min_leaf}`",
        "",
        "## Model Summary",
        md_table(summary),
        "## Best Thresholds",
        md_table([r for r in threshold_summary if r["config"] == best]),
        "## Best Draw Deletion",
        md_table([r for r in delete_summary if r["config"] == best]),
        "## Best Calibration",
        md_table([r for r in calibration_summary if r["config"] == best]),
        "",
        "## Files",
        "",
        "- `draw_model_summary.csv`",
        "- `draw_threshold_summary.csv`",
        "- `draw_delete_summary.csv`",
        "- `draw_calibration_summary.csv`",
        "- `draw_prediction_rows.csv`",
        "- `draw_window_metrics.csv`",
        "",
    ]
    (out / "draw_model_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'draw_model_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/beidan_draw_binary"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--feature-sets", default="base")
    parser.add_argument("--model-types", default="market,logistic,logistic_balanced,forest")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--thresholds", default="0.2,0.25,0.3,0.35,0.4,0.45,0.5")
    parser.add_argument("--delete-thresholds", default="0.12,0.15,0.18,0.2,0.22,0.25")
    parser.add_argument("--n-estimators", type=int, default=40)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--min-leaf", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20260625)
    parser.add_argument("--include-form-extras", action="store_true")
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
