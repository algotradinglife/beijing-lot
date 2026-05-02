"""Drawdown anatomy: identify worst peak->trough, count losing weeks, etc."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class DDAnatomy:
    peak_idx: int
    trough_idx: int
    recover_idx: int | None  # first idx after trough where bankroll >= peak
    peak_value: float
    trough_value: float
    peak_week: object
    trough_week: object
    drawdown_pct: float
    n_weeks_in_dd: int
    n_losing_weeks: int
    n_winning_weeks: int
    worst_single_week_pnl: float
    worst_single_week_idx: int
    streak_share: float  # fraction of DD attributable to losing-streak rather than 1 catastrophic week
    verdict: str


def compute_drawdown_series(bankroll: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    peaks = np.maximum.accumulate(bankroll)
    dd = (bankroll - peaks) / peaks
    return peaks, dd


def worst_drawdown(weekly: pd.DataFrame, initial: float) -> DDAnatomy:
    """Find the deepest peak->trough drawdown.

    ``weekly`` must contain columns ``week_pnl`` and ``week_key``."""
    if weekly.empty:
        raise ValueError("empty weekly df")
    pnl = weekly["week_pnl"].to_numpy(dtype=float)
    bankroll = initial + np.cumsum(pnl)
    seq = np.concatenate([[initial], bankroll])  # length n+1
    peaks, dd = compute_drawdown_series(seq)
    trough = int(np.argmin(dd))
    # Peak is the last index <= trough where seq == peaks[trough]
    peak_val = peaks[trough]
    peak = int(np.where(seq[: trough + 1] == peak_val)[0][-1])
    # Recover: first idx > trough where seq >= peak_val
    rec_idx_arr = np.where(seq[trough + 1 :] >= peak_val)[0]
    recover = int(trough + 1 + rec_idx_arr[0]) if len(rec_idx_arr) else None

    # Map seq index back to weekly rows. seq[0] is initial, seq[i] = after week i-1.
    def seq_to_week_key(i: int):
        if i == 0:
            return "initial"
        return weekly.iloc[i - 1]["week_key"]

    # Slice of pnl that occurs strictly between peak (after) and trough (after)
    # Weeks producing drawdown are pnl[peak : trough] (these update seq[peak+1..trough])
    dd_pnl = pnl[peak:trough]
    if len(dd_pnl) == 0:
        # Pathological: trough at index 0 (impossible since seq[0]=initial=peak[0])
        n_lose = n_win = 0
        worst_week_pnl = 0.0
        worst_week_idx = peak
        streak_share = 0.0
    else:
        n_lose = int((dd_pnl < 0).sum())
        n_win = int((dd_pnl > 0).sum())
        worst_idx_local = int(np.argmin(dd_pnl))
        worst_week_pnl = float(dd_pnl[worst_idx_local])
        worst_week_idx = peak + worst_idx_local
        total_drop = peak_val - seq[trough]
        streak_share = 1.0 - (abs(worst_week_pnl) / total_drop) if total_drop > 0 else 0.0

    if streak_share > 0.6:
        verdict = "death by a thousand cuts (losing streak)"
    elif streak_share < 0.2:
        verdict = "single catastrophic week dominated"
    else:
        verdict = "mixed: streak + a bad week"

    return DDAnatomy(
        peak_idx=peak,
        trough_idx=trough,
        recover_idx=recover,
        peak_value=float(peak_val),
        trough_value=float(seq[trough]),
        peak_week=seq_to_week_key(peak),
        trough_week=seq_to_week_key(trough),
        drawdown_pct=float(dd[trough]),
        n_weeks_in_dd=int(trough - peak),
        n_losing_weeks=n_lose,
        n_winning_weeks=n_win,
        worst_single_week_pnl=worst_week_pnl,
        worst_single_week_idx=worst_week_idx,
        streak_share=float(streak_share),
        verdict=verdict,
    )
