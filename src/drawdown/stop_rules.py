"""Post-hoc stop-loss / throttle rule overlays.

Each rule returns an ``active_mult`` series (one per week) given the
state of the *new* bankroll path being constructed. They're applied
inside ``replay`` to produce a counterfactual bankroll curve.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


# A rule is a callable: state -> active_mult in [0, inf).
# state dict keys:
#   t, bankroll, peak, dd_pct, recent_pnl_pct (last K weekly pct returns), throttled_until
RuleState = dict
RuleFn = Callable[[RuleState], float]


@dataclass
class Rule:
    name: str
    fn: RuleFn
    note: str = ""
    # Optional post-pnl hooks (e.g. profit-lock skim trigger). Each hook
    # receives the state dict (with updated bankroll) and may set
    # state["skim_request"].
    _post_hooks: list[Callable[[RuleState], None]] | None = None


def hard_stop(drop_pct: float, halt_weeks: int) -> Rule:
    """If dd_pct <= -drop_pct → halt for halt_weeks weeks (mult=0)."""
    def fn(s: RuleState) -> float:
        # halt active?
        if s.get("halted_until", -1) > s["t"]:
            return 0.0
        if s["dd_pct"] <= -drop_pct:
            s["halted_until"] = s["t"] + halt_weeks
            return 0.0
        return 1.0
    return Rule(
        name=f"HardStop_{int(drop_pct*100)}pct_halt{halt_weeks}wk",
        fn=fn,
        note=f"halt {halt_weeks} weeks when DD <= -{int(drop_pct*100)}%",
    )


def stake_throttle(drop_pct: float, throttle_to: float = 0.25) -> Rule:
    """If dd_pct <= -drop_pct, cut Kelly to throttle_to× until peak recovered."""
    def fn(s: RuleState) -> float:
        # active throttling: stay on until DD recovers to within 1% of peak
        if s.get("throttled", False):
            if s["dd_pct"] >= -0.01:
                s["throttled"] = False
                return 1.0
            return throttle_to
        if s["dd_pct"] <= -drop_pct:
            s["throttled"] = True
            return throttle_to
        return 1.0
    return Rule(
        name=f"StakeThrottle_{int(drop_pct*100)}pct_to{throttle_to:g}x",
        fn=fn,
        note=f"cut to {throttle_to}× Kelly when DD <= -{int(drop_pct*100)}% until recovered",
    )


def vol_throttle(window: int = 8, std_threshold: float = 0.10, halt_weeks: int = 2) -> Rule:
    """Halt halt_weeks weeks when rolling-std of recent weekly pct returns > threshold."""
    def fn(s: RuleState) -> float:
        if s.get("halted_until", -1) > s["t"]:
            return 0.0
        recent = s["recent_pct"]
        if len(recent) >= window:
            sd = float(np.std(recent[-window:], ddof=1))
            if sd > std_threshold:
                s["halted_until"] = s["t"] + halt_weeks
                return 0.0
        return 1.0
    return Rule(
        name=f"VolThrottle_w{window}_sd{std_threshold:g}_halt{halt_weeks}wk",
        fn=fn,
        note=f"halt {halt_weeks} weeks when rolling-{window}wk std of weekly%returns > {std_threshold}",
    )


def profit_lock(double_at: float = 2.0, skim_frac: float = 0.30) -> Rule:
    """Each time bankroll/initial crosses next doubling level, skim skim_frac
    *out of play* (subtract from bankroll permanently). Stake mult is always 1;
    actual skim is decided in the POST-pnl hook below."""
    def fn(s: RuleState) -> float:
        return 1.0

    def post(s: RuleState) -> None:
        ratio = s["bankroll"] / s["initial"]
        last_level = s.get("doubling_level", 1.0)
        next_level = last_level * double_at
        if ratio >= next_level:
            s["skim_request"] = skim_frac * s["bankroll"]
            s["doubling_level"] = next_level

    return Rule(
        name=f"ProfitLock_double{double_at:g}_skim{int(skim_frac*100)}pct",
        fn=fn,
        note=f"skim {int(skim_frac*100)}% of bankroll each time it doubles",
        _post_hooks=[post],
    )


def combined(rule_a: Rule, rule_b: Rule, name: str | None = None) -> Rule:
    """Apply two rules; mult is product, both side-effects + post hooks executed."""
    def fn(s: RuleState) -> float:
        m1 = rule_a.fn(s)
        m2 = rule_b.fn(s)
        return m1 * m2
    posts = (rule_a._post_hooks or []) + (rule_b._post_hooks or [])
    return Rule(
        name=name or f"Combo({rule_a.name}+{rule_b.name})",
        fn=fn,
        note=f"{rule_a.note} AND {rule_b.note}",
        _post_hooks=posts or None,
    )


def baseline() -> Rule:
    return Rule(name="Baseline", fn=lambda s: 1.0, note="no overlay")
