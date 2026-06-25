"""Track B — pure odds/parse helpers (no I/O). TDD'd in tests/track_b/test_odds.py.

Outcome index 0/1/2 ↔ 北单 result code '3'/'1'/'0' (home-hcp-win / draw / away).
Asian-handicap prices in the collector are Hong Kong odds (net return per 1 stake),
so decimal = hk + 1.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

# 胜负 (北单 让球 result) -> result code
_WL = {"胜": "3", "平": "1", "负": "0"}


def result_code(wl: Optional[str]) -> Optional[str]:
    """'胜'/'平'/'负' -> '3'/'1'/'0'; anything else -> None."""
    if wl is None:
        return None
    return _WL.get(str(wl).strip())


def parse_rank(s) -> Optional[int]:
    """'[3]' -> 3, '[]'/None/'-' -> None."""
    if s is None:
        return None
    t = str(s).strip().lstrip("[").rstrip("]").strip()
    try:
        return int(t)
    except (ValueError, TypeError):
        return None


def devig3(h: float, d: float, a: float) -> Tuple[float, float, float]:
    """Proportional de-vig of 1X2 decimal odds -> (p3, p1, p0)."""
    ih, idr, ia = 1.0 / h, 1.0 / d, 1.0 / a
    s = ih + idr + ia
    return (ih / s, idr / s, ia / s)


def asian_devig(home_hk: float, away_hk: float) -> Tuple[float, float]:
    """Two-way Asian-handicap Hong-Kong odds -> (p_home_cover, p_away_cover),
    proportional de-vig. decimal = hk + 1."""
    dh, da = home_hk + 1.0, away_hk + 1.0
    ih, ia = 1.0 / dh, 1.0 / da
    s = ih + ia
    return (ih / s, ia / s)


def consensus_mean(vals: Sequence[Optional[float]]) -> Optional[float]:
    """Mean over the non-None values; None if all missing."""
    xs = [float(v) for v in vals if v is not None and _is_num(v)]
    return sum(xs) / len(xs) if xs else None


def _is_num(v) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False


def valid_odds(*vals) -> bool:
    """All present, numeric, > 1.0 (decimal sanity for 1X2)."""
    return all(v is not None and _is_num(v) and float(v) > 1.0 for v in vals)
