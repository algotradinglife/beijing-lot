"""Probability model: derive p3/p1/p0 from average European 1X2 odds.

The Limited Backtest does not have Pinnacle AH historical data so we cannot
run the full Skellam pipeline.  Instead we derive 1X2 probabilities directly
from the average-European 1X2 odds (de-vigged, proportional method), then
apply the spec §4.3 integer-line draw correction keyed on |handicap|.

This is intentionally a simplification — the spec's Phase 4a "Limited
Backtest with Proxies" track.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# Average European 1X2 books typically have 5-7% overround.  Proportional
# de-vig is fine here (margin is approximately equally distributed).

def devig_proportional(odds_h: float, odds_d: float, odds_a: float) -> tuple[float, float, float]:
    raw = np.array([1.0 / odds_h, 1.0 / odds_d, 1.0 / odds_a], dtype=float)
    return tuple(raw / raw.sum())  # type: ignore[return-value]


def apply_draw_correction(p3: float, p1: float, p0: float, abs_h: int) -> tuple[float, float, float]:
    """Apply spec §4.3 piecewise τ correction.

    The avg-European 1X2 implies probabilities for the *no-handicap* outcome
    (h=0).  When the 北单 line h=0 we still apply the +2pp draw boost
    (see spec: the underlying Dixon-Coles τ effect is independent of the
    handicap — it's about low-score draw correlation, which exists at h=0
    matches just as much).

    For |h| >= 2 the draw becomes "exact margin", τ effect washes out.
    """
    if abs_h <= 1:
        p1 += 0.020
        p3 -= 0.010
        p0 -= 0.010
    # else: no correction
    s = p3 + p1 + p0
    return p3 / s, p1 / s, p0 / s


@dataclass
class ModelProbs:
    p3: float
    p1: float
    p0: float


def model_probs_from_eu(
    avg_eu_home: float,
    avg_eu_draw: float,
    avg_eu_away: float,
    handicap: int,
    apply_correction: bool = True,
) -> ModelProbs:
    """Compute p3/p1/p0 *at the 北单 handicap* from avg-European 1X2 odds.

    A subtlety: avg_eu_* is for h=0 (the natural soccer 1X2 market).  When
    the 北单 handicap is non-zero we must shift outcome semantics.  Without
    a goal-difference distribution we cannot do this rigorously from 1X2
    alone.  The honest fallback is: USE the no-handicap 1X2 only when
    handicap == 0; for non-zero handicap the avg-European odds embed
    sportsbook-implied joint of (handicap_line × 1X2) only loosely.

    However, the SP that 500.com preserves IS the SP at the 北单 handicap
    line, with result_code in {3, 1, 0} also defined relative to the
    handicap.  So we need p_3, p_1, p_0 at the 北单 handicap line.

    Compromise (spec Phase 4a explicit choice): for non-zero handicap we
    use the avg-European 1X2 odds *as if* the handicap-shift had already
    been baked in (i.e. treat avg_eu_home as P(home covers) etc.).  This
    is roughly true because the European 1X2 books quote the un-handicapped
    1X2 — and the 北单 让球 is designed to balance the line so the
    handicap-shifted outcome roughly mirrors a fair coin.  This is
    obviously imperfect, hence the "Limited" label.
    """
    p3, p1, p0 = devig_proportional(avg_eu_home, avg_eu_draw, avg_eu_away)
    if apply_correction:
        p3, p1, p0 = apply_draw_correction(p3, p1, p0, abs(handicap))
    return ModelProbs(p3=p3, p1=p1, p0=p0)
