import copy
import pytest
from src.n7_capital_study import describe_capital_plan


def test_capital_diagnostics_preserve_frozen_metrics_and_missing_support():
    plan = dict(budget_cny=512, cash_cny=0, funded_sleeves=4,
        support_space="NONUNIFORM", solver_status="FEASIBLE_NOT_PROVEN",
        max_reuse=3, max_overlap=2, max_fixture_exposure_cny=300,
        max_outcome_exposure_cny=200,
        training=dict(any_hit=.7, payoff_ratio=None),
        evaluation=dict(any_hit=.6, payoff_ratio=1.2))
    before = copy.deepcopy(plan)
    row = describe_capital_plan(plan)
    assert row["budget_cny"] == 512
    assert row["training_any_hit"] == .7
    assert row["evaluation_any_hit"] == .6
    assert row["training_payoff_ratio"] is None
    assert plan == before
    del plan["evaluation"]
    with pytest.raises(KeyError):
        describe_capital_plan(plan)
