"""Settlement-only joins for the frozen Issue #286 ticket manifest."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MatchSettlement:
    realized_outcome: str
    winning_sp: float


def settle_ticket_identity(
    identity: str,
    lookup: dict[str, MatchSettlement],
    *,
    ticket_stake_cny: float = 2.0,
    payout_coefficient: float = 0.65,
) -> dict[str, float | int | bool]:
    """Settle one complete unique ticket with 0.65 applied exactly once."""

    if ticket_stake_cny <= 0 or not 0 < payout_coefficient <= 1:
        raise ValueError("invalid ticket economics")
    legs = parse_ticket_identity(identity)
    settlements = [lookup.get(match_id) for match_id, _ in legs]
    valid = all(
        item is not None and np.isfinite(item.winning_sp) and item.winning_sp > 0
        for item in settlements
    )
    if not valid:
        return {
            "settlement_valid": False,
            "hit": 0,
            "stake_cny": 0.0,
            "gross_cny": 0.0,
            "pnl_cny": 0.0,
        }
    typed = [item for item in settlements if item is not None]
    hit = all(
        selected == item.realized_outcome
        for (_, selected), item in zip(legs, typed, strict=True)
    )
    gross = (
        ticket_stake_cny
        * payout_coefficient
        * float(np.prod([item.winning_sp for item in typed]))
        if hit
        else 0.0
    )
    return {
        "settlement_valid": True,
        "hit": int(hit),
        "stake_cny": ticket_stake_cny,
        "gross_cny": gross,
        "pnl_cny": gross - ticket_stake_cny,
    }


def parse_ticket_identity(identity: str) -> tuple[tuple[str, str], ...]:
    """Decode the manifest's canonical ``match:outcome|...`` identity."""

    if not identity:
        raise ValueError("ticket identity cannot be empty")
    legs = []
    for token in identity.split("|"):
        if ":" not in token:
            raise ValueError(f"invalid ticket leg: {token}")
        match_id, outcome = token.rsplit(":", 1)
        if not match_id or outcome not in {"3", "1", "0"}:
            raise ValueError(f"invalid ticket leg: {token}")
        legs.append((match_id, outcome))
    match_ids = [match_id for match_id, _ in legs]
    if len(set(match_ids)) != len(match_ids):
        raise ValueError("ticket identity contains duplicate matches")
    return tuple(legs)
