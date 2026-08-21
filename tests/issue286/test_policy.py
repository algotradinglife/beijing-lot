from __future__ import annotations

import pandas as pd

from issue286.policy import (
    chronological_capital_path,
    same_budget_random,
    select_positive_prefix,
)


def test_positive_prefix_can_choose_no_protection_and_enforces_quota() -> None:
    candidates = pd.DataFrame(
        {"candidate_identity": list("abcd"), "score": [-1.0, 3.0, 2.0, 1.0]}
    )
    assert select_positive_prefix(
        candidates, score_column="score", k=4, maximum_share=0
    ).empty
    selected = select_positive_prefix(
        candidates, score_column="score", k=4, maximum_share=0.5
    )
    assert selected["candidate_identity"].tolist() == ["b", "c"]


def test_random_control_has_exact_final_unique_ticket_budget() -> None:
    candidates = pd.DataFrame(
        {"candidate_identity": ["a", "b", "c", "d"], "pnl_cny": [-2] * 4}
    )
    selected = same_budget_random(
        candidates, funded_count=3, issue="23001", action_key="action"
    )
    assert len(selected) == 3
    assert selected["candidate_identity"].is_unique


def test_capital_path_uses_year_and_numeric_issue_order() -> None:
    rows = pd.DataFrame(
        {
            "issue": ["23010", "2302", "22099"],
            "issue_year": [2023, 2023, 2022],
            "pnl": [10.0, -5.0, 2.0],
        }
    )
    path = chronological_capital_path(rows, pnl_column="pnl")
    assert path["issue"].tolist() == ["22099", "2302", "23010"]
    assert path["capital_cny"].tolist() == [100002.0, 99997.0, 100007.0]
