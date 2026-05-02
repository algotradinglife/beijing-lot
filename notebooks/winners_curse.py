"""Winner's curse simulator: how should we set the EV threshold for inclusion?

Context: our edge estimate ê = p̂ × SP × 0.65 - 1 is noisy because p̂ has noise.
If we filter "include if ê > threshold T", we're conditionally selecting on positive
estimation noise — the realized edge after filtering is LOWER than the threshold T
(the winner's curse / regression-to-the-mean effect).

This sim quantifies how T affects:
1. Realized edge among accepted bets (true edge, not estimated)
2. Acceptance rate (number of bets per N candidates)
3. Realized portfolio ROI

Goal: find the T that maximizes long-term growth, balancing edge per bet × volume.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

R = 0.65


def simulate_filter(
    n_candidates: int = 200_000,
    edge_mean: float = 0.0,        # population mean of true edge (negative because most bets are -EV)
    edge_std: float = 0.05,        # population std of true edge
    p_noise_std: float = 0.02,     # std of probability estimate noise
    sp_mean: float = 3.0,
    sp_std: float = 1.0,
    threshold_grid: np.ndarray = np.arange(0.00, 0.21, 0.01),
    seed: int = 0,
) -> pd.DataFrame:
    """Simulate a population of candidate bets, draw noisy estimates, filter,
    and report realized stats by threshold."""
    rng = np.random.default_rng(seed)
    # SP draw
    sigma = np.sqrt(np.log(1 + (sp_std / sp_mean) ** 2))
    mu_ = np.log(sp_mean) - 0.5 * sigma ** 2
    sps = rng.lognormal(mean=mu_, sigma=sigma, size=n_candidates)
    sps = np.clip(sps, 1.55, 50.0)

    # True edge per candidate (truncated normal-ish)
    true_edge = rng.normal(edge_mean, edge_std, n_candidates)

    # True probability implied by edge: p = (1 + edge) / (sp * R)
    true_p = (1 + true_edge) / (sps * R)
    true_p = np.clip(true_p, 0.001, 0.99)

    # Noisy probability estimate: p̂ = p + noise, then derived edge ê
    p_hat = true_p + rng.normal(0, p_noise_std, n_candidates)
    p_hat = np.clip(p_hat, 0.001, 0.99)
    est_edge = p_hat * sps * R - 1.0

    rows = []
    for T in threshold_grid:
        sel = est_edge >= T
        n_acc = sel.sum()
        if n_acc == 0:
            continue
        rows.append({
            "T": T,
            "accept_rate": n_acc / n_candidates,
            "n_accepted": int(n_acc),
            "mean_est_edge": est_edge[sel].mean(),
            "mean_true_edge": true_edge[sel].mean(),
            "winners_curse_gap": est_edge[sel].mean() - true_edge[sel].mean(),
            "frac_truly_pos": (true_edge[sel] > 0).mean(),
        })
    return pd.DataFrame(rows)


def main():
    # Scenario A: market-implied baseline (our model = market, no edge anywhere; pure noise)
    print("\n=== Scenario A: zero true edge (population), σ_p = 0.02 ===")
    df = simulate_filter(edge_mean=0.0, edge_std=0.0, p_noise_std=0.02)
    print(df.to_string(index=False))

    # Scenario B: weak signal (small +edge in 10% of population, rest 0)
    print("\n=== Scenario B: 0% population edge but σ_edge=5% (some are real +EV) ===")
    df = simulate_filter(edge_mean=0.0, edge_std=0.05, p_noise_std=0.02)
    print(df.to_string(index=False))

    # Scenario C: realistic — small positive shift + modest noise
    print("\n=== Scenario C: +1% mean edge, σ_edge=4%, σ_p=0.015 ===")
    df = simulate_filter(edge_mean=0.01, edge_std=0.04, p_noise_std=0.015)
    print(df.to_string(index=False))

    # Scenario D: optimistic — assume our priors give us +3% mean edge
    print("\n=== Scenario D: +3% mean edge (priors work), σ_edge=4%, σ_p=0.015 ===")
    df = simulate_filter(edge_mean=0.03, edge_std=0.04, p_noise_std=0.015)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
