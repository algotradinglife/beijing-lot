"""Replay a baseline weekly trace under a stop-loss rule overlay."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .stop_rules import Rule


def baseline_signals(weekly: pd.DataFrame, initial: float) -> pd.DataFrame:
    """Extract bankroll-invariant signals from a baseline simulator output.

    Returns df with columns: week_key, stake_frac, week_roi.
    stake_frac_t = week_stake / bankroll_at_start_of_week.
    """
    wk = weekly.reset_index(drop=True).copy()
    pnl = wk["week_pnl"].to_numpy(dtype=float)
    stake = wk["week_stake"].to_numpy(dtype=float)
    # bankroll at start of week t = initial + cumsum(pnl[:t])
    bk_start = np.concatenate([[initial], initial + np.cumsum(pnl)])[:-1]
    stake_frac = np.where(bk_start > 0, stake / bk_start, 0.0)
    week_roi = np.where(stake > 0, pnl / stake, 0.0)
    return pd.DataFrame({
        "week_key": wk["week_key"].values,
        "stake_frac": stake_frac,
        "week_roi": week_roi,
    })


def replay(signals: pd.DataFrame, rule: Rule, initial: float,
           ruin_threshold: float = 1000.0) -> pd.DataFrame:
    """Replay weekly trace under a rule. Returns weekly df with new bankroll path."""
    n = len(signals)
    bankroll = initial
    peak = initial
    rows = []
    state: dict = {"halted_until": -1, "throttled": False,
                   "doubling_level": 1.0, "initial": initial}
    recent_pct: list[float] = []
    state["recent_pct"] = recent_pct
    ruined = False
    for t in range(n):
        sf = float(signals.iloc[t]["stake_frac"])
        roi = float(signals.iloc[t]["week_roi"])
        dd_pct = (bankroll - peak) / peak if peak > 0 else 0.0
        state.update({"t": t, "bankroll": bankroll, "peak": peak, "dd_pct": dd_pct})
        state.pop("skim_request", None)
        mult = rule.fn(state)
        mult = max(0.0, mult)
        stake = bankroll * sf * mult
        pnl = stake * roi
        bankroll += pnl
        # apply skim if requested (profit lock-in)
        skim = state.pop("skim_request", 0.0)
        if skim and bankroll > skim:
            bankroll -= skim
        if bankroll > peak:
            peak = bankroll
        if bankroll <= ruin_threshold:
            ruined = True
        # track weekly pct return (on bankroll at start of week)
        bk_start = bankroll - pnl + (skim if skim else 0.0)
        pct = pnl / bk_start if bk_start > 0 else 0.0
        recent_pct.append(pct)
        rows.append({
            "week_key": signals.iloc[t]["week_key"],
            "active_mult": mult,
            "stake": stake,
            "pnl": pnl,
            "skim": skim,
            "bankroll": bankroll,
            "peak": peak,
            "dd_pct": (bankroll - peak) / peak if peak > 0 else 0.0,
            "ruined": ruined,
        })
        if ruined:
            # Continue but stake from now on is effectively 0 since bankroll tiny
            pass
    return pd.DataFrame(rows)


def metrics_from_replay(rep: pd.DataFrame, initial: float,
                        ruin_threshold: float = 1000.0) -> dict:
    if rep.empty:
        return dict(cagr=0.0, sharpe=0.0, max_dd=0.0, calmar=0.0, final=initial,
                    ruined=False, n_weeks=0)
    pnl = rep["pnl"].to_numpy(dtype=float)
    skim = rep["skim"].to_numpy(dtype=float)
    # Realized wealth = bankroll + cumulative skim (skim is locked profit)
    cumskim = np.cumsum(skim)
    final_realized = float(rep["bankroll"].iloc[-1] + cumskim[-1])
    n_weeks = len(rep)
    years = n_weeks / 52.0
    cagr = (final_realized / initial) ** (1.0 / max(years, 1e-6)) - 1.0
    # Sharpe on weekly pct return (dollar PnL / initial)
    pct = pnl / initial
    mean_r = float(np.mean(pct))
    std_r = float(np.std(pct, ddof=1)) if n_weeks > 1 else 0.0
    sharpe = (mean_r * 52.0) / (std_r * np.sqrt(52.0)) if std_r > 0 else 0.0
    # MaxDD on realized wealth path (bankroll + cumulative skim)
    wealth = rep["bankroll"].to_numpy() + cumskim
    seq = np.concatenate([[initial], wealth])
    peaks = np.maximum.accumulate(seq)
    dd = (seq - peaks) / peaks
    max_dd = float(np.min(dd))
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0
    return dict(
        cagr=float(cagr), sharpe=float(sharpe), max_dd=max_dd, calmar=float(calmar),
        final=final_realized, ruined=bool(rep["ruined"].iloc[-1]),
        n_weeks=n_weeks, total_skim=float(cumskim[-1]),
        time_underwater=float((dd < -0.05).mean()),
    )


def monte_carlo_ruin(signals: pd.DataFrame, rule: Rule, initial: float,
                     *, n_paths: int = 1000, horizon: int | None = None,
                     ruin_threshold: float = 1000.0,
                     seed: int = 17) -> dict:
    """Bootstrap weekly signals (stake_frac, week_roi) jointly to project paths."""
    if signals.empty:
        return dict(ruin_rate=float("nan"), median_final=initial,
                    p5_final=initial, p95_final=initial, paths_final=np.array([]))
    rng = np.random.default_rng(seed)
    horizon = horizon or len(signals)
    n = len(signals)
    sf_all = signals["stake_frac"].to_numpy()
    roi_all = signals["week_roi"].to_numpy()
    keys = signals["week_key"].to_numpy()
    finals = np.empty(n_paths)
    ruined = np.zeros(n_paths, dtype=bool)
    for k in range(n_paths):
        idx = rng.integers(0, n, size=horizon)
        sig = pd.DataFrame({
            "week_key": keys[idx],
            "stake_frac": sf_all[idx],
            "week_roi": roi_all[idx],
        })
        rep = replay(sig, rule, initial, ruin_threshold=ruin_threshold)
        cumskim = float(rep["skim"].sum())
        finals[k] = float(rep["bankroll"].iloc[-1]) + cumskim
        ruined[k] = bool(rep["ruined"].iloc[-1])
    return dict(
        ruin_rate=float(ruined.mean()),
        median_final=float(np.median(finals)),
        p5_final=float(np.quantile(finals, 0.05)),
        p95_final=float(np.quantile(finals, 0.95)),
        mean_final=float(np.mean(finals)),
        paths_final=finals,
    )
