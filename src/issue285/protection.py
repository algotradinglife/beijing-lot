"""Ticket-level miss distance and pre-event protection construction."""

from __future__ import annotations

import hashlib
import itertools
from collections.abc import Iterable

import numpy as np

PROTECTION_RULES = (
    "LOW_SELECTED_PROBABILITY",
    "ADVERSE_SIGNED_DIVERGENCE",
    "HIGH_ENTROPY",
    "LOW_MODEL_MARGIN",
    "RANDOM_BUDGET_CONTROL",
)
PROTECTION_STRUCTURES = ("SINGLE_FLIP", "FULL_CARTESIAN")


def ticket_miss_distance(
    ticket_outcomes: np.ndarray, realized_outcomes: np.ndarray
) -> np.ndarray:
    """Return Hamming distance from every ticket to the realized outcome code."""
    tickets = np.asarray(ticket_outcomes, dtype=int)
    realized = np.asarray(realized_outcomes, dtype=int)
    if tickets.ndim != 2 or realized.shape != (tickets.shape[1],):
        raise ValueError("tickets and realized outcomes must align on N legs")
    return np.count_nonzero(tickets != realized[None, :], axis=1)


def protect_ticket_portfolio(
    base_tickets: np.ndarray,
    *,
    probability: np.ndarray,
    divergence: np.ndarray,
    proposal_surface: np.ndarray,
    rule: str,
    protected_legs: int,
    alternative_depth: int,
    structure: str,
    seed: int,
) -> np.ndarray:
    """Add protection tickets and deduplicate the complete fixed-subset portfolio."""
    tickets = np.asarray(base_tickets, dtype=int)
    probability = np.asarray(probability, dtype=float)
    divergence = np.asarray(divergence, dtype=float)
    proposal = np.asarray(proposal_surface, dtype=float)
    if tickets.ndim != 2:
        raise ValueError("base tickets must have shape (K, N)")
    n = tickets.shape[1]
    if probability.shape != (n, 3) or divergence.shape != probability.shape:
        raise ValueError("probability and divergence must have shape (N, 3)")
    if proposal.shape != probability.shape:
        raise ValueError("proposal surface must align with probability")
    if rule not in PROTECTION_RULES:
        raise ValueError(f"unsupported protection rule: {rule}")
    if structure not in PROTECTION_STRUCTURES:
        raise ValueError(f"unsupported protection structure: {structure}")
    if not 1 <= protected_legs <= n:
        raise ValueError("protected legs must be inside [1, N]")
    if alternative_depth not in (1, 2):
        raise ValueError("alternative depth must be 1 or 2")

    protected: set[tuple[int, ...]] = {tuple(row) for row in tickets}
    entropy = -np.sum(
        np.where(probability > 0, probability * np.log(probability), 0.0), axis=1
    )
    for ticket_index, ticket in enumerate(tickets):
        legs = _rank_protected_legs(
            ticket,
            probability=probability,
            divergence=divergence,
            proposal_surface=proposal,
            entropy=entropy,
            rule=rule,
            seed=derived_ticket_seed(seed, ticket_index, tuple(ticket)),
        )[:protected_legs]
        alternatives = {
            int(leg): _rank_alternatives(
                proposal[int(leg)], selected=int(ticket[int(leg)])
            )[:alternative_depth]
            for leg in legs
        }
        if structure == "SINGLE_FLIP":
            for leg, outcomes in alternatives.items():
                for outcome in outcomes:
                    replacement = ticket.copy()
                    replacement[leg] = outcome
                    protected.add(tuple(int(value) for value in replacement))
        else:
            choices = []
            for leg in range(n):
                if leg in alternatives:
                    choices.append((int(ticket[leg]), *alternatives[leg]))
                else:
                    choices.append((int(ticket[leg]),))
            protected.update(itertools.product(*choices))
    return np.array(sorted(protected), dtype=int)


