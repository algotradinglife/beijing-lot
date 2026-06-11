import numpy as np
import pandas as pd

from src.sp_drift.drift_stats import drift_metrics


def _legs():
    # decision_sp -> final_sp: ratios 0.75 (down), 1.0 (flat), 1.25 (up)
    return pd.DataFrame({
        "decision_sp": [4.0, 4.0, 4.0],
        "final_sp": [3.0, 4.0, 5.0],
    })


def test_drift_bias_is_signed_mean_of_ratio_minus_one():
    m = drift_metrics(_legs())
    # mean(ratio) = (0.75 + 1.0 + 1.25)/3 = 1.0 → bias 0.0
    assert abs(m["drift_bias"]) < 1e-9


def test_residual_drift_is_mean_abs_and_positive():
    m = drift_metrics(_legs())
    # mean(|ratio-1|) = (0.25 + 0 + 0.25)/3
    assert abs(m["residual_drift"] - (0.5 / 3)) < 1e-9


def test_unfavorable_share():
    m = drift_metrics(_legs())
    # ratio < 0.98 → 1 of 3
    assert abs(m["unfavorable_share"] - 1 / 3) < 1e-9


from src.sp_drift.drift_stats import drift_by_mtk_bucket


def test_drift_by_mtk_bucket_returns_one_row_per_bucket():
    legs = pd.DataFrame({
        "decision_mtk": [200, 200, 20, 20],
        "decision_sp": [4.0, 4.0, 4.0, 4.0],
        "final_sp": [3.0, 3.0, 3.9, 3.9],
    })
    out = drift_by_mtk_bucket(legs, edges=[0, 60, 360]).sort_values("mtk_lo")
    # two buckets: (0,60] and (60,360]
    assert len(out) == 2
    near, far = out.iloc[0], out.iloc[1]   # sorted by left edge ascending
    # far-from-kickoff bucket has bigger residual drift than near
    assert far["residual_drift"] > near["residual_drift"]
