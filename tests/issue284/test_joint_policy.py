import numpy as np
import pandas as pd

from issue282.features import ISSUE_STATE_FEATURES
from issue284.joint_policy import (
    JOINT_FEATURES,
    build_joint_action_table,
    select_policy,
)


def _state() -> pd.DataFrame:
    row = {feature: 1.0 for feature in ISSUE_STATE_FEATURES}
    return pd.DataFrame([{"issue": "x", **row}])


def _raw() -> pd.DataFrame:
    rows = []
    for n, generator, k, realized, expected in (
        (7, "WEIGHTED_WR", 128, -20.0, -15.0),
        (7, "TOP_VALUE", 8, -5.0, 50.0),
    ):
        for family in ("UNIFORM", "VALUE_WEIGHTED"):
            for replica in (1, 2) if generator == "WEIGHTED_WR" else (0,):
                rows.append(
                    {
                        "issue": "x",
                        "issue_year": 2020,
                        "n": n,
                        "proposal_family": family,
                        "subset_id": f"{family}-{n}",
                        "generator": generator,
                        "requested_k": k,
                        "stream_replica": replica,
                        "normalized_pnl_cny100": realized + replica,
                        "model_expected_pnl_cny100": expected,
                    }
                )
    return pd.DataFrame(rows)


def test_joint_table_averages_nuisance_and_matches_baseline() -> None:
    table = build_joint_action_table(_raw(), _state())
    baseline = table.loc[
        table["action_key"].eq("N7_WEIGHTED_WR_K128_FENSEMBLE")
    ].iloc[0]
    candidate = table.loc[
        table["action_key"].eq("N7_TOP_VALUE_K8_FENSEMBLE")
    ].iloc[0]
    assert baseline["realized_roi_pct"] == -18.5
    assert baseline["realized_lift_pct"] == 0.0
    assert candidate["realized_lift_pct"] == 13.5
    assert np.isclose(table["issue_training_weight"].sum(), 1.0)
    assert set(JOINT_FEATURES).issubset(table.columns)
    assert not set(JOINT_FEATURES).intersection(
        {"realized_roi_pct", "realized_lift_pct", "baseline_realized_roi_pct"}
    )


def test_policy_falls_back_when_lower_score_is_not_positive() -> None:
    table = build_joint_action_table(_raw(), _state())
    table["score"] = np.arange(len(table), dtype=float)
    table["lower"] = -1.0
    selected = select_policy(
        table,
        score_column="score",
        fallback_column="lower",
        policy="SAFE",
    )
    assert selected.iloc[0]["action_key"] == "N7_WEIGHTED_WR_K128_FENSEMBLE"
    assert bool(selected.iloc[0]["used_fallback"])
