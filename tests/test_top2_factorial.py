from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from src.top2_factorial.contract import CELLS, FUNDED_UNITS, PAYOUT_FACTOR
from src.top2_factorial.pipeline import (
    _allocate_value,
    _decision,
    _factorial_contrasts,
    _risk,
    construct_preoutcome,
    settle,
)


def predicted_surface(fixtures: int = 8) -> pd.DataFrame:
    rows = []
    for index in range(fixtures):
        rows.append({
            "issue_code": "23001", "issue_year": 2023, "horizon": "10h",
            "issue_anchor_ts": "2023-01-02T12:00:00+00:00",
            "canonical_fixture_key": f"bjslot:23001:{index:03d}",
            "top1_code": "3", "top2_codes": ("3", "1"),
            "retained_mass": 0.8 - index / 100,
            "selector_score": 0.7 + index / 100,
            "action_delta_score": 0.2 if index < 3 else -0.1,
            "outcome_value_3": 0.9, "outcome_value_1": 0.6, "outcome_value_0": 0.2,
        })
    return pd.DataFrame(rows)


def settlement_frame(fixtures: int = 8) -> pd.DataFrame:
    return pd.DataFrame({
        "issue_code": ["23001"] * fixtures,
        "canonical_fixture_key": [f"bjslot:23001:{index:03d}" for index in range(fixtures)],
        "result_code": ["3"] * fixtures,
        "winning_sp": [2.0] * fixtures,
        "has_trusted_settlement": [1] * fixtures,
    })


def test_full_factorial_has_eight_cells_and_equal_funding() -> None:
    cells, tickets = construct_preoutcome(predicted_surface())
    assert set(cells.cell) == set(CELLS)
    assert cells.funded_units.eq(128).all()
    assert cells.planned_stake.eq(256.0).all()
    assert tickets.groupby("cell").stake_units.sum().eq(FUNDED_UNITS).all()


def test_control_reproduces_exact_top2_cartesian_support() -> None:
    _, tickets = construct_preoutcome(predicted_surface())
    control = tickets[tickets.cell.eq("S0O0A0")]
    assert len(control) == 128
    assert control.stake_units.eq(1).all()
    assert not control.ticket_key.duplicated().any()


def test_selective_compression_is_bounded_and_equal_allocator_repeats() -> None:
    cells, tickets = construct_preoutcome(predicted_surface())
    compressed = cells[cells.cell.eq("S0O1A0")].iloc[0]
    assert compressed.compressed_legs == 2
    assert compressed.unique_tickets == 32
    arm = tickets[tickets.cell.eq("S0O1A0")]
    assert len(arm) == 32
    assert arm.stake_units.eq(4).all()


def test_value_allocator_is_integer_and_budget_exact() -> None:
    units = _allocate_value(np.array([0.5, 0.3, 0.2]))
    assert np.issubdtype(units.dtype, np.integer)
    assert units.sum() == FUNDED_UNITS
    assert (units >= 0).all()


def test_settlement_applies_factor_once_to_complete_ticket() -> None:
    cells, tickets = construct_preoutcome(predicted_surface(7))
    cells, tickets, _ = settle(cells, tickets, settlement_frame(7))
    control = cells[cells.cell.eq("S0O0A0")].iloc[0]
    expected = 2.0 * PAYOUT_FACTOR * np.prod([2.0] * 7)
    assert np.isclose(control.gross, expected)
    assert tickets[(tickets.cell.eq("S0O0A0")) & tickets.ticket_hit].shape[0] == 1


def test_missing_settlement_is_unobservable() -> None:
    cells, tickets = construct_preoutcome(predicted_surface(7))
    cells, tickets, native = settle(cells, tickets, settlement_frame(6))
    assert cells.settlement_status.eq("UNOBSERVABLE_SETTLEMENT").all()
    assert cells.pnl.isna().all()
    assert tickets.gross.isna().all()
    assert native.pnl.isna().all()


def test_factorial_contrasts_are_zero_for_additive_surface() -> None:
    row = {}
    for s, o, a in itertools.product((0, 1), repeat=3):
        row[f"S{s}O{o}A{a}"] = 10 * s + 20 * o + 30 * a
    output = _factorial_contrasts(pd.DataFrame([row])).iloc[0]
    assert output.S_main == 10
    assert output.O_main == 20
    assert output.A_main == 30
    assert output.SxO == output.SxA == output.OxA == output.SxOxA == 0


def test_open_underwater_tail_is_not_completed_recovery() -> None:
    path = pd.DataFrame({
        "pnl": [-100.0, 100.0, -50.0, -25.0],
        "gross": [0.0, 200.0, 0.0, 0.0],
        "capital_after": [99_900.0, 100_000.0, 99_950.0, 99_925.0],
    })
    result = _risk(path)
    assert result["completed_recovery_episode_count"] == 1
    assert result["max_completed_recovery_issues"] == 1
    assert result["open_underwater_issues"] == 2


def test_descriptive_joint_gain_does_not_promote_when_ex_largest_fails() -> None:
    rows = []
    for year in (2023, 2024):
        for cell in CELLS:
            total = 100.0 if cell == "S1O1A1" else 0.0
            robust = (-1.0 if year == 2023 else 10.0) if cell == "S1O1A1" else 0.0
            rows.append({
                "horizon": "10h", "issue_year": year, "cell": cell,
                "total_lift": total, "ex_largest_lift": robust,
            })
    result = _decision({"matched_performance": pd.DataFrame(rows)})
    assert result["disposition"] == "NO_INCREMENT"
    assert result["descriptive_joint_positive_both_years"] == ["S1O1A1"]
    assert not result["joint_positive_both_years"]
