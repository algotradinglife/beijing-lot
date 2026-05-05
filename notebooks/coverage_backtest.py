"""包场 (full-coverage) backtest.

Per ISO week:
  - Filter tradable matches (last 8 yrs, valid SPs, league q >= Q_MIN).
  - Pick top N by league q (stable, deterministic, simple).
  - Enumerate all 3^N outcome combos. Compute joint p_hat, joint payout, EV.
  - Take top K% of combos by EV. Bet 2 yuan flat per ticket.
  - Settle against the actual result tuple. Track weekly PnL.

Compare vs baseline `simulate_with_stake` (current per-leg combo strat).
"""
from __future__ import annotations

import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "notebooks"))

INITIAL = 100_000.0
STAKE_PER_TICKET = 2.0
RAKE = 0.65
TAX_FREE_CAP = 5000.0
TAX_RATE = 0.20
WEEKLY_STAKE_CAP_FRAC = 0.50
SP_MIN, SP_MAX = 1.01, 200.0
EIGHT_YEARS_DAYS = 365 * 8

LEAGUE_Q_PATH = ROOT / "src" / "phase5a" / "league_quality.json"
CSV_PATH = ROOT / "data" / "raw" / "beidan_full_3sp.csv"


def load_league_q():
    with open(LEAGUE_Q_PATH) as f:
        d = json.load(f)
    return {k: float(v["q"]) for k, v in d.items()}


def load_matches():
    df = pd.read_csv(CSV_PATH)
    df["kickoff_ts"] = pd.to_datetime(df["kickoff_ts"], errors="coerce")
    df = df.dropna(subset=["kickoff_ts", "sp_3", "sp_1", "sp_0", "result_code"])
    cutoff = df["kickoff_ts"].max() - pd.Timedelta(days=EIGHT_YEARS_DAYS)
    df = df[df["kickoff_ts"] >= cutoff].copy()
    for c in ("sp_3", "sp_1", "sp_0"):
        df = df[(df[c] >= SP_MIN) & (df[c] <= SP_MAX)]
    df["result_code"] = df["result_code"].astype(str).str.strip()
    df = df[df["result_code"].isin(["3", "1", "0"])].reset_index(drop=True)
    iso = df["kickoff_ts"].dt.isocalendar()
    df["week_key"] = iso["year"].astype(int) * 100 + iso["week"].astype(int)
    return df


def filter_tradable(df, league_q, q_min):
    qualified = {l for l, q in league_q.items() if q >= q_min}
    out = df[df["league"].isin(qualified)].copy()
    out["q"] = out["league"].map(league_q)
    return out


# Outcome index 0->'3', 1->'1', 2->'0'
OUTCOME_CODES = ("3", "1", "0")
SP_COLS = ("sp_3", "sp_1", "sp_0")


def select_top_n(week_df, n):
    """Pick top N matches by league q (desc), then earliest kickoff for ties."""
    if len(week_df) < n:
        return None
    return (
        week_df.sort_values(["q", "kickoff_ts"], ascending=[False, True])
        .head(n)
        .reset_index(drop=True)
    )


def enumerate_combos(legs_df):
    """legs_df has columns sp_3, sp_1, sp_0, q, result_code (per leg).

    Returns array of:
      p_hat      : product(q * (1/sp) / RAKE) per leg
      payout     : product(sp) * RAKE
      ev         : p_hat*payout - 1
      win_mask   : bool, joint matches actual result
    """
    n = len(legs_df)
    sps = legs_df[list(SP_COLS)].to_numpy()  # (n, 3)
    q = legs_df["q"].to_numpy()  # (n,)
    actual = legs_df["result_code"].to_numpy()  # (n,)

    # build all 3^n outcome indices
    idx = np.array(list(itertools.product(range(3), repeat=n)))  # (M, n)
    M = idx.shape[0]
    rows = np.arange(n)
    sp_pick = sps[rows[None, :], idx]  # (M, n)

    inv = 1.0 / sp_pick  # implied p
    p_each = (q[None, :] * inv) / RAKE  # (M, n)
    p_hat = np.prod(p_each, axis=1)
    payout = np.prod(sp_pick, axis=1) * RAKE
    ev = p_hat * payout - 1.0

    actual_idx = np.array([OUTCOME_CODES.index(a) for a in actual])
    win_mask = np.all(idx == actual_idx[None, :], axis=1)
    return p_hat, payout, ev, win_mask


