"""Winner's curse v2: realistic σ_p ≈ 0.03 (Pinnacle inherent noise + our model recon).

Adds:
- Combined-noise scenarios bracketing realistic operating point
- Compute realized PORTFOLIO ROI per threshold (Kelly-weighted), giving the
  truly relevant metric — long-run growth — instead of just realized edge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

R = 0.65


def kelly_full(p: float, sp: float, r: float = R) -> float:
    o = sp * r
    if o <= 1:
        return 0.0
    return max(0.0, (p * o - 1) / (o - 1))


def simulate_filter_with_kelly(
    n_candidates: int = 100_000,
    edge_mean: float = 0.0,
    edge_std: float = 0.05,
    p_noise_std: float = 0.03,
    sp_mean: float = 3.0,
    sp_std: float = 1.0,
    threshold_grid: np.ndarray = np.arange(0.00, 0.21, 0.01),
    kelly_frac: float = 0.25,
    seed: int = 0,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    sigma = np.sqrt(np.log(1 + (sp_std / sp_mean) ** 2))
    mu_ = np.log(sp_mean) - 0.5 * sigma ** 2
    sps = rng.lognormal(mean=mu_, sigma=sigma, size=n_candidates)
    sps = np.clip(sps, 1.55, 50.0)

    true_edge = rng.normal(edge_mean, edge_std, n_candidates)
    true_p = (1 + true_edge) / (sps * R)
    true_p = np.clip(true_p, 0.001, 0.95)

    p_hat = true_p + rng.normal(0, p_noise_std, n_candidates)
    p_hat = np.clip(p_hat, 0.001, 0.95)
    est_edge = p_hat * sps * R - 1.0

    rows = []
    for T in threshold_grid:
        sel = est_edge >= T
        if sel.sum() < 10:
            continue
        sps_sel = sps[sel]
        true_p_sel = true_p[sel]
        true_edge_sel = true_edge[sel]
        est_edge_sel = est_edge[sel]
        p_hat_sel = p_hat[sel]

        # Kelly stake fraction per candidate (using estimated p, as we'd do live)
        k = np.array([kelly_full(p, s) for p, s in zip(p_hat_sel, sps_sel)])
        k *= kelly_frac
        # Cap at 5% per match
        k = np.minimum(k, 0.05)

        # ROI per yuan staked, using TRUE probabilities
        # E[return per yuan] = true_p * (sps*R) - 1
        ev_per_yuan_true = true_p_sel * sps_sel * R - 1
        # Mean stake-weighted ROI (this is the realized portfolio ROI under quarter-Kelly)
        # Each "bet" gets a stake fraction k of bankroll; total fraction at risk = sum(k)/N (normalized)
        if k.sum() == 0:
            roi_weighted = 0.0
        else:
            roi_weighted = (k * ev_per_yuan_true).sum() / k.sum()

        # Growth rate proxy: E[log(1 + k * (return per yuan))]
        # For each bet: log-growth = p × log(1 + k×(o-1)) + (1-p) × log(1-k)
        o = sps_sel * R
        with np.errstate(divide="ignore", invalid="ignore"):
            log_growth = (
                true_p_sel * np.log(np.maximum(1 + k * (o - 1), 1e-9))
                + (1 - true_p_sel) * np.log(np.maximum(1 - k, 1e-9))
            )
        # Take mean log-growth per bet (approximation to portfolio log-growth assuming
        # independent matches and bankroll re-up between bets)
        mean_log_growth = log_growth.mean()

        rows.append({
            "T": T,
            "accept_rate": sel.sum() / n_candidates,
            "n_accepted": int(sel.sum()),
            "mean_true_edge": true_edge_sel.mean(),
            "winners_curse_gap": est_edge_sel.mean() - true_edge_sel.mean(),
            "frac_truly_pos": (true_edge_sel > 0).mean(),
            "mean_kelly_stake": k.mean(),
            "roi_per_yuan": roi_weighted,
            "log_growth_per_bet": mean_log_growth,
        })
    return pd.DataFrame(rows)


def main():
    print("\n=== Realistic: σ_p = 0.03, edge mean=+1%, edge std=4% ===")
    df = simulate_filter_with_kelly(p_noise_std=0.03, edge_mean=0.01, edge_std=0.04)
    print(df.to_string(index=False))

    print("\n=== Realistic optimistic: σ_p = 0.03, edge mean=+3% (priors work), edge std=4% ===")
    df = simulate_filter_with_kelly(p_noise_std=0.03, edge_mean=0.03, edge_std=0.04)
    print(df.to_string(index=False))

    print("\n=== Pessimistic: σ_p = 0.04, edge mean=0% ===")
    df = simulate_filter_with_kelly(p_noise_std=0.04, edge_mean=0.0, edge_std=0.04)
    print(df.to_string(index=False))

    print("\n=== Stress: σ_p = 0.05, edge mean=0% ===")
    df = simulate_filter_with_kelly(p_noise_std=0.05, edge_mean=0.0, edge_std=0.04)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
