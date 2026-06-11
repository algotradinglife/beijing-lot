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
