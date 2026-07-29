from __future__ import annotations

import math

import pytest

from src.score_prediction.v771 import (
    EXPLICIT_AWAY,
    EXPLICIT_DRAW,
    EXPLICIT_HOME,
    GRID,
    MatchOdds,
    ThreeWayOdds,
    predict,
)


def _all_score_odds() -> dict[tuple[int, int] | str, float]:
    odds: dict[tuple[int, int] | str, float] = {}
    for home, away in sorted(EXPLICIT_HOME | EXPLICIT_DRAW | EXPLICIT_AWAY):
        odds[(home, away)] = 5.0 + home * 4.0 + away * 3.0
    odds.update({"胜其它": 50.0, "平其它": 80.0, "负其它": 55.0})
    return odds


def _inputs(
    *,
    one_x_two: ThreeWayOdds = ThreeWayOdds(2.15, 3.30, 3.50),
    handicap: ThreeWayOdds = ThreeWayOdds(3.20, 3.55, 2.05),
    half_full: ThreeWayOdds = ThreeWayOdds(4.80, 5.30, 5.10),
    total_goals: tuple[float, ...] = (12.0, 5.4, 3.2, 3.5, 5.5, 10.0, 18.0, 30.0),
) -> MatchOdds:
    return MatchOdds(
        one_x_two=one_x_two,
        handicap=handicap,
        handicap_line=-1,
        half_full=half_full,
        total_goals=total_goals,  # type: ignore[arg-type]
        score_odds=_all_score_odds(),
    )


def test_prediction_is_complete_normalized_and_ranked() -> None:
    result = predict(_inputs())

    assert len(result.distribution) == len(GRID) == 45
    assert math.isclose(sum(result.distribution.values()), 1.0, abs_tol=1e-12)
    assert len(result.candidates) == 15
    assert len(result.main) == 3
    assert len(result.auxiliary) == 2
    assert set(candidate.score for candidate in result.main).isdisjoint(
        candidate.score for candidate in result.auxiliary
    )
    assert [candidate.probability for candidate in result.candidates] == sorted(
        (candidate.probability for candidate in result.candidates),
        reverse=True,
    )
    assert all(
        math.isclose(candidate.bayes_score, candidate.probability * 10_000.0)
        for candidate in result.candidates
    )


def test_manual_intermediate_formulas_and_weight_range() -> None:
    inputs = _inputs()
    result = predict(inputs)
    diagnostics = result.diagnostics

    weights = [0.85 / odd for odd in inputs.total_goals]
    expected_mu = sum(goal * weight for goal, weight in enumerate(weights)) / sum(
        weights
    )
    raw_one_x_two = [
        0.92 / inputs.one_x_two.home,
        0.92 / inputs.one_x_two.draw,
        0.92 / inputs.one_x_two.away,
    ]
    expected_p_win = raw_one_x_two[0] / sum(raw_one_x_two)
    expected_delta = 0.8 * math.log(expected_p_win / (1.0 - expected_p_win))

    assert diagnostics.mu == pytest.approx(expected_mu)
    assert diagnostics.p_win == pytest.approx(expected_p_win)
    assert diagnostics.delta == pytest.approx(expected_delta)
    assert diagnostics.score_odds_count == 15
    assert 0.20 <= diagnostics.market_weight < 1.0
    assert diagnostics.lambda_home >= 0.2
    assert diagnostics.lambda_away >= 0.2


def test_draw_hijack_boundary_is_inclusive() -> None:
    at_boundary = predict(_inputs(one_x_two=ThreeWayOdds(2.4, 3.50, 3.0)))
    above_boundary = predict(_inputs(one_x_two=ThreeWayOdds(2.4, 3.51, 3.0)))

    assert at_boundary.diagnostics.draw_hijack_applied is True
    assert above_boundary.diagnostics.draw_hijack_applied is False


def test_direction_conflict_halves_spread_correction_without_inverting_cover() -> None:
    result = predict(
        _inputs(
            one_x_two=ThreeWayOdds(1.35, 4.8, 8.0),
            handicap=ThreeWayOdds(8.0, 4.0, 1.35),
        )
    )
    diagnostics = result.diagnostics

    assert diagnostics.direction_conflict is True
    assert diagnostics.p_cover < diagnostics.p_win
    assert diagnostics.delta_spread_used == pytest.approx(
        diagnostics.delta_spread_raw * 0.5
    )


def test_tail_multiplier_triggers_and_is_capped() -> None:
    result = predict(
        _inputs(
            one_x_two=ThreeWayOdds(1.20, 6.0, 14.0),
            total_goals=(80.0, 50.0, 30.0, 18.0, 9.0, 5.0, 3.0, 2.0),
        )
    )

    assert result.diagnostics.tail_multiplier > 1.0
    assert result.diagnostics.tail_multiplier <= 1.40
    assert result.diagnostics.tail_side == "home"


def test_partial_score_market_and_other_buckets_are_supported() -> None:
    inputs = MatchOdds(
        one_x_two=ThreeWayOdds(2.2, 3.4, 3.3),
        handicap=ThreeWayOdds(3.0, 3.4, 2.2),
        handicap_line=1,
        half_full=ThreeWayOdds(4.5, 5.0, 5.5),
        total_goals=(10.0, 5.0, 3.1, 3.4, 6.0, 11.0, 20.0, 35.0),
        score_odds={"1:0": 7.0, "1-1": 6.5, "负其它": 45.0, "0:0": None},
    )
    result = predict(inputs)

    assert result.diagnostics.score_odds_count == 3
    assert math.isclose(sum(result.distribution.values()), 1.0, abs_tol=1e-12)
    assert all(probability >= 0 for probability in result.distribution.values())


@pytest.mark.parametrize(
    "bad_key",
    ["not-a-score", "9:0", (4, 3)],
)
def test_invalid_score_market_keys_fail_closed(bad_key: tuple[int, int] | str) -> None:
    with pytest.raises(ValueError):
        MatchOdds(
            one_x_two=ThreeWayOdds(2.2, 3.4, 3.3),
            handicap=ThreeWayOdds(3.0, 3.4, 2.2),
            handicap_line=-1,
            half_full=ThreeWayOdds(4.5, 5.0, 5.5),
            total_goals=(10.0, 5.0, 3.1, 3.4, 6.0, 11.0, 20.0, 35.0),
            score_odds={bad_key: 9.0},
        )
