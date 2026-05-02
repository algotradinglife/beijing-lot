"""Tests for Beta-Binomial posterior arithmetic."""

import math

import numpy as np
import pytest
from scipy import stats

from src.niche_analysis.bayesian import (
    binomial_pvalue_one_sided, bootstrap_mean, fit_posterior,
)


def test_posterior_mean_matches_conjugate_formula():
    # Prior Beta(50*0.4, 50*0.6) = Beta(20, 30); k=15, n=30
    post = fit_posterior(k=15, n=30, prior_mean=0.4, kappa=50.0)
    expected_mean = (20 + 15) / (20 + 15 + 30 + 15)
    assert math.isclose(post.mean(), expected_mean, rel_tol=1e-9)


def test_posterior_quantiles_match_scipy():
    post = fit_posterior(k=10, n=20, prior_mean=0.5, kappa=20.0)
    # alpha = 10 + 10 = 20; beta = 10 + 10 = 20
    assert math.isclose(post.quantile(0.05), stats.beta.ppf(0.05, 20, 20), rel_tol=1e-9)
    assert math.isclose(post.quantile(0.95), stats.beta.ppf(0.95, 20, 20), rel_tol=1e-9)


def test_posterior_cdf_matches_scipy():
    post = fit_posterior(k=8, n=16, prior_mean=0.5, kappa=10.0)
    # alpha=5+8=13, beta=5+8=13
    assert math.isclose(post.cdf(0.5), stats.beta.cdf(0.5, 13, 13), rel_tol=1e-9)
    # symmetric -> cdf(0.5) == 0.5
    assert math.isclose(post.cdf(0.5), 0.5, abs_tol=1e-9)


def test_prob_ev_above_zero_when_breakeven_above_one():
    # Tiny SP -> breakeven p > 1, so P(EV>1.05)=0
    post = fit_posterior(k=10, n=20, prior_mean=0.5, kappa=10.0)
    assert post.prob_ev_above(sp_proxy=0.5, threshold=1.05) == 0.0


def test_prob_ev_above_one_when_breakeven_negative():
    post = fit_posterior(k=10, n=20, prior_mean=0.5, kappa=10.0)
    # Huge SP -> p_crit ~ 0
    p_ev = post.prob_ev_above(sp_proxy=1000.0, threshold=1.05)
    assert p_ev > 0.999


def test_prob_ev_above_monotone_in_k():
    # More wins -> higher P(EV > 1.05) at fixed sp_proxy
    post_low = fit_posterior(k=10, n=50, prior_mean=0.3, kappa=20.0)
    post_high = fit_posterior(k=25, n=50, prior_mean=0.3, kappa=20.0)
    sp = 4.0
    assert post_high.prob_ev_above(sp_proxy=sp) > post_low.prob_ev_above(sp_proxy=sp)


def test_bootstrap_mean_shape_and_range():
    rng = np.random.default_rng(0)
    wins = np.array([0, 1, 1, 0, 1, 1, 0, 0, 1, 0], dtype=float)
    means = bootstrap_mean(wins, n_boot=500, rng=rng)
    assert means.shape == (500,)
    assert means.min() >= 0.0
    assert means.max() <= 1.0
    # Bootstrap mean ~ empirical mean
    assert abs(means.mean() - wins.mean()) < 0.1


def test_binomial_pvalue_matches_scipy():
    p = binomial_pvalue_one_sided(k=15, n=30, p0=0.4)
    expected = stats.binom.sf(14, 30, 0.4)
    assert math.isclose(p, expected, rel_tol=1e-9)


def test_binomial_pvalue_n_zero():
    assert binomial_pvalue_one_sided(0, 0, 0.5) == 1.0
