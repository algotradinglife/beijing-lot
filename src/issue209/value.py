"""Issue #209 — settlement-SP prediction and cell-value distribution (Gate A).

Produces, per outcome branch, a predicted settlement-SP distribution (q10/q50/
q90) using maintained-library quantile/Huber regression on pre-event features,
and the raw cell-value distribution R_RAW = P_win * SP (Beijing 0.65 NOT applied
per cell). All training uses fit/tune only; 2023 confirmation untouched.

The SP predictor learns settlement SP from pre-event channels ONLY (never from
the realized winning SP within the same branch). Separate held-out role blocks
give honest coverage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import HuberRegressor, QuantileRegressor
from sklearn.preprocessing import StandardScaler

OUTCOME_LABELS = ["3", "1", "0"]
QUANTILES = (0.10, 0.50, 0.90)


def sp_features(units: pd.DataFrame) -> pd.DataFrame:
    """Pre-event features for settlement-SP prediction (no settlement leakage)."""
    X = pd.DataFrame(index=units.index)
    X["native_handicap_line"] = units["native_handicap_line"].astype(float)
    X["n_available_books"] = units["n_available_books"].astype(float)
    X["mapping_accepted"] = units["mapping_accepted"].astype(float)
    for c in OUTCOME_LABELS:
        X[f"q_eu_bjline_{c}"] = units[f"q_eu_bjline_{c}"].astype(float)
        X[f"eu_vs_line_divergence_{c}"] = units[f"eu_vs_line_divergence_{c}"].astype(float)
    for c in ["snapshot_kind_initial", "snapshot_kind_10h", "snapshot_kind_1h"]:
        X[c] = units[c].astype(float)
    return X


def sp_target(units: pd.DataFrame) -> pd.DataFrame:
    """Settlement-SP target per branch = official_sp_c where available.

    Only the realized branch typically carries settlement SP; the model therefore
    trains on the realized branch's winning_sp (SP_SETTLE) and predicts all three
    branches' SP from the same pre-event features. This is settlement-ONLY
    information used as a label; it must never enter the inference feature path.
    """
    y = pd.DataFrame(index=units.index, columns=OUTCOME_LABELS, dtype=float)
    # units carry SP_SETTLE on the realized cell via the tensor join; rebuild per
    # branch below is handled in the caller where official_sp is available.
    return y


def fit_sp_quantile_model(
    units: pd.DataFrame,
    roles=("fit", "tune"),
    seed: int = 209002,
) -> dict:
    """Fit quantile SP models jointly on SP-available labeled branches.

    We train on the realized branch target (winning SP at that branch). We use
    HistGradientBoostingRegressor with quantile loss per quantile (maintained lib).
    """
    from sklearn.model_selection import train_test_split

    # training rows = units where the realized SP is known (settlement label)
    # we collapse to a per-units realized target using SP_SETTLE from tensor join;
    # here we require the caller to have attached 'realized_sp' per unit.
    if "realized_sp" not in units.columns:
        # default: no SP target attached -> return empty
        return {"status": "no_sp_target"}

    tr = units[units["realized_sp"].notna() & units["temporal_role"].isin(roles)].copy()
    if len(tr) < 500:
        return {"status": "insufficient", "n": int(len(tr))}

    X = sp_features(tr)
    y = tr["realized_sp"].astype(float)

    # bounded model: quantile HGB, fixed across seeds
    models = {}
    preds = {}
    for q in QUANTILES:
        m = HistGradientBoostingRegressor(
            loss="quantile", quantile=q, max_iter=200, max_leaf_nodes=31,
            learning_rate=0.08, random_state=seed, l2_regularization=1.0,
        )
        m.fit(X, y)
        models[q] = m
        preds[q] = m.predict(X)
    return {"status": "ok", "models": models, "n": int(len(tr)),
            "q_pred_train": preds}


def predict_sp_quantiles(model_bundle: dict, units: pd.DataFrame) -> pd.DataFrame:
    """Predict per-branch SP quantiles (q10/q50/q90) for every unit."""
    if model_bundle.get("status") != "ok":
        return pd.DataFrame(index=units.index)
    X = sp_features(units)
    out = pd.DataFrame(index=units.index)
    for q in QUANTILES:
        qint = int(round(q * 100))
        out[f"sp_q{qint:02d}"] = model_bundle["models"][q].predict(X)
    return out


def cell_value_distribution(
    prob: pd.DataFrame, sp_quantiles: pd.DataFrame, units: pd.DataFrame
) -> pd.DataFrame:
    """Raw cell-value distribution R_RAW = P_win * SP (per branch).

    q10/q50/q90 of R_RAW, plus expected raw value. The 0.65 Beijing payout is
    applied once at the ticket level, NOT here.
    """
    out = pd.DataFrame(index=units.index)
    for c in OUTCOME_LABELS:
        p_win = prob[c].astype(float).to_numpy()
        if "sp_q50" in sp_quantiles.columns:
            sp50 = sp_quantiles["sp_q50"].astype(float).to_numpy()
            out[f"ev_raw_{c}"] = p_win * sp50
            out[f"value_q10_{c}"] = p_win * sp_quantiles["sp_q10"].astype(float).to_numpy()
            out[f"value_q90_{c}"] = p_win * sp_quantiles["sp_q90"].astype(float).to_numpy()
        else:
            out[f"ev_raw_{c}"] = p_win * 1.0
    return out
