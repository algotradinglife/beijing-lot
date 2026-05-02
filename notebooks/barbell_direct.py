"""Direct barbell analysis (no agent).

For N ∈ {2, 3, 4, 5}, run independent backtest at 100k initial bankroll
on Archetype A qualifying picks. Then for various barbell allocations
(w_2, w_3, w_4, w_5), compute combined weekly PnL = Σ w_i × pnl_i and
derive metrics (CAGR, Sharpe, Max DD, Calmar) for each allocation.

Compares against single-N baselines.
"""
from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dual_sweep.variants import build_archetype_a_qual
from src.sweep.simulator import simulate

INITIAL = 100_000.0
N_VALUES = (2, 3, 4, 5)


def annualize_factor(weeks: int) -> float:
    return 52.0 / max(weeks, 1)


def metrics(weekly_pnl: np.ndarray, initial: float = INITIAL) -> dict:
    bankroll = initial + np.cumsum(weekly_pnl)
    n_weeks = len(weekly_pnl)
    if n_weeks == 0 or bankroll[-1] <= 0:
        return dict(final=bankroll[-1] if n_weeks else initial,
                    cagr=-1.0, sharpe=0.0, max_dd=-1.0, calmar=0.0,
                    cum_roi=-1.0, mean_pnl=0.0, std_pnl=0.0,
                    p5_weekly=0.0, hit_rate=0.0)
    cum_roi = (bankroll[-1] - initial) / initial
    years = n_weeks / 52.0
    cagr = (bankroll[-1] / initial) ** (1.0 / max(years, 1e-6)) - 1.0
    pct_return = weekly_pnl / initial
    mean_r = float(np.mean(pct_return))
    std_r = float(np.std(pct_return, ddof=1)) if len(pct_return) > 1 else 0.0
    sharpe = (mean_r * 52.0) / (std_r * np.sqrt(52.0)) if std_r > 0 else 0.0
    running_max = np.maximum.accumulate(np.concatenate([[initial], bankroll]))
    dd = (np.concatenate([[initial], bankroll]) - running_max) / running_max
    max_dd = float(np.min(dd))
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0
    return dict(
        final=float(bankroll[-1]),
        cum_roi=float(cum_roi),
        cagr=float(cagr),
        sharpe=float(sharpe),
        max_dd=float(max_dd),
        calmar=float(calmar),
        mean_pnl=float(np.mean(weekly_pnl)),
        std_pnl=float(np.std(weekly_pnl, ddof=1)),
        p5_weekly=float(np.quantile(weekly_pnl, 0.05)),
        hit_rate=float((weekly_pnl > 0).mean()),
        n_weeks=n_weeks,
    )


