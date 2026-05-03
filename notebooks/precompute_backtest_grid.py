"""Pre-compute a grid of backtest results so the webui can display live preview.

Output: data/raw/backtest_grid.json
  Each cell keyed by f"N{n}_K{kelly_str}_L{lambda_str}_M{max_combos}_C{comm_str}"
  Value: dict with metrics + weekly equity series (downsampled to ~50 points).
"""
from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))

from src.dual_sweep.variants import build_archetype_a_qual
from equity_curve_default import simulate_with_stake, INITIAL


def cell_key(n_legs, kelly_fraction, diversity_lambda, max_combos, commission_rate):
    return (
        f"N{n_legs}_K{kelly_fraction:.4f}_L{diversity_lambda:.2f}"
        f"_M{max_combos}_C{commission_rate:.3f}"
    )


def metrics_full(weekly_pnl, weekly_stake, initial=INITIAL):
    bankroll = initial + np.cumsum(weekly_pnl)
    bankroll = np.maximum(bankroll, 0.01)
    n_weeks = len(weekly_pnl)
    if n_weeks == 0:
        return None
    cum_roi = (bankroll[-1] - initial) / initial
    yrs = n_weeks / 52.0
    cagr = (bankroll[-1] / initial) ** (1.0 / max(yrs, 1e-6)) - 1.0
    pct = weekly_pnl / initial
    sharpe = (np.mean(pct) * 52) / (np.std(pct, ddof=1) * np.sqrt(52)) if len(pct) > 1 and np.std(pct, ddof=1) > 0 else 0
    seq = np.concatenate([[initial], bankroll])
    rm = np.maximum.accumulate(seq)
    dd = (seq - rm) / rm
    max_dd = float(np.min(dd))
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0
    avg_stake = float(weekly_stake[weekly_stake > 0].mean()) if (weekly_stake > 0).any() else 0
    util = avg_stake / initial * 100
    return dict(
        n_weeks=n_weeks,
        final=float(bankroll[-1]),
        cum_roi=float(cum_roi),
        cagr=float(cagr),
        sharpe=float(sharpe),
        max_dd=float(max_dd),
        calmar=float(calmar),
        hit_rate=float((weekly_pnl > 0).mean()),
        avg_weekly_stake=avg_stake,
        utilization_pct=util,
    )


def main():
    print("Loading qual_a (one-time)...")
    qual_a, _ = build_archetype_a_qual()
    print(f"qual_a rows: {len(qual_a)}")

    grid = {
        "n_legs": [3, 4],
        "kelly_fraction": [1/32, 1/16, 1/8, 1/4],
        "diversity_lambda": [0.0, 0.5, 1.0, 2.0],
        "max_combos": [25, 50, 100, 200],
        "commission_rate": [0.0, 0.07],
    }
    total = (len(grid["n_legs"]) * len(grid["kelly_fraction"])
             * len(grid["diversity_lambda"]) * len(grid["max_combos"])
             * len(grid["commission_rate"]))
    print(f"Total cells: {total}")

    cells = {}
    i = 0
    for n in grid["n_legs"]:
        for kf in grid["kelly_fraction"]:
            for lam in grid["diversity_lambda"]:
                for mc in grid["max_combos"]:
                    for comm in grid["commission_rate"]:
                        i += 1
                        key = cell_key(n, kf, lam, mc, comm)
                        try:
                            df = simulate_with_stake(
                                qual_a, n_legs=n, kelly_fraction=kf,
                                diversity_lambda=lam, max_combos_per_week=mc,
                                commission_rate=comm,
                            )
                            m = metrics_full(df["week_pnl"].values, df["week_stake"].values)
                            if m is None:
                                continue
                            # Equity curve as cumulative bankroll, downsampled to 50 points
                            bankroll_series = INITIAL + np.cumsum(df["week_pnl"].values)
                            n_pts = len(bankroll_series)
                            if n_pts > 50:
                                idx = np.linspace(0, n_pts - 1, 50).astype(int)
                                bankroll_series = bankroll_series[idx]
                            m["equity_curve"] = [round(float(x), 0) for x in bankroll_series]
                            cells[key] = m
                            if i % 20 == 0 or i == total:
                                print(f"  [{i}/{total}] {key}: CAGR={m['cagr']*100:.1f}%, "
                                      f"Sharpe={m['sharpe']:.2f}, util={m['utilization_pct']:.1f}%")
                        except Exception as e:
                            print(f"  [{i}/{total}] {key}: ERROR {e}")
    out = Path("/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/backtest_grid.json")
    out.write_text(json.dumps(cells, ensure_ascii=False))
    print(f"\nSaved {len(cells)} cells to {out}")


if __name__ == "__main__":
    main()
