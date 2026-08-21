from __future__ import annotations

import pytest

from issue286.settlement import MatchSettlement, settle_ticket_identity


def test_complete_ticket_applies_payout_coefficient_once() -> None:
    lookup = {
        "a": MatchSettlement("3", 2.0),
        "b": MatchSettlement("1", 3.0),
        "c": MatchSettlement("0", 4.0),
    }
    winner = settle_ticket_identity("a:3|b:1|c:0", lookup)
    loser = settle_ticket_identity("a:3|b:0|c:0", lookup)
    assert winner["gross_cny"] == pytest.approx(2 * 0.65 * 2 * 3 * 4)
    assert winner["pnl_cny"] == pytest.approx(29.2)
    assert loser["gross_cny"] == 0
    assert loser["pnl_cny"] == -2


def test_missing_or_nonfinite_sp_excludes_ticket_without_charging_stake() -> None:
    lookup = {
        "a": MatchSettlement("3", 2.0),
        "b": MatchSettlement("1", float("nan")),
    }
    result = settle_ticket_identity("a:3|b:1", lookup)
    assert result == {
        "settlement_valid": False,
        "hit": 0,
        "stake_cny": 0.0,
        "gross_cny": 0.0,
        "pnl_cny": 0.0,
    }
