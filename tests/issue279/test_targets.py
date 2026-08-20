import numpy as np
import pandas as pd

from issue279.targets import add_budget_matched_targets


def _surface() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"issue": "A", "issue_year": 2023, "action_key": "NO_BET", "n": 0, "k": 0, "generator": "NO_BET", "stake_total": 0.0, "mean_pnl": 0.0},
            {"issue": "A", "issue_year": 2023, "action_key": "N7_K8_X", "n": 7, "k": 8, "generator": "X", "stake_total": 16.0, "mean_pnl": 4.0},
            {"issue": "A", "issue_year": 2023, "action_key": "N7_K32_X", "n": 7, "k": 32, "generator": "X", "stake_total": 64.0, "mean_pnl": 8.0},
        ]
    )


def test_budget_matching_removes_turnover_advantage() -> None:
    result = add_budget_matched_targets(_surface())
    k8 = result[result.action_key.eq("N7_K8_X")].iloc[0]
    k32 = result[result.action_key.eq("N7_K32_X")].iloc[0]
    assert k8.budget_matched_pnl == 4.0
    assert k32.budget_matched_pnl == 2.0
    assert k8.budget_matched_rank_pct > k32.budget_matched_rank_pct


def test_no_bet_remains_zero_and_marginal_k_is_explicit() -> None:
    result = add_budget_matched_targets(_surface())
    no_bet = result[result.action_key.eq("NO_BET")].iloc[0]
    k32 = result[result.action_key.eq("N7_K32_X")].iloc[0]
    assert no_bet.budget_matched_pnl == 0.0
    assert np.isnan(no_bet.marginal_k_pnl_per_cny)
    assert k32.marginal_k_stake == 48.0
    assert k32.marginal_k_pnl == 4.0
    assert np.isclose(k32.marginal_k_pnl_per_cny, 4.0 / 48.0)
