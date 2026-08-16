"""Issue #232 — the single causal availability gate (R2 fresh).

EV C1 (R1): recovery/waterfall/modelability checked ``observed_at <=
decision_epoch`` but NOT ``decision_epoch <= kickoff``; 365/741 published
matches were post-kickoff.  R2 removes every module-local gate: all causal
decisions flow through ``causal_available`` here, and the verifier
recomputes it from raw upstream columns.

Rule (frozen, contract):
    source present AND observed_at notna
    AND observed_at <= decision_epoch
    AND decision_epoch <= kickoff
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def causal_available(
    observed_at: pd.Series | np.ndarray,
    decision_epoch: pd.Series | np.ndarray,
    kickoff: pd.Series | np.ndarray,
) -> pd.Series:
    """Boolean causal availability for aligned series (fail-closed).

    Missing observation, missing epoch, missing kickoff, observation after
    the decision epoch, or a decision epoch after kickoff all return False.
    """
    observed = pd.to_datetime(pd.Series(observed_at), errors="coerce", utc=True)
    epoch = pd.to_datetime(pd.Series(decision_epoch), errors="coerce", utc=True)
    kick = pd.to_datetime(pd.Series(kickoff), errors="coerce", utc=True)
    return (
        observed.notna()
        & epoch.notna()
        & kick.notna()
        & observed.le(epoch)
        & epoch.le(kick)
    )


def causal_available_frame(
    frame: pd.DataFrame,
    observed_col: str,
    epoch_col: str,
    kickoff_col: str,
) -> pd.Series:
    """Column-named convenience wrapper over :func:`causal_available`."""
    return causal_available(
        frame[observed_col], frame[epoch_col], frame[kickoff_col]
    )
