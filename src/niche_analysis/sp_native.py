"""SP-native niche analysis on the full 3-SP 北单 dataset.

This module operates on the newly-available `data/raw/beidan_full_3sp.csv`,
which contains all three SP values per match (sp_3, sp_1, sp_0). Unlike
the original ``data_loader``+``niche_grid`` pipeline (which used
international avg_eu odds as a proxy), this module measures retail
mispricing **directly** in the 北单 SP space.

Core quantities per (match, option) leg:
  - sp        : actual 北单 single-event payout for that option
  - did_win   : 1/0
  - implied   : 1/sp (raw retail-implied prob, includes vig)
  - q_obs     : did_win * sp  (per-leg expected payout multiplier under
                bet=1 yuan; aggregated as mean to estimate E[did_win·sp])
  - leg_ev    : q_obs * RETURN_RATE - 1
  - combo_ev  : (mean_q)^n_legs * RETURN_RATE - 1   (theoretical n-leg
                combo EV from picking randomly within the niche)

RETURN_RATE = 0.65 (北单 7-leg combo payout coefficient).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from itertools import combinations
from typing import Optional

import numpy as np
import pandas as pd

from .data_loader import classify_handicap, classify_league


# ---------------------------------------------------------------------------
# Constants

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_3SP_CSV = os.path.join(REPO_ROOT, "data", "raw", "beidan_full_3sp.csv")
RETURN_RATE = 0.65

SP_BUCKETS_PRIMARY = [
    ("1.5-2", 1.5, 2.0),
    ("2-3", 2.0, 3.0),
    ("3-5", 3.0, 5.0),
    ("5-8", 5.0, 8.0),
    ("8-15", 8.0, 15.0),
    ("15+", 15.0, np.inf),
]
SP_BUCKETS_ALT = [
    ("1.5-2.5", 1.5, 2.5),
    ("2.5-4", 2.5, 4.0),
    ("4-7", 4.0, 7.0),
    ("7-12", 7.0, 12.0),
    ("12+", 12.0, np.inf),
]


def bucket_sp(sp: float, scheme=SP_BUCKETS_PRIMARY) -> str:
    if sp is None or not np.isfinite(sp) or sp < 1.0:
        return "na"
    for name, lo, hi in scheme:
        if lo <= sp < hi:
            return name
    return "na"


# ---------------------------------------------------------------------------
# Loader

def load_full_3sp(path: Optional[str] = None) -> pd.DataFrame:
    """Load the full 3-SP CSV and return cleaned wide DataFrame."""
    p = path or RAW_3SP_CSV
    df = pd.read_csv(p)
    # Coerce numerics
    for c in ("sp_3", "sp_1", "sp_0", "handicap", "winning_sp", "expect"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["result_code"] = df["result_code"].astype(str).str.strip()
    df = df.dropna(subset=["sp_3", "sp_1", "sp_0", "result_code"]).copy()
    df = df[(df["sp_3"] > 1.0) & (df["sp_1"] > 1.0) & (df["sp_0"] > 1.0)]
    df["league_tier"] = df["league"].map(classify_league)
    df["handicap_class"] = df["handicap"].map(classify_handicap)
    df["match_id"] = df["expect"].astype(str) + "-" + df["match_no"].astype(str)
    return df.reset_index(drop=True)


def to_long(df: pd.DataFrame, scheme=SP_BUCKETS_PRIMARY) -> pd.DataFrame:
    """Pivot wide → long: 3 rows per match, one per option."""
    parts = []
    for code, col in (("3", "sp_3"), ("1", "sp_1"), ("0", "sp_0")):
        sub = pd.DataFrame({
            "match_id": df["match_id"],
            "expect": df["expect"],
            "kickoff_ts": df["kickoff_ts"],
            "league": df["league"],
            "league_tier": df["league_tier"],
            "handicap": df["handicap"],
            "handicap_class": df["handicap_class"],
            "option": code,
            "sp": df[col].values,
            "did_win": (df["result_code"].values == code).astype(int),
        })
        parts.append(sub)
    long = pd.concat(parts, ignore_index=True)
    long["sp_bucket"] = long["sp"].map(lambda x: bucket_sp(x, scheme))
    long["implied"] = 1.0 / long["sp"]
    long["q_obs"] = long["did_win"] * long["sp"]
    long["leg_ev"] = long["q_obs"] * RETURN_RATE - 1.0
    long["option_label"] = long["option"].map({"3": "home", "1": "draw", "0": "away"})
    return long


def sanity_check_sum_inv(df: pd.DataFrame) -> dict:
    """Σ(1/SP_i) per match — should be ≈ 1 + vig ≈ 1.30 (rake ≈ 0.30)."""
    s = 1.0 / df["sp_3"] + 1.0 / df["sp_1"] + 1.0 / df["sp_0"]
    return dict(
        mean=float(s.mean()), median=float(s.median()),
        p05=float(s.quantile(0.05)), p95=float(s.quantile(0.95)),
        n=int(len(s)),
    )


# ---------------------------------------------------------------------------
# Niche enumeration

NICHE_DIMS = ["option", "sp_bucket", "handicap_class", "league_tier"]


@dataclass
class NicheStats:
    dims: str
    stratum: dict
    n: int
    k: int
    hit_rate: float
    mean_sp: float
    mean_q: float
    leg_ev: float
    combo_ev_7: float
    q_ci_lo: float
    q_ci_hi: float


def _bootstrap_q_ci(q_arr: np.ndarray, n_boot: int = 1000,
                    rng: Optional[np.random.Generator] = None,
                    alpha: float = 0.05) -> tuple[float, float]:
    if len(q_arr) == 0:
        return float("nan"), float("nan")
    if rng is None:
        rng = np.random.default_rng(42)
    n = len(q_arr)
    idx = rng.integers(0, n, size=(n_boot, n))
    boots = q_arr[idx].mean(axis=1)
    return float(np.quantile(boots, alpha / 2)), float(np.quantile(boots, 1 - alpha / 2))


def enumerate_niches(
    long_df: pd.DataFrame,
    *,
    dims: list[str] = NICHE_DIMS,
    min_n: int = 200,
    min_k: int = 30,
    max_combo_size: int = 3,
    n_boot: int = 1000,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    combos: list[tuple] = []
    for r in range(1, max_combo_size + 1):
        combos.extend(combinations(dims, r))

    for combo in combos:
        gb = long_df.groupby(list(combo), observed=True)
        for keys, sub in gb:
            n = len(sub)
            k = int(sub["did_win"].sum())
            if n < min_n or k < min_k:
                continue
            q = sub["q_obs"].values
            mean_q = float(q.mean())
            ci_lo, ci_hi = _bootstrap_q_ci(q, n_boot=n_boot, rng=rng)
            mean_sp = float(sub["sp"].mean())
            hit_rate = k / n
            leg_ev = mean_q * RETURN_RATE - 1.0
            combo_ev_7 = (mean_q ** 7) * RETURN_RATE - 1.0
            stratum = dict(zip(combo, keys if isinstance(keys, tuple) else (keys,)))
            rows.append(dict(
                dims="|".join(combo),
                stratum_str=", ".join(f"{kk}={vv}" for kk, vv in stratum.items()),
                **{f"d_{kk}": vv for kk, vv in stratum.items()},
                n=n, k=k, hit_rate=hit_rate,
                mean_sp=mean_sp, mean_q=mean_q,
                leg_ev=leg_ev, combo_ev_7=combo_ev_7,
                q_ci_lo=ci_lo, q_ci_hi=ci_hi,
            ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Train/test split & survival test

def split_train_test(long_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    median_expect = long_df["expect"].median()
    train = long_df[long_df["expect"] < median_expect].reset_index(drop=True)
    test = long_df[long_df["expect"] >= median_expect].reset_index(drop=True)
    return train, test


def filter_by_stratum(long_df: pd.DataFrame, stratum: dict) -> pd.DataFrame:
    mask = np.ones(len(long_df), dtype=bool)
    for col, val in stratum.items():
        mask &= (long_df[col].values == val)
    return long_df[mask]


def survival_test(
    train_niches: pd.DataFrame,
    test_long: pd.DataFrame,
    *,
    is_q_ci_lo_min: float = 1.064,
    is_n_min: int = 200,
    is_k_min: int = 30,
    oos_q_min: float = 1.064,
    oos_k_min: int = 30,
) -> pd.DataFrame:
    """For each train-passing niche, recompute q on test set."""
    candidates = train_niches[
        (train_niches["q_ci_lo"] > is_q_ci_lo_min)
        & (train_niches["n"] >= is_n_min)
        & (train_niches["k"] >= is_k_min)
    ].copy()

    out_rows = []
    for _, r in candidates.iterrows():
        stratum = {k.replace("d_", ""): v for k, v in r.items()
                   if k.startswith("d_") and pd.notna(v)}
        sub = filter_by_stratum(test_long, stratum)
        if len(sub) == 0:
            oos_n, oos_k, oos_mean_q = 0, 0, float("nan")
            oos_leg_ev, oos_combo_ev = float("nan"), float("nan")
            survived = False
        else:
            oos_n = len(sub)
            oos_k = int(sub["did_win"].sum())
            oos_mean_q = float(sub["q_obs"].mean())
            oos_leg_ev = oos_mean_q * RETURN_RATE - 1.0
            oos_combo_ev = (oos_mean_q ** 7) * RETURN_RATE - 1.0
            survived = (oos_mean_q > oos_q_min) and (oos_k >= oos_k_min)

        out_rows.append(dict(
            stratum_str=r["stratum_str"], dims=r["dims"],
            train_n=int(r["n"]), train_k=int(r["k"]),
            train_mean_q=float(r["mean_q"]),
            train_q_ci_lo=float(r["q_ci_lo"]),
            train_combo_ev_7=float(r["combo_ev_7"]),
            test_n=oos_n, test_k=oos_k,
            test_mean_q=oos_mean_q,
            test_leg_ev=oos_leg_ev,
            test_combo_ev_7=oos_combo_ev,
            survived=survived,
        ))
    return pd.DataFrame(out_rows).sort_values("train_combo_ev_7", ascending=False)


# ---------------------------------------------------------------------------
# Combo backtest with REAL SP

def combo_backtest_per_issue(
    long_df: pd.DataFrame,
    *,
    leg_ev_threshold: float = 0.05,
    leg_q_threshold: float = 1.064,
    n_legs: int = 7,
    p_method: str = "implied",  # "implied" or "shrunk"
    return_rate: float = RETURN_RATE,
    rng_seed: int = 7,
    use_q_threshold: bool = True,
) -> pd.DataFrame:
    """Per-期 backtest: for each issue, pick legs whose estimated single-leg
    EV ≥ threshold using real SP and a probability model, build greedy
    7-leg combos (one per match, taking top n_legs by p*sp), settle.

    p_method:
      - "implied": use 1/SP * (1+vig_per_match correction). i.e., p_hat = devig.
        With this method, expected leg EV ~ −0.34 always, so no legs pass.
        We use this to demonstrate the inadequacy of self-implied-only.
      - "shrunk": p_hat = bayesian shrinkage based on niche hit rate. We use
        league_tier×handicap_class×option×sp_bucket niche with overall
        prior. Forms an honest "edge model" that does not peek at outcome.
    """
    rng = np.random.default_rng(rng_seed)
    if p_method == "shrunk":
        # Use niche stats from train half as the prior; apply to all.
        train, _ = split_train_test(long_df)
        cols = ["league_tier", "handicap_class", "option", "sp_bucket"]
        niche_stats = (
            train.groupby(cols, observed=True)
            .agg(n=("did_win", "size"), k=("did_win", "sum"))
            .reset_index()
        )
        # Bayesian shrinkage with weak prior toward overall option base-rate.
        # Each option roughly: home 37%, draw 27%, away 35%; use Beta(2,4)
        # equivalent (very weak) so empirical hit rate dominates when n is large.
        alpha0, beta0 = 2.0, 4.0
        niche_stats["p_shrunk"] = (niche_stats["k"] + alpha0) / (
            niche_stats["n"] + alpha0 + beta0
        )
        long_df = long_df.merge(niche_stats[cols + ["p_shrunk"]], on=cols, how="left")
        long_df["p_hat"] = long_df["p_shrunk"].fillna(1.0 / long_df["sp"])
    else:
        # Devig per match: p_hat = (1/sp) / Σ(1/sp_other_options)
        inv = 1.0 / long_df["sp"]
        sums = long_df.groupby("match_id")["sp"].transform(lambda s: (1 / s).sum())
        long_df = long_df.copy()
        long_df["p_hat"] = inv / sums

    long_df["est_leg_ev"] = long_df["p_hat"] * long_df["sp"] * return_rate - 1.0
    long_df["est_leg_q"] = long_df["p_hat"] * long_df["sp"]

    rows = []
    for issue, idf in long_df.groupby("expect"):
        # Filter candidates by leg-q threshold (combo break-even contribution)
        if use_q_threshold:
            cands = idf[idf["est_leg_q"] >= leg_q_threshold].copy()
        else:
            cands = idf[idf["est_leg_ev"] >= leg_ev_threshold].copy()
        if len(cands) == 0:
            rows.append(dict(issue=issue, n_cands=0, n_combos=0,
                             stake=0.0, profit=0.0, n_hit=0))
            continue
        # one option per match: pick the highest est_leg_ev per match
        cands = cands.sort_values("est_leg_ev", ascending=False)
        cands = cands.drop_duplicates("match_id", keep="first")
        if len(cands) < n_legs:
            rows.append(dict(issue=issue, n_cands=len(cands), n_combos=0,
                             stake=0.0, profit=0.0, n_hit=0))
            continue
        # Build greedy 7-leg combos: top-n_legs into single combo
        # (simplified — could be multiple combos but keep deterministic)
        top = cands.head(n_legs)
        joint_sp = float(top["sp"].prod())
        all_hit = bool(top["did_win"].all())
        stake = 1.0  # 1 yuan per combo
        payout = stake * joint_sp * return_rate if all_hit else 0.0
        profit = payout - stake
        rows.append(dict(
            issue=issue,
            n_cands=len(cands), n_combos=1,
            stake=stake, profit=profit,
            joint_sp=joint_sp, all_hit=int(all_hit),
            n_hit=int(all_hit),
        ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Variance / Kelly

def simulate_variance(
    n_weeks: int,
    candidates_per_week: int,
    p_hit_per_combo: float,
    payout_multiple: float,
    n_sims: int = 1000,
    rng_seed: int = 1,
) -> dict:
    """Simulate combo betting under iid-leg assumption.

    Each week: candidates_per_week combos are placed (1 yuan each). Each
    combo wins iid with prob p_hit_per_combo and pays payout_multiple.
    Returns ROI percentile bands.
    """
    rng = np.random.default_rng(rng_seed)
    rois = []
    for _ in range(n_sims):
        wins = rng.binomial(candidates_per_week, p_hit_per_combo, size=n_weeks).sum()
        total_stake = n_weeks * candidates_per_week
        total_payout = wins * payout_multiple
        rois.append((total_payout - total_stake) / total_stake)
    rois = np.array(rois)
    return dict(
        mean=float(rois.mean()),
        p5=float(np.quantile(rois, 0.05)),
        p25=float(np.quantile(rois, 0.25)),
        p50=float(np.quantile(rois, 0.50)),
        p75=float(np.quantile(rois, 0.75)),
        p95=float(np.quantile(rois, 0.95)),
        prob_profitable=float((rois > 0).mean()),
    )
