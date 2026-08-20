"""Budget-explicit settlement of nested distinct-ticket prefixes."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from .tickets import DistinctTicketStream

TICKET_STAKE_CNY = 2.0
PAYOUT_COEFFICIENT = 0.65


def settle_distinct_prefixes(
    stream: DistinctTicketStream,
    realized_outcomes: np.ndarray,
    winning_sp: np.ndarray,
    k_values: Iterable[int],
    *,
    stake_multipliers: np.ndarray | None = None,
    ticket_stake_cny: float = TICKET_STAKE_CNY,
    payout_coefficient: float = PAYOUT_COEFFICIENT,
) -> pd.DataFrame:
    """Settle common-stream K prefixes with the coefficient once per ticket.

    ``stake_multipliers`` is Stage 4's explicit R vector.  Proposal frequency
    never becomes stake implicitly.  The default therefore funds one CNY2 unit
    for each distinct ticket identity.
    """

    realized = np.asarray(realized_outcomes, dtype=int)
    sp = np.asarray(winning_sp, dtype=float)
    if realized.ndim != 1 or sp.shape != realized.shape:
        raise ValueError("realized outcomes and winning SP must be aligned vectors")
    if np.any((realized < 0) | (realized > 2)):
        raise ValueError("realized outcomes must use integer positions 0, 1 or 2")
    if ticket_stake_cny <= 0 or not 0 < payout_coefficient <= 1:
        raise ValueError("ticket stake and payout coefficient are invalid")
    requested = tuple(sorted(set(int(k) for k in k_values)))
    if not requested or requested[0] <= 0:
        raise ValueError("k_values must contain positive integers")

    unique_k = stream.unique_k
    if stake_multipliers is None:
        multipliers = np.ones(unique_k, dtype=float)
    else:
        multipliers = np.asarray(stake_multipliers, dtype=float)
        if multipliers.shape != (unique_k,):
            raise ValueError("stake multipliers must align with unique tickets")
        if np.any(~np.isfinite(multipliers)) or np.any(multipliers < 0):
            raise ValueError("stake multipliers must be finite and nonnegative")

    if unique_k:
        if stream.match_positions.max(initial=-1) >= len(realized):
            raise ValueError("ticket stream refers to an unknown match position")
        ticket_realized = realized[stream.match_positions]
        ticket_sp = sp[stream.match_positions]
        valid_sp = np.all(np.isfinite(ticket_sp) & (ticket_sp > 0), axis=1)
        hits = np.all(stream.outcome_positions == ticket_realized, axis=1) & valid_sp
        unit_stakes = ticket_stake_cny * multipliers
        gross = np.where(
            hits,
            unit_stakes * payout_coefficient * np.prod(ticket_sp, axis=1),
            0.0,
        )
        cumulative_stake = np.cumsum(unit_stakes)
        cumulative_gross = np.cumsum(gross)
        cumulative_hits = np.cumsum(hits.astype(int))
    else:
        cumulative_stake = cumulative_gross = np.array([], dtype=float)
        cumulative_hits = np.array([], dtype=int)

    rows: list[dict[str, float | int]] = []
    for k in requested:
        prefix = stream.prefix(k)
        effective_k = prefix.unique_k
        if effective_k:
            stake = float(cumulative_stake[effective_k - 1])
            gross = float(cumulative_gross[effective_k - 1])
            hit_count = int(cumulative_hits[effective_k - 1])
            funded = multipliers[:effective_k]
            funded_sum = funded.sum()
            shares = funded / funded_sum if funded_sum > 0 else np.zeros(effective_k)
            hhi = float(np.square(shares).sum()) if effective_k else 0.0
            ess = float(1.0 / hhi) if hhi > 0 else 0.0
        else:
            stake = gross = 0.0
            hit_count = 0
            hhi = ess = 0.0
        rows.append(
            {
                "requested_k": k,
                "effective_k": effective_k,
                "proposal_count": int(len(prefix.proposal_identity_indices)),
                "stake_cny": stake,
                "gross_return_cny": gross,
                "pnl_cny": gross - stake,
                "hit_count": hit_count,
                "hit_rate": hit_count / effective_k if effective_k else 0.0,
                "stake_hhi": hhi,
                "stake_ess": ess,
            }
        )
    return pd.DataFrame(rows)
