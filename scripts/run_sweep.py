"""Orchestrate the full N ∈ {2..8} combo sweep and render the HTML report."""
from __future__ import annotations

import os
import sys
import time

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)

from src.sweep.qualifying_picks import build_qualifying_picks
from src.sweep.simulator import simulate
from src.sweep.metrics import summarize
from src.sweep.monte_carlo import forward_simulate
from src.sweep.report import render_report


def main() -> None:
    t0 = time.time()
    print("[1/4] Building qualifying picks (this may take 30–60s on first run)...")
    qual, surv = build_qualifying_picks()
    print(f"      {len(qual):,} qualifying legs · {len(surv)} surviving niches "
          f"({time.time()-t0:.1f}s)")

    summaries: list[dict] = []
    sims: dict = {}
    mc_results: dict = {}
    for n in [2, 3, 4, 5, 6, 7, 8]:
        ts = time.time()
        sim = simulate(qual, n_legs=n)
        mc = forward_simulate(sim.weekly)
        s = summarize(sim, n, qual)
        sims[n] = sim
        mc_results[n] = mc
        summaries.append(s)
        print(f"[2/4] N={n}: {s['n_combos_total']:,} combos · {s['n_hits']:,} hits "
              f"· cum_ROI={s['cumulative_ROI']:+.1%} · Sharpe={s['sharpe']:.2f} "
              f"({time.time()-ts:.1f}s)")

    summary_df = pd.DataFrame(summaries)
    print(f"[3/4] Rendering report...")
    render_report(summary_df, mc_results, sims,
                  n_qual_picks=len(qual), n_surviving_niches=len(surv))
    out = os.path.join(REPO, "docs", "research", "combo_sweep_report.html")
    print(f"      → {out}")
    print(f"[4/4] Total {time.time()-t0:.1f}s")
    # Also dump CSV summary
    csv_path = os.path.join(REPO, "docs", "research", "combo_sweep_summary.csv")
    summary_df.to_csv(csv_path, index=False)
    print(f"      summary CSV → {csv_path}")


if __name__ == "__main__":
    main()
