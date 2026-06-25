"""Track B P2 — pure scoring metrics for the beat-the-closing-line test. TDD'd.

A prediction is a (p3, p1, p0) tuple over result codes '3'/'1'/'0'. The benchmark
is the bookmaker closing consensus; the model must beat its OOS log-loss to have
any signal beyond the market.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

CODES = ("3", "1", "0")          # index 0/1/2
Prob = Tuple[float, float, float]


def _clip(p: float, eps: float = 1e-15) -> float:
    return min(max(p, eps), 1.0 - eps)


def multiclass_log_loss(probs: Sequence[Prob], labels: Sequence[str],
                        eps: float = 1e-15) -> float:
    """Mean −log(p_trueclass). Lower is better."""
    tot, n = 0.0, 0
    for p, y in zip(probs, labels):
        tot += -math.log(_clip(p[CODES.index(y)], eps))
        n += 1
    return tot / n if n else float("nan")


def multiclass_brier(probs: Sequence[Prob], labels: Sequence[str]) -> float:
    """Mean over samples of Σ_k (p_k − 1[y=k])². Lower is better."""
    tot, n = 0.0, 0
    for p, y in zip(probs, labels):
        tot += sum((p[k] - (1.0 if y == c else 0.0)) ** 2 for k, c in enumerate(CODES))
        n += 1
    return tot / n if n else float("nan")


def accuracy(probs: Sequence[Prob], labels: Sequence[str]) -> float:
    """Argmax accuracy."""
    ok, n = 0, 0
    for p, y in zip(probs, labels):
        pred = CODES[max(range(3), key=lambda k: p[k])]
        ok += int(pred == y)
        n += 1
    return ok / n if n else float("nan")


def divergence_lift(p_hat: Sequence[Prob], p_close: Sequence[Prob],
                    labels: Sequence[str], outcome_idx: int,
                    edges: Sequence[float]) -> List[dict]:
    """CLV-style: bucket the model's divergence (p_hat − p_close) for one outcome;
    per bucket report n, mean divergence, mean p_close, realized rate. If the model
    has signal beyond the close, buckets with positive divergence should realize
    ABOVE their p_close (and negative buckets below)."""
    code = CODES[outcome_idx]
    diffs = [(ph[outcome_idx] - pc[outcome_idx], pc[outcome_idx], y == code)
             for ph, pc, y in zip(p_hat, p_close, labels)]
    out = []
    for lo, hi in zip(edges, edges[1:]):
        sel = [d for d in diffs if d[0] >= lo and (d[0] < hi or hi == edges[-1])]
        if sel:
            n = len(sel)
            out.append(dict(lo=lo, hi=hi, n=n,
                            mean_div=sum(d[0] for d in sel) / n,
                            mean_p_close=sum(d[1] for d in sel) / n,
                            realized=sum(1 for d in sel if d[2]) / n))
        else:
            out.append(dict(lo=lo, hi=hi, n=0, mean_div=float("nan"),
                            mean_p_close=float("nan"), realized=float("nan")))
    return out
