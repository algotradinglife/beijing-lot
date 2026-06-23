"""P1 of the SP-drift quantile-haircut MVP (plan 2026-06-24).

Model the distribution of ``ratio = final_sp / decision_sp`` by
(SP-band × MTK-bucket), trained on ALL legs/snapshots (not just winning legs,
so no survivorship bias): each snapshot at MTK ``m`` with SP ``s`` contributes
one observation ``final_sp / s`` to the cell ``(sp_band(s), mtk_bucket(m))``,
where ``final_sp`` is the leg's closing (smallest-MTK) SP.

Cells are shrunk toward their band-level prior by ``n / (n + shrink_k)`` so thin
cells don't drive sizing. Deterministic given the same panel.

P2 turns this into a conservative-quantile SP adjustment; this module only
fits + looks up the (mean, sd, n) of the ratio.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

import pandas as pd

from src.sp_drift.drift_stats import sp_band

# MTK bucket edges in minutes: (0,120] 0-2h, (120,360] 2-6h, (360,720] 6-12h,
# (720,1440] 12-24h, (1440, inf) 24h+.
MTK_EDGES = [0.0, 120.0, 360.0, 720.0, 1440.0, float("inf")]


def mtk_bucket(mtk: float, edges=MTK_EDGES) -> str:
    """Label the MTK bucket as 'lo-hi' (minutes), deterministic."""
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        if lo < mtk <= hi:
            hi_s = "inf" if hi == float("inf") else f"{int(hi)}"
            return f"{int(lo)}-{hi_s}"
    return f"{int(edges[0])}-{int(edges[1])}"  # mtk<=0 shouldn't occur (panel keeps mtk>0)


@dataclass(frozen=True)
class DriftModel:
    cells: Dict[Tuple[str, str], Tuple[float, float, int]]  # (band,bucket)->(mean,sd,n) shrunk
    band_prior: Dict[str, Tuple[float, float]]              # band->(mean,sd)
    global_prior: Tuple[float, float]                       # (mean,sd)
    edges: tuple = field(default=tuple(MTK_EDGES))

    def lookup(self, sp: float, mtk: float) -> Tuple[float, float, int]:
        """Return (mean_ratio, sd_ratio, n_raw) for the cell of (sp, mtk),
        falling back to band prior then global prior for unseen cells (n=0)."""
        band = sp_band(sp)
        bucket = mtk_bucket(mtk, list(self.edges))
        cell = self.cells.get((band, bucket))
        if cell is not None:
            return cell
        if band in self.band_prior:
            m, s = self.band_prior[band]
            return (m, s, 0)
        m, s = self.global_prior
        return (m, s, 0)

    def table(self) -> pd.DataFrame:
        """Tidy (band, bucket, mean, sd, n) table, sorted deterministically."""
        rows = [
            {"band": b, "mtk_bucket": k, "mean_ratio": round(m, 4),
             "sd_ratio": round(s, 4), "n": n}
            for (b, k), (m, s, n) in self.cells.items()
        ]
        df = pd.DataFrame(rows, columns=["band", "mtk_bucket", "mean_ratio",
                                         "sd_ratio", "n"])
        return df.sort_values(["band", "mtk_bucket"]).reset_index(drop=True)


def _ratios(panel: pd.DataFrame) -> pd.DataFrame:
    """One row per snapshot with ratio = final_sp/sp, band, mtk_bucket."""
    df = panel[["match_id", "selection", "sp", "mtk"]].copy()
    df = df[(df["sp"] > 0) & df["mtk"].notna()]
    # final_sp = SP at smallest MTK (closing) per (match, selection)
    closing = df.loc[df.groupby(["match_id", "selection"])["mtk"].idxmin(),
                     ["match_id", "selection", "sp"]].rename(columns={"sp": "final_sp"})
    df = df.merge(closing, on=["match_id", "selection"], how="left")
    df = df[df["final_sp"] > 0]
    df["ratio"] = df["final_sp"] / df["sp"]
    df["band"] = df["sp"].map(sp_band)
    df["mtk_bucket"] = df["mtk"].map(mtk_bucket)
    return df


def fit_drift_model(panel: pd.DataFrame, *, mtk_edges=MTK_EDGES,
                    shrink_k: float = 20.0) -> DriftModel:
    """Fit the (band × bucket) ratio model with shrinkage toward band priors."""
    df = _ratios(panel)
    g_mean = float(df["ratio"].mean()) if len(df) else 1.0
    g_sd = float(df["ratio"].std(ddof=0)) if len(df) > 1 else 0.0
    band_prior = {}
    for band, grp in df.groupby("band"):
        band_prior[band] = (float(grp["ratio"].mean()),
                            float(grp["ratio"].std(ddof=0)) if len(grp) > 1 else g_sd)
    cells: Dict[Tuple[str, str], Tuple[float, float, int]] = {}
    for (band, bucket), grp in df.groupby(["band", "mtk_bucket"]):
        n = len(grp)
        raw_m = float(grp["ratio"].mean())
        raw_s = float(grp["ratio"].std(ddof=0)) if n > 1 else 0.0
        pm, ps = band_prior.get(band, (g_mean, g_sd))
        w = n / (n + shrink_k)
        cells[(band, bucket)] = (w * raw_m + (1 - w) * pm,
                                 w * raw_s + (1 - w) * ps, n)
    return DriftModel(cells=cells, band_prior=band_prior,
                      global_prior=(g_mean, g_sd), edges=tuple(mtk_edges))
