"""Phase 1 descriptive drift statistics.

Two distinct quantities (see spec §7):
- drift_bias = E[final/decision - 1]   (signed; systematic bias; P2 haircut target)
- residual_drift = E[|final/decision - 1|]  (magnitude; P1 window / P4 timing target)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def drift_metrics(legs: pd.DataFrame) -> dict:
    """legs must have columns decision_sp, final_sp (both > 0).

    Returns drift_bias, residual_drift, favorable/stable/unfavorable shares, n.
    """
    df = legs[(legs["decision_sp"] > 0) & (legs["final_sp"] > 0)]
    if df.empty:
        return dict(n=0, drift_bias=float("nan"), residual_drift=float("nan"),
                    favorable_share=float("nan"), stable_share=float("nan"),
                    unfavorable_share=float("nan"))
    ratio = (df["final_sp"] / df["decision_sp"]).to_numpy()
    return dict(
        n=int(len(ratio)),
        drift_bias=float(np.mean(ratio - 1.0)),
        residual_drift=float(np.mean(np.abs(ratio - 1.0))),
        favorable_share=float(np.mean(ratio > 1.02)),
        stable_share=float(np.mean((ratio >= 0.98) & (ratio <= 1.02))),
        unfavorable_share=float(np.mean(ratio < 0.98)),
    )


def drift_by_mtk_bucket(legs: pd.DataFrame, edges: list[float]) -> pd.DataFrame:
    """Drift metrics grouped by the decision MTK bucket (decision_mtk column).
    `edges` are bucket boundaries in minutes, e.g. [0,30,60,120,360,720].
    """
    df = legs.copy()
    df["mtk_bucket"] = pd.cut(df["decision_mtk"], bins=edges)
    rows = []
    for bucket, grp in df.groupby("mtk_bucket", observed=True):
        m = drift_metrics(grp)
        m["mtk_bucket"] = str(bucket)
        m["mtk_lo"] = float(bucket.left)   # numeric sort key
        rows.append(m)
    return pd.DataFrame(rows)


_SP_EDGES = [(3.5, "<3.5"), (4.5, "3.5-4.5"), (5.0, "4.5-5"), (8.0, "5-8")]


def sp_band(sp: float) -> str:
    """Bucket an SP into the strategy-relevant bands."""
    for hi, label in _SP_EDGES:
        if sp < hi:
            return label
    return ">8"


def drift_by_cell(legs: pd.DataFrame, by: list[str], min_n: int = 1) -> pd.DataFrame:
    """Drift metrics per cell (group key `by`); cells with < min_n legs dropped.
    Sorted by drift_bias ascending (most adverse first)."""
    rows = []
    for key, grp in legs.groupby(by, observed=True):
        m = drift_metrics(grp)
        if m["n"] < min_n:
            continue
        for col, val in zip(by, key if isinstance(key, tuple) else (key,)):
            m[col] = val
        rows.append(m)
    out = pd.DataFrame(rows)
    return out.sort_values("drift_bias").reset_index(drop=True) if len(out) else out


def slice_consistency(legs: pd.DataFrame, slice_col: str, min_n: int = 30) -> dict:
    """Check whether drift_bias has the same sign across >=3 slices of slice_col.
    Implements the spec's multi-slice consistency standard."""
    cells = drift_by_cell(legs, by=[slice_col], min_n=min_n)
    biases = cells["drift_bias"].dropna()
    n_neg = int((biases < 0).sum())
    n_pos = int((biases > 0).sum())
    return dict(
        n_slices=int(len(biases)),
        n_negative=n_neg,
        n_positive=n_pos,
        consistent=bool(max(n_neg, n_pos) >= 3 and min(n_neg, n_pos) == 0),
    )


def winners_vs_all_bias(legs: pd.DataFrame) -> dict:
    """Compare drift_bias on winning legs only vs all legs, to expose the
    selection bias in the live -16.5% figure (which used winners only).
    `legs` needs is_winner, decision_sp, final_sp."""
    all_m = drift_metrics(legs)
    win_m = drift_metrics(legs[legs["is_winner"]])
    return dict(
        all_bias=all_m["drift_bias"], all_n=all_m["n"],
        winners_bias=win_m["drift_bias"], winners_n=win_m["n"],
        bias_gap=win_m["drift_bias"] - all_m["drift_bias"],
    )


def vol_imbalance_predictivity(legs: pd.DataFrame, vol_split: float = 40.0) -> dict:
    """Does a selection's own vol% share at decision time predict drift direction?
    Splits legs by decision_vol_pct >= vol_split and reports drift_bias of each
    group. Mechanism: high public share → SP keeps being bet down (negative bias).
    `legs` needs decision_vol_pct, decision_sp, final_sp."""
    hi = legs[legs["decision_vol_pct"] >= vol_split]
    lo = legs[legs["decision_vol_pct"] < vol_split]
    hm, lm = drift_metrics(hi), drift_metrics(lo)
    return dict(
        high_vol_bias=hm["drift_bias"], high_vol_n=hm["n"],
        low_vol_bias=lm["drift_bias"], low_vol_n=lm["n"],
        spread=hm["drift_bias"] - lm["drift_bias"],
    )
