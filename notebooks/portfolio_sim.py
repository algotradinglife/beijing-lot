"""Portfolio Monte Carlo for 北单 让球胜平负 single-bet strategy.

Goal: quantify how batch size N, edge size, and stake rule affect the
distribution of batch outcomes, especially the worst-case loss tail.

Conventions
-----------
- 单关 (single bets) only — each match's outcome is independent.
- For each "candidate" bet, we have:
    p     : true probability of the chosen selection winning
    sp    : the parimutuel SP (raw, pre-return-rate)
    return rate r = 0.65
    decimal payout per yuan = sp * r  (gross, includes stake)
    edge per yuan staked = p * sp * r - 1  (== EV - 1)
- Kelly fraction: f* = (p*sp*r - 1) / (sp*r - 1)  (full Kelly for binary bet)
- Loss per yuan = -1 if bet loses; gain per yuan = (sp*r - 1) if bet wins.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

R = 0.65  # 北单 return rate


def kelly_full(p: float, sp: float, r: float = R) -> float:
    """Full Kelly fraction. Returns 0 if EV <= 0."""
    b = sp * r - 1.0
    if b <= 0:
        return 0.0
    f = (p * (b + 1) - 1) / b
    return max(0.0, f)


def simulate_batches(
    n_batches: int,
    n_per_batch: int,
    edge: float,
    sp_mean: float = 3.0,
    sp_std: float = 1.0,
    stake_rule: str = "equal",
    bankroll_per_batch: float = 1000.0,
    kelly_frac: float = 0.25,
    seed: int = 0,
) -> pd.DataFrame:
    """Simulate `n_batches` batches of `n_per_batch` independent bets each.

    Each bet has decimal-payout `sp*r` (sp drawn lognormal-ish) and
    a true probability `p` constructed so EV per yuan = `edge`.

    Returns a DataFrame with one row per batch:
        stake_total, gross_return, profit, hit_count, max_single_win
    """
    rng = np.random.default_rng(seed)
    rows = []
    n_total = n_batches * n_per_batch

    # Draw SP values: lognormal scaled to target mean/std
    sigma = np.sqrt(np.log(1 + (sp_std / sp_mean) ** 2))
    mu = np.log(sp_mean) - 0.5 * sigma ** 2
    sps = rng.lognormal(mean=mu, sigma=sigma, size=n_total)
    sps = np.clip(sps, 1.55, 50.0)  # 北单 SP is rarely <1.55 or >50

    # p chosen so that p*sp*r - 1 = edge → p = (1+edge)/(sp*r)
    ps = (1.0 + edge) / (sps * R)
    ps = np.clip(ps, 0.001, 0.95)

    # Per-bet stakes
    if stake_rule == "equal":
        stakes = np.full(n_total, bankroll_per_batch / n_per_batch)
    elif stake_rule == "frac_kelly":
        kf = np.array([kelly_full(p, sp) for p, sp in zip(ps, sps)])
        kf *= kelly_frac
        # Allocate proportional to kelly fraction within each batch,
        # capped by per-bet limit (kelly_frac * bankroll), with leftover unbet.
        kf = kf.reshape(n_batches, n_per_batch)
        # Each bet stake = bankroll * kf[i,j], but capped so sum per batch <= bankroll
        kf_sum = kf.sum(axis=1, keepdims=True)
        # If sum > 1, scale down; else use raw
        scale = np.where(kf_sum > 1.0, 1.0 / kf_sum, 1.0)
        stakes = (kf * scale * bankroll_per_batch).flatten()
    elif stake_rule == "ev_proportional":
        # stake proportional to edge, normalized to bankroll
        edge_per = ps * sps * R - 1.0
        edge_per = np.maximum(edge_per, 0)
        edge_per = edge_per.reshape(n_batches, n_per_batch)
        es = edge_per.sum(axis=1, keepdims=True)
        es = np.where(es == 0, 1, es)
        stakes = (edge_per / es * bankroll_per_batch).flatten()
    else:
        raise ValueError(f"unknown stake_rule {stake_rule}")

    wins = rng.uniform(size=n_total) < ps
    payout_per_yuan = sps * R  # gross, includes stake
    # profit per bet = stake * (payout_per_yuan - 1) on win, -stake on loss
    profits = np.where(wins, stakes * (payout_per_yuan - 1), -stakes)

    profits_b = profits.reshape(n_batches, n_per_batch)
    stakes_b = stakes.reshape(n_batches, n_per_batch)
    wins_b = wins.reshape(n_batches, n_per_batch)

    return pd.DataFrame({
        "stake_total": stakes_b.sum(axis=1),
        "profit": profits_b.sum(axis=1),
        "hits": wins_b.sum(axis=1),
    })


def summarize(df: pd.DataFrame, label: str) -> dict:
    p = df["profit"].values
    s = df["stake_total"].values
    roi = p / s
    return {
        "label": label,
        "n_batches": len(df),
        "mean_profit": p.mean(),
        "mean_stake": s.mean(),
        "mean_roi": roi.mean(),
        "roi_p05": np.quantile(roi, 0.05),
        "roi_p25": np.quantile(roi, 0.25),
        "roi_p50": np.quantile(roi, 0.50),
        "roi_p75": np.quantile(roi, 0.75),
        "roi_p95": np.quantile(roi, 0.95),
        "p_negative": float((p < 0).mean()),
        "p_lose_50pct": float((roi < -0.5).mean()),  # batch loses >50% of stake
        "worst_roi": roi.min(),
        "best_roi": roi.max(),
    }


def main():
    edges = [0.00, 0.03, 0.05, 0.10]
    Ns = [5, 10, 20, 50, 100]
    rules = ["equal", "frac_kelly", "ev_proportional"]
    results = []
    for edge in edges:
        for N in Ns:
            for rule in rules:
                df = simulate_batches(
                    n_batches=20000,
                    n_per_batch=N,
                    edge=edge,
                    stake_rule=rule,
                    seed=42 + N + int(edge * 1000),
                )
                r = summarize(df, f"edge={edge:+.2%} N={N} rule={rule}")
                r["edge"] = edge
                r["N"] = N
                r["rule"] = rule
                results.append(r)
    out = pd.DataFrame(results)
    out_path = "/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/portfolio_sweep.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {len(out)} rows to {out_path}")

    # Print key tables
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)

    print("\n=== EQUAL STAKES — ROI distribution by edge × N ===")
    eq = out[out["rule"] == "equal"]
    print(eq.pivot_table(index="N", columns="edge", values="mean_roi"))
    print("\nP(batch profit < 0):")
    print(eq.pivot_table(index="N", columns="edge", values="p_negative"))
    print("\nROI 5th percentile (worst 5% of batches):")
    print(eq.pivot_table(index="N", columns="edge", values="roi_p05"))

    print("\n=== FRAC KELLY (1/4) — ROI distribution by edge × N ===")
    fk = out[out["rule"] == "frac_kelly"]
    print(fk.pivot_table(index="N", columns="edge", values="mean_roi"))
    print("\nP(batch profit < 0):")
    print(fk.pivot_table(index="N", columns="edge", values="p_negative"))


if __name__ == "__main__":
    main()
