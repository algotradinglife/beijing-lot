"""Track 5 — Hit-rate × P/L Pareto scatter, plus equity curves."""
from __future__ import annotations

import os
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def pareto_scatter(metrics_df: pd.DataFrame, out_path: str) -> str:
    """Hit-rate vs win/loss-ratio scatter. Size=cum_roi, color=Sharpe."""
    df = metrics_df.copy()
    df = df[df["n_weeks"] > 0]
    if df.empty:
        return out_path
    fig, ax = plt.subplots(figsize=(10, 7))
    x = df["weekly_win_rate"].to_numpy()
    y = df["win_loss_ratio"].to_numpy()
    # Replace inf for visualization
    y = np.where(np.isfinite(y), y, np.nanmax(y[np.isfinite(y)]) * 1.2 if np.isfinite(y).any() else 1.0)
    cum = df["cum_roi"].to_numpy()
    sharpe = df["sharpe"].to_numpy()
    sharpe_v = np.where(np.isfinite(sharpe), sharpe, 0.0)
    sizes = 80 + 1200 * np.clip((cum - cum.min()) / max(1e-9, (cum.max() - cum.min())), 0, 1)
    sc = ax.scatter(x, y, s=sizes, c=sharpe_v, cmap="viridis",
                    alpha=0.85, edgecolor="black", linewidth=0.6)
    cb = plt.colorbar(sc, ax=ax)
    cb.set_label("Sharpe")
    for _, r in df.iterrows():
        ax.annotate(r["variant"],
                    (r["weekly_win_rate"], r["win_loss_ratio"] if np.isfinite(r["win_loss_ratio"]) else 1.0),
                    fontsize=8, alpha=0.9, xytext=(4, 4), textcoords="offset points")
    # Iso-Sharpe (heuristic) contours: lines of constant win_rate * (1+wlr)
    xs = np.linspace(max(1e-3, x.min() * 0.5), x.max() * 1.2, 100)
    for k in (0.5, 1.0, 1.5, 2.0):
        ys = (k / xs) - 1.0
        ys = np.where(ys > 0, ys, np.nan)
        ax.plot(xs, ys, "--", color="grey", alpha=0.3, linewidth=0.8)
    ax.set_xlabel("Weekly win rate")
    ax.set_ylabel("Avg win / |Avg loss|")
    ax.set_title("Pareto: Hit rate × P/L ratio (size=cum_ROI, color=Sharpe)")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return out_path


def equity_overlay(curves: dict, out_path: str, title: str = "Equity curves") -> str:
    """curves: { label: bankroll_curve_array }."""
    fig, ax = plt.subplots(figsize=(11, 6))
    cmap = plt.colormaps["tab20"]
    for i, (label, bb) in enumerate(curves.items()):
        if len(bb) == 0:
            continue
        ax.plot(bb, label=label, color=cmap(i % 20), linewidth=1.2, alpha=0.85)
    ax.axhline(100_000, color="black", linestyle=":", linewidth=0.7)
    ax.set_xlabel("Active week")
    ax.set_ylabel("Bankroll (yuan)")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return out_path


def small_multiples(curves_by_period: dict, out_path: str) -> str:
    """curves_by_period: { period: { label: bb_array } }."""
    n_periods = len(curves_by_period)
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    axes = axes.flatten()
    cmap = plt.colormaps["tab20"]
    for ax, (period, curves) in zip(axes, curves_by_period.items()):
        for i, (label, bb) in enumerate(curves.items()):
            if len(bb) == 0:
                continue
            ax.plot(bb, label=label, color=cmap(i % 20), linewidth=1.0, alpha=0.85)
        ax.axhline(100_000, color="black", linestyle=":", linewidth=0.6)
        ax.set_title(period)
        ax.grid(True, alpha=0.3)
        ax.set_xlabel("Active week")
        ax.set_ylabel("Bankroll")
    axes[0].legend(fontsize=7, ncol=2, loc="upper left")
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return out_path
