import pandas as pd
import pytest

from issue284.outcome_joint import build_issue_action_table, summarize_actions


def _raw() -> pd.DataFrame:
    rows = []
    for year in (2022, 2023):
        for mode, value in (("CELL_VALUE", -20.0), ("MARKET_PROBABILITY", 10.0)):
            for replica in (0, 1):
                rows.append(
                    {
                        "issue": str(year),
                        "issue_year": year,
                        "n": 7,
                        "proposal_family": "UNIFORM",
                        "outcome_weight_mode": mode,
                        "generator": "TOP_VALUE",
                        "requested_k": 8,
                        "subset_id": f"{year}-subset",
                        "stream_replica": replica,
                        "normalized_pnl_cny100": value,
                        "model_expected_pnl_cny100": -5.0,
                    }
                )
    return pd.DataFrame(rows)


def test_table_averages_nuisance_and_matches_cell_control() -> None:
    table = build_issue_action_table(_raw())
    market = table.loc[
        table["outcome_weight_mode"].eq("MARKET_PROBABILITY")
        & table["proposal_family"].eq("UNIFORM")
    ]
    assert len(market) == 2
    assert market["lift_to_cell_pct"].eq(30.0).all()


def test_summary_keeps_development_and_holdout() -> None:
    summary = summarize_actions(build_issue_action_table(_raw()))
    market = summary.loc[
        summary["outcome_weight_mode"].eq("MARKET_PROBABILITY")
        & summary["proposal_family"].eq("UNIFORM")
    ].iloc[0]
    assert market["development_roi_pct"] == pytest.approx(10.0)
    assert market["holdout_roi_pct"] == pytest.approx(10.0)
