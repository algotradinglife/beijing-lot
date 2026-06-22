"""Unit tests for reconcile leg-settlement semantics.

A combo ticket pays only if ALL legs win. The key invariant under test:
once ANY leg is settled-and-lost, the whole ticket is lost — regardless of
whether some other leg is still unsettled. Only a ticket with no lost leg and
at least one unsettled leg is genuinely "pending".
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.live_collector.db import SCHEMA
from src.phase5a.reconcile import _ticket_settles, reconcile_plan


def _leg(match_id: str, selection: str, sp: float = 4.0) -> dict:
    return {"match_id": match_id, "selection": selection, "sp": sp}


def test_lost_leg_after_pending_leg_settles_as_lost():
    # Leg order: the UNSETTLED leg comes first, then a settled-and-lost leg.
    # The already-lost leg must make the whole ticket lost, not pending.
    legs = [_leg("m_pending", "3"), _leg("m_lost", "3")]
    settlements = {
        # picked "3" but result was "0" -> this leg lost
        "m_lost": {"result_code": "0", "winning_sp": None},
        # m_pending absent -> unsettled
    }
    all_hit, n_settled = _ticket_settles(legs, settlements)
    assert all_hit is False
    assert n_settled == 1


def test_pending_when_unsettled_and_no_lost_leg():
    # One leg already won, the other not settled yet, none lost -> still pending.
    legs = [_leg("m_won", "3"), _leg("m_pending", "3")]
    settlements = {"m_won": {"result_code": "3", "winning_sp": 4.0}}
    all_hit, n_settled = _ticket_settles(legs, settlements)
    assert all_hit is None


def test_all_settled_all_hit():
    legs = [_leg("a", "3"), _leg("b", "1")]
    settlements = {
        "a": {"result_code": "3", "winning_sp": 4.0},
        "b": {"result_code": "1", "winning_sp": 3.0},
    }
    all_hit, n_settled = _ticket_settles(legs, settlements)
    assert all_hit is True
    assert n_settled == 2


def test_empty_string_result_code_is_unsettled():
    # result_code "" / "None" counts as not-yet-settled, not as a loss.
    legs = [_leg("a", "3"), _leg("b", "1")]
    settlements = {
        "a": {"result_code": "", "winning_sp": None},
        "b": {"result_code": "1", "winning_sp": 3.0},
    }
    all_hit, n_settled = _ticket_settles(legs, settlements)
    assert all_hit is None


def _write_db(path: Path, settlements: list[dict]) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    for st in settlements:
        conn.execute(
            "INSERT INTO settlements(match_id,issue,match_idx,fthg,ftag,"
            "result_code,winning_sp) VALUES (?,?,?,?,?,?,?)",
            (st["match_id"], st.get("issue", "26065"), st.get("match_idx", 1),
             st.get("fthg", 0), st.get("ftag", 0), st["result_code"],
             st.get("winning_sp")),
        )
    conn.commit()
    conn.close()


def test_reconcile_plan_lost_ticket_with_unsettled_leg(tmp_path):
    # A ticket whose first leg is unsettled but second leg is already lost must
    # reconcile as a settled loss (pnl = -stake), not crash and not pending.
    db = tmp_path / "live.db"
    _write_db(db, [
        # the lost leg: picked "3" (home) but result was "0" (away)
        {"match_id": "26065_010", "result_code": "0", "winning_sp": None},
        # 26065_005 deliberately absent -> unsettled
    ])
    plan = {
        "plan_id": "26065",
        "tickets": [{
            "ticket_no": 1,
            "total_stake": 10,
            "stake_per_ticket": 10,
            "n_tickets": 1,
            "legs": [
                {"match_id": "26065_005", "selection": "3", "sp": 4.0},
                {"match_id": "26065_010", "selection": "3", "sp": 4.0},
            ],
        }],
    }
    plan_path = tmp_path / "26065.json"
    plan_path.write_text(json.dumps(plan))
    pnl_log = tmp_path / "pnl.csv"

    res = reconcile_plan(plan_path, db, pnl_log)

    assert res.pending == 0
    assert res.n_tickets == 1
    assert res.ticket_outcomes[0].status == "lost"
    assert res.ticket_outcomes[0].pnl == -10
    assert res.net_pnl == -10
