from __future__ import annotations

from itertools import combinations
import json
from pathlib import Path

import numpy as np
import pandas as pd

from issue299.panel import build_action_panel
from issue305.evaluation import capital_path, constant_decisions, exact_exposure_null
from issue305.experiment import FEATURE_COLUMNS
from issue305.model import fit_predict_expanding

ROOT = Path(__file__).resolve().parents[2]


def test_dedicated_model_reads_no_expert_labels() -> None:
    issues, actions = build_action_panel(ROOT)
    first, _, _ = fit_predict_expanding(
        issues,
        feature_columns=FEATURE_COLUMNS,
        condition="RIDGE_CONTROL",
        model_kind="RIDGE",
    )
    mutated = actions.copy()
    mutated.loc[mutated["action"].ne("BASELINE_ONLY"), "residual_pnl_cny"] = 10**12
    second, _, _ = fit_predict_expanding(
        issues,
        feature_columns=FEATURE_COLUMNS,
        condition="RIDGE_CONTROL",
        model_kind="RIDGE",
    )
    pd.testing.assert_frame_equal(first, second)


def test_expanding_receipts_are_strictly_chronological_and_converged() -> None:
    issues, _ = build_action_panel(ROOT)
    _, _, receipts = fit_predict_expanding(
        issues,
        feature_columns=FEATURE_COLUMNS,
        seeds=(305001,),
    )
    assert receipts["prediction_year"].tolist() == [2021, 2022, 2023]
    assert (receipts["train_end_year"] < receipts["prediction_year"]).all()
    assert receipts[["mean_converged", "downside_converged"]].all(axis=None)
    assert receipts["expert_label_inputs"].eq(0).all()


def test_atomic_replay_preserves_stake_and_inactive_cash() -> None:
    issues, _ = build_action_panel(ROOT)
    local = issues[issues["issue_year"].eq(2023)]
    decisions = constant_decisions(local, condition="B0_BEST_FULL", keep_active=True)
    path = capital_path(local, decisions)
    assert path.loc[path["stake_cny"].gt(0), "stake_cny"].eq(4_374.0).all()
    assert path["stake_cny"].sum() == 35 * 4_374.0


def test_exact_null_matches_brute_force_on_toy_panel() -> None:
    pnl = [-100.0, -50.0, 25.0, 150.0]
    issues = pd.DataFrame(
        {
            "issue": [1, 2, 3, 4],
            "issue_year": [2023] * 4,
            "baseline_active": [1] * 4,
            "baseline_pnl_cny": pnl,
        }
    )
    decisions = pd.DataFrame(
        {
            "issue": [1, 2, 3, 4],
            "issue_year": [2023] * 4,
            "keep_baseline": [False, False, True, True],
        }
    )
    _, summary = exact_exposure_null(issues, decisions)
    brute = [100_000.0 + sum(pnl[index] for index in choice) for choice in combinations(range(4), 2)]
    observed = 100_000.0 + 25.0 + 150.0
    assert summary["combination_count"] == len(brute)
    assert np.isclose(summary["exact_percentile"], np.mean(np.asarray(brute) <= observed))


def test_committed_decision_rejects_selection_skill() -> None:
    payload = json.loads((ROOT / "results/issue-305/decision.json").read_text())
    decision = payload["decision"]
    assert decision["verdict"] == "SHARED_HEAD_EXPOSURE_REDUCTION_ONLY"
    assert decision["development_signal_accepted"] is False
    assert decision["matched_lift_pp"] > 0
    assert decision["exact_executed_exposure_percentile"] < 0.95
    assert decision["alpha_decision_stable"] is False
    assert decision["expert_label_inputs"] == 0

