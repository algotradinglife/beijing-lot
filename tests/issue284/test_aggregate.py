import pandas as pd

from issue282.features import ISSUE_STATE_FEATURES
from issue284.aggregate import build_issue_n_table


def test_issue_n_table_separates_pre_event_features_from_realized_targets() -> None:
    rows = []
    for n in (3, 7):
        for family, expected, realized in (("A", -10.0, -20.0), ("B", 10.0, 40.0)):
            rows.append(
                {
                    "issue": "A",
                    "issue_year": 2020,
                    "issue_match_count": 12,
                    "n": n,
                    "proposal_family": family,
                    "subset_id": f"{n}-{family}",
                    "normalized_pnl_cny100": realized + n,
                    "model_expected_pnl_cny100": expected + n,
                }
            )
    labels = pd.DataFrame(rows)
    state = pd.DataFrame(
        [{"issue": "A", **{feature: 1.0 for feature in ISSUE_STATE_FEATURES}}]
    )
    result = build_issue_n_table(labels, state).set_index("n")
    assert result.loc[3, "expected_mean"] == 3.0
    assert result.loc[3, "realized_mean"] == 13.0
    assert result.loc[7, "expected_margin_to_n7"] == 0.0
    assert result.loc[7, "realized_lift_to_n7"] == 0.0
    assert result.loc[3, "residual_to_expected"] == 10.0