def main():
    print("Loading Archetype A qualifying picks...")
    qual_a, surv_a = build_archetype_a_qual()
    print(f"qual_a rows: {len(qual_a)}; surv niches: {len(surv_a)}")

    # Run single-N independent backtests
    weekly_pnl_per_n = {}
    print("\nRunning single-N backtests:")
    for n in N_VALUES:
        res = simulate(qual_a, n_legs=n, initial_bankroll=INITIAL,
                       kelly_fraction=0.25, per_combo_cap_frac=0.005,
                       weekly_stake_cap_frac=0.25, max_combos_per_week=300,
                       seed=7, test_only=True)
        weekly_pnl_per_n[n] = res.weekly[["week_key", "week_pnl"]].copy()
        m = metrics(res.weekly["week_pnl"].values, INITIAL)
        print(f"  N={n}: final={m['final']:>11,.0f}  CAGR={m['cagr']*100:>6.1f}%  "
              f"Sharpe={m['sharpe']:>5.2f}  MaxDD={m['max_dd']*100:>6.1f}%  "
              f"Calmar={m['calmar']:>5.2f}  P5_wk={m['p5_weekly']:>9,.0f}  "
              f"hit={m['hit_rate']*100:>5.1f}%")

    # Align weeks across N's (outer join on week_key)
    base = weekly_pnl_per_n[N_VALUES[0]][["week_key"]].copy()
    for n in N_VALUES[1:]:
        base = base.merge(weekly_pnl_per_n[n][["week_key"]], on="week_key", how="outer")
    base = base.sort_values("week_key").reset_index(drop=True)
    pnl_mat = pd.DataFrame({"week_key": base["week_key"]})
    for n in N_VALUES:
        merged = pnl_mat.merge(weekly_pnl_per_n[n], on="week_key", how="left")
        pnl_mat[f"n{n}"] = merged["week_pnl"].fillna(0.0).values
    print(f"\nAligned weeks: {len(pnl_mat)}")

    # Barbell sweep: weights summing to 1 in 0.1 steps over (w2, w3, w4, w5)
    rows = []
    grid = np.arange(0.0, 1.01, 0.1)
    for w2, w3, w4, w5 in product(grid, repeat=4):
        s = w2 + w3 + w4 + w5
        if abs(s - 1.0) > 1e-6:
            continue
        combined = (w2 * pnl_mat["n2"] + w3 * pnl_mat["n3"]
                    + w4 * pnl_mat["n4"] + w5 * pnl_mat["n5"]).values
        m = metrics(combined, INITIAL)
        rows.append({"w2": round(w2,1), "w3": round(w3,1), "w4": round(w4,1),
                     "w5": round(w5,1), **m})
    df = pd.DataFrame(rows)
    df["sortable_calmar"] = df["calmar"]
    df = df.sort_values("calmar", ascending=False).reset_index(drop=True)

    print(f"\n=== Top 10 barbell allocations by Calmar ===")
    cols_show = ["w2", "w3", "w4", "w5", "final", "cagr", "sharpe", "max_dd", "calmar",
                 "p5_weekly", "hit_rate"]
    top10 = df.head(10).copy()
    top10["final"] = top10["final"].map(lambda x: f"{x:,.0f}")
    top10["cagr"] = (top10["cagr"]*100).round(1)
    top10["max_dd"] = (top10["max_dd"]*100).round(1)
    top10["calmar"] = top10["calmar"].round(2)
    top10["sharpe"] = top10["sharpe"].round(2)
    top10["p5_weekly"] = top10["p5_weekly"].map(lambda x: f"{x:,.0f}")
    top10["hit_rate"] = (top10["hit_rate"]*100).round(1)
    print(top10[cols_show].to_string(index=False))

    print(f"\n=== Best Sharpe ===")
    df_s = df.sort_values("sharpe", ascending=False).head(5).copy()
    df_s["final"] = df_s["final"].map(lambda x: f"{x:,.0f}")
    df_s["cagr"] = (df_s["cagr"]*100).round(1)
    df_s["max_dd"] = (df_s["max_dd"]*100).round(1)
    df_s["calmar"] = df_s["calmar"].round(2)
    df_s["sharpe"] = df_s["sharpe"].round(2)
    print(df_s[cols_show].to_string(index=False))

    print(f"\n=== Min Max DD (s.t. CAGR > 0) ===")
    pos = df[df["cagr"] > 0].copy()
    df_d = pos.sort_values("max_dd", ascending=False).head(5).copy()
    df_d["final"] = df_d["final"].map(lambda x: f"{x:,.0f}")
    df_d["cagr"] = (df_d["cagr"]*100).round(1)
    df_d["max_dd"] = (df_d["max_dd"]*100).round(1)
    df_d["calmar"] = df_d["calmar"].round(2)
    df_d["sharpe"] = df_d["sharpe"].round(2)
    print(df_d[cols_show].to_string(index=False))

    # Single-N baselines for comparison
    print(f"\n=== Single-N baselines (for comparison) ===")
    for n in N_VALUES:
        m = metrics(pnl_mat[f"n{n}"].values, INITIAL)
        print(f"  N={n}: final={m['final']:>11,.0f}  CAGR={m['cagr']*100:>6.1f}%  "
              f"Sharpe={m['sharpe']:>5.2f}  MaxDD={m['max_dd']*100:>6.1f}%  "
              f"Calmar={m['calmar']:>5.2f}")

    out = Path("/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/barbell_grid.csv")
    df.to_csv(out, index=False)
    print(f"\nSaved full grid ({len(df)} allocations) to {out}")


if __name__ == "__main__":
    main()
