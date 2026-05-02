"""Build the stream of niche-qualifying single-leg picks.

Niche selection rule (train-only, frozen):
  - We use the survival-validated niche frame from sp_native: 1- to 3-dim
    cells over (option, sp_bucket, handicap_class, league_tier) where
    train q_ci_lo > 1.064, n >= 200, k >= 30 AND test_mean_q > 1.064.
  - On the FULL data, label every leg row whose stratum belongs to ANY
    surviving niche as a "qualifying pick".
  - We attach the train-estimated `q_train` (used for forward simulation)
    rather than peeking at the test mean (avoids look-ahead).

The output is a long DataFrame with one row per qualifying leg.
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
import pandas as pd

from src.niche_analysis.sp_native import (
    NICHE_DIMS,
    RAW_3SP_CSV,
    enumerate_niches,
    load_full_3sp,
    split_train_test,
    survival_test,
    to_long,
)


# ---------------------------------------------------------------------------
# Cache locations (we cache the long frame + the niches so re-runs are fast)

CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "cache",
)


def _cache_path(name: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, name)


# ---------------------------------------------------------------------------
# Niche selection

def select_surviving_niches(
    long_df: pd.DataFrame,
    *,
    min_n: int = 200,
    min_k: int = 30,
    q_ci_lo_min: float = 1.064,
    oos_q_min: float = 1.064,
    oos_k_min: int = 30,
    max_combo_size: int = 3,
    seed: int = 42,
) -> pd.DataFrame:
    """Return surviving niches as a DataFrame with stratum keys columns."""
    train, test = split_train_test(long_df)
    train_niches = enumerate_niches(
        train,
        min_n=min_n,
        min_k=min_k,
        max_combo_size=max_combo_size,
        n_boot=200,
        seed=seed,
    )
    surv = survival_test(
        train_niches,
        test,
        is_q_ci_lo_min=q_ci_lo_min,
        is_n_min=min_n,
        is_k_min=min_k,
        oos_q_min=oos_q_min,
        oos_k_min=oos_k_min,
    )
    surv = surv[surv["survived"]].copy().reset_index(drop=True)
    # Attach the dim-key columns from the train_niches table.
    keep_cols = [c for c in train_niches.columns if c.startswith("d_")]
    surv = surv.merge(
        train_niches[["stratum_str"] + keep_cols], on="stratum_str", how="left",
    )
    return surv


# ---------------------------------------------------------------------------
# Qualifying-pick stream

def label_qualifying(
    long_df: pd.DataFrame, surviving_niches: pd.DataFrame,
) -> pd.DataFrame:
    """Return rows of long_df that match ≥1 surviving niche, with niche_id, q_train."""
    if surviving_niches.empty:
        return long_df.iloc[0:0].assign(niche_id=pd.Series([], dtype=str),
                                        q_train=np.nan)

    all_match: list[pd.Series] = []
    masks: list[np.ndarray] = []
    niche_ids: list[str] = []
    q_trains: list[float] = []
    for _, r in surviving_niches.iterrows():
        m = np.ones(len(long_df), dtype=bool)
        for col in NICHE_DIMS:
            key = f"d_{col}"
            if key in r.index and pd.notna(r[key]):
                m &= (long_df[col].values == r[key])
        if m.any():
            masks.append(m)
            niche_ids.append(r["stratum_str"])
            q_trains.append(float(r["train_mean_q"]))

    if not masks:
        return long_df.iloc[0:0].assign(niche_id=pd.Series([], dtype=str),
                                        q_train=np.nan)

    # Combine: for each row, keep the BEST (highest q_train) matching niche.
    n = len(long_df)
    best_q = np.full(n, -np.inf)
    best_id = np.array(["" for _ in range(n)], dtype=object)
    for nid, q, m in zip(niche_ids, q_trains, masks):
        upd = m & (q > best_q)
        best_q[upd] = q
        best_id[upd] = nid

    qual_mask = best_q > -np.inf
    out = long_df.loc[qual_mask].copy()
    out["niche_id"] = best_id[qual_mask]
    out["q_train"] = best_q[qual_mask]
    out["p_train"] = out["q_train"] / out["sp"]  # implied p under niche q estimate
    out["p_train"] = out["p_train"].clip(0.0, 0.99)
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Top-level

def build_qualifying_picks(
    csv_path: Optional[str] = None,
    *,
    use_cache: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (qualifying_picks_long_df, surviving_niches_df).

    qualifying_picks columns include: match_id, expect, kickoff_ts, league,
    league_tier, handicap_class, option, sp, did_win, sp_bucket, niche_id,
    q_train, p_train.
    """
    qpath = _cache_path("qualifying_picks.parquet")
    npath = _cache_path("surviving_niches.parquet")
    if use_cache and os.path.exists(qpath) and os.path.exists(npath):
        return pd.read_parquet(qpath), pd.read_parquet(npath)

    df = load_full_3sp(csv_path or RAW_3SP_CSV)
    long_df = to_long(df)
    surv = select_surviving_niches(long_df)
    qual = label_qualifying(long_df, surv)
    # Make sure kickoff_ts is datetime + add iso week info for combo grouping.
    qual["kickoff_ts"] = pd.to_datetime(qual["kickoff_ts"], errors="coerce")
    qual = qual.dropna(subset=["kickoff_ts"]).reset_index(drop=True)
    iso = qual["kickoff_ts"].dt.isocalendar()
    qual["iso_year"] = iso["year"].astype(int)
    qual["iso_week"] = iso["week"].astype(int)
    qual["week_key"] = qual["iso_year"] * 100 + qual["iso_week"]

    try:
        qual.to_parquet(qpath, index=False)
        surv.to_parquet(npath, index=False)
    except Exception:
        pass
    return qual, surv
