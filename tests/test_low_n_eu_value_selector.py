from __future__ import annotations

import pandas as pd
import pytest

from src.low_n_eu_value_selector.contract import ARMS
from src.low_n_eu_value_selector.pipeline import (
    ContractError,
    _arm_bits,
    _path_risk,
    _strict_bool,
    construct_preoutcome,
)


def _surface() -> pd.DataFrame:
    rows = []
    for match_idx, values in enumerate(
        [
            (0.90, 0.91, 1.20, 0.06),
            (0.88, 0.90, 1.18, 0.05),
            (0.86, 0.89, 1.16, 0.04),
            (0.84, 0.88, 0.80, 0.01),
        ],
        start=1,
    ):
        s0, coverage, value, gap = values
        rows.append(
            {
                "issue": "19001",
                "issue_year": 2019,
                "issue_anchor_ts": pd.Timestamp("2019-01-01", tz="UTC"),
                "match_idx": match_idx,
                "baseline_support": "31",
                "s0_score": s0,
                "coverage_score": coverage,
                "value_factor": value,
                "top2_third_gap": gap,
                "source_quality_valid": True,
            }
        )
    return pd.DataFrame(rows)


def _parameter(**overrides: float) -> dict[str, float]:
    value = {
        "coverage_quantile": -1.0,
        "coverage_floor": float("-inf"),
        "value_leg_floor": float("-inf"),
        "gap_quantile": -1.0,
        "gap_floor": float("-inf"),
        "complete_ticket_return_floor": float("-inf"),
    }
    value.update(overrides)
    return value


def test_all_eight_factorial_arms_have_distinct_bits() -> None:
    assert len(ARMS) == 8
    assert len({_arm_bits(arm) for arm in ARMS}) == 8


def test_top2_ticket_budget_is_exact_for_n3() -> None:
    selections, bundles, tickets, decisions = construct_preoutcome(
        _surface(), 3, "C0V0G0", _parameter(), (2019,)
    )
    assert len(selections) == 3
    assert len(bundles) == 1
    assert len(tickets) == 8
    assert tickets.ticket_key.nunique() == 8
    assert tickets.stake_cny.sum() == pytest.approx(1_024.0)
    assert bundles.ticket_count.iloc[0] == 8
    assert bundles.units_per_ticket.iloc[0] == 64
    assert decisions.bet.dtype == bool
    assert bool(decisions.bet.iloc[0]) is True


def test_value_floor_never_backfills_ineligible_fixture() -> None:
    _, bundles, _, decisions = construct_preoutcome(
        _surface(),
        3,
        "C0V1G0",
        _parameter(value_leg_floor=1.0, complete_ticket_return_floor=1.1),
        (2019,),
    )
    assert bundles.empty
    assert decisions.decision.iloc[0] == "COMPLETE_TICKET_VALUE_FLOOR"
    assert bool(decisions.bet.iloc[0]) is False


def test_recovery_distinguishes_completed_and_open_underwater() -> None:
    open_path = _path_risk(pd.Series([-100.0, 50.0]).to_numpy())
    assert open_path["completed_recovery_issues"] == 0
    assert open_path["open_underwater_issues"] == 2
    assert open_path["recovery_censored"] is True
    recovered = _path_risk(pd.Series([-100.0, 150.0]).to_numpy())
    assert recovered["completed_recovery_issues"] == 2
    assert recovered["open_underwater_issues"] == 0
    assert recovered["recovery_censored"] is False


def test_construct_rejects_unknown_arm() -> None:
    with pytest.raises(ContractError, match="unknown factorial arm"):
        construct_preoutcome(_surface(), 3, "BAD", _parameter(), (2019,))


def test_strict_boolean_rejects_integer_flags() -> None:
    with pytest.raises(ContractError, match="strict boolean"):
        _strict_bool(pd.Series([0, 1]), "integer_flag")


def test_ticket_level_payout_factor_is_applied_once() -> None:
    surface = _surface()
    surface.loc[surface["match_idx"].le(3), "value_factor"] = 1.20
    _, bundles, _, decisions = construct_preoutcome(
        surface,
        3,
        "C0V1G0",
        _parameter(value_leg_floor=1.0, complete_ticket_return_floor=1.0),
        (2019,),
    )
    expected = 0.65 * 1.20**3
    assert bundles.complete_ticket_proxy_return.iloc[0] == pytest.approx(expected)
    assert decisions.complete_ticket_proxy_return.iloc[0] == pytest.approx(expected)
