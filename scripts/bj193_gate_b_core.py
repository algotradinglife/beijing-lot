#!/usr/bin/env python3
"""Pure deterministic helpers for #193 Gate B."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np

MIN_ACTION_SUPPORT = 20
STATIC_POLICY = "STATIC_BEST_FULL_FULL"
PRIOR_POLICY = "PRIOR_ONLY_BEST_FIXED"
NO_BET_ACTION = "NO_BET_ZERO_FLOW"


def canonical_sha(lines: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def action_identity(namespace: str, selector: str, allocation: str) -> str:
    return f"{namespace}|{selector}|{allocation}"


def selector_rank(
    net: np.ndarray,
    stake: np.ndarray,
    selector_ids: Sequence[str],
    issue_indices: Sequence[int],
    keep: int,
    minimum_support: int = MIN_ACTION_SUPPORT,
) -> list[int]:
    """Frozen aggregate ROI screen with exact deterministic tie breaks."""
    ix = np.asarray(issue_indices, dtype=np.int64)
    rows: list[tuple[float, int, float, str, int]] = []
    for si, selector in enumerate(selector_ids):
        values = stake[si, ix]
        support = int(np.count_nonzero(values > 0.0))
        total_stake = float(values.sum())
        score = (
            float(net[si, ix].sum()) / total_stake
            if support >= minimum_support and total_stake > 0.0
            else -math.inf
        )
        rows.append((score, support, total_stake, selector, si))
    rows.sort(key=lambda row: (-row[0], -row[1], row[2], row[3]))
    return [row[-1] for row in rows[:keep]]


def allocator_rank(
    net: np.ndarray,
    stake: np.ndarray,
    action_ids: Sequence[str],
    issue_indices: Sequence[int],
    keep: int,
    minimum_support: int = MIN_ACTION_SUPPORT,
) -> list[int]:
    return selector_rank(net, stake, action_ids, issue_indices, keep, minimum_support)


def stochastic_scale(seed_scope: str) -> float:
    return 100.0 if seed_scope == "ENSEMBLE_100" else 1.0


def normalize_seed_aggregated(values: np.ndarray, seed_scope: str) -> np.ndarray:
    """Mean replicate money, never the 100-seed sum, is one strategy action."""
    return values / stochastic_scale(seed_scope)


@dataclass(frozen=True)
class FeatureTransform:
    medians: np.ndarray
    low: np.ndarray
    high: np.ndarray
    means: np.ndarray
    scales: np.ndarray

    @classmethod
    def fit(cls, raw: np.ndarray) -> "FeatureTransform":
        if raw.ndim != 2 or raw.shape[0] == 0:
            raise ValueError("nonempty 2-D training feature matrix required")
        medians = np.nanmedian(raw, axis=0)
        medians = np.where(np.isnan(medians), 0.0, medians)
        filled = np.where(np.isnan(raw), medians, raw)
        low = np.quantile(filled, 0.01, axis=0)
        high = np.quantile(filled, 0.99, axis=0)
        clipped = np.clip(filled, low, high)
        means = clipped.mean(axis=0)
        scales = clipped.std(axis=0)
        scales = np.where(scales > 1e-12, scales, 1.0)
        return cls(medians, low, high, means, scales)

    def apply(self, raw: np.ndarray) -> np.ndarray:
        missing = np.isnan(raw).astype(np.float64)
        filled = np.where(np.isnan(raw), self.medians, raw)
        standardized = (np.clip(filled, self.low, self.high) - self.means) / self.scales
        return np.concatenate([standardized, missing], axis=1)


def _masked_mean(y: np.ndarray, active: np.ndarray) -> np.ndarray:
    count = active.sum(axis=0)
    total = np.where(active, y, 0.0).sum(axis=0)
    return np.divide(total, count, out=np.full(y.shape[1], np.nan), where=count > 0)


def prior_predictions(
    train_y: np.ndarray, train_active: np.ndarray, query_count: int
) -> np.ndarray:
    means = _masked_mean(train_y, train_active)
    means[train_active.sum(axis=0) < MIN_ACTION_SUPPORT] = np.nan
    return np.repeat(means[None, :], query_count, axis=0)


def nearest_predictions(
    train_x: np.ndarray,
    query_x: np.ndarray,
    train_y: np.ndarray,
    train_active: np.ndarray,
    k: int,
    inverse_distance: bool,
) -> np.ndarray:
    """Action-specific KNN with one shared pre-event distance matrix."""
    distances = np.sqrt(
        np.maximum(
            0.0,
            ((query_x[:, None, :] - train_x[None, :, :]) ** 2).sum(axis=2),
        )
    )
    order = np.argsort(distances, axis=1, kind="stable")
    output = np.full((len(query_x), train_y.shape[1]), np.nan)
    valid_action = train_active.sum(axis=0) >= MIN_ACTION_SUPPORT
    for qi in range(len(query_x)):
        ranked = order[qi]
        for action in np.flatnonzero(valid_action):
            chosen = ranked[train_active[ranked, action]][:k]
            if len(chosen) == 0:
                continue
            if inverse_distance:
                d = distances[qi, chosen]
                exact = d <= 1e-12
                weights = exact.astype(float) if exact.any() else 1.0 / d
                output[qi, action] = float(
                    np.dot(weights, train_y[chosen, action]) / weights.sum()
                )
            else:
                output[qi, action] = float(train_y[chosen, action].mean())
    return output


def binned_predictions(
    train_x: np.ndarray,
    query_x: np.ndarray,
    train_y: np.ndarray,
    train_active: np.ndarray,
    bins: int,
    min_leaf: int,
) -> np.ndarray:
    """Best action-specific univariate quantile regime rule."""
    nquery, naction = len(query_x), train_y.shape[1]
    output = np.full((nquery, naction), np.nan)
    supports = train_active.sum(axis=0)
    for action in np.flatnonzero(supports >= MIN_ACTION_SUPPORT):
        mask = train_active[:, action]
        y = train_y[mask, action]
        fallback = float(y.mean())
        best: tuple[float, int, np.ndarray, np.ndarray] | None = None
        for feature in range(train_x.shape[1]):
            values = train_x[mask, feature]
            edges = np.unique(np.quantile(values, np.arange(1, bins) / bins))
            leaf = np.searchsorted(edges, values, side="right")
            means = np.full(len(edges) + 1, fallback)
            error = 0.0
            for li in range(len(means)):
                take = leaf == li
                if int(take.sum()) >= min_leaf:
                    means[li] = float(y[take].mean())
                error += float(((y[take] - means[li]) ** 2).sum())
            key = (error, feature)
            if best is None or key < (best[0], best[1]):
                best = (error, feature, edges, means)
        assert best is not None
        leaf = np.searchsorted(best[2], query_x[:, best[1]], side="right")
        output[:, action] = best[3][leaf]
    return output


def _tree_fit(
    x: np.ndarray,
    y: np.ndarray,
    rows: np.ndarray,
    depth: int,
    max_depth: int,
    min_leaf: int,
) -> tuple:
    mean = float(y[rows].mean())
    if depth >= max_depth or len(rows) < 2 * min_leaf:
        return ("leaf", mean)
    best: tuple[float, int, float, np.ndarray, np.ndarray] | None = None
    for feature in range(x.shape[1]):
        order = rows[np.argsort(x[rows, feature], kind="stable")]
        values = x[order, feature]
        yy = y[order]
        csum = np.cumsum(yy)
        csq = np.cumsum(yy * yy)
        total, total_sq = csum[-1], csq[-1]
        for split in range(min_leaf, len(order) - min_leaf + 1):
            if values[split - 1] == values[split]:
                continue
            ln = split
            rn = len(order) - split
            lsum, lsq = csum[split - 1], csq[split - 1]
            rsum, rsq = total - lsum, total_sq - lsq
            sse = float(lsq - lsum * lsum / ln + rsq - rsum * rsum / rn)
            threshold = float((values[split - 1] + values[split]) / 2.0)
            key = (sse, feature, threshold)
            if best is None or key < (best[0], best[1], best[2]):
                best = (sse, feature, threshold, order[:split], order[split:])
    if best is None:
        return ("leaf", mean)
    return (
        "node",
        best[1],
        best[2],
        _tree_fit(x, y, best[3], depth + 1, max_depth, min_leaf),
        _tree_fit(x, y, best[4], depth + 1, max_depth, min_leaf),
    )


def _tree_predict_one(tree: tuple, row: np.ndarray) -> float:
    while tree[0] == "node":
        tree = tree[3] if row[tree[1]] <= tree[2] else tree[4]
    return float(tree[1])


def shallow_tree_predictions(
    train_x: np.ndarray,
    query_x: np.ndarray,
    train_y: np.ndarray,
    train_active: np.ndarray,
    max_depth: int,
    min_leaf: int,
) -> np.ndarray:
    output = np.full((len(query_x), train_y.shape[1]), np.nan)
    for action in np.flatnonzero(train_active.sum(axis=0) >= MIN_ACTION_SUPPORT):
        rows = np.flatnonzero(train_active[:, action])
        tree = _tree_fit(train_x, train_y[:, action], rows, 0, max_depth, min_leaf)
        output[:, action] = [_tree_predict_one(tree, row) for row in query_x]
    return output


def ridge_score_predictions(
    train_x: np.ndarray,
    query_x: np.ndarray,
    train_y: np.ndarray,
    train_active: np.ndarray,
    feature_indices: Sequence[int],
    l2: float,
) -> np.ndarray:
    """Regularized action-specific score; deterministic ridge implementation."""
    cols = np.asarray(feature_indices, dtype=np.int64)
    output = np.full((len(query_x), train_y.shape[1]), np.nan)
    q = np.column_stack([np.ones(len(query_x)), query_x[:, cols]])
    for action in np.flatnonzero(train_active.sum(axis=0) >= MIN_ACTION_SUPPORT):
        mask = train_active[:, action]
        x = np.column_stack([np.ones(int(mask.sum())), train_x[mask][:, cols]])
        penalty = np.eye(x.shape[1]) * l2
        penalty[0, 0] = 0.0
        beta = np.linalg.solve(x.T @ x + penalty, x.T @ train_y[mask, action])
        output[:, action] = q @ beta
    return output


def predict_model(
    family: str,
    parameters: Mapping[str, object],
    train_x: np.ndarray,
    query_x: np.ndarray,
    train_y: np.ndarray,
    train_active: np.ndarray,
    group_columns: Mapping[str, Sequence[int]],
) -> np.ndarray:
    if family == "PRIOR_ONLY_FIXED":
        return prior_predictions(train_y, train_active, len(query_x))
    if family == "BINNED_REGIME_RULE":
        return binned_predictions(
            train_x, query_x, train_y, train_active,
            int(parameters["quantile_bins"]), int(parameters["min_leaf"])
        )
    if family == "SHALLOW_TREE":
        return shallow_tree_predictions(
            train_x, query_x, train_y, train_active,
            int(parameters["max_depth"]), int(parameters["min_leaf"])
        )
    if family == "MONOTONE_REGULARIZED_SCORE":
        name = str(parameters["monotone_feature_group"])
        return ridge_score_predictions(
            train_x, query_x, train_y, train_active,
            group_columns[name], float(parameters["l2"])
        )
    if family == "NEAREST_HISTORICAL_REGIME":
        return nearest_predictions(
            train_x, query_x, train_y, train_active, int(parameters["k"]),
            parameters["weighting"] == "INVERSE_DISTANCE"
        )
    raise ValueError(f"unknown model family {family}")


def choose_actions(
    predicted: np.ndarray,
    available: np.ndarray,
    action_ids: Sequence[str],
    action_stake: np.ndarray,
    complexity: Sequence[int],
    prior_predictions_by_issue: np.ndarray,
    fallback_index: int,
) -> list[int]:
    """Causal action choice using the frozen improvement and tie contract."""
    chosen: list[int] = []
    for issue in range(len(predicted)):
        eligible = np.flatnonzero(available[issue] & np.isfinite(predicted[issue]))
        if len(eligible) == 0:
            chosen.append(fallback_index)
            continue
        prior = prior_predictions_by_issue[issue]
        prior_best = (
            float(np.nanmax(prior[available[issue]]))
            if available[issue].any() else 0.0
        )
        candidates = [i for i in eligible if predicted[issue, i] > prior_best]
        if not candidates:
            chosen.append(fallback_index)
            continue
        candidates.sort(
            key=lambda i: (
                -float(predicted[issue, i]), float(action_stake[issue, i]),
                int(complexity[i]), action_ids[i]
            )
        )
        chosen.append(candidates[0])
    return chosen


def max_streak(flags: Sequence[bool]) -> int:
    best = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        best = max(best, current)
    return best


def holding_metrics(
    rows: Sequence[Mapping[str, float | str]],
    reference_capital: float = 220_000.0,
) -> dict[str, object]:
    """Exact issue-level equity, streak, rolling-window and drawdown summary."""
    nets = [float(row["net"]) for row in rows]
    stakes = [float(row["stake"]) for row in rows]
    gross = [float(row["gross"]) for row in rows]
    equity = reference_capital
    peak = reference_capital
    max_dd = 0.0
    max_dd_pct = 0.0
    peak_at = 0
    trough_at = 0
    underwater_start: int | None = None
    max_tuw = 0
    for i, net in enumerate(nets, 1):
        equity += net
        if equity >= peak:
            peak = equity
            peak_at = i
            underwater_start = None
        else:
            if underwater_start is None:
                underwater_start = peak_at
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd / peak if peak else math.nan
                trough_at = i
            max_tuw = max(max_tuw, i - underwater_start)
    rolling: dict[int, dict[str, object]] = {}
    for window in (5, 10, 20):
        values = []
        for start in range(0, len(rows) - window + 1):
            net = sum(nets[start : start + window])
            stake = sum(stakes[start : start + window])
            values.append((net, net / stake if stake else None, start))
        rolling[window] = {
            "count": len(values),
            "negative_probability": (
                sum(value[0] < 0 for value in values) / len(values)
                if values else None
            ),
            "worst_net": min((value[0] for value in values), default=None),
            "worst_roi": min(
                (value[1] for value in values if value[1] is not None), default=None
            ),
        }
    active = [i for i, stake in enumerate(stakes) if stake > 0.0]
    total_stake = sum(stakes)
    return {
        "support": len(active), "stake": total_stake, "net": sum(nets),
        "roi": sum(nets) / total_stake if total_stake else None,
        "max_negative_pnl_streak_calendar": max_streak([value < 0 for value in nets]),
        "max_miss_streak_calendar": max_streak(
            [stakes[i] > 0 and gross[i] == 0 for i in range(len(rows))]
        ),
        "max_negative_pnl_streak_active": max_streak([nets[i] < 0 for i in active]),
        "max_miss_streak_active": max_streak([gross[i] == 0 for i in active]),
        "max_drawdown_yuan": max_dd, "max_drawdown_pct": max_dd_pct,
        "max_drawdown_duration_issues": max(0, trough_at - peak_at),
        "max_time_under_water_issues": max_tuw, "rolling": rolling,
    }


def json_params(value: str) -> dict[str, object]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("model parameters must be an object")
    return parsed
