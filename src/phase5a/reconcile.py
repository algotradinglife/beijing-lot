"""Compare a saved plan against settlements and append PnL.

A combo ticket pays only if ALL legs win. Per-leg "win" semantics:
    Live Collector ``settlements.result_code`` ∈ {"3","1","0"} (stringified).
    A leg with selection s wins iff result_code == str(s).

Per ticket:
    gross_prize = (∏ leg SP) × 0.65 × stake_per_ticket   (parlay payout)
    payout      = gross_prize × n_tickets   if all legs hit, else 0

If a leg has no settlement row yet, the ticket is reported as "pending"
and excluded from PnL until reconciled later.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from src.combo_optimizer import RETURN_RATE

from .data_loader import load_settlements
from .pnl_log import append_pnl_row


@dataclass
class TicketOutcome:
    ticket_no: int
    status: str   # "won" | "lost" | "pending"
    stake: int
    payout: float
    pnl: float


@dataclass
class ReconcileResult:
    plan_id: str
    reconciled_at: str
    ticket_outcomes: List[TicketOutcome] = field(default_factory=list)
    n_tickets: int = 0
    n_settled_legs: int = 0
    n_winning_tickets: int = 0
    total_stake: int = 0
    gross_payout: float = 0.0
    net_pnl: float = 0.0
    pending: int = 0


def _ticket_settles(legs: list[dict], settlements: dict[str, dict]) -> tuple[Optional[bool], int]:
    """Return (all_hit | None if pending, n_settled_legs)."""
    n_settled = 0
    all_hit = True
    for leg in legs:
        s = settlements.get(leg["match_id"])
        if s is None or s.get("result_code") in (None, "", "None"):
            return None, n_settled
        n_settled += 1
        if str(s["result_code"]) != str(leg["selection"]):
            all_hit = False
    return all_hit, n_settled


def reconcile_plan(
    plan_path: str | Path,
    db_path: str | Path,
    pnl_log_path: str | Path,
    *,
    now: Optional[datetime] = None,
) -> ReconcileResult:
    plan = json.loads(Path(plan_path).read_text())
    settlements = load_settlements(db_path)
    now = now or datetime.now(timezone.utc)
    res = ReconcileResult(
        plan_id=plan["plan_id"],
        reconciled_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    for tk in plan.get("tickets", []):
        legs = tk["legs"]
        all_hit, n_settled_legs = _ticket_settles(legs, settlements)
        stake = int(tk["total_stake"])
        if all_hit is None:
            res.ticket_outcomes.append(
                TicketOutcome(ticket_no=tk["ticket_no"], status="pending",
                              stake=stake, payout=0.0, pnl=0.0)
            )
            res.pending += 1
            continue
        joint_sp = 1.0
        for leg in legs:
            s = settlements[leg["match_id"]]
            # Use winning_sp if present (leg matched winning option), else
            # the recorded leg.sp (more reliable for losing legs).
            joint_sp *= float(leg["sp"])
        payout = (
            int(tk["stake_per_ticket"]) * joint_sp * RETURN_RATE
            * int(tk["n_tickets"])
        ) if all_hit else 0.0
        pnl = payout - stake
        res.ticket_outcomes.append(
            TicketOutcome(ticket_no=tk["ticket_no"],
                          status=("won" if all_hit else "lost"),
                          stake=stake, payout=payout, pnl=pnl)
        )
        res.n_tickets += 1
        res.n_settled_legs += n_settled_legs
        if all_hit:
            res.n_winning_tickets += 1
        res.total_stake += stake
        res.gross_payout += payout
        res.net_pnl += pnl

    if res.n_tickets > 0:
        append_pnl_row(pnl_log_path, dict(
            plan_id=res.plan_id,
            reconciled_at=res.reconciled_at,
            n_tickets=res.n_tickets,
            n_settled_legs=res.n_settled_legs,
            n_winning_tickets=res.n_winning_tickets,
            total_stake=res.total_stake,
            gross_payout=round(res.gross_payout, 2),
            net_pnl=round(res.net_pnl, 2),
        ))
    return res
