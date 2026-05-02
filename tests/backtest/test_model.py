"""Tests for the probability model (avg-EU 1X2 → p3/p1/p0)."""
from __future__ import annotations

import pytest

from src.backtest.model import (
    apply_draw_correction,
    devig_proportional,
    model_probs_from_eu,
)


def test_devig_sums_to_one():
    p = devig_proportional(2.5, 3.5, 2.8)
    assert abs(sum(p) - 1.0) < 1e-9
    for x in p:
        assert 0 < x < 1


def test_devig_symmetric():
    """Equal odds -> equal probabilities."""
    p = devig_proportional(3.0, 3.0, 3.0)
    for x in p:
        assert abs(x - 1 / 3) < 1e-9


def test_draw_correction_h_zero():
    p3, p1, p0 = apply_draw_correction(0.5, 0.25, 0.25, 0)
    assert p1 > 0.25  # boosted
    assert p3 < 0.5
    assert abs(p3 + p1 + p0 - 1.0) < 1e-9


def test_draw_correction_disabled_for_large_h():
    # |h|>=2 should not change anything (only normalisation).
    in_p = (0.5, 0.25, 0.25)
    out = apply_draw_correction(*in_p, abs_h=3)
    for a, b in zip(in_p, out):
        assert abs(a - b) < 1e-9


def test_model_probs_realistic_inputs():
    res = model_probs_from_eu(2.0, 3.5, 4.0, handicap=0)
    s = res.p3 + res.p1 + res.p0
    assert abs(s - 1.0) < 1e-9
    assert res.p3 > res.p0  # home favoured
    assert 0 < res.p1 < 1


def test_model_probs_no_correction():
    res = model_probs_from_eu(2.0, 3.5, 4.0, handicap=0, apply_correction=False)
    direct = devig_proportional(2.0, 3.5, 4.0)
    assert abs(res.p3 - direct[0]) < 1e-9
    assert abs(res.p1 - direct[1]) < 1e-9
    assert abs(res.p0 - direct[2]) < 1e-9
