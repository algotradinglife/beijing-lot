from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from issue299.experiment import FEATURE_COLUMNS
from issue299.model import fit_residual_ensemble, select_actions
from issue299.panel import build_action_panel

ROOT = Path(__file__).resolve().parents[2]


def test_negative_scores_fall_back_to_baseline() -> None:
    scores = pd.DataFrame(
        {
            "issue": [1, 1],
            "issue_year": [2023, 2023],
            "condition": ["X", "X"],
            "action": ["BASELINE_ONLY", "BASELINE_PLUS_TAIL"],
            "utility_cny": [0.0, -1.0],
        }
    )
    chosen = select_actions(scores)
    assert chosen.loc[0, "action"] == "BASELINE_ONLY"
    assert not bool(chosen.loc[0, "activated"])


def test_model_refuses_2024_rows() -> None:
    issues, actions = build_action_panel(ROOT)
    sealed = issues.copy()
    sealed.loc[sealed.index[-1], "issue_year"] = 2024
    with pytest.raises(AssertionError, match="2024"):
        fit_residual_ensemble(
            sealed,
            actions,
            feature_columns=FEATURE_COLUMNS,
            condition="LEARNED_RESIDUAL",
            seeds=(1,),
        )
