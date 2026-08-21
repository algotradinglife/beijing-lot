from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from issue302.evaluation import capital_path, scale_expert_weights
from issue302.panel import EXPERT_IDS, action_ledger, build_panel

ROOT = Path(__file__).resolve().parents[2]


def test_panel_is_exact_common_support_and_excludes_nuisance_expert() -> None:
    issues, experts = build_panel(ROOT)
    assert len(issues) == 227
    assert len(experts) == 227 * 4
    assert set(experts["expert_id"]) == set(EXPERT_IDS)
    assert "Q_WOR_M64" not in set(experts["expert_id"])
    assert issues["issue_year"].max() == 2023


def test_action_ledger_preserves_atomic_best_full() -> None:
    issues, experts = build_panel(ROOT)
    actions = action_ledger(issues, experts)
    baseline = actions[actions["action_id"].eq("B0_BEST_FULL")]
    active = baseline["stake_unit_cny"].gt(0)
    assert baseline.loc[active, "stake_unit_cny"].eq(4374.0).all()
    assert actions.groupby("issue")["action_id"].nunique().eq(5).all()


def test_atomic_baseline_is_not_fractionally_replicated() -> None:
    issues, experts = build_panel(ROOT)
    actions = action_ledger(issues, experts)
    issue = issues[issues["baseline_active"].eq(1)].head(1)
    local_actions = actions[actions["issue"].isin(issue["issue"])]
    decisions = issue[["issue", "issue_year"]].assign(
        condition="TEST", keep_baseline=True,
        predicted_baseline_utility_cny=1.0, weight_CASH=1.0,
        **{f"weight_{expert}": 0.0 for expert in EXPERT_IDS},
    )
    path = capital_path(issue, local_actions, decisions)
    assert path.loc[0, "stake_cny"] == 4374.0
    assert bool(path.loc[0, "baseline_executed"])


def test_funding_scale_preserves_simplex() -> None:
    row = {
        "issue": 1, "issue_year": 2023, "condition": "RAW",
        "keep_baseline": True, "predicted_baseline_utility_cny": 1.0,
        "weight_CASH": 0.2,
        **{f"weight_{expert}": 0.2 for expert in EXPERT_IDS},
    }
    scaled = scale_expert_weights(pd.DataFrame([row]), 0.25, "SCALED")
    columns = [f"weight_{expert}" for expert in EXPERT_IDS] + ["weight_CASH"]
    assert np.allclose(scaled[columns].sum(axis=1), 1.0)
    assert scaled.loc[0, "weight_CASH"] == 0.8


def test_committed_result_is_relative_signal_not_expert_placement() -> None:
    decision = json.loads((ROOT / "results/issue-302/decision.json").read_text())["decision"]
    assert decision["verdict"] == "RELATIVE_SIGNAL"
    assert decision["promotable"] is False
    assert decision["primary_2023_capital_growth_pct"] > 0
    assert decision["causally_selected_2023_expert_funding_scale"] == 0
    assert decision["expert_allocation_increment_cny"] == 0
    assert decision["placement_vs_permutation_percentile"] < 0.95
