"""High-N coverage construction primitives (moonshot Track A).

A 北单 parlay ticket fixes one outcome per leg; the rake (RR=0.65) applies ONCE
per ticket to the product of the per-outcome winning SPs. "Covering" a leg means
buying every combination across the covered outcomes (a cartesian product of
tickets), so one ticket is guaranteed to match the realised outcomes iff every
covered set contains the realised outcome.

Key identity (proved in the EV decomposition):

    EV / budget = RR · ∏_i [ (Σ_{o∈C_i} p_o·sp_o) / |C_i| ]

For a FAIR market (p_o·sp_o = 1 for every outcome) this is exactly RR for ANY
coverage — covering raises P(hit) and reshapes the payoff, it does NOT beat the
−35% floor. Only a real per-leg edge (∏ selection > 1, Track B) can move EV.

Outcome index 0/1/2 ↔ result code '3'/'1'/'0' (home-hcp-win / draw / away-hcp-win).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Sequence, Tuple

RR = 0.65


def devig3(eu_h: float, eu_d: float, eu_a: float) -> Tuple[float, float, float]:
    """Proportional de-vig of 1X2 European odds → (p3, p1, p0)."""
    ih, idr, ia = 1.0 / eu_h, 1.0 / eu_d, 1.0 / eu_a
    s = ih + idr + ia
    return (ih / s, idr / s, ia / s)


@dataclass(frozen=True)
class Leg:
    probs: Tuple[float, float, float]   # market-implied P(outcome), index 0/1/2
    sps: Tuple[float, float, float]     # 北单 SP per outcome (gross decimal odds)


def parlay_ev_single(legs: Sequence[Leg], selections: Sequence[int]) -> float:
    """EV per yuan of a single-select parlay = RR · ∏ (p_sel · sp_sel)."""
    prod = 1.0
    for leg, sel in zip(legs, selections):
        prod *= leg.probs[sel] * leg.sps[sel]
    return RR * prod


def _validate_covered(legs: Sequence[Leg], covered: Sequence[Sequence[int]]) -> None:
    """Guard against the silent zip-truncation / bad-index footguns."""
    if len(covered) != len(legs):
        raise ValueError(f"covered has {len(covered)} sets for {len(legs)} legs")
    for i, C in enumerate(covered):
        if len(C) == 0:
            raise ValueError(f"leg {i}: covered set is empty")
        if any(o not in (0, 1, 2) for o in C):
            raise ValueError(f"leg {i}: outcome index out of range in {C}")
        if len(set(C)) != len(C):
            raise ValueError(f"leg {i}: duplicate outcome in {C}")


def config_metrics(legs: Sequence[Leg], covered: Sequence[Sequence[int]]) -> dict:
    """Analytic metrics for one coverage configuration.

    covered[i] = outcome indices bought on leg i (1..3 of them).
    Returns ticket count, P(parlay yields a winning ticket), and EV/budget.
    """
    _validate_covered(legs, covered)
    tickets = 1
    hit_prob = 1.0
    ev_num = 1.0   # ∏_i (Σ_{o∈C_i} p_o·sp_o)
    for leg, C in zip(legs, covered):
        tickets *= len(C)
        hit_prob *= sum(leg.probs[o] for o in C)
        ev_num *= sum(leg.probs[o] * leg.sps[o] for o in C)
    return dict(
        tickets=tickets,
        hit_prob=hit_prob,
        ev_per_budget=RR * ev_num / tickets,
        ev_numerator=ev_num,
    )


def simulate_config(legs: Sequence[Leg], covered: Sequence[Sequence[int]],
                    budget: float = 100.0, n_sims: int = 100000,
                    seed: int = 0, thresholds: Sequence[float] = ()) -> dict:
    """Monte-Carlo the realised payoff distribution for one config.

    Stakes the whole budget evenly across the cartesian-product tickets
    (stake_per_ticket = budget / tickets). Samples each leg's realised outcome
    from its market probs; the parlay wins iff every leg's outcome is covered,
    paying stake_per_ticket · ∏ sp_realised · RR on the single matching ticket.
    Deterministic per seed.
    """
    tickets = 1
    for C in covered:
        tickets *= len(C)
    spt = budget / tickets
    cov_sets = [set(C) for C in covered]
    rng = random.Random(seed)
    hits = 0
    payoffs: List[float] = []
    thr_counts = [0] * len(thresholds)
    total_return = 0.0
    for _ in range(n_sims):
        win = True
        mult = 1.0
        for leg, C in zip(legs, cov_sets):
            r = rng.random()
            o = 0 if r < leg.probs[0] else (1 if r < leg.probs[0] + leg.probs[1] else 2)
            if o not in C:
                win = False
                break
            mult *= leg.sps[o]
        payoff = spt * mult * RR if win else 0.0
        total_return += payoff
        if win:
            hits += 1
            payoffs.append(payoff)
            for i, t in enumerate(thresholds):
                if payoff >= t:
                    thr_counts[i] += 1
    payoffs.sort()
    median_jackpot = payoffs[len(payoffs) // 2] if payoffs else 0.0
    return dict(
        tickets=tickets,
        hit_rate=hits / n_sims,
        mean_roi=total_return / (n_sims * budget) - 1.0,
        median_jackpot=median_jackpot,
        max_jackpot=payoffs[-1] if payoffs else 0.0,
        p_threshold={t: thr_counts[i] / n_sims for i, t in enumerate(thresholds)},
        n_sims=n_sims,
    )


def _top_k_outcomes(probs: Tuple[float, float, float], k: int) -> frozenset:
    """The k highest-probability outcome indices (the ones you'd cover)."""
    return frozenset(sorted(range(3), key=lambda o: probs[o], reverse=True)[:k])


def simulate_strategy(pool: Sequence[Leg], n_legs: int, n_cover2: int = 0,
                      n_cover3: int = 0, budget: float = 1000.0,
                      n_sims: int = 200000, seed: int = 0,
                      thresholds: Sequence[float] = ()) -> dict:
    """Marginalise the moonshot over real leg draws. Each sim draws n_legs legs
    from `pool`, sorts by confidence (max prob), then by position:
      - most-confident (n_legs − n_cover2 − n_cover3): SINGLE the favourite,
      - next n_cover2: COVER the top-2 outcomes (drop the least likely),
      - least-confident n_cover3: COVER all 3.
    Budget is spread over the 2^n_cover2 · 3^n_cover3 cartesian tickets. The
    parlay wins iff every leg's realised outcome is in its covered set.
    Deterministic per seed.
    """
    if n_cover2 + n_cover3 > n_legs:
        raise ValueError("n_cover2 + n_cover3 exceeds n_legs")
    rng = random.Random(seed)
    tickets = (2 ** n_cover2) * (3 ** n_cover3)
    spt = budget / tickets
    n_single = n_legs - n_cover2 - n_cover3
    npool = len(pool)
    hits = 0
    total_return = 0.0
    payoffs: List[float] = []
    thr_counts = [0] * len(thresholds)
    for _ in range(n_sims):
        legs = [pool[i] for i in rng.sample(range(npool), n_legs)]
        legs.sort(key=lambda L: max(L.probs), reverse=True)  # confident first
        win = True
        mult = 1.0
        for j, L in enumerate(legs):
            r = rng.random()
            p0, p1 = L.probs[0], L.probs[1]
            o = 0 if r < p0 else (1 if r < p0 + p1 else 2)
            if j < n_single:                       # single: must hit favourite
                covered = {L.probs.index(max(L.probs))}
            elif j < n_single + n_cover2:          # cover top-2
                covered = _top_k_outcomes(L.probs, 2)
            else:                                  # cover all 3
                covered = {0, 1, 2}
            if o not in covered:
                win = False
                break
            mult *= L.sps[o]
        payoff = spt * mult * RR if win else 0.0
        total_return += payoff
        if win:
            hits += 1
            payoffs.append(payoff)
            for i, t in enumerate(thresholds):
                if payoff >= t:
                    thr_counts[i] += 1
    payoffs.sort()
    return dict(
        n_cover2=n_cover2,
        n_cover3=n_cover3,
        tickets=tickets,
        stake_per_ticket=spt,
        hit_rate=hits / n_sims,
        mean_roi=total_return / (n_sims * budget) - 1.0,
        median_jackpot=(payoffs[len(payoffs) // 2] if payoffs else 0.0),
        p95_jackpot=(payoffs[int(0.95 * len(payoffs))] if payoffs else 0.0),
        max_jackpot=(payoffs[-1] if payoffs else 0.0),
        p_threshold={t: thr_counts[i] / n_sims for i, t in enumerate(thresholds)},
        n_sims=n_sims,
    )
