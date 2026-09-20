"""Tests for the Dixon-Coles handicap-line-gap rebase.

The rebase must be *faithful* -- with ``rho = 0`` it has to reproduce the
independent-Poisson audit exactly -- and *correct* -- with ``rho != 0`` it must
move draw mass in the direction Dixon-Coles predicts.  Both properties are
asserted here, along with the chronology contract (frozen per-issue rho, never
re-selected) and the failure paths.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "rebase_handicap_line_gap_dc.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("rebase_handicap_line_gap_dc", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rebase = _load_module()

GOALS = np.arange(0, rebase.MAX_GOALS + 1)
NET_GRID = GOALS[:, None] - GOALS[None, :]


def _independent_distribution(lambda_home: float, lambda_away: float):
    grid = np.outer(stats.poisson.pmf(GOALS, lambda_home), stats.poisson.pmf(GOALS, lambda_away))
    return rebase.net_distribution(grid / grid.sum(), NET_GRID)


# --- tau semantics -----------------------------------------------------------


def test_tau_touches_only_the_four_low_score_cells():
    lh, la, rho = 1.4, 1.1, -0.14
    expected = {
        (0, 0): 1.0 - lh * la * rho,
        (0, 1): 1.0 + lh * rho,
        (1, 0): 1.0 + la * rho,
        (1, 1): 1.0 - rho,
    }
    for home in range(4):
        for away in range(4):
            got = rebase.dc_tau(home, away, lh, la, rho)
            assert got == pytest.approx(expected.get((home, away), 1.0))


def test_tau_is_one_everywhere_when_rho_is_zero():
    for home in range(4):
        for away in range(4):
            assert rebase.dc_tau(home, away, 1.4, 1.1, 0.0) == 1.0


# --- degenerate case: rho = 0 must reproduce independent Poisson ------------


def test_zero_rho_reproduces_the_independent_grid_exactly():
    lh, la = 1.35, 1.05
    _, expected = _independent_distribution(lh, la)
    _, got = rebase.net_distribution(rebase.score_grid(lh, la, 0.0, GOALS), NET_GRID)
    assert np.allclose(got, expected, atol=1e-12)


def test_score_grid_is_normalized_for_every_supported_rho():
    for rho in (-0.20, -0.14, -0.02, 0.0):
        grid = rebase.score_grid(1.3, 1.2, rho, GOALS)
        assert grid.sum() == pytest.approx(1.0, abs=1e-12)
        assert (grid >= 0).all()


# --- direction of the correction --------------------------------------------


def test_negative_rho_increases_draw_mass():
    lh, la = 1.05, 1.05
    _, base = _independent_distribution(lh, la)
    _, corrected = rebase.net_distribution(rebase.score_grid(lh, la, -0.14, GOALS), NET_GRID)
    base_draw = base[np.unique(NET_GRID) == 0].sum()
    corrected_draw = corrected[np.unique(NET_GRID) == 0].sum()
    assert corrected_draw > base_draw


def test_draw_mass_is_monotone_in_rho():
    lh, la = 1.2, 1.0
    nets = np.unique(NET_GRID)
    masses = []
    for rho in (-0.20, -0.15, -0.10, -0.05, 0.0):
        _, dist = rebase.net_distribution(rebase.score_grid(lh, la, rho, GOALS), NET_GRID)
        masses.append(dist[nets == 0].sum())
    assert all(later < earlier for earlier, later in zip(masses, masses[1:]))


def test_positive_rho_decreases_draw_mass():
    lh, la = 1.1, 1.1
    nets = np.unique(NET_GRID)
    _, base = _independent_distribution(lh, la)
    _, corrected = rebase.net_distribution(rebase.score_grid(lh, la, 0.10, GOALS), NET_GRID)
    assert corrected[nets == 0].sum() < base[nets == 0].sum()


# --- handicap_line_gap port --------------------------------------------------


def test_port_matches_hand_computed_symmetric_case():
    # Symmetric, low-scoring: the optimal line is 0 and the sides balance.
    nets = np.array([-2, -1, 0, 1, 2])
    masses = np.array([0.05, 0.20, 0.50, 0.20, 0.05])
    got = rebase.handicap_line_gap(nets, masses, 0, 1e-12)
    assert got["optimal_line"] == 0.0
    assert got["delta"] == 0.0
    assert got["signal"] == "NONE"
    assert got["q_W"] == pytest.approx(0.25)
    assert got["q_D"] == pytest.approx(0.50)
    assert got["q_L"] == pytest.approx(0.25)


def test_port_moves_optimal_line_with_skew():
    nets = np.array([-2, -1, 0, 1, 2])
    masses = np.array([0.02, 0.08, 0.20, 0.40, 0.30])
    got = rebase.handicap_line_gap(nets, masses, 0, 1e-12)
    # Home is stronger, so the balancing line is negative (home gives goals).
    assert got["optimal_line"] < 0
    assert got["delta"] > 0
    assert got["signal"] == "W"


def test_port_reports_ties_without_letting_actual_line_break_them():
    nets = np.array([-1, 0, 1])
    masses = np.array([1 / 3, 1 / 3, 1 / 3])
    got = rebase.handicap_line_gap(nets, masses, 0, 1e-12)
    assert got["ties"] >= 1
    assert got["optimal_min"] <= got["optimal_line"] <= got["optimal_max"]


def test_port_handicap_changes_q_but_not_optimal_line():
    nets = np.array([-2, -1, 0, 1, 2])
    masses = np.array([0.05, 0.20, 0.50, 0.20, 0.05])
    zero = rebase.handicap_line_gap(nets, masses, 0, 1e-12)
    minus = rebase.handicap_line_gap(nets, masses, -1, 1e-12)
    assert zero["optimal_line"] == minus["optimal_line"]
    # A negative handicap means home concedes goals, so home win mass falls.
    assert minus["q_W"] < zero["q_W"]
    assert minus["q_L"] > zero["q_L"]


def test_q_components_sum_to_one():
    nets = np.array([-1, 0, 1, 2])
    masses = np.array([0.2, 0.3, 0.35, 0.15])
    for handicap in (-1, 0, 1):
        got = rebase.handicap_line_gap(nets, masses, handicap, 1e-12)
        assert got["q_W"] + got["q_D"] + got["q_L"] == pytest.approx(1.0)


# --- lambda recovery ---------------------------------------------------------


def test_lambda_recovery_round_trips_a_known_pair():
    lh, la = 1.45, 0.95
    nets, observed = _independent_distribution(lh, la)
    got_home, got_away, residual = rebase.recover_lambdas(nets, observed, GOALS, NET_GRID)
    assert got_home == pytest.approx(lh, abs=1e-6)
    assert got_away == pytest.approx(la, abs=1e-6)
    assert residual < 1e-9


def test_lambda_recovery_is_exact_for_a_symmetric_pair():
    nets, observed = _independent_distribution(1.2, 1.2)
    home, away, residual = rebase.recover_lambdas(nets, observed, GOALS, NET_GRID)
    assert home == pytest.approx(away, abs=1e-8)
    assert residual < 1e-9


# --- end-to-end rebase behaviour --------------------------------------------


def test_rebase_preserves_grid_mass_and_ordering_under_rho():
    lh, la, rho = 1.3, 1.1, -0.14
    nets, base = _independent_distribution(lh, la)
    dc_nets, corrected = rebase.net_distribution(rebase.score_grid(lh, la, rho, GOALS), NET_GRID)
    assert np.array_equal(nets, dc_nets)
    assert corrected.sum() == pytest.approx(1.0, abs=1e-12)
    # The correction is a local low-score reshuffle, not a wholesale move.
    assert np.abs(corrected - base).max() < 0.05


def test_rebase_shifts_q_draw_upward_for_a_symmetric_low_scoring_fixture():
    lh, la = 1.0, 1.0
    nets, base = _independent_distribution(lh, la)
    _, corrected = rebase.net_distribution(rebase.score_grid(lh, la, -0.14, GOALS), NET_GRID)
    before = rebase.handicap_line_gap(nets, base, 0, 1e-12)
    after = rebase.handicap_line_gap(nets, corrected, 0, 1e-12)
    assert after["q_D"] > before["q_D"]


# --- chronology contract -----------------------------------------------------


def test_rho_is_applied_from_the_table_and_never_reselected():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "select_dixon_coles_rho" not in source
    assert "rho_by_issue" in source


def test_missing_rho_for_an_issue_fails_closed():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "absent from the rho table" in source


def test_duplicate_issue_codes_in_the_rho_table_fail_closed():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "duplicate issue codes" in source


# --- failure paths -----------------------------------------------------------


def test_score_grid_rejects_a_non_finite_lambda():
    with pytest.raises(ValueError, match="lambda_home"):
        rebase.score_grid(float("nan"), 1.0, 0.0, GOALS)


def test_score_grid_rejects_a_non_positive_lambda():
    with pytest.raises(ValueError, match="lambda_away"):
        rebase.score_grid(1.0, 0.0, 0.0, GOALS)


def test_score_grid_rejects_rho_outside_the_r_supported_range():
    # r/dixon_coles_grid.R's dc_validate_rho accepts [-0.5, 0.5]; the port must agree.
    for rho in (-0.51, 0.51, float("inf")):
        with pytest.raises(ValueError, match="rho"):
            rebase.score_grid(1.2, 1.0, rho, GOALS)


def test_score_grid_accepts_the_range_boundaries():
    for rho in (-0.5, 0.5):
        grid = rebase.score_grid(1.2, 1.0, rho, GOALS)
        assert grid.sum() == pytest.approx(1.0, abs=1e-12)


def test_handicap_line_gap_rejects_an_empty_distribution():
    with pytest.raises(ValueError):
        rebase.handicap_line_gap(np.array([], dtype=int), np.array([]), 0, 1e-12)
