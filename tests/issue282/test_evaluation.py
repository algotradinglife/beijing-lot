import pandas as pd

from issue282.evaluation import (
    build_attribution_ledger,
    capital_path_metrics,
    choose_actions,
)


def test_choose_actions_uses_cash_when_every_score_is_nonpositive() -> None:
    labels = pd.DataFrame(
        {
            "issue": ["A", "A", "B", "B"],
            "issue_year": [2023] * 4,
            "action_key": ["X", "Y", "X", "Y"],
            "pnl_cny_mean": [10.0, -2.0, 5.0, -1.0],
            "stake_cny_mean": [2.0] * 4,
        }
    )
    selected = choose_actions(
        labels, [-1.0, -2.0, 2.0, 1.0], policy_name="MODEL"
    )
    assert selected["action_key"].tolist() == ["NO_BET", "X"]
    assert selected["pnl_cny_mean"].tolist() == [0.0, 5.0]


def test_capital_metrics_are_issue_level_and_matched() -> None:
    ledger = pd.DataFrame(
        {
            "issue": [str(i) for i in range(1, 7)],
            "issue_year": [2023] * 6,
            "action_key": ["M"] * 6,
            "pnl_cny_mean": [10.0, -5.0, -5.0, 20.0, -4.0, 1.0],
            "stake_cny_mean": [2.0] * 6,
        }
    )
    baseline = ledger.assign(action_key="B", pnl_cny_mean=0.0)
    metrics = capital_path_metrics(ledger, baseline=baseline)
    assert metrics["ending_capital_cny"] == 100_017.0
    assert metrics["max_consecutive_losing_issues"] == 2
    assert metrics["changed_action_issues"] == 6
    assert metrics["matched_lift_cny"] == 17.0
    assert metrics["ex_largest_matched_lift_cny"] == -3.0


def test_attribution_keeps_oracle_diagnostic_out_of_policy_input() -> None:
    actions = pd.DataFrame(
        {
            "issue": ["A", "A"],
            "issue_year": [2023, 2023],
            "action_key": ["BASE", "MODEL"],
            "selector": ["ALL", "TOP_HALF_VALUE"],
            "outcome_weight_mode": ["CELL_VALUE", "DIVERGENCE_VALUE"],
            "n": [7, 5],
            "generator": ["TOP_VALUE", "WEIGHTED_WR"],
            "k": [8, 32],
            "pnl_cny_mean": [-10.0, 20.0],
            "stake_cny_mean": [16.0, 64.0],
        }
    )
    chosen = actions[actions.action_key.eq("MODEL")].assign(
        predicted_score=1.0, policy="MODEL"
    )
    baseline = actions[actions.action_key.eq("BASE")]
    ledger = build_attribution_ledger(chosen, baseline, actions)
    assert ledger.loc[0, "matched_lift_cny"] == 30.0
    assert ledger.loc[0, "oracle_regret_cny_diagnostic"] == 0.0
    assert ledger.loc[0, "changed_stage_count"] == 5
