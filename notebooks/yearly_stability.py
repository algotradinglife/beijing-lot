"""Yearly stability check for N=4 Kelly=1/16.

Run the strategy independently each year (each year starts from 100k).
Verify CAGR is consistent, not driven by 1-2 lucky years.
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


def metrics(weekly_pnl: np.ndarray, initial: float = INITIAL) -> dict:
    if len(weekly_pnl) == 0:
        return dict(n_weeks=0, final=initial, cum_roi=0.0, cagr=0.0,
                    sharpe=0.0, max_dd=0.0, calmar=0.0, hit_rate=0.0)
    bankroll = initial + np.cumsum(weekly_pnl)
    bankroll = np.maximum(bankroll, 0.01)
    n_weeks = len(weekly_pnl)
    cum_roi = (bankroll[-1] - initial) / initial
    years = n_weeks / 52.0
    cagr = (bankroll[-1] / initial) ** (1.0 / max(years, 1e-6)) - 1.0
    pct = weekly_pnl / initial
    mean_r = float(np.mean(pct))
    std_r = float(np.std(pct, ddof=1)) if len(pct) > 1 else 0.0
    sharpe = (mean_r * 52.0) / (std_r * np.sqrt(52.0)) if std_r > 0 else 0.0
    seq = np.concatenate([[initial], bankroll])
    rm = np.maximum.accumulate(seq)
    dd = (seq - rm) / rm
    max_dd = float(np.min(dd))
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0
    return dict(
        n_weeks=n_weeks,
        final=float(bankroll[-1]),
        cum_roi=float(cum_roi),
        cagr=float(cagr),
        sharpe=float(sharpe),
        max_dd=float(max_dd),
        calmar=float(calmar),
        hit_rate=float((weekly_pnl > 0).mean()),
    )


def main():
    print("Loading Archetype A qualifying picks...")
    qual_a, _ = build_archetype_a_qual()

    # Date column 'kickoff_ts' might be present? Let's check
    print("Columns:", list(qual_a.columns))

    # 期号 ranges by year — use match in qual_a's expect column
    # 期号 format: 6 digits, first 2-3 = year-derived
    # Looking at data: 18xxxx for 2018, 25xxx-26xxx for recent years
    # Strategy: bin by year using kickoff_ts if present, else by expect range

    if "kickoff_ts" in qual_a.columns:
        qual_a["year"] = pd.to_datetime(qual_a["kickoff_ts"], errors="coerce").dt.year
    else:
        # Use date column if present
        date_col = next((c for c in qual_a.columns if "date" in c.lower() or "ts" in c.lower()),
                        None)
        if date_col:
            qual_a["year"] = pd.to_datetime(qual_a[date_col], errors="coerce").dt.year
        else:
            print("No date column found, using 期号 prefix")
            # 期号 like 180201 → 2018; 260512 → 2026
            qual_a["year"] = qual_a["expect"].astype(str).str[:2].astype(int).apply(
                lambda x: 2000 + x if x < 50 else 1900 + x)

    print(f"\nYear distribution:")
    print(qual_a["year"].value_counts().sort_index())

    rows = []
    for year in sorted(qual_a["year"].dropna().unique()):
        sub = qual_a[qual_a["year"] == year].copy()
        if len(sub) < 50:
            print(f"  Year {int(year)}: skip (n={len(sub)} too small)")
            continue
        # Each year independently from 100k, but no test_only filter
        # (we want each year to be the test universe)
        res = simulate(sub, n_legs=4, initial_bankroll=INITIAL,
                       kelly_fraction=1/16, per_combo_cap_frac=0.005,
                       weekly_stake_cap_frac=0.25, max_combos_per_week=300,
                       seed=7, test_only=False)
        m = metrics(res.weekly["week_pnl"].values) if len(res.weekly) else metrics(np.array([]))
        m["year"] = int(year)
        m["n_picks"] = len(sub)
        rows.append(m)
        print(f"  Year {int(year)}: n_picks={len(sub):>5}  weeks={m['n_weeks']:>3}  "
              f"final={m['final']:>11,.0f}  CAGR={m['cagr']*100:>7.1f}%  "
              f"Sharpe={m['sharpe']:>5.2f}  MaxDD={m['max_dd']*100:>6.1f}%")

    df = pd.DataFrame(rows)
    out = "/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/yearly_stability.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved to {out}")

    print("\n=== Cross-year stability metrics ===")
    pos_count = (df["cagr"] > 0).sum()
    neg_count = (df["cagr"] < 0).sum()
    print(f"Years with positive CAGR: {pos_count}/{len(df)}")
    print(f"Years with negative CAGR: {neg_count}/{len(df)}")
    print(f"Median CAGR: {df['cagr'].median()*100:.1f}%")
    print(f"Mean CAGR: {df['cagr'].mean()*100:.1f}%")
    print(f"Std CAGR: {df['cagr'].std()*100:.1f}%")
    print(f"Min CAGR: {df['cagr'].min()*100:.1f}% (year {int(df.loc[df['cagr'].idxmin(),'year'])})")
    print(f"Max CAGR: {df['cagr'].max()*100:.1f}% (year {int(df.loc[df['cagr'].idxmax(),'year'])})")
    print(f"\nMedian Sharpe: {df['sharpe'].median():.2f}")
    print(f"Median MaxDD: {df['max_dd'].median()*100:.1f}%")


if __name__ == "__main__":
    main()
