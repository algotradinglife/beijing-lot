#!/usr/bin/env python3
"""Snapshot-pure result probability model.

This module intentionally avoids ``euro_final_*`` and final-vs-snapshot
movement features.  It is meant for entry-time probability estimates where the
decision snapshot is either 10h or 1h.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_result_model_eval import (
    CONT_START,
    OUTCOMES,
    FeatureContext,
    MatchSample,
    accuracy,
    build_feature_context,
    logloss,
    prior_key_hcp,
    safe_log,
    softmax,
    standardize,
    val,
)
from scripts.walkforward_beidan_strategy_eval import ActionRow, snapshot_odds_p


@dataclass(frozen=True)
class SnapshotPureModel:
    beta: np.ndarray
    mean: np.ndarray
    std: np.ndarray
    ctx: FeatureContext
    snapshot: str
    feature_set: str
    train_logloss: float
    train_accuracy: float


def snapshot_market_probabilities(samples: list[MatchSample], snapshot: str) -> np.ndarray:
    rows = []
    for sample in samples:
        probs = []
        for code in OUTCOMES:
            odds, p = snapshot_odds_p(sample.rows[code], snapshot)
            if p is not None and p > 0:
                probs.append(float(p))
            elif odds is not None and odds > 1.0:
                probs.append(1.0 / float(odds))
            else:
                probs.append(0.0)
        total = sum(probs)
        if total <= 0:
            rows.append([1 / 3, 1 / 3, 1 / 3])
        else:
            rows.append([p / total for p in probs])
    return np.asarray(rows, dtype=float)


def sample_snapshot_ranks(sample: MatchSample, snapshot: str) -> dict[str, int]:
    by_code: dict[str, float] = {}
    for code in OUTCOMES:
        _, p = snapshot_odds_p(sample.rows[code], snapshot)
        if p is not None and p > 0:
            by_code[code] = float(p)
    if len(by_code) != len(OUTCOMES):
        return {}
    return {code: 1 + sum(1 for other in by_code.values() if other > p) for code, p in by_code.items()}


def market_shape_features(sample: MatchSample, snapshot: str) -> list[float]:
    probs = snapshot_market_probabilities([sample], snapshot)[0]
    ranked = sorted((float(p) for p in probs), reverse=True)
    entropy = -sum(p * math.log(p) for p in probs if p > 0)
    return [
        ranked[0],
        ranked[1],
        ranked[0] - ranked[1],
        entropy,
    ]


def snapshot_feature_parts(
    row: ActionRow,
    outcome_idx: int,
    sample: MatchSample,
    ctx: FeatureContext,
    snapshot: str,
) -> dict[str, list[float]]:
    alt = [1.0 if outcome_idx == i else 0.0 for i in range(3)]
    hcp = val(row.hcp)
    abs_hcp = abs(hcp)
    odds, p = snapshot_odds_p(row, snapshot)
    odds = val(odds)
    p = val(p)
    odds_10h = val(row.euro_10h_odds)
    p_10h = val(row.euro_10h_p)
    ranks = sample_snapshot_ranks(sample, snapshot)
    rank = float(ranks.get(row.action_code, 0))
    rank_flags = [
        1.0 if rank == 1 else 0.0,
        1.0 if rank == 2 else 0.0,
        1.0 if rank == 3 else 0.0,
    ]
    if snapshot == "10h":
        p_move = 0.0
        log_p_move = 0.0
        odds_move_log = 0.0
    else:
        p_move = p - p_10h if p_10h > 0 else 0.0
        log_p_move = math.log(p / p_10h) if p > 0 and p_10h > 0 else 0.0
        odds_move_log = math.log(odds / odds_10h) if odds > 1.0 and odds_10h > 1.0 else 0.0

    hkey = prior_key_hcp(hcp)
    league_prior = ctx.league_prior.get(row.league or "", ctx.global_prior)
    hcp_prior = ctx.hcp_prior.get(hkey, ctx.global_prior)
    league_hcp_prior = ctx.league_hcp_prior.get((row.league or "", hkey), ctx.global_prior)
    prior_vals = [
        ctx.global_prior[outcome_idx],
        league_prior[outcome_idx],
        hcp_prior[outcome_idx],
        league_hcp_prior[outcome_idx],
    ]
    kelly_snapshot = row.kelly_10h if snapshot == "10h" else row.kelly_1h
    market_shape = market_shape_features(sample, snapshot)
    base = [
        p,
        safe_log(p),
        safe_log(odds),
        rank,
        *rank_flags,
        *market_shape,
        p_10h,
        safe_log(p_10h),
        safe_log(odds_10h),
        p_move,
        log_p_move,
        odds_move_log,
        max(0.0, odds_move_log),
        max(0.0, -odds_move_log),
        hcp * alt[0],
        hcp * alt[1],
        hcp * alt[2],
        abs_hcp * alt[0],
        abs_hcp * alt[1],
        abs_hcp * alt[2],
        1.0 if hcp <= -2 else 0.0,
        1.0 if hcp == -1 else 0.0,
        1.0 if hcp == 0 else 0.0,
        1.0 if hcp == 1 else 0.0,
        1.0 if hcp >= 2 else 0.0,
    ]
    priors = [
        *prior_vals,
        *(prior - p for prior in prior_vals),
        *(math.log(prior / p) if prior > 0 and p > 0 else 0.0 for prior in prior_vals),
    ]
    kelly = [
        val(kelly_snapshot, 1.0),
        val(row.kelly_initial, 1.0),
        val(kelly_snapshot, 1.0) - val(row.kelly_initial, 1.0),
    ]
    return {
        "base": base,
        "priors": priors,
        "kelly": kelly,
    }


def row_features(
    row: ActionRow,
    outcome_idx: int,
    sample: MatchSample,
    ctx: FeatureContext,
    *,
    snapshot: str,
    feature_set: str,
) -> list[float]:
    alt = [1.0 if outcome_idx == i else 0.0 for i in range(3)]
    parts = snapshot_feature_parts(row, outcome_idx, sample, ctx, snapshot)
    if feature_set == "snapshot":
        features = parts["base"]
    elif feature_set == "snapshot_priors":
        features = parts["base"] + parts["priors"]
    elif feature_set == "snapshot_kelly":
        features = parts["base"] + parts["kelly"]
    elif feature_set == "snapshot_full":
        features = parts["base"] + parts["priors"] + parts["kelly"]
    else:
        raise ValueError(f"unsupported snapshot-pure feature set: {feature_set}")
    return alt + features


def feature_tensor(
    samples: list[MatchSample],
    ctx: FeatureContext,
    *,
    snapshot: str,
    feature_set: str,
) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(
        [
            [
                row_features(sample.rows[code], i, sample, ctx, snapshot=snapshot, feature_set=feature_set)
                for i, code in enumerate(OUTCOMES)
            ]
            for sample in samples
        ],
        dtype=float,
    )
    y = np.asarray([sample.y for sample in samples], dtype=int)
    return x, y


def loss_grad(beta: np.ndarray, x: np.ndarray, y: np.ndarray, l2: float) -> tuple[float, np.ndarray]:
    scores = np.einsum("naf,f->na", x, beta)
    p = softmax(scores)
    n = x.shape[0]
    loss = -np.log(np.maximum(p[np.arange(n), y], 1e-12)).mean() + 0.5 * l2 * float(beta @ beta)
    diff = p
    diff[np.arange(n), y] -= 1.0
    grad = np.einsum("na,naf->f", diff, x) / n + l2 * beta
    return loss, grad


def fit_snapshot_pure_model(
    samples: list[MatchSample],
    *,
    snapshot: str,
    feature_set: str,
    l2: float,
    maxiter: int,
) -> SnapshotPureModel:
    ctx = build_feature_context(samples)
    x_raw, y = feature_tensor(samples, ctx, snapshot=snapshot, feature_set=feature_set)
    x, mean, std = standardize(x_raw)
    beta0 = np.zeros(x.shape[-1], dtype=float)

    def fun(beta: np.ndarray) -> tuple[float, np.ndarray]:
        return loss_grad(beta, x, y, l2)

    opt = minimize(fun, beta0, method="L-BFGS-B", jac=True, options={"maxiter": maxiter, "ftol": 1e-8})
    beta = np.asarray(opt.x, dtype=float)
    probs = predict_snapshot_pure_proba(samples, SnapshotPureModel(
        beta=beta,
        mean=mean,
        std=std,
        ctx=ctx,
        snapshot=snapshot,
        feature_set=feature_set,
        train_logloss=0.0,
        train_accuracy=0.0,
    ))
    return SnapshotPureModel(
        beta=beta,
        mean=mean,
        std=std,
        ctx=ctx,
        snapshot=snapshot,
        feature_set=feature_set,
        train_logloss=logloss(probs, y),
        train_accuracy=accuracy(probs, y),
    )


def predict_snapshot_pure_proba(samples: list[MatchSample], model: SnapshotPureModel) -> np.ndarray:
    x_raw, _ = feature_tensor(samples, model.ctx, snapshot=model.snapshot, feature_set=model.feature_set)
    x, _, _ = standardize(x_raw, mean=model.mean, std=model.std)
    return softmax(np.einsum("naf,f->na", x, model.beta))


def fit_predict_snapshot_pure(
    train_samples: list[MatchSample],
    test_samples: list[MatchSample],
    *,
    snapshot: str,
    feature_set: str,
    l2: float,
    maxiter: int,
) -> tuple[np.ndarray, SnapshotPureModel]:
    model = fit_snapshot_pure_model(
        train_samples,
        snapshot=snapshot,
        feature_set=feature_set,
        l2=l2,
        maxiter=maxiter,
    )
    return predict_snapshot_pure_proba(test_samples, model), model
