"""Check if niche q is degrading year-over-year.

For each year, compute mean q for each surviving niche. If q is dropping
over time, the edge is being arbitrated away → strategy will degrade.
If q is stable, the niche is structural.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dual_sweep.variants import build_archetype_a_qual


def main():
    qual_a, surv_a = build_archetype_a_qual()
    qual_a["year"] = pd.to_datetime(qual_a["kickoff_ts"], errors="coerce").dt.year

    print(f"Surviving niches: {len(surv_a)}")
    print("Niche columns:", list(surv_a.columns)[:10])
    print()
    print(f"Year range: {qual_a['year'].min():.0f} → {qual_a['year'].max():.0f}")

    # For each year, compute mean q across all qualifying picks (q = did_win × sp)
    print("\n=== Mean q by year (all qualifying picks pooled) ===")
    yr = qual_a.groupby("year").agg(
        n_picks=("did_win", "size"),
        hit_rate=("did_win", "mean"),
        mean_sp=("sp", "mean"),
        q_obs_mean=("q_obs", "mean"),
        q_train_mean=("q_train", "mean"),
    ).round(4)
    yr["per_leg_EV"] = (yr["q_obs_mean"] * 0.65 - 1).round(4)
    print(yr)

    # Per niche × year (for top niches)
    print("\n=== Mean q by year × niche (top 10 niches by total picks) ===")
    if "niche_id" in qual_a.columns:
        top_niches = qual_a["niche_id"].value_counts().head(10).index.tolist()
        for nid in top_niches:
            sub = qual_a[qual_a["niche_id"] == nid]
            if len(sub) < 50:
                continue
            yr_n = sub.groupby("year").agg(
                n=("did_win", "size"),
                q=("q_obs", "mean"),
            ).round(3)
            yr_n["q"] = yr_n["q"].round(3)
            print(f"\nNiche: {nid}")
            print(yr_n.T)
    else:
        print("(niche_id not present, skip per-niche)")

    # Trend test: linear regression of yearly q vs year
    print("\n=== q linear trend by year (do edges decay?) ===")
    from scipy.stats import linregress
    yrs = yr.index.values
    qs = yr["q_obs_mean"].values
    # Normalize year to 0
    x = yrs - yrs[0]
    if len(x) >= 3:
        slope, intercept, r_value, p_value, std_err = linregress(x, qs)
        print(f"Slope (q change per year): {slope:.4f}")
        print(f"R²: {r_value**2:.3f}")
        print(f"p-value: {p_value:.3f}")
        print(f"Year 1 implied q: {intercept:.3f}")
        print(f"Year {len(x)+1} implied q: {intercept + slope*(len(x)-1):.3f}")
        if p_value < 0.05:
            if slope < 0:
                print("⚠ Statistically significant DECAY in q over time")
            else:
                print("✓ Statistically significant INCREASE in q over time")
        else:
            print("✓ No significant trend; q is stable")

    out = "/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/niche_q_yearly.csv"
    yr.to_csv(out)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
