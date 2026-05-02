"""Metrics for the combo sweep — Sharpe, drawdown, percentiles, bootstrap CI."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from src.sweep.simulator import SimulationResult


def max_drawdown(bankroll_curve: np.ndarray) -> float:
    if len(bankroll_curve) == 0:
        return 0.0
    peaks = np.maximum.accumulate(bankroll_curve)
    dd = (bankroll_curve - peaks) / peaks
    return float(dd.min())


def sharpe_weekly(roi_weekly: np.ndarray) -> float:
    if len(roi_weekly) < 2:
        return 0.0
    s = roi_weekly.std(ddof=1)
    if s <= 0:
        return 0.0
    return float(roi_weekly.mean() / s * np.sqrt(52))


def time_to_first_hit(weekly: pd.DataFrame) -> Optional[int]:
    if weekly.empty:
        return None
    hits = weekly["n_hits"].to_numpy()
    nz = np.where(hits > 0)[0]
    return int(nz[0] + 1) if len(nz) else None


def bootstrap_ci(
    values: np.ndarray, *, n_boot: int = 1000, alpha: float = 0.05,
    rng_seed: int = 1,
) -> tuple[float, float]:
    if len(values) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(rng_seed)
    n = len(values)
    idx = rng.integers(0, n, size=(n_boot, n))
    means = values[idx].mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def bootstrap_cumulative_roi(
    weekly: pd.DataFrame, initial_bankroll: float,
    *, n_boot: int = 1000, rng_seed: int = 1,
) -> tuple[float, float]:
    """Resample weekly PnL events to estimate uncertainty on cum ROI."""
    if weekly.empty:
        return float("nan"), float("nan")
    pnl = weekly["week_pnl"].to_numpy()
    rng = np.random.default_rng(rng_seed)
    n = len(pnl)
    idx = rng.integers(0, n, size=(n_boot, n))
    cum = pnl[idx].sum(axis=1)
    rois = cum / initial_bankroll
    return float(np.quantile(rois, 0.025)), float(np.quantile(rois, 0.975))


def summarize(
    sim: SimulationResult, n_legs: int, qual_test: pd.DataFrame,
) -> dict:
    weekly = sim.weekly
    combos = sim.combos
    bb = np.concatenate(
        ([sim.initial_bankroll], weekly["bankroll_end"].to_numpy())
    ) if not weekly.empty else np.array([sim.initial_bankroll])
    cum_roi = (sim.final_bankroll / sim.initial_bankroll) - 1.0
    weekly_rois = weekly["week_roi"].to_numpy() if not weekly.empty else np.array([])
    n_combos = int(combos.shape[0]) if not combos.empty else 0
    n_hits = int(combos["all_hit"].sum()) if not combos.empty else 0
    hit_rate = n_hits / n_combos if n_combos else float("nan")
    expected_hit_rate = float(combos["joint_p"].mean()) if not combos.empty else float("nan")

    p5 = float(np.quantile(weekly_rois, 0.05)) if len(weekly_rois) else float("nan")
    p95 = float(np.quantile(weekly_rois, 0.95)) if len(weekly_rois) else float("nan")
    median_roi = float(np.median(weekly_rois)) if len(weekly_rois) else float("nan")
    mean_roi = float(weekly_rois.mean()) if len(weekly_rois) else float("nan")
    std_roi = float(weekly_rois.std(ddof=1)) if len(weekly_rois) > 1 else float("nan")
    sharpe = sharpe_weekly(weekly_rois)
    dd = max_drawdown(bb)
    tfh = time_to_first_hit(weekly)
    ci_lo, ci_hi = bootstrap_cumulative_roi(weekly, sim.initial_bankroll)

    # Tax / payout
    if not combos.empty:
        avg_prize = float(combos["prize_per_ticket"].mean())
        max_prize = float(combos["prize_per_ticket"].max())
        split_rate = float((combos["n_tickets"] > 1).mean())
        # at stake=2: prize would be 2 × payout_per_yuan
        avg_prize_2y = float((combos["payout_per_yuan"] * 2).mean())
    else:
        avg_prize = max_prize = split_rate = avg_prize_2y = float("nan")

    return dict(
        n_legs=n_legs,
        n_weeks_active=int(len(weekly)),
        n_combos_total=n_combos,
        n_hits=n_hits,
        hit_rate=hit_rate,
        expected_hit_rate=expected_hit_rate,
        cumulative_ROI=float(cum_roi),
        mean_weekly_ROI=mean_roi,
        median_weekly_ROI=median_roi,
        weekly_ROI_std=std_roi,
        sharpe=sharpe,
        max_drawdown=float(dd),
        P5_weekly_ROI=p5,
        P95_weekly_ROI=p95,
        time_to_first_hit=tfh,
        boot_ROI_lo=ci_lo,
        boot_ROI_hi=ci_hi,
        avg_prize_per_ticket=avg_prize,
        max_prize_per_ticket=max_prize,
        split_rate=split_rate,
        avg_prize_at_2y=avg_prize_2y,
        final_bankroll=float(sim.final_bankroll),
    )
