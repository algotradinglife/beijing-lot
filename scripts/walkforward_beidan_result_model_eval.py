#!/usr/bin/env python3
"""Evaluate a lightweight result-probability model for N=7 Beidan tickets.

The model is a rolling-window multinomial logistic regression implemented with
numpy/scipy only. It predicts P(3/1/0) from market odds, market movement, Kelly
features, and handicap interactions, then ranks legs by p_model * proxy_odds.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
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

from scripts.walkforward_beidan_strategy_eval import (
    ActionRow,
    Leg,
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    full_cover_lookup,
    group_by_issue as group_action_rows_by_issue,
    load_action_rows,
    make_tickets,
    md_table,
    settle_ticket,
    summarize_tickets,
    train_q_model,
    write_csv,
)


OUTCOMES = ("3", "1", "0")
OUTCOME_TO_INDEX = {"3": 0, "1": 1, "0": 2}
CONT_START = 3

EXTRA_FEATURE_KEYS = [
    "home_rank_num",
    "away_rank_num",
    "rank_diff_home_minus_away",
    "rank_abs_diff",
    "home_rank_missing",
    "away_rank_missing",
    "hist_eu_home",
    "hist_eu_draw",
    "hist_eu_away",
    "hist_eu_home_p",
    "hist_eu_draw_p",
    "hist_eu_away_p",
    "euro_final_n_complete",
    "euro_final_home_std_rel",
    "euro_final_draw_std_rel",
    "euro_final_away_std_rel",
    "euro_final_home_range_rel",
    "euro_final_draw_range_rel",
    "euro_final_away_range_rel",
    "asian_final_home_price",
    "asian_final_line",
    "asian_final_away_price",
    "asian_final_price_gap",
    "asian_final_line_abs",
    "asian_line_move_10h_final",
    "asian_home_price_move_10h_final",
    "asian_away_price_move_10h_final",
    "ou_final_over_price",
    "ou_final_line",
    "ou_final_under_price",
    "ou_final_line_abs",
    "ou_line_move_10h_final",
    "ou_over_price_move_10h_final",
    "ou_under_price_move_10h_final",
]

TEAM_FORM_PROB_KEYS = ("team_poisson_p3", "team_poisson_p1", "team_poisson_p0")


@dataclass(frozen=True)
class MatchSample:
    issue: str
    match_id: int
    rows: dict[str, ActionRow]
    y: int
    extras: dict[str, float]


@dataclass(frozen=True)
class FeatureContext:
    global_prior: np.ndarray
    league_prior: dict[str, np.ndarray]
    hcp_prior: dict[str, np.ndarray]
    league_hcp_prior: dict[tuple[str, str], np.ndarray]


@dataclass(frozen=True)
class FittedModel:
    beta: np.ndarray
    mean: np.ndarray
    std: np.ndarray
    ctx: FeatureContext
    train_logloss: float
    train_accuracy: float
    feature_set: str


def valid_single_row(row: ActionRow) -> bool:
    return (
        row.action_code in OUTCOME_TO_INDEX
        and row.euro_final_odds is not None
        and row.euro_final_odds > 1.0
        and row.euro_final_p is not None
        and row.euro_final_p > 0
    )


def parse_rank(raw: str | None) -> tuple[float, float]:
    if not raw:
        return 0.0, 1.0
    m = re.search(r"-?\d+", str(raw))
    if not m:
        return 0.0, 1.0
    return float(m.group(0)), 0.0


def rel_std(avg: float | None, sq_avg: float | None) -> float:
    if avg is None or sq_avg is None or avg == 0:
        return 0.0
    var = max(0.0, float(sq_avg) - float(avg) * float(avg))
    return math.sqrt(var) / abs(float(avg))


def rel_range(avg: float | None, lo: float | None, hi: float | None) -> float:
    if avg is None or lo is None or hi is None or avg == 0:
        return 0.0
    return (float(hi) - float(lo)) / abs(float(avg))


def load_match_extras(db_path: Path, min_year: int) -> dict[int, dict[str, float]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    extras: dict[int, dict[str, float]] = defaultdict(dict)
    for r in conn.execute(
        """
        SELECT match_id, home_rank, away_rank,
               history_avg_eu_home, history_avg_eu_draw, history_avg_eu_away
        FROM match_features
        WHERE has_winning_sp=1 AND season_year>=?
        """,
        (min_year,),
    ):
        mid = int(r["match_id"])
        hr, hr_missing = parse_rank(r["home_rank"])
        ar, ar_missing = parse_rank(r["away_rank"])
        e = extras[mid]
        e["home_rank_num"] = hr
        e["away_rank_num"] = ar
        e["rank_diff_home_minus_away"] = hr - ar
        e["rank_abs_diff"] = abs(hr - ar)
        e["home_rank_missing"] = hr_missing
        e["away_rank_missing"] = ar_missing
        h = float(r["history_avg_eu_home"] or 0.0)
        d = float(r["history_avg_eu_draw"] or 0.0)
        a = float(r["history_avg_eu_away"] or 0.0)
        e["hist_eu_home"] = h
        e["hist_eu_draw"] = d
        e["hist_eu_away"] = a
        inv = [1 / x if x > 1 else 0.0 for x in (h, d, a)]
        s = sum(inv)
        if s > 0:
            e["hist_eu_home_p"], e["hist_eu_draw_p"], e["hist_eu_away_p"] = [x / s for x in inv]
        else:
            e["hist_eu_home_p"] = e["hist_eu_draw_p"] = e["hist_eu_away_p"] = 0.0

    market_rows = conn.execute(
        """
        SELECT mc.*
        FROM market_consensus mc
        JOIN match_features mf ON mf.match_id = mc.match_id
        WHERE mf.has_winning_sp=1
          AND mf.season_year>=?
          AND mc.market IN ('euro_1x2','asian_handicap','over_under')
          AND mc.snapshot IN ('final','10h')
        """,
        (min_year,),
    )
    for r in market_rows:
        mid = int(r["match_id"])
        market = str(r["market"])
        snap = str(r["snapshot"])
        e = extras[mid]
        vals = {
            "v1": float(r["v1_avg"] or 0.0),
            "v2": float(r["v2_avg"] or 0.0),
            "v3": float(r["v3_avg"] or 0.0),
        }
        if market == "euro_1x2" and snap == "final":
            e["euro_final_n_complete"] = float(r["n_complete"] or 0.0)
            for label, v in (("home", "v1"), ("draw", "v2"), ("away", "v3")):
                e[f"euro_final_{label}_std_rel"] = rel_std(r[f"{v}_avg"], r[f"{v}_sq_avg"])
                e[f"euro_final_{label}_range_rel"] = rel_range(r[f"{v}_avg"], r[f"{v}_min"], r[f"{v}_max"])
        elif market == "asian_handicap":
            prefix = f"asian_{snap}"
            e[f"{prefix}_home_price"] = vals["v1"]
            e[f"{prefix}_line"] = vals["v2"]
            e[f"{prefix}_away_price"] = vals["v3"]
            if snap == "final":
                e["asian_final_price_gap"] = vals["v1"] - vals["v3"]
                e["asian_final_line_abs"] = abs(vals["v2"])
        elif market == "over_under":
            prefix = f"ou_{snap}"
            e[f"{prefix}_over_price"] = vals["v1"]
            e[f"{prefix}_line"] = vals["v2"]
            e[f"{prefix}_under_price"] = vals["v3"]
            if snap == "final":
                e["ou_final_line_abs"] = abs(vals["v2"])

    for e in extras.values():
        e["asian_line_move_10h_final"] = e.get("asian_final_line", 0.0) - e.get("asian_10h_line", 0.0)
        e["asian_home_price_move_10h_final"] = e.get("asian_final_home_price", 0.0) - e.get("asian_10h_home_price", 0.0)
        e["asian_away_price_move_10h_final"] = e.get("asian_final_away_price", 0.0) - e.get("asian_10h_away_price", 0.0)
        e["ou_line_move_10h_final"] = e.get("ou_final_line", 0.0) - e.get("ou_10h_line", 0.0)
        e["ou_over_price_move_10h_final"] = e.get("ou_final_over_price", 0.0) - e.get("ou_10h_over_price", 0.0)
        e["ou_under_price_move_10h_final"] = e.get("ou_final_under_price", 0.0) - e.get("ou_10h_under_price", 0.0)

    conn.close()
    return dict(extras)


def build_samples(rows: list[ActionRow], extras: dict[int, dict[str, float]] | None = None) -> list[MatchSample]:
    grouped: dict[int, dict[str, ActionRow]] = defaultdict(dict)
    extras = extras or {}
    for row in rows:
        if valid_single_row(row):
            grouped[row.match_id][row.action_code] = row

    samples: list[MatchSample] = []
    for match_id, by_outcome in grouped.items():
        if any(code not in by_outcome for code in OUTCOMES):
            continue
        result = by_outcome["3"].result_code
        if result not in OUTCOME_TO_INDEX:
            continue
        samples.append(
            MatchSample(
                issue=by_outcome["3"].issue,
                match_id=match_id,
                rows=by_outcome,
                y=OUTCOME_TO_INDEX[result],
                extras=extras.get(match_id, {}),
            )
        )
    return sorted(samples, key=lambda s: (s.issue, s.rows["3"].match_idx))


def safe_log(x: float | None, default: float = 0.0) -> float:
    if x is None or x <= 0 or not math.isfinite(x):
        return default
    return math.log(x)


def val(x: float | None, default: float = 0.0) -> float:
    if x is None or not math.isfinite(x):
        return default
    return float(x)


def prior_key_hcp(hcp: float) -> str:
    if hcp <= -2:
        return "<=-2"
    if hcp == -1:
        return "-1"
    if hcp == 0:
        return "0"
    if hcp == 1:
        return "1"
    if hcp >= 2:
        return ">=2"
    return str(hcp)


def smoothed_prior(counts: Counter[int], global_prior: np.ndarray, alpha: float = 30.0) -> np.ndarray:
    total = sum(counts.values())
    out = np.asarray([counts.get(i, 0.0) for i in range(3)], dtype=float)
    return (out + alpha * global_prior) / (total + alpha) if total > 0 else global_prior.copy()


def build_feature_context(samples: list[MatchSample]) -> FeatureContext:
    global_counts: Counter[int] = Counter(s.y for s in samples)
    total = sum(global_counts.values())
    if total > 0:
        global_prior = np.asarray([global_counts.get(i, 0.0) / total for i in range(3)], dtype=float)
    else:
        global_prior = np.asarray([1 / 3, 1 / 3, 1 / 3], dtype=float)

    league_counts: dict[str, Counter[int]] = defaultdict(Counter)
    hcp_counts: dict[str, Counter[int]] = defaultdict(Counter)
    league_hcp_counts: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
    for s in samples:
        row = s.rows["3"]
        league = row.league or ""
        hkey = prior_key_hcp(row.hcp)
        league_counts[league][s.y] += 1
        hcp_counts[hkey][s.y] += 1
        league_hcp_counts[(league, hkey)][s.y] += 1

    return FeatureContext(
        global_prior=global_prior,
        league_prior={k: smoothed_prior(v, global_prior) for k, v in league_counts.items()},
        hcp_prior={k: smoothed_prior(v, global_prior) for k, v in hcp_counts.items()},
        league_hcp_prior={k: smoothed_prior(v, global_prior, alpha=60.0) for k, v in league_hcp_counts.items()},
    )


def row_features(
    row: ActionRow,
    outcome_idx: int,
    sample: MatchSample,
    ctx: FeatureContext,
    feature_set: str,
) -> list[float]:
    alt = [1.0 if outcome_idx == i else 0.0 for i in range(3)]
    hcp = val(row.hcp)
    abs_hcp = abs(hcp)
    rank = float(row.euro_final_rank or 0)
    rank_flags = [
        1.0 if row.euro_final_rank == 1 else 0.0,
        1.0 if row.euro_final_rank == 2 else 0.0,
        1.0 if row.euro_final_rank == 3 else 0.0,
    ]
    p_final = val(row.euro_final_p)
    odds_final = val(row.euro_final_odds)
    p_1h = val(row.euro_1h_p)
    p_10h = val(row.euro_10h_p)
    odds_1h = val(row.euro_1h_odds)
    odds_10h = val(row.euro_10h_odds)
    p_move_1h = (p_final / p_1h - 1.0) if p_1h else 0.0
    p_move_10h = (p_final / p_10h - 1.0) if p_10h else 0.0
    odds_move_1h = (odds_final / odds_1h - 1.0) if odds_1h else 0.0
    odds_move_10h = (odds_final / odds_10h - 1.0) if odds_10h else 0.0
    hkey = prior_key_hcp(hcp)
    league_prior = ctx.league_prior.get(row.league or "", ctx.global_prior)
    hcp_prior = ctx.hcp_prior.get(hkey, ctx.global_prior)
    league_hcp_prior = ctx.league_hcp_prior.get((row.league or "", hkey), ctx.global_prior)
    base_features = [
        p_final,
        safe_log(p_final),
        safe_log(odds_final),
        rank,
        *rank_flags,
        p_move_1h,
        p_move_10h,
        odds_move_1h,
        odds_move_10h,
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
    kelly_features = [
        val(row.kelly_final, 1.0),
        val(row.kelly_1h, 1.0),
        val(row.kelly_10h, 1.0),
        val(row.kelly_initial, 1.0),
        val(row.kelly_move_10h_final),
        p_final - p_1h if p_1h else 0.0,
        p_final - p_10h if p_10h else 0.0,
    ]
    prior_features = [
        ctx.global_prior[outcome_idx],
        league_prior[outcome_idx],
        hcp_prior[outcome_idx],
        league_hcp_prior[outcome_idx],
        league_prior[outcome_idx] - p_final,
        hcp_prior[outcome_idx] - p_final,
        league_hcp_prior[outcome_idx] - p_final,
    ]
    extra_features = [val(sample.extras.get(k)) for k in EXTRA_FEATURE_KEYS]
    team_probs = [val(sample.extras.get(k)) for k in TEAM_FORM_PROB_KEYS]
    team_p = team_probs[outcome_idx]
    team_rank = 1 + sum(1 for other_p in team_probs if other_p > team_p)
    team_draw_rate = 0.5 * (val(sample.extras.get("team_home_draw_rate")) + val(sample.extras.get("team_away_draw_rate")))
    team_form_features = [
        team_p,
        safe_log(team_p),
        team_p - p_final,
        math.log(team_p / p_final) if team_p > 0 and p_final > 0 else 0.0,
        float(team_rank),
        1.0 if team_rank == 1 else 0.0,
        1.0 if team_rank == 2 else 0.0,
        1.0 if team_rank == 3 else 0.0,
        val(sample.extras.get("team_xg_diff")) * alt[0],
        -val(sample.extras.get("team_xg_diff")) * alt[2],
        val(sample.extras.get("team_abs_xg_diff")) * alt[1],
        val(sample.extras.get("team_xg_total")) * alt[1],
        val(sample.extras.get("team_home_draw_rate")) * alt[1],
        val(sample.extras.get("team_away_draw_rate")) * alt[1],
        team_draw_rate * alt[1],
        val(sample.extras.get("team_home_form_points")) * alt[0],
        val(sample.extras.get("team_away_form_points")) * alt[2],
        val(sample.extras.get("team_home_role_n")),
        val(sample.extras.get("team_away_role_n")),
    ]

    if feature_set == "base":
        features = base_features
    elif feature_set == "kelly":
        features = base_features + kelly_features
    elif feature_set == "priors":
        features = base_features + prior_features
    elif feature_set == "extras":
        features = base_features + extra_features
    elif feature_set == "rich":
        features = base_features + kelly_features + prior_features + extra_features
    elif feature_set == "team":
        features = base_features + team_form_features
    elif feature_set == "team_rich":
        features = base_features + kelly_features + prior_features + team_form_features
    else:
        raise ValueError(f"unsupported feature set: {feature_set}")
    return alt + features


def sample_features(sample: MatchSample, ctx: FeatureContext, feature_set: str = "rich") -> np.ndarray:
    return np.asarray(
        [row_features(sample.rows[code], i, sample, ctx, feature_set) for i, code in enumerate(OUTCOMES)],
        dtype=float,
    )


def feature_tensor(
    samples: list[MatchSample],
    ctx: FeatureContext,
    feature_set: str = "rich",
) -> tuple[np.ndarray, np.ndarray]:
    x = np.stack([sample_features(s, ctx, feature_set) for s in samples], axis=0)
    y = np.asarray([s.y for s in samples], dtype=int)
    return x, y


def standardize(x: np.ndarray, mean: np.ndarray | None = None, std: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    out = x.copy()
    if mean is None:
        mean = np.zeros(x.shape[-1], dtype=float)
        std = np.ones(x.shape[-1], dtype=float)
        cont = x[:, :, CONT_START:].reshape(-1, x.shape[-1] - CONT_START)
        mean[CONT_START:] = cont.mean(axis=0)
        std_part = cont.std(axis=0)
        std_part[std_part < 1e-8] = 1.0
        std[CONT_START:] = std_part
    out[:, :, CONT_START:] = (out[:, :, CONT_START:] - mean[CONT_START:]) / std[CONT_START:]
    return out, mean, std


def softmax(scores: np.ndarray) -> np.ndarray:
    z = scores - scores.max(axis=1, keepdims=True)
    ez = np.exp(z)
    return ez / ez.sum(axis=1, keepdims=True)


def loss_grad(beta: np.ndarray, x: np.ndarray, y: np.ndarray, l2: float) -> tuple[float, np.ndarray]:
    scores = np.einsum("naf,f->na", x, beta)
    p = softmax(scores)
    n = x.shape[0]
    loss = -np.log(np.maximum(p[np.arange(n), y], 1e-12)).mean() + 0.5 * l2 * float(beta @ beta)
    diff = p
    diff[np.arange(n), y] -= 1.0
    grad = np.einsum("na,naf->f", diff, x) / n + l2 * beta
    return loss, grad


def fit_model(samples: list[MatchSample], *, l2: float, maxiter: int, feature_set: str = "rich") -> FittedModel:
    ctx = build_feature_context(samples)
    x_raw, y = feature_tensor(samples, ctx, feature_set)
    x, mean, std = standardize(x_raw)
    beta0 = np.zeros(x.shape[-1], dtype=float)

    def fun(beta: np.ndarray) -> tuple[float, np.ndarray]:
        return loss_grad(beta, x, y, l2)

    opt = minimize(fun, beta0, method="L-BFGS-B", jac=True, options={"maxiter": maxiter, "ftol": 1e-8})
    beta = np.asarray(opt.x, dtype=float)
    probs = predict_proba_with_stats(samples, beta, mean, std, ctx, feature_set)
    train_logloss = logloss(probs, y)
    train_accuracy = accuracy(probs, y)
    return FittedModel(
        beta=beta,
        mean=mean,
        std=std,
        ctx=ctx,
        train_logloss=train_logloss,
        train_accuracy=train_accuracy,
        feature_set=feature_set,
    )


def predict_proba_with_stats(
    samples: list[MatchSample],
    beta: np.ndarray,
    mean: np.ndarray,
    std: np.ndarray,
    ctx: FeatureContext,
    feature_set: str = "rich",
) -> np.ndarray:
    x_raw, _ = feature_tensor(samples, ctx, feature_set)
    x, _, _ = standardize(x_raw, mean=mean, std=std)
    return softmax(np.einsum("naf,f->na", x, beta))


def predict_proba(samples: list[MatchSample], model: FittedModel) -> np.ndarray:
    return predict_proba_with_stats(samples, model.beta, model.mean, model.std, model.ctx, model.feature_set)


def market_probs(samples: list[MatchSample]) -> np.ndarray:
    out = []
    for s in samples:
        probs = [val(s.rows[code].euro_final_p) for code in OUTCOMES]
        total = sum(probs)
        if total <= 0:
            out.append([1 / 3, 1 / 3, 1 / 3])
        else:
            out.append([p / total for p in probs])
    return np.asarray(out, dtype=float)


def logloss(probs: np.ndarray, y: np.ndarray) -> float:
    return float(-np.log(np.maximum(probs[np.arange(len(y)), y], 1e-12)).mean())


def accuracy(probs: np.ndarray, y: np.ndarray) -> float:
    return float((probs.argmax(axis=1) == y).mean())


def build_model_legs(
    samples: list[MatchSample],
    probs: np.ndarray,
    *,
    min_proxy_odds: float,
    max_proxy_odds: float,
    min_score_factor: float,
) -> list[Leg]:
    legs: list[Leg] = []
    for sample, p_row in zip(samples, probs):
        for i, code in enumerate(OUTCOMES):
            row = sample.rows[code]
            odds = row.euro_final_odds
            if odds is None or odds < min_proxy_odds or odds > max_proxy_odds:
                continue
            score = float(p_row[i] * odds)
            if score < min_score_factor:
                continue
            legs.append(
                Leg(
                    row=row,
                    strategy="result_model_high_sp",
                    score_factor=score,
                    p_hat=float(p_row[i]),
                    source_rule="multinomial_logit",
                )
            )
    return legs


def build_q_model_veto_legs(
    issue_rows: list[ActionRow],
    q_model: dict[tuple[str, str, str, str], float],
    global_q: float,
    model_probs: np.ndarray,
    test_samples: list[MatchSample],
    *,
    snapshot: str,
    min_proxy_odds: float,
    max_proxy_odds: float,
    min_score_factor: float,
    min_model_p: float,
    min_model_market_ratio: float,
) -> list[Leg]:
    q_legs = build_q_baseline_legs(
        issue_rows,
        q_model,
        global_q,
        snapshot=snapshot,
        min_proxy_odds=min_proxy_odds,
        max_proxy_odds=max_proxy_odds,
        min_score_factor=min_score_factor,
    )
    p_model: dict[tuple[int, str], float] = {}
    p_market: dict[tuple[int, str], float] = {}
    for sample, probs in zip(test_samples, model_probs):
        for i, code in enumerate(OUTCOMES):
            p_model[(sample.match_id, code)] = float(probs[i])
            p_market[(sample.match_id, code)] = val(sample.rows[code].euro_final_p)

    out: list[Leg] = []
    for leg in q_legs:
        key = (leg.row.match_id, leg.row.action_code)
        mp = p_model.get(key, 0.0)
        market_p = p_market.get(key, 0.0)
        ratio = mp / market_p if market_p > 0 else 0.0
        if mp < min_model_p:
            continue
        if ratio < min_model_market_ratio:
            continue
        out.append(
            Leg(
                row=leg.row,
                strategy="q_baseline_model_veto",
                score_factor=leg.score_factor,
                p_hat=leg.p_hat,
                source_rule=f"{leg.source_rule};model_p={mp:.4f};model_market_ratio={ratio:.4f}",
            )
        )
    return out


def issue_order(samples: list[MatchSample]) -> list[str]:
    return sorted({s.issue for s in samples})


def group_samples_by_issue(samples: list[MatchSample]) -> dict[str, list[MatchSample]]:
    out: dict[str, list[MatchSample]] = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def compact_pred_metrics(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if not rows:
        return []
    return [
        {
            "n_windows": len(rows),
            "n_test_matches": sum(int(r["n_test_matches"]) for r in rows),
            "model_logloss": weighted_mean(rows, "model_logloss", "n_test_matches"),
            "market_logloss": weighted_mean(rows, "market_logloss", "n_test_matches"),
            "model_accuracy": weighted_mean(rows, "model_accuracy", "n_test_matches"),
            "market_accuracy": weighted_mean(rows, "market_accuracy", "n_test_matches"),
            "avg_train_logloss": weighted_mean(rows, "train_logloss", "n_train_matches"),
            "avg_train_accuracy": weighted_mean(rows, "train_accuracy", "n_train_matches"),
        }
    ]


def weighted_mean(rows: list[dict[str, object]], value_key: str, weight_key: str) -> float:
    num = 0.0
    den = 0.0
    for row in rows:
        w = float(row[weight_key])
        num += float(row[value_key]) * w
        den += w
    return num / den if den else float("nan")


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    extras = load_match_extras(args.db, args.min_year)
    samples = build_samples(action_rows, extras)
    by_issue = group_samples_by_issue(samples)
    issues = issue_order(samples)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    ticket_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    pred_rows: list[dict[str, object]] = []
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    action_by_issue: dict[str, list[ActionRow]] = defaultdict(list)
    for row in action_rows:
        action_by_issue[row.issue].append(row)

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues:issue_idx]
        train_samples = [s for issue in train_issues for s in by_issue[issue]]
        test_samples = by_issue[test_issue]
        if len(train_samples) < args.min_train_matches:
            continue

        model = fit_model(train_samples, l2=args.l2, maxiter=args.maxiter, feature_set=args.feature_set)
        probs = predict_proba(test_samples, model)
        market = market_probs(test_samples)
        _, y_test = feature_tensor(test_samples, model.ctx, model.feature_set)
        pred_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "train_logloss": model.train_logloss,
                "train_accuracy": model.train_accuracy,
                "model_logloss": logloss(probs, y_test),
                "market_logloss": logloss(market, y_test),
                "model_accuracy": accuracy(probs, y_test),
                "market_accuracy": accuracy(market, y_test),
            }
        )

        legs = build_model_legs(
            test_samples,
            probs,
            min_proxy_odds=args.baseline_min_proxy_odds,
            max_proxy_odds=args.baseline_max_proxy_odds,
            min_score_factor=threshold,
        )
        full_rows = full_cover_lookup(action_by_issue[test_issue])
        tickets = make_tickets(
            legs,
            strategy="result_model_high_sp",
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            full_rows=full_rows,
            action_model={},
            protect_full_count=0,
        )
        ticket_rows.extend(settle_ticket(t) for t in tickets)

        train_action_rows = [r for issue in train_issues for r in action_by_issue[issue]]
        q_model, global_q = train_q_model(
            train_action_rows,
            snapshot=args.snapshot,
            prior_n=args.q_prior_n,
        )
        veto_legs = build_q_model_veto_legs(
            action_by_issue[test_issue],
            q_model,
            global_q,
            probs,
            test_samples,
            snapshot=args.snapshot,
            min_proxy_odds=args.baseline_min_proxy_odds,
            max_proxy_odds=args.baseline_max_proxy_odds,
            min_score_factor=threshold,
            min_model_p=args.filter_min_model_p,
            min_model_market_ratio=args.filter_min_model_market_ratio,
        )
        veto_tickets = make_tickets(
            veto_legs,
            strategy="q_baseline_model_veto",
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            full_rows=full_rows,
            action_model={},
            protect_full_count=0,
        )
        ticket_rows.extend(settle_ticket(t) for t in veto_tickets)
        window_rows.append(
            {
                "test_issue": test_issue,
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_candidate_legs": len(legs),
                "n_tickets": len(tickets),
                "n_veto_candidate_legs": len(veto_legs),
                "n_veto_tickets": len(veto_tickets),
                "threshold_factor": threshold,
            }
        )

    summary = summarize_tickets(ticket_rows)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "result_model_tickets.csv", ticket_rows)
    write_csv(out / "result_model_summary.csv", summary)
    write_csv(out / "result_model_windows.csv", window_rows)
    write_csv(out / "result_model_prediction_metrics.csv", pred_rows)

    report = [
        "# Beidan N=7 result model evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- N legs: `{args.n_legs}`",
        f"- Max tickets per issue: `{args.max_tickets_per_issue}`",
        f"- Proxy odds band: `{args.baseline_min_proxy_odds}` to `{args.baseline_max_proxy_odds}`",
        f"- L2: `{args.l2}`",
        f"- Feature set: `{args.feature_set}`",
        f"- Q veto: model_p >= `{args.filter_min_model_p}`, model/market >= `{args.filter_min_model_market_ratio}`",
        "",
        "## Prediction Metrics",
        md_table(compact_pred_metrics(pred_rows)),
        "## Ticket Summary",
        md_table(summary),
        "## Window Sample",
        md_table(window_rows[:40]),
        "",
        "## Files",
        "",
        "- `result_model_summary.csv`",
        "- `result_model_tickets.csv`",
        "- `result_model_prediction_metrics.csv`",
        "- `result_model_windows.csv`",
        "",
    ]
    (out / "result_model_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'result_model_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows and {len(pred_rows)} prediction windows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/beidan_result_model_n7"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--filter-min-model-p", type=float, default=0.0)
    parser.add_argument("--filter-min-model-market-ratio", type=float, default=1.0)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--l2", type=float, default=0.03)
    parser.add_argument(
        "--feature-set",
        choices=("base", "kelly", "priors", "extras", "rich", "team", "team_rich"),
        default="rich",
    )
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--min-train-matches", type=int, default=300)
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
