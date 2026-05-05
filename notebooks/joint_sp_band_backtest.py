"""Backtest a 'joint-SP band' combo strategy.

Per week:
  1. For each match, pick the highest-SP outcome (the long-shot side).
  2. Greedy: assemble N-leg combos whose joint SP product falls in
     ``[target_low, target_high]``.
  3. Bet flat stake_per_ticket on each combo.
  4. Settle: a combo wins iff all picked outcomes equal the actual
     ``result_code`` (after handicap, which is already baked into result_code).

Outputs metrics for several (N, band) configs.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data" / "raw" / "beidan_full_3sp.csv"
RAKE = 0.65
INITIAL = 100_000.0
STAKE = 2.0  # 元 per ticket (avoids tax: max win at SP_band=2000 = 4000 元 < 10000)
TICKETS_PER_WEEK = 450
RANDOM_SEED = 42


@dataclass
class Leg:
    match_id: str
    pick: str         # "3" / "1" / "0"
    sp: float
    actual: str       # actual result_code

    @property
    def hit(self) -> bool:
        return self.pick == self.actual


def load_legs() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df = df.dropna(subset=["sp_3", "sp_1", "sp_0", "result_code"])
    df = df[df["result_code"].astype(str).isin(["0", "1", "3"])]
    df["result_code"] = df["result_code"].astype(str)
    df["expect"] = df["expect"].astype(str)
    df["match_id"] = df["expect"] + "_" + df["match_no"].astype(str)
    # Pick highest-SP side per match
    sps = df[["sp_3", "sp_1", "sp_0"]].values
    picks = ["3", "1", "0"]
    pick_idx = sps.argmax(axis=1)
    df["pick"] = [picks[i] for i in pick_idx]
    df["pick_sp"] = sps[np.arange(len(df)), pick_idx]
    df["hit"] = df["pick"] == df["result_code"]
    df = df[df["pick_sp"] > 1.01]
    df["week"] = df["expect"]
    return df


def assemble_combos(legs: list, N: int, lo: float, hi: float,
                    target: int, rng: random.Random) -> list:
    """Direct stratified pick (vectorized, no swap loop).

    For each combo: independently pick N legs from a "near-target" subset
    (legs whose log_SP is near target_avg = log(midpoint)/N). Compute joint
    SP; accept if in band. Reject samples are cheap.
    """
    if len(legs) < N:
        return []
    log_lo, log_hi = math.log(lo), math.log(hi)
    target_log = (log_lo + log_hi) / 2
    avg_log = target_log / N
    log_sps = np.array([math.log(l.sp) for l in legs])
    # Weight legs by closeness to avg_log (Gaussian-ish), wider window
    sigma = 1.0
    weights = np.exp(-((log_sps - avg_log) ** 2) / (2 * sigma ** 2))
    weights = weights / weights.sum()
    out = []
    n = len(legs)
    max_attempts = 5 * target
    for _ in range(max_attempts):
        if len(out) >= target:
            break
        idxs = np.random.choice(n, size=N, replace=False, p=weights)
        joint_log = log_sps[idxs].sum()
        if log_lo <= joint_log <= log_hi:
            out.append([legs[i] for i in idxs])
    return out


def run_backtest(N: int, lo: float, hi: float) -> dict:
    df = load_legs()
    rng = random.Random(RANDOM_SEED)
    bankroll = INITIAL
    weekly_pnl = []
    weekly_stake = []
    n_hits_total = 0
    n_combos_total = 0
    for week, wdf in df.groupby("week"):
        legs = [Leg(row.match_id, row.pick, row.pick_sp, row.result_code)
                for row in wdf.itertuples()]
        combos = assemble_combos(legs, N, lo, hi, TICKETS_PER_WEEK, rng)
        if not combos:
            weekly_pnl.append(0.0)
            weekly_stake.append(0.0)
            continue
        stake = len(combos) * STAKE
        if stake > bankroll * 0.5:
            # Cap at 50% bankroll per week as safety
            keep = int(bankroll * 0.5 / STAKE)
            combos = combos[:keep]
            stake = len(combos) * STAKE
        if stake <= 0:
            weekly_pnl.append(0.0); weekly_stake.append(0.0); continue
        payout = 0.0
        n_hits_week = 0
        for c in combos:
            if all(l.hit for l in c):
                joint_sp = math.prod(leg.sp for leg in c)
                payout += STAKE * joint_sp * RAKE
                n_hits_week += 1
        pnl = payout - stake
        bankroll += pnl
        bankroll = max(bankroll, 0.01)
        weekly_pnl.append(pnl)
        weekly_stake.append(stake)
        n_hits_total += n_hits_week
        n_combos_total += len(combos)

    pnl_arr = np.array(weekly_pnl)
    stake_arr = np.array(weekly_stake)
    n_weeks = len(pnl_arr)
    bk = INITIAL + np.cumsum(pnl_arr)
    bk = np.maximum(bk, 0.01)
    cagr = (bk[-1] / INITIAL) ** (52/max(n_weeks, 1)) - 1
    pct = pnl_arr / INITIAL
    sharpe = ((np.mean(pct) * 52) /
              (np.std(pct, ddof=1) * np.sqrt(52))
              if np.std(pct, ddof=1) > 0 else 0)
    seq = np.concatenate([[INITIAL], bk])
    rm = np.maximum.accumulate(seq)
    dd = (seq - rm) / rm
    max_dd = float(np.min(dd))
    avg_stake = float(stake_arr[stake_arr > 0].mean()) if (stake_arr > 0).any() else 0
    weeks_with_hit = int((pnl_arr > 0).sum())
    return dict(
        N=N, band=f"[{lo:.0f},{hi:.0f}]",
        n_weeks=n_weeks, n_combos=n_combos_total, n_hits=n_hits_total,
        hit_rate_per_combo=n_hits_total/max(n_combos_total, 1),
        weekly_win_rate=weeks_with_hit/max(n_weeks, 1),
        cagr=cagr, sharpe=sharpe, max_dd=max_dd,
        calmar=cagr/abs(max_dd) if max_dd < 0 else 0,
        final=float(bk[-1]),
        avg_stake=avg_stake, util_pct=avg_stake/INITIAL*100,
    )


def main():
    configs = [
        # (N, joint_SP_low, joint_SP_high)
        (5, 100, 300),
        (5, 300, 800),
        (5, 800, 2000),
        (6, 200, 600),
        (6, 600, 1500),
        (6, 1500, 4000),
        (7, 300, 800),
        (7, 800, 2000),
        (7, 2000, 5000),
        (8, 500, 1500),
        (8, 1500, 4000),
        (8, 4000, 10000),
    ]
    print(f"{'cfg':<20} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7} "
          f"{'final万':>9} {'hit/combo':>11} {'wk_win':>7} {'util%':>6}")
    print("-" * 100)
    for N, lo, hi in configs:
        r = run_backtest(N, lo, hi)
        print(f"N={r['N']} band={r['band']:<13} {r['cagr']*100:>+7.1f}% "
              f"{r['sharpe']:>7.2f} {r['max_dd']*100:>+7.1f}% "
              f"{r['calmar']:>7.2f} {r['final']/1e4:>8.1f} "
              f"{r['hit_rate_per_combo']*100:>10.4f}% "
              f"{r['weekly_win_rate']*100:>6.1f}% "
              f"{r['util_pct']:>5.1f}")


if __name__ == "__main__":
    main()
