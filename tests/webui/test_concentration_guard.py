"""Concentration guardrail: a plan that repeatedly re-bets a few core legs
(few qualified legs, or one leg present in too many tickets) is high-risk and
must not be auto-placed. History shows max-concentration >= 60% plans ran
~-40% ROI.
"""
from __future__ import annotations

from src.webui.services import leg_concentration_pct, passes_concentration_guard


def _tk(*legs):
    return {"legs": [{"match_id": m, "selection": s} for m, s in legs]}


def test_concentration_empty_is_zero():
    assert leg_concentration_pct([]) == 0.0


def test_concentration_single_shared_leg_is_100pct():
    # Leg (A,3) appears in both tickets -> 100% concentration.
    tickets = [_tk(("A", "3"), ("B", "1")), _tk(("A", "3"), ("C", "0"))]
    assert leg_concentration_pct(tickets) == 100.0


def test_concentration_is_max_leg_fraction():
    # (A,3) in 3/4 tickets = 75%; no other leg higher.
    tickets = [
        _tk(("A", "3"), ("B", "1")),
        _tk(("A", "3"), ("C", "1")),
        _tk(("A", "3"), ("D", "1")),
        _tk(("E", "3"), ("F", "1")),
    ]
    assert leg_concentration_pct(tickets) == 75.0


def test_same_match_other_selection_is_a_distinct_leg():
    # (A,3) and (A,1) are different legs; neither exceeds 50%.
    tickets = [_tk(("A", "3"), ("B", "1")), _tk(("A", "1"), ("B", "1"))]
    # (B,1) is in both -> 100%; assert that, not the A legs.
    assert leg_concentration_pct(tickets) == 100.0


def test_guard_passes_healthy_plan():
    ok, reason = passes_concentration_guard(
        n_qualified_legs=20, concentration_max_pct=45.0)
    assert ok is True
    assert reason == ""


def test_guard_blocks_too_few_legs():
    ok, reason = passes_concentration_guard(
        n_qualified_legs=9, concentration_max_pct=30.0)
    assert ok is False
    assert "leg" in reason.lower()


def test_guard_blocks_over_concentration():
    ok, reason = passes_concentration_guard(
        n_qualified_legs=20, concentration_max_pct=72.0)
    assert ok is False
    assert "concentration" in reason.lower()
