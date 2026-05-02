"""Drawdown decomposition + stop-loss overlay tooling.

This module never modifies ``src/sweep/simulator.py``. Instead it works on
the *output* (per-week stake & ROI series) of a baseline simulation, and
applies stop-loss / throttle rules as a post-hoc bankroll re-evolution.

Approximation: in the live simulator, ``week_stake`` is roughly
``stake_frac_t × bankroll_t`` (Kelly is multiplicative in bankroll, modulo
combo cap & integer rounding). So we treat the empirical
``stake_frac_t = week_stake / bankroll_at_start_of_week`` and weekly
``roi_t = week_pnl / week_stake`` as bankroll-invariant signals. New
bankroll path under a rule:

    stake_t' = bankroll_t' × stake_frac_t × active_mult_t
    pnl_t'   = stake_t' × roi_t
    bankroll_{t+1}' = bankroll_t' + pnl_t'

Where ``active_mult_t ∈ [0, 1]`` is set by the stop-loss rule given the
running peak/trough state of the new path.
"""
