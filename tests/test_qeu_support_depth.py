from __future__ import annotations

import pandas as pd

from src.qeu_support_depth.contract import ISSUE_STAKE_CNY, PAYOUT_FACTOR
from src.qeu_support_depth.pipeline import (
    construct_and_settle,
    prepare_matches,
    select_development_arm,
)


def _cells() -> pd.DataFrame:
    rows = []
    for match in range(1, 8):
        for outcome, q_eu, q_line in (("3", .60, .55), ("1", .30, .35), ("0", .10, .10)):
            rows.append({
                "issue": "23001", "issue_year": 2023,
                "issue_anchor_ts": pd.Timestamp("2023-01-01", tz="UTC"),
                "match_idx": match, "outcome": outcome, "q_eu": q_eu, "q_line": q_line,
                "result_code": "3", "winning_sp": 2.0, "settlement_available": True,
            })
    return pd.DataFrame(rows)


def test_support_depth_keeps_matched_exposure_and_applies_factor_once() -> None:
    matches = prepare_matches(_cells())
    bundles, _ = construct_and_settle(matches)
    assert bundles["stake_cny"].eq(ISSUE_STAKE_CNY).all()
    assert bundles["selected_match_ids"].nunique() == 1
    expected = 2.0 * 4 * PAYOUT_FACTOR * 2.0**7
    assert bundles["gross_cny"].eq(expected).all()


def test_qeu_support_is_ratio_rank_not_probability_rank() -> None:
    matches = prepare_matches(_cells())
    first = matches.iloc[0]
    assert first["baseline_support"] == "31"
    assert first["qeu_support"] == "30"
    assert first["lost_outcome"] == "1"
    assert first["gained_outcome"] == "0"


def test_untrusted_selected_settlement_fails_closed() -> None:
    cells = _cells()
    cells.loc[cells["match_idx"].eq(1), "settlement_available"] = False
    bundles, attribution = construct_and_settle(prepare_matches(cells))
    assert bundles.empty
    assert attribution.empty


def test_development_selection_uses_positive_ex_largest_as_gate_not_magnitude() -> None:
    performance = pd.DataFrame([
        {"r": 1, "issue_year": 2023, "matched_lift_cny": -1.0, "ex_largest_lift_cny": 9.0},
        {"r": 3, "issue_year": 2023, "matched_lift_cny": 20.0, "ex_largest_lift_cny": 1.0},
    ])
    risk = pd.DataFrame([
        {"r": 1, "issue_year": 2023, "max_drawdown_fraction": .10},
        {"r": 3, "issue_year": 2023, "max_drawdown_fraction": .20},
    ])
    selected, _ = select_development_arm(performance, risk)
    assert selected == 3
