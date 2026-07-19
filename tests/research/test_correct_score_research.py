from __future__ import annotations

from datetime import datetime, timezone

import pytest

from research.correct_score.contract import CorrectScoreOddsSnapshot, CorrectScoreQuote, validate_snapshot
from research.correct_score.experiment import run_research_experiment
from research.correct_score.model import fit_temperature_calibration, independent_poisson_score_probs


UTC = timezone.utc
SCORELINES = ((0, 0), (1, 0), (0, 1), (1, 1))


def snapshot(*, as_of: datetime | None = None, captured: datetime | None = None, phase: str = "pre_match") -> CorrectScoreOddsSnapshot:
    kickoff = datetime(2026, 7, 18, 18, 0, tzinfo=UTC)
    as_of = as_of or datetime(2026, 7, 18, 17, 50, tzinfo=UTC)
    captured = captured or datetime(2026, 7, 18, 17, 51, tzinfo=UTC)
    return CorrectScoreOddsSnapshot(
        snapshot_id="hash-1",
        match_id="match-1",
        provider="fixture-provider",
        market_as_of=as_of,
        captured_at=captured,
        decision_at=datetime(2026, 7, 18, 17, 55, tzinfo=UTC),
        kickoff_at=kickoff,
        required_scorelines=SCORELINES,
        quotes=(
            CorrectScoreQuote((0, 0), 8.0),
            CorrectScoreQuote((1, 0), 6.0),
            CorrectScoreQuote((0, 1), 9.0),
            CorrectScoreQuote((1, 1), 7.0),
        ),
        market_phase=phase,
    )


def test_snapshot_contract_accepts_fresh_complete_pre_match_evidence():
    assert validate_snapshot(snapshot()).eligible


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"as_of": datetime(2026, 7, 18, 17, 40, tzinfo=UTC)}, "odds_stale_at_decision"),
        ({"captured": datetime(2026, 7, 18, 18, 0, tzinfo=UTC)}, "terminal_or_live_odds"),
        ({"phase": "terminal"}, "market_phase_not_pre_match"),
    ],
)
def test_snapshot_contract_rejects_stale_and_terminal_evidence(kwargs, reason):
    eligibility = validate_snapshot(snapshot(**kwargs))
    assert not eligibility.eligible
    assert reason in eligibility.reasons


def test_poisson_grid_preserves_omitted_tail_mass():
    probabilities = independent_poisson_score_probs(1.3, 1.1, SCORELINES)
    assert 0 < sum(probabilities.values()) < 1
    assert probabilities[(1, 0)] > probabilities[(0, 0)]


def test_temperature_calibration_uses_settled_training_rows_only():
    rows = [
        ({(0, 0): 0.70, (1, 0): 0.10, (0, 1): 0.10, (1, 1): 0.10}, (0, 0)),
        ({(0, 0): 0.70, (1, 0): 0.10, (0, 1): 0.10, (1, 1): 0.10}, (0, 0)),
    ]
    calibration = fit_temperature_calibration(rows, SCORELINES)
    assert calibration.n_training_rows == 2
    assert calibration.temperature < 1.0
    assert calibration.logloss_after < calibration.logloss_before


def test_experiment_fail_closed_for_terminal_odds():
    calibration = fit_temperature_calibration(
        [({scoreline: 0.25 for scoreline in SCORELINES}, (0, 0))], SCORELINES
    )
    result = run_research_experiment(
        snapshot(phase="terminal"),
        {scoreline: 0.25 for scoreline in SCORELINES},
        calibration,
        top_k=2,
    )
    assert not result.eligibility.eligible
    assert result.candidates == ()


def test_experiment_rejects_truncated_poisson_tail():
    calibration = fit_temperature_calibration(
        [({scoreline: 0.25 for scoreline in SCORELINES}, (0, 0))], SCORELINES
    )
    with pytest.raises(ValueError, match="truncated tails"):
        run_research_experiment(
            snapshot(),
            independent_poisson_score_probs(1.3, 1.1, SCORELINES),
            calibration,
            top_k=2,
        )


def test_experiment_ranks_top_k_and_applies_diagnostic_ev_q_filters():
    calibration = fit_temperature_calibration(
        [({scoreline: 0.25 for scoreline in SCORELINES}, (0, 0))], SCORELINES
    )
    result = run_research_experiment(
        snapshot(),
        {(0, 0): 0.10, (1, 0): 0.60, (0, 1): 0.20, (1, 1): 0.10},
        calibration,
        top_k=2,
        min_theoretical_edge=0.0,
        min_q_ratio=1.0,
    )
    assert result.eligibility.eligible
    assert [candidate.scoreline for candidate in result.candidates] == [(1, 0)]
    assert result.candidates[0].top_k_rank == 1
    assert result.candidates[0].theoretical_edge > 0
