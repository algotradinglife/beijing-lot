import numpy as np
import pandas as pd

from issue282.features import ISSUE_STATE_FEATURES
from issue284.mode_policy import apply_mode_policy, build_mode_learning_table


def test_mode_table_and_policy_are_issue_level() -> None:
    actions = pd.DataFrame(
        [
            {
                "issue": "1",
                "issue_year": 2022,
                "proposal_family": "DIVERGENCE_WEIGHTED",
                "outcome_weight_mode": mode,
                "realized_roi_pct": roi,
            }
            for mode, roi in (("CELL_VALUE", -10.0), ("DIVERGENCE_VALUE", 20.0))
        ]
    )
    state = pd.DataFrame(
        [{"issue": "1", **dict.fromkeys(ISSUE_STATE_FEATURES, 1.0)}]
    )
    table = build_mode_learning_table(actions, state)
    assert len(table) == 1
    assert table.iloc[0]["realized_lift_pct"] == 30.0
    selected = apply_mode_policy(table, np.array([1.0]), policy="TEST")
    assert selected.iloc[0]["selected_mode"] == "DIVERGENCE_VALUE"
    assert selected.iloc[0]["matched_lift_to_cell_pct"] == 30.0
