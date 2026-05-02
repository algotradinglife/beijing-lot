"""Tests for the EV / proxy-SP module."""
from __future__ import annotations

import numpy as np

from src.backtest.ev import (
    RETURN_RATE_RATIO_NAIVE,
    fit_empirical_sp_model,
    model_ev,
    naive_proxy_sp,
)


def test_naive_proxy_sp_scales():
    sp = naive_proxy_sp(3.0)
    assert abs(sp - 3.0 * RETURN_RATE_RATIO_NAIVE) < 1e-9


def test_model_ev_formula():
    # p=0.5, sp=4 -> ev = 0.5 * 4 * 0.65 = 1.30
    assert abs(model_ev(0.5, 4.0) - 1.30) < 1e-9


def test_empirical_fit_falls_back_to_naive_with_few_samples():
    eu = np.array([2.0, 3.0])
    sp = np.array([1.4, 1.7])
    codes = np.array(["3", "3"])
    m = fit_empirical_sp_model(eu, sp, codes)
    a, b = m.coefs["3"]
    assert b == RETURN_RATE_RATIO_NAIVE


def test_empirical_fit_recovers_known_relationship():
    rng = np.random.default_rng(0)
    n = 200
    eu = rng.uniform(1.5, 6.0, size=n)
    sp_true = 0.2 + 0.8 * eu + rng.normal(0, 0.05, size=n)
    codes = np.array(["3"] * n)
    m = fit_empirical_sp_model(eu, sp_true, codes)
    a, b = m.coefs["3"]
    assert 0.7 < b < 0.9
    assert -0.1 < a < 0.5


def test_empirical_predict():
    eu = np.array([2.0] * 60)
    sp = np.array([1.5] * 60)
    codes = np.array(["1"] * 60)
    m = fit_empirical_sp_model(eu, sp, codes)
    # When all SPs are 1.5 the slope is 0 and intercept is 1.5
    assert abs(m.predict(2.0, "1") - 1.5) < 1e-3
