"""Track B P1 — benchmark calibration helpers (pure). TDD'd.

The closing-consensus de-vigged prob is our 'beat-this' benchmark. Before trusting
it we check it's calibrated against realised outcomes (the O5 discipline: on
handicap_line=0 the straight 1X2 prob ↔ 北单 让球 result, so calibration must hold
there; mismatched-line handicap matches need supremacy conversion — deferred).
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

Pair = Tuple[float, bool]   # (predicted prob, outcome happened)


def calibration_table(pairs: Sequence[Pair], edges: Sequence[float]) -> List[dict]:
    """Bucket (prob, hit) pairs by prob into [edges[i], edges[i+1]); per bucket
    return n, mean predicted prob, realised hit rate."""
    out = []
    for lo, hi in zip(edges, edges[1:]):
        sel = [(p, h) for p, h in pairs if (p >= lo and (p < hi or hi == edges[-1]))]
        if sel:
            n = len(sel)
            out.append(dict(lo=lo, hi=hi, n=n,
                            mean_p=sum(p for p, _ in sel) / n,
                            hit_rate=sum(1 for _, h in sel if h) / n))
        else:
            out.append(dict(lo=lo, hi=hi, n=0, mean_p=float("nan"), hit_rate=float("nan")))
    return out


def max_calibration_gap(table: Sequence[dict], min_n: int = 30) -> float:
    """Largest |mean_p − hit_rate| over buckets with at least min_n samples."""
    gaps = [abs(b["mean_p"] - b["hit_rate"]) for b in table if b["n"] >= min_n]
    return max(gaps) if gaps else float("nan")


def brier(pairs: Sequence[Pair]) -> float:
    """Mean squared error of the probabilistic prediction."""
    if not pairs:
        return float("nan")
    return sum((p - (1.0 if h else 0.0)) ** 2 for p, h in pairs) / len(pairs)
