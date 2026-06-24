"""Uncertainty quantification for the N walk-forward (A1).

N is a structural choice, not a fitted parameter, so the "walk-forward" test is
out-of-time realized performance + per-period stability + bootstrap CI, NOT a
train/test parameter search. With only ~16 live weeks and hits concentrated in a
handful of weeks, per-N ROI is dominated by a few wins (the N=5 "sweet spot"
artifact). These helpers quantify that fragility honestly.

A `week` is an (issue, stake, pnl) triple — the shape replay_policy rolls.
All functions are pure and deterministic (seeded RNG).
"""
from __future__ import annotations

import random
from typing import List, Tuple

Week = Tuple[str, float, float]


def total_roi(weeks: List[Week]) -> float:
    """Σpnl / Σstake over the weeks; nan if no stake."""
    stake = sum(w[1] for w in weeks)
    pnl = sum(w[2] for w in weeks)
    return pnl / stake if stake else float("nan")


def weekly_roi(weeks: List[Week]) -> List[Tuple[str, float]]:
    """Per-week (issue, roi)."""
    return [(w[0], (w[2] / w[1] if w[1] else float("nan"))) for w in weeks]


def bootstrap_roi_ci(weeks: List[Week], n_boot: int = 10000, seed: int = 0,
                     alpha: float = 0.05) -> dict:
    """Block bootstrap over weeks: resample whole weeks with replacement (weeks
    are the independent unit — tickets within a week share legs), recompute ROI,
    return the (alpha/2, 1-alpha/2) percentile interval. Deterministic per seed.
    """
    n = len(weeks)
    rng = random.Random(seed)
    rois: List[float] = []
    for _ in range(n_boot):
        s = p = 0.0
        for _ in range(n):
            _i, st, pn = weeks[rng.randrange(n)]
            s += st
            p += pn
        if s:
            rois.append(p / s)
    rois.sort()
    m = len(rois)
    lo = rois[int((alpha / 2) * m)] if m else float("nan")
    hi = rois[min(m - 1, int((1 - alpha / 2) * m))] if m else float("nan")
    mean = sum(rois) / m if m else float("nan")
    median = rois[m // 2] if m else float("nan")
    p_positive = sum(1 for r in rois if r > 0) / m if m else float("nan")
    return dict(lo=lo, hi=hi, mean=mean, median=median, p_positive=p_positive,
                point=total_roi(weeks), n_boot=m)


def leave_one_week_out(weeks: List[Week]) -> dict:
    """Jackknife fragility: ROI with each single week removed. Reveals how much
    one week (a few hits) drives the headline ROI."""
    base = total_roi(weeks)
    per_week = []
    for i in range(len(weeks)):
        rest = weeks[:i] + weeks[i + 1:]
        per_week.append((weeks[i][0], total_roi(rest)))
    swings = [(iss, roi - base) for iss, roi in per_week]
    return dict(
        base=base,
        per_week=per_week,
        max_drop=min(swings, key=lambda x: x[1]),   # removing this week drops ROI most
        max_rise=max(swings, key=lambda x: x[1]),   # removing this week raises ROI most
    )