def chosen_protected_legs(
    ticket: np.ndarray,
    *,
    probability: np.ndarray,
    divergence: np.ndarray,
    proposal_surface: np.ndarray,
    rule: str,
    protected_legs: int,
    seed: int,
) -> np.ndarray:
    """Expose the pre-event leg decision for attribution and tests."""
    probability = np.asarray(probability, dtype=float)
    entropy = -np.sum(
        np.where(probability > 0, probability * np.log(probability), 0.0), axis=1
    )
    ranked = _rank_protected_legs(
        np.asarray(ticket, dtype=int),
        probability=probability,
        divergence=np.asarray(divergence, dtype=float),
        proposal_surface=np.asarray(proposal_surface, dtype=float),
        entropy=entropy,
        rule=rule,
        seed=seed,
    )
    return ranked[:protected_legs]


def ranked_alternative_outcomes(
    proposal_row: Iterable[float], *, selected: int
) -> tuple[int, ...]:
    return _rank_alternatives(np.asarray(tuple(proposal_row), dtype=float), selected)


def settle_unique_ticket_portfolio(
    tickets: np.ndarray,
    *,
    realized_outcomes: np.ndarray,
    winning_sp: np.ndarray,
    ticket_stake_cny: float = 2.0,
    payout_coefficient: float = 0.65,
) -> dict[str, float | int]:
    """Settle unique fixed-subset tickets with 0.65 once per winning N-fold."""
    unique = np.unique(np.asarray(tickets, dtype=int), axis=0)
    realized = np.asarray(realized_outcomes, dtype=int)
    sp = np.asarray(winning_sp, dtype=float)
    if unique.ndim != 2 or realized.shape != (unique.shape[1],):
        raise ValueError("ticket portfolio and realized outcomes must align")
    if sp.shape != realized.shape or not np.isfinite(sp).all():
        raise ValueError("winning SP must be finite and align with N legs")
    winners = np.all(unique == realized[None, :], axis=1)
    hit_count = int(winners.sum())
    stake = ticket_stake_cny * len(unique)
    gross = (
        ticket_stake_cny
        * payout_coefficient
        * float(np.prod(sp))
        * hit_count
    )
    return {
        "unique_tickets": len(unique),
        "hit_count": hit_count,
        "stake_cny": stake,
        "gross_cny": gross,
        "pnl_cny": gross - stake,
    }


def _rank_protected_legs(
    ticket: np.ndarray,
    *,
    probability: np.ndarray,
    divergence: np.ndarray,
    proposal_surface: np.ndarray,
    entropy: np.ndarray,
    rule: str,
    seed: int,
) -> np.ndarray:
    legs = np.arange(len(ticket), dtype=int)
    selected_probability = probability[legs, ticket]
    selected_divergence = divergence[legs, ticket]
    selected_proposal = proposal_surface[legs, ticket]
    alternative_best = np.array(
        [
            np.max(np.delete(proposal_surface[leg], int(ticket[leg])))
            for leg in legs
        ]
    )
    margin = selected_proposal - alternative_best
    if rule == "LOW_SELECTED_PROBABILITY":
        score = selected_probability
        return legs[np.argsort(score, kind="stable")]
    if rule == "ADVERSE_SIGNED_DIVERGENCE":
        return legs[np.argsort(selected_divergence, kind="stable")]
    if rule == "HIGH_ENTROPY":
        return legs[np.argsort(-entropy, kind="stable")]
    if rule == "LOW_MODEL_MARGIN":
        return legs[np.argsort(margin, kind="stable")]
    if rule == "RANDOM_BUDGET_CONTROL":
        return np.random.default_rng(seed).permutation(legs)
    raise ValueError(f"unsupported protection rule: {rule}")


def _rank_alternatives(proposal_row: np.ndarray, selected: int) -> tuple[int, ...]:
    if proposal_row.shape != (3,) or selected not in (0, 1, 2):
        raise ValueError("proposal row must contain three outcomes")
    candidates = [outcome for outcome in range(3) if outcome != selected]
    return tuple(
        sorted(candidates, key=lambda outcome: (-proposal_row[outcome], outcome))
    )


def derived_ticket_seed(seed: int, ticket_index: int, ticket: tuple[int, ...]) -> int:
    payload = f"{seed}|{ticket_index}|{','.join(map(str, ticket))}"
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big")
