"""Pairwise correlation + hierarchical clustering of niche return streams."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform


def pairwise_corr(R: pd.DataFrame, min_overlap: int = 20) -> pd.DataFrame:
    """Pearson correlation, pairwise complete (NaNs excluded). Pairs with
    fewer than `min_overlap` overlapping weeks are set to NaN."""
    cols = list(R.columns)
    n = len(cols)
    out = np.full((n, n), np.nan)
    for i in range(n):
        for j in range(n):
            if i == j:
                out[i, j] = 1.0
                continue
            a = R[cols[i]]
            b = R[cols[j]]
            mask = a.notna() & b.notna()
            if mask.sum() < min_overlap:
                continue
            out[i, j] = np.corrcoef(a[mask], b[mask])[0, 1]
    return pd.DataFrame(out, index=cols, columns=cols)


def cluster_niches(corr: pd.DataFrame, t: float = 0.7) -> dict:
    """Hierarchical clustering on distance = 1 - |corr|.

    Returns dict with keys 'linkage', 'labels', 'order' (leaf order).
    `t` is the distance threshold for fcluster.
    """
    C = corr.fillna(0.0).values
    dist = 1.0 - np.abs(C)
    np.fill_diagonal(dist, 0.0)
    # symmetric
    dist = (dist + dist.T) / 2.0
    condensed = squareform(dist, checks=False)
    Z = linkage(condensed, method="average")
    labels = fcluster(Z, t=t, criterion="distance")
    # Leaf order via dendrogram (no plotting)
    from scipy.cluster.hierarchy import leaves_list
    order = leaves_list(Z)
    return dict(linkage=Z, labels=labels, order=order, ids=list(corr.index))


def summarize_clusters(cluster_info: dict) -> pd.DataFrame:
    df = pd.DataFrame(dict(id=cluster_info["ids"],
                           cluster=cluster_info["labels"]))
    return df.sort_values(["cluster", "id"]).reset_index(drop=True)
