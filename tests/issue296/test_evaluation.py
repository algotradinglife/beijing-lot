from __future__ import annotations

import pandas as pd

from issue296.evaluation import capital_path, summarize_path


def test_whole_bundle_path_obeys_capital_and_compounds() -> None:
    table = pd.DataFrame(
        {
            "issue": [1, 2],
            "issue_year": [2023, 2023],
            "stake_A": [20.0, 20.0],
            "pnl_A": [10.0, -20.0],
            "gross_A": [30.0, 0.0],
            "hits_A": [1.0, 0.0],
            "available_A": [True, True],
        }
    )
    weights = pd.DataFrame(
        {
            "issue": [1, 2],
            "issue_year": [2023, 2023],
            "condition": ["TEST", "TEST"],
            "weight_A": [0.5, 0.5],
            "weight_CASH": [0.5, 0.5],
        }
    )
    path = capital_path(table, weights, ["A"], initial_capital_cny=100.0)
    assert path["closing_capital_cny"].tolist() == [120.0, 60.0]
    summary = summarize_path(path)
    assert summary["terminal_capital_cny"] == 60.0
    assert summary["max_drawdown_pct"] == 50.0
