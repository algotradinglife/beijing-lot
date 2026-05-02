"""Build per-niche weekly N=3 combo return series.

Logic:
  For each (niche, week):
    1. From the long-format SP frame, take all legs whose stratum matches
       the niche AND whose kickoff falls in that ISO week.
    2. Score legs by est_leg_q = p_hat * sp where p_hat is the devig-implied
       probability `(1/sp) / Σ(1/sp_other)` per match. (Bayesian-shrunk
       probabilities would peek at outcome via the train half; for an
       unbiased weekly stream we use within-match devig only.)
    3. Drop matches where another option of the same match is already in
       the candidate set (one leg per match).
    4. If <3 legs survive that week → no return that week (NaN).
    5. Otherwise pick the top 3 by est_leg_q, settle as a 3-leg combo:
            payout multiplier = 0.65 * Π sp_i  if all hit, else 0
            return = payout - 1   (one yuan stake)

Output: pandas DataFrame indexed by ISO-week start date, columns = niche ids,
        values = combo return (NaN if no qualifying week).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .niches import SURVIVED_16, filter_long_by_stratum

RETURN_RATE = 0.65
N_LEGS = 3


def add_devig_phat(long_df: pd.DataFrame) -> pd.DataFrame:
    """Add per-match devig p_hat column (no outcome leakage)."""
    df = long_df.copy()
    inv = 1.0 / df["sp"].values
    sums = df.groupby("match_id")["sp"].transform(lambda s: (1.0 / s).sum()).values
    df["p_hat"] = inv / sums
    df["est_leg_q"] = df["p_hat"] * df["sp"]
    return df


def assign_week(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["kickoff_ts"] = pd.to_datetime(df["kickoff_ts"], errors="coerce")
    # Use ISO week start (Monday)
    df["week"] = df["kickoff_ts"].dt.to_period("W-SUN").dt.start_time
    return df


def per_niche_weekly_return(long_df_with_phat: pd.DataFrame, stratum: dict,
                            n_legs: int = N_LEGS,
                            return_rate: float = RETURN_RATE) -> pd.Series:
    sub = filter_long_by_stratum(long_df_with_phat, stratum)
    if sub.empty:
        return pd.Series(dtype=float, name="r")
    out = {}
    # group by week then per match keep best leg, then top n_legs
    for wk, wdf in sub.groupby("week", observed=True):
        # one option per match (keep the row with the higher est_leg_q if a
        # match has multiple matching options, which can happen for option-
        # agnostic niches like sp=5-8 only).
        wdf = wdf.sort_values("est_leg_q", ascending=False)
        wdf = wdf.drop_duplicates("match_id", keep="first")
        if len(wdf) < n_legs:
            continue
        top = wdf.head(n_legs)
        joint_sp = float(top["sp"].prod())
        all_hit = bool(top["did_win"].all())
        payout = return_rate * joint_sp if all_hit else 0.0
        out[wk] = payout - 1.0  # net return on 1 yuan stake
    s = pd.Series(out, name="r").sort_index()
    s.index.name = "week"
    return s


def build_return_matrix(long_df: pd.DataFrame,
                        niches=SURVIVED_16,
                        n_legs: int = N_LEGS) -> pd.DataFrame:
    long_df = add_devig_phat(long_df)
    long_df = assign_week(long_df)
    cols = {}
    for n in niches:
        s = per_niche_weekly_return(long_df, n["stratum"], n_legs=n_legs)
        cols[n["id"]] = s
    R = pd.DataFrame(cols)
    R = R.sort_index()
    return R
