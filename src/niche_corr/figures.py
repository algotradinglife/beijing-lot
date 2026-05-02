"""Matplotlib figure helpers for the niche-corr report."""
from __future__ import annotations

import os
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.cluster.hierarchy import dendrogram


def heatmap(corr: pd.DataFrame, path: str, title: str = "Niche return correlation"):
    fig, ax = plt.subplots(figsize=(8, 7))
    C = corr.values
    im = ax.imshow(C, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.index)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(corr.index, fontsize=9)
    for i in range(C.shape[0]):
        for j in range(C.shape[1]):
            v = C[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7,
                    color="black" if abs(v) < 0.5 else "white")
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.04)
    ax.set_title(title)
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def dendro(cluster_info: dict, path: str, title: str = "Niche hierarchical clustering"):
    fig, ax = plt.subplots(figsize=(9, 5))
    dendrogram(cluster_info["linkage"], labels=cluster_info["ids"],
               leaf_rotation=45, leaf_font_size=9, ax=ax,
               color_threshold=0.7)
    ax.set_title(title)
    ax.set_ylabel("distance (1 − |corr|)")
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def frontier_plot(frontier: pd.DataFrame, mu: np.ndarray, cov: np.ndarray,
                  ids: list[str], path: str):
    fig, ax = plt.subplots(figsize=(7, 5))
    vols = np.sqrt(np.diag(cov))
    ax.scatter(vols, mu, c="grey", s=35, label="individual niches", alpha=0.7)
    for x, y, lab in zip(vols, mu, ids):
        ax.annotate(lab, (x, y), fontsize=7, alpha=0.7)
    ax.plot(frontier["vol"], frontier["mu"], "-", color="#b04a2f",
            label="efficient frontier")
    ax.set_xlabel("weekly per-yuan return std")
    ax.set_ylabel("weekly per-yuan return mean")
    ax.set_title("Markowitz efficient frontier")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def equity_plot(strategies: dict, path: str):
    fig, ax = plt.subplots(figsize=(9, 5))
    palette = {"single_best": "#8b2424", "equal": "#2e6b4a",
               "markowitz": "#b04a2f", "dynamic_top3": "#1a4a8b"}
    for key, s in strategies.items():
        eq = s["equity"]
        ax.plot(eq.index, eq.values, label=s["name"], color=palette.get(key, "grey"),
                lw=1.5)
    ax.set_yscale("log")
    ax.set_ylabel("Equity (¥, log scale)")
    ax.set_xlabel("Week")
    ax.set_title("Backtest equity curves (¥100k start, f=2%/wk)")
    ax.axhline(100_000, color="grey", lw=0.8, ls="--", alpha=0.6)
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
