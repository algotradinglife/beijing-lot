"""Issue #306 focused tests: causal discipline, tamper resistance, invariants."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from issue306.panel import FEATURE_COLUMNS, action_ledger, build_issue_table, build_panel
from issue306.portfolio import allocate_integer_bundles, composition_from_value
from issue306.stage_a import fit_local_reference, stage_a_decisions
from issue306.value_model import fit_predict_expanding


@pytest.fixture(scope="module")
def panel_data():
    issues, experts = build_panel(".")
    issue_table = build_issue_table(".")
    actions = action_ledger(issue_table, experts)
    return issues, issue_table, actions


def test_2024_sealed(panel_data):
    _, issue_table, _ = panel_data
    assert issue_table["issue_year"].max() <= 2023


def test_support_matches_baseline_count(panel_data):
    _, issue_table, _ = panel_data
    assert len(issue_table) == 227
    assert int(issue_table["baseline_active"].sum()) == 122


def test_stage_a_expert_label_invariance(panel_data):
    """Mutating any expert label must leave Stage A byte-identical.

    Stage A fits only on issue features + BEST_FULL labels.  Expert columns are
    not read at all; we still mutate them to prove the fit is invariant.
    """

    _, issue_table, _ = panel_data
    base = fit_local_reference(issue_table, feature_columns=FEATURE_COLUMNS)
    mutated = issue_table.copy()
    # The #299 action panel has no per-expert columns, so Stage A structurally
    # cannot depend on them; add and mutate them to prove byte invariance.
    for expert in ["SMOOTH_M512", "Q_TAIL_M192", "DIVERGENCE_Z100_K1", "RARE_LOGIT_TOP64"]:
        mutated[f"pnl_{expert}"] = np.arange(len(mutated)) * 1000.0 + 7.0
        mutated[f"stake_{expert}"] = np.arange(len(mutated)) * 3.0 + 1.0
    alt = fit_local_reference(mutated, feature_columns=FEATURE_COLUMNS)
    assert base.scores["predicted_utility_cny"].equals(alt.scores["predicted_utility_cny"])


def test_stage_a_source_tag(panel_data):
    _, issue_table, _ = panel_data
    fit = fit_local_reference(issue_table, feature_columns=FEATURE_COLUMNS)
    assert fit.source == "LOCAL_REFERENCE_FIT_PENDING_305"
    decisions = stage_a_decisions(issue_table, fit)
    assert (decisions["stage_a_source"] == "LOCAL_REFERENCE_FIT_PENDING_305").all()
    assert set(decisions["keep_baseline"].unique()) <= {True, False}


def test_composition_weights_nonnegative_and_sum(panel_data):
    _, issue_table, actions = panel_data
    scores, _, _ = fit_predict_expanding(
        issue_table, actions, feature_columns=FEATURE_COLUMNS
    )
    comp = composition_from_value(scores, objective="log_wealth")
    expert_cols = [f"weight_{e}" for e in ["SMOOTH_M512", "Q_TAIL_M192", "DIVERGENCE_Z100_K1", "RARE_LOGIT_TOP64"]]
    assert (comp[expert_cols] >= -1e-12).all(axis=None)
    totals = comp[expert_cols].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=1e-9)


def test_integer_bundles_never_exceed_budget(panel_data):
    issue_row = pd.Series(
        {
            "available_SMOOTH_M512": True,
            "stake_SMOOTH_M512": 1024.0,
            "pnl_SMOOTH_M512": 200.0,
            "gross_SMOOTH_M512": 1224.0,
            "available_Q_TAIL_M192": True,
            "stake_Q_TAIL_M192": 1536.0,
            "pnl_Q_TAIL_M192": -150.0,
            "gross_Q_TAIL_M192": 0.0,
            "available_DIVERGENCE_Z100_K1": True,
            "stake_DIVERGENCE_Z100_K1": 4374.0,
            "pnl_DIVERGENCE_Z100_K1": -4374.0,
            "gross_DIVERGENCE_Z100_K1": 0.0,
            "available_RARE_LOGIT_TOP64": True,
            "stake_RARE_LOGIT_TOP64": 128.0,
            "pnl_RARE_LOGIT_TOP64": 512.0,
            "gross_RARE_LOGIT_TOP64": 640.0,
        }
    )
    composition = pd.Series(
        {
            "weight_SMOOTH_M512": 0.3,
            "weight_Q_TAIL_M192": 0.3,
            "weight_DIVERGENCE_Z100_K1": 0.2,
            "weight_RARE_LOGIT_TOP64": 0.2,
        }
    )
    result = allocate_integer_bundles(issue_row, composition, 0.5, initial_capital_cny=100_000.0)
    assert result["stake_cny"] <= 50_000.0 + 1e-6
    for expert in ["SMOOTH_M512", "Q_TAIL_M192", "DIVERGENCE_Z100_K1", "RARE_LOGIT_TOP64"]:
        assert result[f"copies_{expert}"] >= 0
        assert isinstance(result[f"copies_{expert}"], (int, np.integer))


def test_zero_intensity_deploys_nothing(panel_data):
    issue_row = pd.Series(
        {
            "available_SMOOTH_M512": True, "stake_SMOOTH_M512": 1024.0, "pnl_SMOOTH_M512": 1.0,
            "gross_SMOOTH_M512": 1.0,
            "available_Q_TAIL_M192": True, "stake_Q_TAIL_M192": 1536.0, "pnl_Q_TAIL_M192": 1.0,
            "gross_Q_TAIL_M192": 1.0,
            "available_DIVERGENCE_Z100_K1": True, "stake_DIVERGENCE_Z100_K1": 4374.0,
            "pnl_DIVERGENCE_Z100_K1": 1.0, "gross_DIVERGENCE_Z100_K1": 1.0,
            "available_RARE_LOGIT_TOP64": True, "stake_RARE_LOGIT_TOP64": 128.0,
            "pnl_RARE_LOGIT_TOP64": 1.0, "gross_RARE_LOGIT_TOP64": 1.0,
        }
    )
    composition = pd.Series(
        {
            "weight_SMOOTH_M512": 0.25, "weight_Q_TAIL_M192": 0.25,
            "weight_DIVERGENCE_Z100_K1": 0.25, "weight_RARE_LOGIT_TOP64": 0.25,
        }
    )
    result = allocate_integer_bundles(issue_row, composition, 0.0, initial_capital_cny=100_000.0)
    assert result["stake_cny"] == 0.0
    assert result["pnl_cny"] == 0.0