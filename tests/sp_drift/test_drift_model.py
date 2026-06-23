"""P1: fit a drift model of ratio=final_sp/decision_sp by (SP-band × MTK-bucket).

Trains on ALL legs/snapshots (not just winners → no survivorship): every
snapshot at MTK m with SP s contributes ratio = final_sp/s to the cell
(band(s), bucket(m)). Small cells shrink toward the band-level prior.
"""
from __future__ import annotations

import pandas as pd

from src.sp_drift.drift_model import MTK_EDGES, fit_drift_model


def _panel(rows):
    return pd.DataFrame(rows, columns=["match_id", "selection", "sp", "mtk"])


def test_cell_estimates_mean_ratio_and_n():
    # 30 legs, each 2 snapshots: decision sp=4.0 @ mtk=1000 (12-24h bucket),
    # close sp=3.2 @ mtk=10. final_sp = closing sp = 3.2 → decision ratio 0.8.
    rows = []
    for i in range(30):
        rows.append((f"M{i}", "3", 4.0, 1000.0))
        rows.append((f"M{i}", "3", 3.2, 10.0))
    model = fit_drift_model(_panel(rows))
    mean, sd, n = model.lookup(4.0, 1000.0)      # band 3.5-4.5, 12-24h cell
    assert abs(mean - 0.8) < 0.03
    assert n == 30


def test_small_cell_shrinks_toward_band_prior():
    # Band 3.5-4.5 prior is dominated by a big 12-24h cell at ratio ~0.8.
    # A tiny 6-12h cell (n=2) at an extreme ratio must be pulled toward 0.8.
    rows = []
    for i in range(200):                          # big cell, ratio 0.8
        rows.append((f"A{i}", "3", 4.0, 1000.0))
        rows.append((f"A{i}", "3", 3.2, 10.0))
    for i in range(2):                            # tiny cell, ratio 0.3 (extreme)
        rows.append((f"B{i}", "3", 4.0, 500.0))   # 6-12h bucket
        rows.append((f"B{i}", "3", 1.2, 10.0))
    model = fit_drift_model(_panel(rows), shrink_k=20.0)
    raw = 1.2 / 4.0                               # 0.3
    mean, sd, n = model.lookup(4.0, 500.0)
    assert n == 2
    assert mean > raw + 0.1                        # shrunk well above 0.3
    assert mean < 0.8                              # but below the prior


def test_missing_cell_falls_back_to_prior():
    rows = []
    for i in range(30):
        rows.append((f"M{i}", "3", 4.0, 1000.0))
        rows.append((f"M{i}", "3", 3.2, 10.0))
    model = fit_drift_model(_panel(rows))
    # an SP band with no data → global/band prior, finite, no crash
    mean, sd, n = model.lookup(10.0, 1000.0)       # band >8, unseen
    assert n == 0
    assert mean > 0


def test_deterministic():
    rows = []
    for i in range(50):
        rows.append((f"M{i}", "3", 4.5, 800.0))
        rows.append((f"M{i}", "3", 3.6, 5.0))
    m1 = fit_drift_model(_panel(rows)).table().to_csv(index=False)
    m2 = fit_drift_model(_panel(rows)).table().to_csv(index=False)
    assert m1 == m2


# ---- P2: conservative-quantile SP adjustment ----
from src.sp_drift.drift_model import DriftModel


def _model(cells):
    # cells: {(band,bucket):(mean,sd,n)}; priors = first cell's (mean,sd)
    any_ms = next(iter(cells.values()))[:2]
    bands = {b: (m, s) for (b, _k), (m, s, _n) in cells.items()}
    return DriftModel(cells=cells, band_prior=bands, global_prior=any_ms)


def test_adjusted_sp_q50_recovers_mean_point_estimate():
    m = _model({("3.5-4.5", "720-1440"): (0.9, 0.3, 100)})
    # q=0.5 → ratio = mean → adjusted_sp = sp*mean
    assert abs(m.adjusted_sp(4.0, 1000.0, q=0.5) - 4.0 * 0.9) < 1e-6


def test_lower_quantile_is_more_conservative():
    m = _model({("3.5-4.5", "720-1440"): (0.9, 0.3, 100)})
    q50 = m.adjusted_sp(4.0, 1000.0, q=0.5)
    q25 = m.adjusted_sp(4.0, 1000.0, q=0.25)
    assert q25 < q50                      # conservative = lower SP


def test_wider_sd_gives_bigger_haircut():
    tight = _model({("3.5-4.5", "720-1440"): (0.9, 0.1, 100)})
    wide = _model({("3.5-4.5", "720-1440"): (0.9, 0.5, 100)})
    # same mean, same q<0.5 → wider sd → lower (more haircut)
    assert wide.adjusted_sp(4.0, 1000.0, q=0.25) < tight.adjusted_sp(4.0, 1000.0, q=0.25)


def test_adjusted_sp_floored_positive():
    # extreme: mean 0.17, big sd → q=0.05 must stay positive, not negative
    m = _model({(">8", "1440-inf"): (0.17, 0.21, 100)})
    v = m.adjusted_sp(10.0, 2000.0, q=0.05)
    assert v > 0
