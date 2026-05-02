"""Track 4: full canonical-quant metric suite for a SimulationResult.

Pure-numpy/pandas. Formulas chosen to match common empyrical-like ones.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

from src.sweep.simulator import SimulationResult


WEEKS_PER_YEAR = 52.0


def _safe_div(a: float, b: float) -> float:
    if b == 0 or not np.isfinite(b):
        return float("nan")
    return a / b


def cagr(initial: float, final: float, n_weeks: int) -> float:
    if initial <= 0 or final <= 0 or n_weeks <= 0:
        return float("nan")
    years = n_weeks / WEEKS_PER_YEAR
    if years <= 0:
        return float("nan")
    return (final / initial) ** (1.0 / years) - 1.0


def sharpe(weekly_pnl_ret: np.ndarray) -> float:
    if len(weekly_pnl_ret) < 2:
        return float("nan")
    s = weekly_pnl_ret.std(ddof=1)
    if s <= 0:
        return float("nan")
    return float(weekly_pnl_ret.mean() / s * math.sqrt(WEEKS_PER_YEAR))


def sortino(weekly_pnl_ret: np.ndarray, mar: float = 0.0) -> float:
    if len(weekly_pnl_ret) < 2:
        return float("nan")
    downside = weekly_pnl_ret[weekly_pnl_ret < mar]
    if len(downside) == 0:
        return float("inf")
    dstd = math.sqrt((downside ** 2).mean())
    if dstd <= 0:
        return float("nan")
    return float((weekly_pnl_ret.mean() - mar) / dstd * math.sqrt(WEEKS_PER_YEAR))


def max_drawdown_curve(bb: np.ndarray) -> tuple[float, float, int, int]:
    """Returns (max_dd_frac, max_dd_abs, dd_duration_weeks, time_underwater_weeks)."""
    if len(bb) == 0:
        return float("nan"), float("nan"), 0, 0
    peaks = np.maximum.accumulate(bb)
    dd_frac = (bb - peaks) / peaks
    dd_abs = bb - peaks
    max_dd_frac = float(dd_frac.min())
    max_dd_abs = float(dd_abs.min())
    # underwater = bb < peak (strictly)
    underwater = bb < peaks
    time_uw = int(underwater.sum())
    # Longest single drawdown (consecutive weeks underwater)
    longest = cur = 0
    for u in underwater:
        if u:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 0
    return max_dd_frac, max_dd_abs, longest, time_uw


def calmar(cagr_val: float, max_dd_frac: float) -> float:
    if not np.isfinite(cagr_val) or not np.isfinite(max_dd_frac):
        return float("nan")
    if max_dd_frac >= 0:
        return float("nan")
    return _safe_div(cagr_val, abs(max_dd_frac))


def var_cvar(values: np.ndarray, alpha: float = 0.05) -> tuple[float, float]:
    if len(values) == 0:
        return float("nan"), float("nan")
    var = float(np.quantile(values, alpha))
    cvar = float(values[values <= var].mean()) if (values <= var).any() else var
    return var, cvar


def streaks(weekly_pnl: np.ndarray) -> tuple[int, int]:
    """Returns (max_consecutive_losing_weeks, longest_overall_losing_streak).

    Equivalent for our purposes.
    """
    longest = cur = 0
    for v in weekly_pnl:
        if v < 0:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 0
    return longest, longest


def quality_metrics(weekly_pnl: np.ndarray) -> dict:
    wins = weekly_pnl[weekly_pnl > 0]
    losses = weekly_pnl[weekly_pnl < 0]
    sum_w = float(wins.sum()) if len(wins) else 0.0
    sum_l = float(losses.sum()) if len(losses) else 0.0
    avg_w = float(wins.mean()) if len(wins) else 0.0
    avg_l = float(losses.mean()) if len(losses) else 0.0
    pf = _safe_div(sum_w, abs(sum_l)) if sum_l != 0 else float("inf")
    wlr = _safe_div(avg_w, abs(avg_l)) if avg_l != 0 else float("inf")
    return dict(
        profit_factor=pf, avg_win=avg_w, avg_loss=avg_l, win_loss_ratio=wlr,
    )


def full_metrics(sim: SimulationResult, label: str) -> dict:
    weekly = sim.weekly
    combos = sim.combos
    bb_start = sim.initial_bankroll
    bb_end = sim.final_bankroll
    if weekly.empty:
        return dict(
            variant=label, n_weeks=0, n_combos=0, n_hits=0,
            cum_roi=float("nan"), final_bankroll=bb_end,
            cagr=float("nan"), sharpe=float("nan"), sortino=float("nan"),
            calmar=float("nan"), max_dd=float("nan"), max_dd_abs=float("nan"),
            dd_duration=0, time_underwater_pct=0.0,
            mean_weekly_roi=float("nan"), std_weekly_roi=float("nan"),
            p5_weekly_roi=float("nan"), p95_weekly_roi=float("nan"),
            var_95=float("nan"), cvar_95=float("nan"),
            max_single_week_loss=float("nan"),
            weekly_win_rate=float("nan"), max_losing_streak=0,
            profit_factor=float("nan"), avg_win=float("nan"),
            avg_loss=float("nan"), win_loss_ratio=float("nan"),
            mean_weekly_stake=float("nan"), mean_weekly_stake_pct=float("nan"),
            mean_weekly_pnl=float("nan"),
            stake_cap_bind_pct=float("nan"),
            total_profit=bb_end - bb_start,
        )

    bb = np.concatenate(([bb_start], weekly["bankroll_end"].to_numpy()))
    n_weeks = len(weekly)
    weekly_roi = weekly["week_roi"].to_numpy()  # (PnL / stake) per active week
    weekly_pnl = weekly["week_pnl"].to_numpy()
    weekly_stake = weekly["week_stake"].to_numpy()
    # Per-week return on bankroll (start-of-week bankroll = bb[i])
    week_ret_bk = weekly_pnl / bb[:-1]

    cum_roi = bb_end / bb_start - 1.0
    cagr_val = cagr(bb_start, bb_end, n_weeks)
    sh = sharpe(week_ret_bk)
    so = sortino(week_ret_bk)
    max_dd_frac, max_dd_abs, dd_dur, time_uw = max_drawdown_curve(bb)
    cm = calmar(cagr_val, max_dd_frac)
    p5 = float(np.quantile(weekly_roi, 0.05))
    p95 = float(np.quantile(weekly_roi, 0.95))
    var95, cvar95 = var_cvar(weekly_pnl, 0.05)
    quality = quality_metrics(weekly_pnl)
    longest_loss, _ = streaks(weekly_pnl)

    # Capital constraint (Track 6)
    weekly_cap = 0.25 * bb[:-1]
    bind_mask = weekly_stake >= weekly_cap * 0.99
    bind_pct = float(bind_mask.mean())
    n_combos = int(combos.shape[0]) if not combos.empty else 0
    n_hits = int(combos["all_hit"].sum()) if not combos.empty else 0

    return dict(
        variant=label,
        n_weeks=n_weeks,
        n_combos=n_combos,
        n_hits=n_hits,
        cum_roi=float(cum_roi),
        final_bankroll=float(bb_end),
        total_profit=float(bb_end - bb_start),
        cagr=float(cagr_val),
        sharpe=float(sh),
        sortino=float(so),
        calmar=float(cm),
        max_dd=float(max_dd_frac),
        max_dd_abs=float(max_dd_abs),
        dd_duration=int(dd_dur),
        time_underwater_pct=float(time_uw / max(1, len(bb))),
        mean_weekly_roi=float(weekly_roi.mean()),
        std_weekly_roi=float(weekly_roi.std(ddof=1)) if n_weeks > 1 else float("nan"),
        p5_weekly_roi=p5,
        p95_weekly_roi=p95,
        var_95=float(var95),
        cvar_95=float(cvar95),
        max_single_week_loss=float(weekly_pnl.min()),
        weekly_win_rate=float((weekly_pnl > 0).mean()),
        max_losing_streak=int(longest_loss),
        profit_factor=quality["profit_factor"],
        avg_win=quality["avg_win"],
        avg_loss=quality["avg_loss"],
        win_loss_ratio=quality["win_loss_ratio"],
        mean_weekly_stake=float(weekly_stake.mean()),
        mean_weekly_stake_pct=float((weekly_stake / bb[:-1]).mean()),
        mean_weekly_pnl=float(weekly_pnl.mean()),
        stake_cap_bind_pct=bind_pct,
    )
