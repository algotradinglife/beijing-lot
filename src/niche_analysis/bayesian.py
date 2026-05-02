"""Beta-Binomial posterior + P(EV>threshold) tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import stats


@dataclass
class Posterior:
    alpha: float
    beta: float
    n: int
    k: int
    prior_mean: float
    kappa: float

    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def quantile(self, q: float) -> float:
        return float(stats.beta.ppf(q, self.alpha, self.beta))

    def cdf(self, p: float) -> float:
        return float(stats.beta.cdf(p, self.alpha, self.beta))

    def prob_greater(self, p: float) -> float:
        return 1.0 - self.cdf(p)

    def prob_ev_above(
        self,
        sp_proxy: float,
        threshold: float = 1.05,
        net_payout_factor: float = 0.65,
    ) -> float:
        """P(p * sp_proxy * net_payout_factor > threshold).

        We solve for p_critical = threshold / (sp_proxy * net_payout_factor)
        and return P(p > p_critical).  In the user's framing
        net_payout_factor=0.65 (1 - 35% rake).
        """
        denom = sp_proxy * net_payout_factor
        if denom <= 0:
            return 0.0
        p_crit = threshold / denom
        if p_crit >= 1.0:
            return 0.0
        if p_crit <= 0.0:
            return 1.0
        return self.prob_greater(p_crit)


def fit_posterior(
    k: int,
    n: int,
    prior_mean: float,
    kappa: float = 100.0,
) -> Posterior:
    """Beta-Binomial conjugate update.

    prior: Beta(kappa * mean, kappa * (1-mean))
    likelihood: Binomial(n, p) with k successes
    posterior: Beta(alpha + k, beta + n - k)
    """
    prior_mean = float(np.clip(prior_mean, 1e-6, 1.0 - 1e-6))
    a0 = kappa * prior_mean
    b0 = kappa * (1.0 - prior_mean)
    return Posterior(alpha=a0 + k, beta=b0 + (n - k), n=n, k=k,
                     prior_mean=prior_mean, kappa=kappa)


def bootstrap_mean(
    wins: np.ndarray,
    n_boot: int = 1000,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """Bootstrap the empirical mean of a 0/1 vector."""
    if rng is None:
        rng = np.random.default_rng(42)
    n = len(wins)
    if n == 0:
        return np.array([])
    idx = rng.integers(0, n, size=(n_boot, n))
    return wins[idx].mean(axis=1)


def binomial_pvalue_one_sided(k: int, n: int, p0: float) -> float:
    """One-sided p-value: P(X >= k | n, p0).  Used for Bonferroni reporting."""
    if n == 0:
        return 1.0
    return float(stats.binom.sf(k - 1, n, p0))
