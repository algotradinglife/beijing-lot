"""End-to-end runner: build returns, correlation, clustering, Markowitz,
backtest, render HTML report.

Usage (from repo root):
    python -m scripts.run_niche_corr
"""
from __future__ import annotations

import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)

import numpy as np
import pandas as pd

from src.niche_analysis.sp_native import load_full_3sp, to_long
from src.niche_corr.niches import SURVIVED_16
from src.niche_corr.returns import build_return_matrix
from src.niche_corr.corr import pairwise_corr, cluster_niches, summarize_clusters
from src.niche_corr.portfolio import stats, efficient_frontier, bootstrap_min_var
from src.niche_corr.backtest import run_all
from src.niche_corr import figures, report

OUT_HTML = os.path.join(REPO, "docs", "research", "niche_corr_report.html")
FIG_DIR = os.path.join(REPO, "docs", "research", "figures")


def main():
    print("[1/7] loading 3-SP frame …", flush=True)
    df = load_full_3sp()
    long = to_long(df)
    print(f"  long rows: {len(long):,}")

    print("[2/7] building per-niche weekly N=3 return matrix …", flush=True)
    R = build_return_matrix(long, niches=SURVIVED_16, n_legs=3)
    print(f"  R shape: {R.shape}, weeks={len(R)}, niches={R.shape[1]}")
    print(f"  per-niche bet weeks: min={R.notna().sum().min()} "
          f"med={int(R.notna().sum().median())} max={R.notna().sum().max()}")

    print("[3/7] correlation + clustering …", flush=True)
    C = pairwise_corr(R, min_overlap=20)
    cinfo = cluster_niches(C, t=0.7)
    csum = summarize_clusters(cinfo)
    print(f"  clusters: {csum['cluster'].nunique()}")

    print("[4/7] Markowitz frontier + bootstrap …", flush=True)
    mu, cov = stats(R)
    front = efficient_frontier(mu, cov, n_points=25)
    boot = bootstrap_min_var(R, n_boot=200, seed=0)

    print("[5/7] backtest 4 strategies …", flush=True)
    strats = run_all(R, bankroll=100_000.0, f=0.02)
    for k, s in strats.items():
        print(f"  {s['name']:24s} CAGR={s['CAGR']*100:+6.2f}% "
              f"Sharpe={s['Sharpe']:+5.2f} MaxDD={s['MaxDD']*100:+6.1f}% "
              f"Calmar={s['Calmar']:+.2f}  final=¥{s['final']:>13,.0f}")

    print("[6/7] rendering figures …", flush=True)
    fig_paths = dict(
        heatmap=os.path.join(FIG_DIR, "niche_corr_heatmap.png"),
        dendrogram=os.path.join(FIG_DIR, "niche_corr_dendrogram.png"),
        frontier=os.path.join(FIG_DIR, "niche_corr_frontier.png"),
        equity=os.path.join(FIG_DIR, "niche_corr_equity.png"),
    )
    figures.heatmap(C, fig_paths["heatmap"])
    figures.dendro(cinfo, fig_paths["dendrogram"])
    figures.frontier_plot(front, mu, cov, list(R.columns), fig_paths["frontier"])
    figures.equity_plot(strats, fig_paths["equity"])

    # ---- verdict ----
    sharpes = {k: s["Sharpe"] for k, s in strats.items()}
    best_strat = max(sharpes, key=sharpes.get)
    sb = strats["single_best"]
    bs = strats[best_strat]
    if best_strat == "single_best":
        verdict = (f"Multi-niche diversification did NOT beat the single best "
                   f"niche on this dataset. Single best ({sb.get('niche', '?')}) "
                   f"Sharpe={sb['Sharpe']:.2f} vs equal={strats['equal']['Sharpe']:.2f}, "
                   f"Markowitz={strats['markowitz']['Sharpe']:.2f}, "
                   f"dyn-top3={strats['dynamic_top3']['Sharpe']:.2f}.")
    else:
        verdict = (f"Diversification helps: best strategy is {bs['name']} "
                   f"(Sharpe={bs['Sharpe']:.2f}, CAGR={bs['CAGR']*100:+.1f}%) vs "
                   f"single-best ({sb.get('niche','?')}) Sharpe={sb['Sharpe']:.2f}, "
                   f"CAGR={sb['CAGR']*100:+.1f}%.")

    caveats = [
        "Sparse weekly returns: many niches have <2 picks/week, NaNs treated as zero P&L for the week.",
        "Markowitz is fitted on the FULL sample → in-sample bias; bootstrap p05/p95 columns show weight instability.",
        "Single-best selects the niche with highest historical mean (full-sample look-ahead). A strict prior-only baseline would be lower.",
        "Dynamic top-3 uses ONLY trailing 8 weeks strictly before t (no lookahead).",
        "Combo settle uses real SP and 0.65 北单 return rate; per-leg p_hat uses within-match devig only (no outcome leakage).",
        "NaN-as-zero for cov estimation under-states niche variance and can over-state the diversification benefit.",
    ]

    print("[7/7] writing HTML report …", flush=True)
    report.render_report(
        OUT_HTML,
        niche_meta=SURVIVED_16,
        R=R,
        corr=C,
        cluster_summary=csum,
        bootstrap_w=boot,
        efficient_frontier=front,
        strategies=strats,
        fig_paths=fig_paths,
        caveats=caveats,
        verdict=verdict,
    )
    print(f"  wrote {OUT_HTML}")
    print("done.")
    # Print machine-readable summary line
    off = C.values[np.triu_indices(C.shape[0], k=1)]
    off = off[~np.isnan(off)]
    print(f"\nSUMMARY  mean_abs_corr={np.mean(np.abs(off)):.3f}  "
          f"n_clusters={csum['cluster'].nunique()}  "
          f"best_sharpe_strat={best_strat}  best_sharpe={sharpes[best_strat]:.3f}  "
          f"single_best_sharpe={sb['Sharpe']:.3f}")


if __name__ == "__main__":
    main()
