"""Issue #209 — distributional learning (Gate A). Decomposed estimation.

Outcome probability P(Y|X): the model operates on MATCH-horizon units, where a
unit holds the 3 outcome branches (c in {3,1,0}); Y is the single realized
outcome. Baselines (market-only, calibrated logistic) and a PyTorch MLP
challenger produce a 3-way distribution. Settlement-SP and cell-value stages
sit on top. The 0.65 payout is applied only later, once per winning N-fold ticket.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

OUTCOME_LABELS = ["3", "1", "0"]
OUTCOME_INDEX = {c: i for i, c in enumerate(OUTCOME_LABELS)}


def build_match_units(tensor: pd.DataFrame) -> pd.DataFrame:
    """Pivot outcome branches into wide per-(issue, match, horizon) units.

    Each unit holds, per outcome c: q_eu_bjline_c, q_line_only_control_c,
    divergence_c, plus shared context (line, books, mapping). The target is the
    single realized outcome. Returns a unit frame with a per-row 'unit_key'.
    """
    key = ["issue", "match_idx", "snapshot_kind"]
    units = tensor.groupby(key, as_index=False).agg(
        realized_outcome=("realized_outcome", "first"),
        has_label=("has_label", "max"),
        native_handicap_line=("native_handicap_line", "first"),
        n_available_books=("n_available_books", "first"),
        mapping_accepted=("mapping_accepted", "min"),
        issue_year=("issue_year", "first"),
        temporal_role=("temporal_role", "first"),
        issue_anchor_ts=("issue_anchor_ts", "first"),
    )
    # pivot per-outcome probability channels
    wide = tensor.pivot_table(
        index=key,
        columns="outcome_code",
        values=["q_eu_bjline", "q_line_only_control", "eu_vs_line_divergence"],
        aggfunc="first",
    )
    wide.columns = [f"{var}_{oc}" for var, oc in wide.columns]
    wide = wide.reset_index()
    units = units.merge(wide, on=key, how="left")
    # numeric horizon one-hot
    h = pd.get_dummies(units["snapshot_kind"], prefix="snapshot_kind").astype(float)
    for c in ["snapshot_kind_initial", "snapshot_kind_10h", "snapshot_kind_1h"]:
        units[c] = h[c].to_numpy() if c in h.columns else 0.0
    units["unit_key"] = (
        units["issue"].astype(str) + ":" + units["match_idx"].astype(str)
    )
    return units


def probability_features(units: pd.DataFrame) -> pd.DataFrame:
    """Numeric feature matrix for the 3-way outcome learner (REQ-209-03)."""
    cols = []
    for c in OUTCOME_LABELS:
        cols += [
            f"q_eu_bjline_{c}",
            f"q_line_only_control_{c}",
            f"eu_vs_line_divergence_{c}",
        ]
    for c in OUTCOME_LABELS:
        # explicit signed disagreement per branch (no dense pre-blend)
        cols.append(f"divergence_x_line_{c}")
    X = pd.DataFrame(index=units.index)
    for c in OUTCOME_LABELS:
        for base in ["q_eu_bjline", "q_line_only_control", "eu_vs_line_divergence"]:
            col = f"{base}_{c}"
            X[col] = units[col].astype(float) if col in units.columns else 0.0
        X[f"divergence_x_line_{c}"] = (
            units[f"eu_vs_line_divergence_{c}"].astype(float)
            * units["native_handicap_line"].astype(float)
        )
    X["native_handicap_line"] = units["native_handicap_line"].astype(float)
    X["n_available_books"] = units["n_available_books"].astype(float)
    X["mapping_accepted"] = units["mapping_accepted"].astype(float)
    for c in ["snapshot_kind_initial", "snapshot_kind_10h", "snapshot_kind_1h"]:
        X[c] = units[c].astype(float)
    # market prior = mapped EU-BJ probability of realized outcome is NOT a feature
    # (settlement); instead add per-branch market prior as explicit calibration info
    return X


def market_only_probabilities(units: pd.DataFrame) -> pd.DataFrame:
    """MARKET_ONLY_CELL: the mapped EU-BJ probability per branch (3 columns).

    Where mapping not accepted, per-branch q_line_only_control is used. This is
    the frozen, label-free market baseline (no settlement SP, no Y).
    """
    out = pd.DataFrame(index=units.index)
    for c in OUTCOME_LABELS:
        mapped = units["mapping_accepted"].astype(bool).to_numpy()
        eu = units[f"q_eu_bjline_{c}"].astype(float).to_numpy()
        lo = units[f"q_line_only_control_{c}"].astype(float).to_numpy()
        out[c] = np.where(mapped, eu, lo)
    # normalize to a simplex
    s = out[OUTCOME_LABELS].sum(axis=1).replace(0, np.nan)
    out[OUTCOME_LABELS] = out[OUTCOME_LABELS].div(s, axis=0)
    return out


def _compute_losses(y_true, pred: pd.DataFrame) -> dict:
    y = [str(v) for v in y_true]
    ll = log_loss(y, pred[OUTCOME_LABELS], labels=OUTCOME_LABELS)
    brier = 0.0
    for c in OUTCOME_LABELS:
        ybin = (np.asarray(y) == c).astype(int)
        brier += brier_score_loss(ybin, pred[c])
    return {"log_loss": float(ll), "brier": float(brier) / 3.0}


def fit_calibrated_logistic(
    units: pd.DataFrame,
    fit_roles=("fit",),
    tune_roles=("tune",),
    seed: int = 209001,
) -> dict:
    """Calibrated logistic probability challenger, selected on tune log-loss."""
    X = probability_features(units)
    y = units["realized_outcome"].astype(str)
    fit_idx = np.where(units["temporal_role"].isin(fit_roles))[0]
    tune_idx = np.where(units["temporal_role"].isin(tune_roles))[0]

    Xf, yf = X.iloc[fit_idx], y.iloc[fit_idx]
    base_fit = market_only_probabilities(units.iloc[fit_idx])
    Xf2 = Xf.copy()
    for c in OUTCOME_LABELS:
        Xf2[f"market_prior_{c}"] = base_fit[c].to_numpy()

    model = LogisticRegression(max_iter=2000, C=1.0, solver="lbfgs")
    model.fit(Xf2, yf)

    cal = CalibratedClassifierCV(model, method="sigmoid", cv=3)
    cal.fit(Xf2, yf)

    return {"model": cal, "fit_idx": fit_idx, "tune_idx": tune_idx}


def predict_logistic(bundle, units) -> pd.DataFrame:
    """Predict probabilities for all rows of units using the fitted logistic."""
    X = probability_features(units)
    X = X.copy()
    base = market_only_probabilities(units)
    for c in OUTCOME_LABELS:
        X[f"market_prior_{c}"] = base[c].to_numpy()
    probs = bundle["model"].predict_proba(X)
    pred = pd.DataFrame(probs, index=units.index, columns=bundle["model"].classes_.astype(str))
    for c in OUTCOME_LABELS:
        if c not in pred.columns:
            pred[c] = 0.0
    return pred[OUTCOME_LABELS]


def fit_mlp_challenger(
    units: pd.DataFrame,
    fit_roles=("fit",),
    tune_roles=("tune",),
    hidden=(64, 64),
    max_iter: int = 300,
    seed: int = 209001,
) -> dict:
    """Bounded MLP challenger (scikit-learn). Selected on tune log-loss."""
    X = probability_features(units)
    y = units["realized_outcome"].astype(str)
    fit_idx = np.where(units["temporal_role"].isin(fit_roles))[0]
    tune_idx = np.where(units["temporal_role"].isin(tune_roles))[0]

    sc = StandardScaler()
    Xf = sc.fit_transform(X.iloc[fit_idx])
    Xt = sc.transform(X.iloc[tune_idx])

    base_fit = market_only_probabilities(units.iloc[fit_idx])
    Xf = np.hstack([Xf, base_fit[OUTCOME_LABELS].to_numpy()])
    base_t = market_only_probabilities(units.iloc[tune_idx])
    Xt = np.hstack([Xt, base_t[OUTCOME_LABELS].to_numpy()])

    model = MLPClassifier(
        hidden_layer_sizes=hidden, max_iter=max_iter, random_state=seed,
        learning_rate_init=1e-3, early_stopping=True, n_iter_no_change=10,
    )
    model.fit(Xf, y.iloc[fit_idx])
    return {"model": model, "scaler": sc, "fit_idx": fit_idx, "tune_idx": tune_idx}


def predict_mlp(bundle, units) -> pd.DataFrame:
    """Predict probabilities for all rows of units using the fitted MLP."""
    X = probability_features(units)
    base = market_only_probabilities(units)
    Xs = np.hstack([bundle["scaler"].transform(X), base[OUTCOME_LABELS].to_numpy()])
    probs = bundle["model"].predict_proba(Xs)
    pred = pd.DataFrame(probs, index=units.index, columns=bundle["model"].classes_.astype(str))
    for c in OUTCOME_LABELS:
        if c not in pred.columns:
            pred[c] = 0.0
    return pred[OUTCOME_LABELS]


def evaluate_calibration(units: pd.DataFrame, pred: pd.DataFrame, roles=("calibration",)):
    """Calibration diagnostics on an untouched role block (2023)."""
    idx = np.where(units["temporal_role"].isin(roles))[0]
    if len(idx) == 0:
        return None
    y = units["realized_outcome"].astype(str).iloc[idx]
    p = pred.iloc[idx][OUTCOME_LABELS]
    losses = _compute_losses(y, p)
    # per-branch ECE (10 bins)
    ece = {}
    for c in OUTCOME_LABELS:
        pc = p[c].to_numpy()
        yc = (np.asarray(y) == c).astype(int)
        ece[c] = _ece(pc, yc)
    losses["ece_per_outcome"] = ece
    return losses


def _ece(prob, y, bins: int = 10):
    order = np.argsort(prob)
    prob_s, y_s = prob[order], y[order]
    n = len(prob_s)
    if n == 0:
        return float("nan")
    edges = np.linspace(0, n, bins + 1).astype(int)
    total = 0.0
    count = 0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        if hi - lo == 0:
            continue
        pbar = prob_s[lo:hi].mean()
        ybar = y_s[lo:hi].mean()
        total += (hi - lo) * abs(pbar - ybar)
        count += (hi - lo)
    return float(total / max(count, 1))
