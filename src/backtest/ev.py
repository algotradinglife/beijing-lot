"""EV calculation using a proxy SP derived from avg-European odds.

Two flavours are supported:

* ``naive`` — proxy SP = avg_eu_odds × (0.65 / 0.95) i.e. just rescale by
  the return-rate ratio (北单 returns 65%, avg-European book returns ~95%).
  This is the simplest possible proxy and is mathematically the SP that
  would result if the 北单 pool perfectly mirrored the avg-European
  market and only the house cut differed.

* ``empirical`` — fit a per-result-code linear regression on the historical
  data (winning-side SP ~ avg_eu_winning_odds) and predict SP from that.
  This bakes in any systematic 北单-vs-EU pricing bias that exists in the
  historical sample.

Both flavours are then passed into ``ev_from_proxy_sp`` to compute the
model EV per outcome.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 北单 return-rate / typical avg-EU book return-rate.
RETURN_RATE_RATIO_NAIVE = 0.65 / 0.95


def naive_proxy_sp(avg_eu_odds: float) -> float:
    """SP if 北单 pool mirrors avg-EU market exactly, only house cut differs."""
    return float(avg_eu_odds) * RETURN_RATE_RATIO_NAIVE


@dataclass
class EmpiricalSPModel:
    """Per-result-code linear fit: sp = a + b * eu_odds, with simple OLS."""
    coefs: dict[str, tuple[float, float]]  # result_code -> (a, b)

    def predict(self, eu_odds: float, result_code: str) -> float:
        a, b = self.coefs.get(result_code, (0.0, RETURN_RATE_RATIO_NAIVE))
        return a + b * eu_odds


def fit_empirical_sp_model(
    eu_odds: np.ndarray, sp: np.ndarray, result_codes: np.ndarray
) -> EmpiricalSPModel:
    """Fit a per-result-code OLS of winning-SP on winning-side EU odds.

    Drops NaNs.  Falls back to naive ratio if fewer than 30 samples in a code.
    """
    coefs: dict[str, tuple[float, float]] = {}
    for code in ("3", "1", "0"):
        mask = (result_codes == code) & np.isfinite(eu_odds) & np.isfinite(sp)
        if mask.sum() < 30:
            coefs[code] = (0.0, RETURN_RATE_RATIO_NAIVE)
            continue
        x = eu_odds[mask]
        y = sp[mask]
        # OLS slope/intercept
        b, a = np.polyfit(x, y, 1)
        coefs[code] = (float(a), float(b))
    return EmpiricalSPModel(coefs=coefs)


def model_ev(p: float, proxy_sp: float, return_rate: float = 0.65) -> float:
    """Model EV per yuan staked given probability p and *raw* SP.

    Payout per winning yuan = SP × return_rate.  EV = p × SP × return_rate.
    """
    return p * proxy_sp * return_rate
