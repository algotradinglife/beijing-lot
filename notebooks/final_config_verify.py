"""Final config verification: N=4 + Kelly=1/16 + ProfitLock.

Run baseline + ProfitLock variants, confirm Drawdown agent's findings.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dual_sweep.variants import build_archetype_a_qual
from src.sweep.simulator import simulate

INITIAL = 100_000.0


def metrics(weekly_pnl, initial=INITIAL, locked=0):
    """Metrics with optional locked-pile."""
    bankroll = initial + np.cumsum(weekly_pnl)
    bankroll = np.maximum(bankroll, 0.01)
    n_weeks = len(weekly_pnl)
    if n_weeks == 0 or bankroll[-1] <= 0:
        return None
    final_wealth = bankroll[-1] + locked
    cum_roi = (final_wealth - initial) / initial
    years = n_weeks / 52.0
    cagr = (final_wealth / initial) ** (1.0 / max(years, 1e-6)) - 1.0
    pct = weekly_pnl / initial
    mean_r = float(np.mean(pct))
    std_r = float(np.std(pct, ddof=1)) if len(pct) > 1 else 0.0
    sharpe = (mean_r * 52.0) / (std_r * np.sqrt(52.0)) if std_r > 0 else 0.0
    seq = np.concatenate([[initial], bankroll])
    rm = np.maximum.accumulate(seq)
    dd = (seq - rm) / rm
    max_dd = float(np.min(dd))
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0
    return dict(final=float(final_wealth), final_active=float(bankroll[-1]),
                locked=float(locked), cum_roi=float(cum_roi),
                cagr=float(cagr), sharpe=float(sharpe), max_dd=float(max_dd),
                calmar=float(calmar))


def apply_profitlock(weekly_pnl_series, initial=INITIAL, mult=2.0, skim=0.30):
    """Skim `skim` fraction off when bankroll reaches `mult` × peak high-water-mark.
    Returns (active_bankroll_path, locked_path, total_wealth_path)."""
    bankroll = initial
    threshold = initial * mult
    locked = 0.0
    active_path = []
    locked_path = []
    for pnl in weekly_pnl_series:
        bankroll += pnl
        if bankroll >= threshold:
            skimmed = bankroll * skim
            locked += skimmed
            bankroll -= skimmed
            threshold = bankroll * mult
        active_path.append(bankroll)
        locked_path.append(locked)
    return np.array(active_path), np.array(locked_path)


def metrics_total(active_path, locked_path, initial=INITIAL):
    """Metrics on TOTAL wealth (active + locked) — psychological DD."""
    total = active_path + locked_path
    n = len(total)
    if n == 0 or total[-1] <= 0: return None
    final = total[-1]
    cum_roi = (final - initial) / initial
    yrs = n / 52.0
    cagr = (final / initial) ** (1.0 / max(yrs, 1e-6)) - 1.0
    # Returns based on TOTAL wealth
    total_seq = np.concatenate([[initial], total])
    rm = np.maximum.accumulate(total_seq)
    dd = (total_seq - rm) / rm
    max_dd = float(np.min(dd))
    pct = np.diff(total_seq) / total_seq[:-1]
    mean_r = float(np.mean(pct))
    std_r = float(np.std(pct, ddof=1)) if len(pct) > 1 else 0.0
    sharpe = (mean_r * 52.0) / (std_r * np.sqrt(52.0)) if std_r > 0 else 0.0
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0
    return dict(final=float(final), final_active=float(active_path[-1]),
                locked=float(locked_path[-1]), cum_roi=float(cum_roi),
                cagr=float(cagr), sharpe=float(sharpe),
                max_dd=float(max_dd), calmar=float(calmar))


def main():
    print("Loading qualifying picks...")
    qual_a, _ = build_archetype_a_qual()
    print(f"qual_a rows: {len(qual_a)}\n")

    # Baseline N=4 Kelly=1/16
    print("Baseline: N=4 Kelly=1/16, no ProfitLock")
    res = simulate(qual_a, n_legs=4, initial_bankroll=INITIAL,
                   kelly_fraction=1/16, per_combo_cap_frac=0.005,
                   weekly_stake_cap_frac=0.25, max_combos_per_week=300,
                   seed=7, test_only=True)
    base_pnl = res.weekly["week_pnl"].values
    m = metrics(base_pnl)
    print(f"  final={m['final']:>11,.0f}  CAGR={m['cagr']*100:>6.1f}%  "
          f"Sharpe={m['sharpe']:>5.2f}  MaxDD={m['max_dd']*100:>6.1f}%  "
          f"Calmar={m['calmar']:>5.2f}")
    baseline_metrics = m

    # ProfitLock variants — using TOTAL WEALTH definition (active + locked)
    print("\nProfitLock variants (DD measured on TOTAL = active + locked):")
    print(f"{'mult':>6} {'skim':>6} {'total':>13} {'active':>13} {'locked':>13} "
          f"{'CAGR':>7} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7}")
    for mult, skim in [(2.0, 0.30), (2.0, 0.20), (2.0, 0.50),
                       (1.5, 0.30), (3.0, 0.30), (2.0, 0.10),
                       (1.3, 0.20), (1.5, 0.50)]:
        active_p, locked_p = apply_profitlock(base_pnl, INITIAL, mult, skim)
        m = metrics_total(active_p, locked_p, INITIAL)
        if m is None:
            continue
        print(f"  {mult:>4.1f}  {skim:>4.2f}  {m['final']:>11,.0f}  "
              f"{m['final_active']:>11,.0f}  {m['locked']:>11,.0f}  "
              f"{m['cagr']*100:>6.1f}%  "
              f"{m['sharpe']:>5.2f}  {m['max_dd']*100:>7.1f}%  {m['calmar']:>5.2f}")

    # Forward-looking: how often does bankroll double in 1 year?
    print("\n=== ProfitLock practical advice ===")
    bankroll_path = INITIAL + np.cumsum(base_pnl)
    doublings = 0
    last_high = INITIAL
    for b in bankroll_path:
        if b >= last_high * 2:
            doublings += 1
            last_high = b
    weeks = len(base_pnl)
    yrs = weeks / 52
    print(f"In {weeks} weeks ({yrs:.1f} years): {doublings} doublings observed")
    print(f"Average: 1 doubling per {yrs/max(doublings,1):.1f} years")
    print(f"Implication: in 100k bankroll, expect ProfitLock trigger ~每 {yrs/max(doublings,1):.1f} 年一次")
    print(f"Each trigger transfers 30% of new bankroll to 'locked' pile (e.g., bank account)")


if __name__ == "__main__":
    main()
