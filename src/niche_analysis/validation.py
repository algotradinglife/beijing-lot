"""Train/test validation + bootstrap stability test for niches."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from .bayesian import bootstrap_mean, fit_posterior
from .niche_grid import empirical_sp_proxy, filter_long_by_stratum


def evaluate_stratum(long_df: pd.DataFrame, stratum: dict, kappa: float = 100.0) -> dict:
    sub = filter_long_by_stratum(long_df, stratum)
    n = len(sub)
    k = int(sub["did_win"].sum()) if n else 0
    if n == 0:
        return {"n": 0, "k": 0}
    mean_implied = float(sub["implied_prob"].mean())
    sp_proxy = empirical_sp_proxy(sub)
    post = fit_posterior(k=k, n=n, prior_mean=mean_implied, kappa=kappa)
    p_ev = post.prob_ev_above(sp_proxy=sp_proxy, threshold=1.05, net_payout_factor=0.65)
    point_ev = (k / n) * sp_proxy * 0.65 if n else 0.0
    return {
        "n": n, "k": k,
        "mean_implied": mean_implied,
        "sp_proxy": sp_proxy,
        "post_mean": post.mean(),
        "post_p05": post.quantile(0.05),
        "post_p50": post.quantile(0.50),
        "post_p95": post.quantile(0.95),
        "P_p_gt_implied": post.prob_greater(mean_implied),
        "P_EV_gt_1_05": p_ev,
        "point_EV": point_ev,
    }


def bootstrap_niche(long_df: pd.DataFrame, stratum: dict, n_boot: int = 1000,
                     seed: int = 42) -> dict:
    sub = filter_long_by_stratum(long_df, stratum)
    if len(sub) == 0:
        return {"ci_low": float("nan"), "ci_high": float("nan"), "boot_mean": float("nan")}
    rng = np.random.default_rng(seed)
    means = bootstrap_mean(sub["did_win"].values.astype(float), n_boot=n_boot, rng=rng)
    return {
        "boot_mean": float(np.mean(means)),
        "ci_low": float(np.quantile(means, 0.025)),
        "ci_high": float(np.quantile(means, 0.975)),
    }
