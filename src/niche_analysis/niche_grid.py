"""Enumerate candidate niches (feature subsets) and aggregate stats."""

from __future__ import annotations

from itertools import combinations
from typing import Iterable

import numpy as np
import pandas as pd

DIMENSIONS = ["option_type", "handicap_class", "option_strength",
              "league_tier", "prob_bucket"]


def enumerate_niches(
    long_df: pd.DataFrame,
    min_n: int = 50,
) -> pd.DataFrame:
    """Build niches from 1-, 2-, and 3-dimensional combinations of features.

    For each combination of dims, group_by and emit one row per cell.
    """
    rows = []
    dims = DIMENSIONS

    # Marginal (1D) niches across each single dimension
    combos: list[tuple] = []
    for r in (1, 2, 3):
        for combo in combinations(dims, r):
            combos.append(combo)

    for combo in combos:
        gb = long_df.groupby(list(combo), observed=True)
        agg = gb.agg(
            n=("did_win", "size"),
            k=("did_win", "sum"),
            mean_implied=("implied_prob", "mean"),
            mean_winning_sp=("winning_sp", "mean"),
        ).reset_index()
        agg = agg[agg["n"] >= min_n]
        for _, r in agg.iterrows():
            stratum = {col: r[col] for col in combo}
            rows.append({
                "dims": "|".join(combo),
                "stratum": stratum,
                "stratum_str": ", ".join(f"{k}={v}" for k, v in stratum.items()),
                "n": int(r["n"]),
                "k": int(r["k"]),
                "mean_implied": float(r["mean_implied"]),
                "mean_winning_sp": (
                    float(r["mean_winning_sp"]) if pd.notna(r["mean_winning_sp"]) else float("nan")
                ),
            })
    return pd.DataFrame(rows)


def filter_long_by_stratum(long_df: pd.DataFrame, stratum: dict) -> pd.DataFrame:
    mask = np.ones(len(long_df), dtype=bool)
    for col, val in stratum.items():
        mask &= (long_df[col].values == val)
    return long_df[mask]


def empirical_sp_proxy(long_df: pd.DataFrame, default: float = 3.0) -> float:
    """Median winning_sp among rows where did_win=1, as a niche-specific proxy.

    If too few wins to estimate, fall back to mean(eu_odds * 0.65 / 0.95).
    """
    wins = long_df[long_df["did_win"] == 1]
    if len(wins) >= 10 and wins["winning_sp"].notna().any():
        return float(np.nanmedian(wins["winning_sp"]))
    if len(long_df) > 0:
        return float(np.nanmean(long_df["eu_odds"]) * 0.65 / 0.95)
    return default
