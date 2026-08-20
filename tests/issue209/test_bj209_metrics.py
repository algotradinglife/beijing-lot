"""Issue #209 golden metric tests — definitions per frozen method protocol.

These tests pin the exact semantics of the primary metrics so an EV auditor can
verify the implementation matches the frozen definitions, independent of any run
output. They do not depend on generated results; they test the metric functions
on constructed fixtures.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from issue209.ticket import settle_ticket, TAX_FACTOR
from issue209.bankroll import (
    simulate_bankroll,
    summarize_capital,
    matched_lift,
    promotion_rule,
    _max_consecutive_losses,
)


def _tensor_for(*spec):
    """Build a long tensor from (match_idx, realized, chosen_outcome, sp)."""
    rows = []
    for m, realized, sp in spec:
        for oc in ["3", "1", "0"]:
            rows.append({
                "match_idx": m, "outcome_code": oc,
                "realized_outcome": realized,
                "SP_SETTLE": sp if oc == realized else np.nan,
            })
    return pd.DataFrame(rows)


def test_payout_65_applied_once():
    """0.65 applied exactly once to the winning product, never 0.65^N (REQ-209-06)."""
    tensor = _tensor_for(
        (1, "3", 2.0), (2, "1", 3.0), (3, "0", 4.0), (4, "3", 5.0),
        (5, "1", 6.0), (6, "0", 7.0), (7, "3", 8.0),
    )
    # 7-leg winner, all hit
    res = settle_ticket([1, 2, 3, 4, 5, 6, 7], ["3", "1", "0", "3", "1", "0", "3"], tensor)
    assert res["hit"] is True
    product = 2.0 * 3.0 * 4.0 * 5.0 * 6.0 * 7.0 * 8.0
    assert res["product_sp"] == pytest.approx(product)
    # 0.65 exactly once, not 0.65**7
    assert res["gross_multiple"] == pytest.approx(0.65 * product)
    assert res["gross_multiple"] != pytest.approx((0.65 ** 7) * product)


def test_payout_65_miss_zero():
    """A single miss makes the whole N-fold ticket lose (REQ-209-06 shared settlement)."""
    tensor = _tensor_for((1, "3", 2.0), (2, "1", 3.0))
    res = settle_ticket([1, 2], ["3", "0"], tensor)  # match 2 chosen '0' but realized '1'
    assert res["hit"] is False
    assert res["gross_multiple"] == 0.0


def test_matched_lift_definition():
    """Matched ending-capital lift vs frozen baseline (REQ-209-08)."""
    cand = {"ending_capital": 110_000.0, "max_drawdown_pct": 5.0}
    lift = matched_lift(cand, 100_000.0)
    assert lift["matched_lift"] == pytest.approx(10.0)
    assert lift["candidate_ending_capital"] == pytest.approx(110_000.0)


def test_promotion_rule_requires_lift_dd_ruin_funding():
    """Promotion gate: positive lift, non-worse dd, no ruin, preserved funding."""
    ok = promotion_rule(
        {"ending_capital": 110_000.0, "max_drawdown_pct": 5.0, "ruin": False,
         "funded_turnover": 1000.0}, 100_000.0)
    assert ok["promote"] is True
    # negative lift -> no promote
    neg = promotion_rule(
        {"ending_capital": 90_000.0, "max_drawdown_pct": 5.0, "ruin": False,
         "funded_turnover": 1000.0}, 100_000.0)
    assert neg["promote"] is False
    # ruin -> no promote
    ruin = promotion_rule(
        {"ending_capital": 0.0, "max_drawdown_pct": 90.0, "ruin": True,
         "funded_turnover": 1000.0}, 100_000.0)
    assert ruin["promote"] is False
    # zero funding (exposure reduction explaining gains) -> no promote
    nofund = promotion_rule(
        {"ending_capital": 101_000.0, "max_drawdown_pct": 0.0, "ruin": False,
         "funded_turnover": 0.0}, 100_000.0)
    assert nofund["promote"] is False


def test_drawdown_definition():
    """Max drawdown from running peak of the CNY100k pre-tax path."""
    res = pd.DataFrame({
        "issue": ["a", "b", "c"],
        "n_tickets": [1, 1, 1],
        "stake_total": [100, 100, 100],
        "realized_gross": [0, 0, 300],
    })
    path = simulate_bankroll(res)
    # a: -100 (100k -> 99900), b: -100 (99900->99800), c: +200 (99800->100000)
    assert path["equity_after"].tolist() == pytest.approx([99900, 99800, 100000])
    # peak reached 100000 at start; dd after b = (100000-99800)/100000 = 0.002
    cap = summarize_capital(path)
    assert cap["max_drawdown_pct"] == pytest.approx(0.2)


def test_no_ruin():
    """Ruin = ending capital <= 0 (equity fully lost)."""
    res = pd.DataFrame({
        "issue": ["a"], "n_tickets": [1], "stake_total": [500_000],
        "realized_gross": [0.0],
    })
    path = simulate_bankroll(res)
    # funded stake capped at available bankroll (100k); full loss -> equity 0
    cap = summarize_capital(path)
    assert cap["ruin"] is True
    assert cap["ending_capital"] == 0.0


def test_max_consecutive_losses():
    path = pd.DataFrame({"pnl": [-1, -1, -1, 2, -1, -1, 0, -1]})
    assert _max_consecutive_losses(path) == 3
