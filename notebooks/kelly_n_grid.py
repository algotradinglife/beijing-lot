"""Full Kelly × N grid: find absolute optimal (Kelly, N) combo.

For each (kelly_fraction, n_legs):
  - Run single backtest at 100k initial bankroll
  - Compute CAGR, Sharpe, MaxDD, Calmar, time underwater, P5_weekly
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dual_sweep.variants import build_archetype_a_qual
from src.sweep.simulator import simulate

INITIAL = 100_000.0
KELLY_GRID = [1/32, 1/16, 1/8, 1/4, 1/2]
N_GRID = [2, 3, 4, 5]


def metrics(weekly_pnl: np.ndarray, initial: float = INITIAL) -> dict:
    if len(weekly_pnl) == 0:
        return dict(n_weeks=0, final=initial, cum_roi=0.0, cagr=0.0,
                    sharpe=0.0, sortino=0.0, max_dd=0.0, calmar=0.0,
                    time_underwater=0.0, p5_weekly=0.0, hit_rate=0.0,
                    mean_pnl=0.0, std_pnl=0.0)
    bankroll = initial + np.cumsum(weekly_pnl)
    bankroll = np.maximum(bankroll, 0.01)  # avoid log(0)
    n_weeks = len(weekly_pnl)
    cum_roi = (bankroll[-1] - initial) / initial
    years = n_weeks / 52.0
    cagr = (bankroll[-1] / initial) ** (1.0 / max(years, 1e-6)) - 1.0
    pct = weekly_pnl / initial
    mean_r = float(np.mean(pct))
    std_r = float(np.std(pct, ddof=1)) if len(pct) > 1 else 0.0
    sharpe = (mean_r * 52.0) / (std_r * np.sqrt(52.0)) if std_r > 0 else 0.0
    downside = pct[pct < 0]
    sortino = (mean_r * 52.0) / (np.std(downside, ddof=1) * np.sqrt(52.0)) if len(downside) > 1 else 0.0
    seq = np.concatenate([[initial], bankroll])
    rm = np.maximum.accumulate(seq)
    dd_series = (seq - rm) / rm
    max_dd = float(np.min(dd_series))
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0
    time_uw = float((dd_series < -0.05).mean())
    return dict(
        n_weeks=n_weeks,
        final=float(bankroll[-1]),
        cum_roi=float(cum_roi),
        cagr=float(cagr),
        sharpe=float(sharpe),
        sortino=float(sortino),
        max_dd=float(max_dd),
        calmar=float(calmar),
        time_underwater=time_uw,
        p5_weekly=float(np.quantile(weekly_pnl, 0.05)),
        hit_rate=float((weekly_pnl > 0).mean()),
        mean_pnl=float(np.mean(weekly_pnl)),
        std_pnl=float(np.std(weekly_pnl, ddof=1)) if len(weekly_pnl) > 1 else 0.0,
    )


def main():
    print("Loading Archetype A qualifying picks...")
    qual_a, _ = build_archetype_a_qual()
    print(f"qual_a rows: {len(qual_a)}\n")

    rows = []
    for n in N_GRID:
        for kf in KELLY_GRID:
            res = simulate(qual_a, n_legs=n, initial_bankroll=INITIAL,
                           kelly_fraction=kf, per_combo_cap_frac=0.005,
                           weekly_stake_cap_frac=0.25, max_combos_per_week=300,
                           seed=7, test_only=True)
            if len(res.weekly) == 0 or "week_pnl" not in res.weekly.columns:
                m = metrics(np.array([]))
                mean_stake = 0.0
            else:
                m = metrics(res.weekly["week_pnl"].values)
                mean_stake = float(res.weekly["week_stake"].mean())
            row = {"N": n, "kelly": kf, "kelly_label": f"1/{int(1/kf)}", **m,
                   "mean_wk_stake": mean_stake,
                   "mean_wk_stake_pct": mean_stake / INITIAL * 100}
            rows.append(row)
            print(f"  N={n} Kelly=1/{int(1/kf):>2}: final={m['final']:>13,.0f} "
                  f"CAGR={m['cagr']*100:>6.1f}% Sharpe={m['sharpe']:>5.2f} "
                  f"Sortino={m['sortino']:>5.2f} MaxDD={m['max_dd']*100:>6.1f}% "
                  f"Calmar={m['calmar']:>5.2f} TimeUW={m['time_underwater']*100:>5.1f}%")

    df = pd.DataFrame(rows)
    out_csv = "/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/kelly_n_grid.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nSaved to {out_csv}")

    # Summary tables
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")
    pd.set_option("display.width", 220)

    def show_pivot(metric_col, mult=1.0, label=None):
        label = label or metric_col
        piv = df.pivot(index="N", columns="kelly_label", values=metric_col) * mult
        cols_order = ["1/32", "1/16", "1/8", "1/4", "1/2"]
        piv = piv[[c for c in cols_order if c in piv.columns]]
        print(f"\n=== {label} ===")
        print(piv.round(2))

    show_pivot("cagr", 100, "CAGR (%)")
    show_pivot("sharpe", 1, "Sharpe")
    show_pivot("sortino", 1, "Sortino")
    show_pivot("max_dd", 100, "Max DD (%)")
    show_pivot("calmar", 1, "Calmar")
    show_pivot("time_underwater", 100, "Time Underwater (%)")
    show_pivot("final", 1/1e6, "Final (M元)")

    # Find optima per metric
    print("\n=== Optima ===")
    for metric in ["cagr", "sharpe", "sortino", "calmar"]:
        best = df.sort_values(metric, ascending=False).iloc[0]
        print(f"  Best {metric}: N={int(best['N'])} Kelly={best['kelly_label']} "
              f"→ {metric}={best[metric]:.3f}, MaxDD={best['max_dd']*100:.1f}%, "
              f"final={best['final']:,.0f}")
    # Min |MaxDD| s.t. CAGR > 0.5
    pos = df[df["cagr"] > 0.5]
    if len(pos):
        best_dd = pos.sort_values("max_dd", ascending=False).iloc[0]
        print(f"  Min |MaxDD| s.t. CAGR≥50%: N={int(best_dd['N'])} Kelly={best_dd['kelly_label']} "
              f"→ MaxDD={best_dd['max_dd']*100:.1f}%, CAGR={best_dd['cagr']*100:.1f}%, "
              f"Sharpe={best_dd['sharpe']:.2f}")

    # Pareto frontier on (Sharpe, |MaxDD|)
    print("\n=== Pareto frontier (Sharpe, |MaxDD|) ===")
    df2 = df.sort_values("max_dd", ascending=False).reset_index(drop=True)
    pareto = []
    best_sh = -1
    for _, r in df2.iterrows():
        if r["sharpe"] > best_sh:
            best_sh = r["sharpe"]
            pareto.append(r)
    par_df = pd.DataFrame(pareto)[
        ["N", "kelly_label", "cagr", "sharpe", "max_dd", "calmar", "final"]]
    par_df["cagr"] = par_df["cagr"] * 100
    par_df["max_dd"] = par_df["max_dd"] * 100
    par_df["final"] = par_df["final"] / 1e6
    print(par_df.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