def simulate_coverage(matches, league_q, q_min, n, k_frac):
    sub = filter_tradable(matches, league_q, q_min)
    bankroll = INITIAL
    rows = []
    for wk, week_df in sub.groupby("week_key", sort=True):
        legs = select_top_n(week_df, n)
        if legs is None:
            rows.append((wk, 0.0, 0.0, bankroll, 0))
            continue
        p_hat, payout, ev, win_mask = enumerate_combos(legs)
        M = len(ev)
        k = max(1, int(np.ceil(k_frac * M)))
        # top-K by EV
        top = np.argpartition(-ev, k - 1)[:k]
        chosen = np.zeros(M, dtype=bool)
        chosen[top] = True

        n_tickets = int(chosen.sum())
        wk_stake = n_tickets * STAKE_PER_TICKET

        # safety cap
        max_stake = WEEKLY_STAKE_CAP_FRAC * bankroll
        if wk_stake > max_stake:
            scale = max_stake / wk_stake
            n_tickets = max(1, int(np.floor(n_tickets * scale)))
            # keep highest-EV chosen
            top_sorted = top[np.argsort(-ev[top])][:n_tickets]
            chosen = np.zeros(M, dtype=bool)
            chosen[top_sorted] = True
            wk_stake = n_tickets * STAKE_PER_TICKET

        wk_payout = 0.0
        # only the win_mask combo (if chosen) pays
        win_idx = np.where(win_mask)[0]
        if len(win_idx) and chosen[win_idx[0]]:
            single_payout = STAKE_PER_TICKET * payout[win_idx[0]]
            # tax on prize > cap
            if single_payout > TAX_FREE_CAP:
                single_payout -= (single_payout - TAX_FREE_CAP) * TAX_RATE
            wk_payout = single_payout

        wk_pnl = wk_payout - wk_stake
        bankroll += wk_pnl
        rows.append((wk, wk_stake, wk_pnl, bankroll, n_tickets))
        if bankroll <= 0:
            break

    df = pd.DataFrame(rows, columns=["week_key", "stake", "pnl", "bankroll", "n_tickets"])
    return df


def metrics(pnl, initial=INITIAL):
    if len(pnl) == 0:
        return None
    bankroll = initial + np.cumsum(pnl)
    bankroll = np.maximum(bankroll, 0.01)
    n = len(pnl)
    yrs = n / 52.0
    cagr = (bankroll[-1] / initial) ** (1 / max(yrs, 1e-6)) - 1.0
    pct = pnl / initial
    sharpe = (np.mean(pct) * 52) / (np.std(pct, ddof=1) * np.sqrt(52)) if len(pct) > 1 and np.std(pct, ddof=1) > 0 else 0.0
    seq = np.concatenate([[initial], bankroll])
    rm = np.maximum.accumulate(seq)
    dd = (seq - rm) / rm
    max_dd = float(np.min(dd))
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0
    hit = float((pnl > 0).mean())
    return dict(final=float(bankroll[-1]), cagr=float(cagr), sharpe=float(sharpe),
                max_dd=float(max_dd), calmar=float(calmar), hit_rate=hit, n_weeks=n)


def run_one(args):
    q_min, n, k_frac, matches, league_q = args
    df = simulate_coverage(matches, league_q, q_min, n, k_frac)
    m = metrics(df["pnl"].values)
    avg_stake = float(df.loc[df["stake"] > 0, "stake"].mean()) if (df["stake"] > 0).any() else 0.0
    return dict(q_min=q_min, n=n, k_frac=k_frac, avg_stake=avg_stake, **(m or {}))


def baseline():
    from notebooks.equity_curve_default import simulate_with_stake
    from src.dual_sweep.variants import build_archetype_a_qual
    qa, _ = build_archetype_a_qual()
    df = simulate_with_stake(qa, n_legs=4, kelly_fraction=1/16, diversity_lambda=0.5,
                             max_combos_per_week=200, commission_rate=0.0)
    return metrics(df["week_pnl"].values)


def main():
    print("Loading matches...")
    matches = load_matches()
    league_q = load_league_q()
    print(f"Matches (last 8y, valid): {len(matches)}; leagues with q: {len(league_q)}")

    Q_MINS = [0.0, 0.65, 0.80]
    NS = [5, 6, 7, 8]
    KS = [0.10, 0.20, 0.30, 0.50, 1.00]

    configs = [(q, n, k, matches, league_q) for q in Q_MINS for n in NS for k in KS]
    print(f"Running {len(configs)} configs...")

    # serial is fine — each run is fast (numpy enumerate up to 3^8=6561)
    results = [run_one(c) for c in configs]

    df = pd.DataFrame(results)
    df = df.sort_values("calmar", ascending=False).reset_index(drop=True)

    print("\n=== Results sorted by Calmar (top 20) ===")
    cols = ["q_min", "n", "k_frac", "n_weeks", "avg_stake", "final", "cagr", "sharpe", "max_dd", "calmar", "hit_rate"]
    fmt = df[cols].copy()
    for c in ("cagr", "max_dd", "hit_rate"):
        fmt[c] = (fmt[c] * 100).round(1)
    for c in ("sharpe", "calmar"):
        fmt[c] = fmt[c].round(2)
    fmt["final"] = fmt["final"].round(0)
    fmt["avg_stake"] = fmt["avg_stake"].round(0)
    print(fmt.head(20).to_string(index=False))

    print("\n=== Top 3 by Calmar ===")
    print(fmt.head(3).to_string(index=False))
    print("\n=== Top 3 by Sharpe ===")
    print(fmt.sort_values("sharpe", ascending=False).head(3).to_string(index=False))

    print("\n=== Baseline (per-leg combo, N=4 Kelly=1/16) ===")
    bm = baseline()
    print(bm)

    out = ROOT / "data" / "raw" / "coverage_backtest_results.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved full results to {out}")


if __name__ == "__main__":
    main()
