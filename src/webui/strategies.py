"""Canonical strategy registry for the webui.

Each strategy = a fixed parameter tuple (mix weights, per-N Kelly, per-N
lambda, max_combos, league_q_min). Plans get tagged with an ID + name at
generation time, so the history page can show "which strategy ran last
week" without rebuilding the params from JSON.

These mirror the presets shown in templates/strategy_explorer.html. If
you add a new preset there, add it here too.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class Strategy:
    sid: str           # short id, e.g. "S1"
    name: str          # human-readable Chinese name
    # cfg arrays are [N=2, N=3, N=4, N=5]
    weights: Tuple[float, float, float, float]
    kelly: Tuple[float, float, float, float]
    lambdas: Tuple[float, float, float, float]
    max_combos: int
    league_q_min: float = 0.0
    cross_n_lambda: float = 0.0  # cross-tier diversity penalty (0 = disabled)


REGISTRY: Dict[str, Strategy] = {
    s.sid: s for s in [
        Strategy("S1", "稳健",
                 weights=(0.30, 0.40, 0.30, 0),
                 kelly=(0.03125, 0.03125, 0.03125, 0.125),
                 lambdas=(0, 0, 0, 0), max_combos=200),
        Strategy("S2", "高 Sharpe N=5",
                 weights=(0, 0, 0, 1),
                 kelly=(0.0625, 0.125, 0.0625, 0.125),
                 lambdas=(0, 0, 0.5, 0), max_combos=100, league_q_min=0.65),
        Strategy("S3", "Sharpe 优先",
                 weights=(0.20, 0.20, 0.60, 0),
                 kelly=(0.25, 0.25, 0.25, 0.125),
                 lambdas=(0, 0, 0.5, 0), max_combos=100),
        Strategy("S4", "平衡",
                 weights=(0, 0.50, 0.50, 0),
                 kelly=(0.0625, 0.125, 0.25, 0.125),
                 lambdas=(0, 0, 0.5, 0), max_combos=100),
        Strategy("S5", "Calmar 王",
                 weights=(0.20, 0.20, 0.60, 0),
                 kelly=(0.25, 0.125, 0.125, 0.125),
                 lambdas=(0, 0, 0.5, 0), max_combos=150),
        Strategy("S6", "激进",
                 weights=(0.20, 0.20, 0.60, 0),
                 kelly=(0.25, 0.125, 0.125, 0.125),
                 lambdas=(0, 0, 0.5, 0), max_combos=200),
        Strategy("S7", "纯 N=3 高 Calmar",
                 weights=(0, 1, 0, 0),
                 kelly=(0.0625, 0.125, 0.0625, 0.125),
                 lambdas=(0, 0, 0.5, 0), max_combos=150),
        Strategy("S8", "满杠杆",
                 weights=(0, 0.50, 0.50, 0),
                 kelly=(0.0625, 0.125, 0.25, 0.125),
                 lambdas=(0, 0, 0.5, 0), max_combos=200),
        Strategy("S9", "跨N多样化",
                 weights=(0.30, 0.40, 0.30, 0),
                 kelly=(0.03125, 0.03125, 0.03125, 0.125),
                 lambdas=(0, 0, 0, 0), max_combos=200,
                 cross_n_lambda=0.5),
    ]
}


def _approx_eq(a, b, tol: float = 1e-3) -> bool:
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return a == b


def match_strategy(*, weights, kelly, lambdas, max_combos: int,
                   league_q_min: float = 0.0,
                   cross_n_lambda: float = 0.0) -> Tuple[str, str]:
    """Return (sid, name) of the matching preset, or a synthetic
    descriptive label when params don't match any preset.

    Kelly/λ for N's with weight=0 are not compared (those params
    are dead — they don't affect plan generation).
    """
    for s in REGISTRY.values():
        if not all(_approx_eq(weights[i], s.weights[i]) for i in range(4)):
            continue
        active = [i for i in range(4) if s.weights[i] > 0]
        if (all(_approx_eq(kelly[i], s.kelly[i]) for i in active)
            and all(_approx_eq(lambdas[i], s.lambdas[i]) for i in active)
            and int(max_combos) == s.max_combos
            and _approx_eq(league_q_min, s.league_q_min)
            and _approx_eq(cross_n_lambda, s.cross_n_lambda)):
            return s.sid, s.name
    return "custom", _describe(weights, kelly, lambdas, max_combos, league_q_min,
                               cross_n_lambda)


def _describe(weights, kelly, lambdas, max_combos, league_q_min,
              cross_n_lambda: float = 0.0) -> str:
    """One-line summary for non-preset params, e.g.
    `Mix 30/40/30/0 K=1/32 max=200`. Used when no preset matches."""
    w = "/".join(f"{int(round(weights[i]*100))}" for i in range(4))
    active_k = [kelly[i] for i in range(4) if weights[i] > 0]
    if active_k and all(_approx_eq(k, active_k[0]) for k in active_k):
        k_str = f"K={_kelly_to_frac(active_k[0])}"
    else:
        k_str = "K=" + ",".join(_kelly_to_frac(kelly[i]) for i in range(4)
                                if weights[i] > 0)
    parts = [f"Mix {w}", k_str, f"max={int(max_combos)}"]
    if league_q_min and league_q_min > 0:
        parts.append(f"q≥{league_q_min:g}")
    if cross_n_lambda and cross_n_lambda > 0:
        parts.append(f"CλN={cross_n_lambda:g}")
    return " ".join(parts)


_KELLY_FRACS = [(1, 1), (1, 2), (1, 4), (1, 8), (1, 16), (1, 32), (1, 64)]


def _kelly_to_frac(k) -> str:
    try:
        kf = float(k)
    except (TypeError, ValueError):
        return str(k)
    if kf <= 0:
        return "0"
    for num, den in _KELLY_FRACS:
        if abs(kf - num / den) < 1e-4:
            return f"{num}/{den}"
    return f"{kf:.3g}"


def lookup(sid: str) -> Optional[Strategy]:
    return REGISTRY.get(sid)
