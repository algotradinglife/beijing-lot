"""Target exactly 10% utilization via precise Kelly tuning per mix."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from equity_curve_default import simulate_with_stake, INITIAL
from src.dual_sweep.variants import build_archetype_a_qual

qual_a, _ = build_archetype_a_qual()
TARGET_UTIL = 0.10


def metrics(pnl, initial=INITIAL):
    bankroll = initial + np.cumsum(pnl)
    bankroll = np.maximum(bankroll, 0.01)
    n = len(pnl)
    cagr = (bankroll[-1] / initial) ** (52/n) - 1 if n > 0 else 0
    pct = pnl / initial
    sharpe = (np.mean(pct) * 52) / (np.std(pct, ddof=1) * np.sqrt(52)) if np.std(pct, ddof=1) > 0 else 0
    seq = np.concatenate([[initial], bankroll])
    rm = np.maximum.accumulate(seq)
    dd = (seq - rm) / rm
    return dict(
        final=float(bankroll[-1]), cagr=float(cagr), sharpe=float(sharpe),
        max_dd=float(np.min(dd)),
        calmar=cagr/abs(np.min(dd)) if np.min(dd) < 0 else 0,
        hit_rate=float((pnl > 0).mean()),
    )


def run(n, k):
    return simulate_with_stake(qual_a, n_legs=n, kelly_fraction=k,
                                diversity_lambda=0.5, max_combos_per_week=100)


def find_kelly(w2, w4, target=0.10, iters=10):
    """Bracketed search for the Kelly fraction that gives mix utilization ~ target."""
    lo, hi = 0.01, 0.6
    best = (None, 1e9, 0)
    for _ in range(iters):
        mid = (lo + hi) / 2
        df2 = run(2, mid); df4 = run(4, mid)
        s2 = df2['week_stake'].mean(); s4 = df4['week_stake'].mean()
        util = (w2 * s2 + w4 * s4) / INITIAL
        diff = abs(util - target)
        if diff < best[1]:
            best = (mid, diff, util)
        if util < target: lo = mid
        else: hi = mid
    return best[0], best[2]


def main():
    print(f"{'config':<22} {'Kelly':>7} {'util%':>6} {'final':>12} {'CAGR':>7} "
          f"{'Sharpe':>7} {'MaxDD':>8} {'hit%':>6}")
    print('-' * 95)
    mixes = [
        ("纯 N=4",            0.0, 1.0),
        ("10% N=2, 90% N=4",  0.1, 0.9),
        ("30% N=2, 70% N=4",  0.3, 0.7),
        ("50% N=2, 50% N=4",  0.5, 0.5),
        ("70% N=2, 30% N=4",  0.7, 0.3),
        ("90% N=2, 10% N=4",  0.9, 0.1),
        ("纯 N=2",            1.0, 0.0),
    ]
    for name, w2, w4 in mixes:
        k, util = find_kelly(w2, w4, TARGET_UTIL, iters=8)
        df2 = run(2, k); df4 = run(4, k)
        m = df2[['week_key', 'week_pnl']].rename(columns={'week_pnl': 'p2'}).merge(
            df4[['week_key', 'week_pnl']].rename(columns={'week_pnl': 'p4'}),
            on='week_key', how='outer').fillna(0).sort_values('week_key').reset_index(drop=True)
        pnl = w2 * m['p2'].values + w4 * m['p4'].values
        r = metrics(pnl)
        print(f"{name:<22} {k:.4f}  {util*100:>5.1f}% {r['final']:>11,.0f}  "
              f"{r['cagr']*100:>5.1f}%  {r['sharpe']:>5.2f}  "
              f"{r['max_dd']*100:>6.1f}%  {r['hit_rate']*100:>5.1f}%")


if __name__ == "__main__":
    main()
