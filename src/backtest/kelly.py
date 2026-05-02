"""Quarter-Kelly stake sizing per spec §4.4.

In 北单, the *gross payout multiplier* per yuan of stake is SP × 0.65,
not SP itself.  Define the effective decimal odds o_eff = SP × 0.65.
Then standard Kelly applies in the o_eff metric:

    edge   = p × o_eff − 1
    f_kelly = edge / (o_eff − 1)
    f_actual = 0.25 × f_kelly
    stake   = min(f_actual × bankroll, 0.05 × bankroll)
"""
from __future__ import annotations

RETURN_RATE = 0.65


def quarter_kelly_stake(
    p: float,
    sp: float,
    bankroll: float,
    fraction: float = 0.25,
    cap_per_match: float = 0.05,
) -> float:
    """Return stake in bankroll units (or 0 if no edge / no payout)."""
    o_eff = sp * RETURN_RATE
    if o_eff <= 1.0:
        return 0.0
    edge = p * o_eff - 1.0
    if edge <= 0:
        return 0.0
    f_kelly = edge / (o_eff - 1.0)
    f_actual = fraction * f_kelly
    stake = min(f_actual * bankroll, cap_per_match * bankroll)
    return max(stake, 0.0)


def realised_pnl(stake: float, sp: float, won: bool) -> float:
    """Profit (in bankroll units) for a settled bet.

    Win: stake × (SP × 0.65 − 1)
    Loss: -stake
    """
    if stake <= 0:
        return 0.0
    if won:
        return stake * (sp * RETURN_RATE - 1.0)
    return -stake
