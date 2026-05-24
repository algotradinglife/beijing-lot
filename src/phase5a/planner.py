"""Glue: qualified candidates → combo_optimizer.build_plan → markdown.

Defaults reflect the Calmar-optimal config from data/raw/kelly_n_grid.csv:
N=4 legs, Kelly fraction = 1/16 = 0.0625.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from src.combo_optimizer import TicketPlan, build_plan

from .data_loader import LiveSnapshot
from .filter import NicheConfig, QualifiedCandidate, qualify_candidates

DEFAULT_N_LEGS = 4
DEFAULT_KELLY_FRACTION = 0.0625  # 1/16


@dataclass
class PlanResult:
    plan_id: str          # e.g. "2026-W18"
    generated_at: str     # ISO UTC
    bankroll: float
    n_legs: int
    kelly_fraction: float
    n_open_matches: int
    n_qualified_legs: int
    tickets: List[TicketPlan] = field(default_factory=list)
    rule_by_match: dict[str, str] = field(default_factory=dict)
    snap_by_match: dict[str, LiveSnapshot] = field(default_factory=dict)

    @property
    def total_stake(self) -> int:
        return sum(t.total_stake for t in self.tickets)

    @property
    def expected_total_return(self) -> float:
        return sum(t.expected_total_return for t in self.tickets)

    def to_dict(self) -> dict:
        return dict(
            plan_id=self.plan_id,
            generated_at=self.generated_at,
            bankroll=self.bankroll,
            n_legs=self.n_legs,
            kelly_fraction=self.kelly_fraction,
            n_open_matches=self.n_open_matches,
            n_qualified_legs=self.n_qualified_legs,
            total_stake=self.total_stake,
            expected_total_return=self.expected_total_return,
            tickets=[
                dict(
                    ticket_no=i + 1,
                    stake_per_ticket=t.stake_per_ticket,
                    n_tickets=t.n_tickets,
                    total_stake=t.total_stake,
                    joint_sp=t.combo.joint_sp,
                    joint_p=t.combo.joint_p,
                    payout_per_yuan=t.combo.payout_per_yuan,
                    prize_per_ticket=t.prize_per_ticket,
                    is_tax_free=t.is_tax_free,
                    ev=t.combo.ev,
                    legs=[
                        dict(
                            match_id=leg.match_id,
                            selection=leg.selection,
                            sp=leg.sp,
                            p_hat=leg.p_hat,
                            rule=self.rule_by_match.get(leg.match_id, ""),
                            kickoff_ts=getattr(self.snap_by_match.get(leg.match_id), "kickoff_ts", None),
                            home=getattr(self.snap_by_match.get(leg.match_id), "home", None),
                            away=getattr(self.snap_by_match.get(leg.match_id), "away", None),
                            league=getattr(self.snap_by_match.get(leg.match_id), "league", None),
                            handicap=getattr(self.snap_by_match.get(leg.match_id), "handicap_line", None),
                        )
                        for leg in t.combo.legs
                    ],
                )
                for i, t in enumerate(self.tickets)
            ],
        )


def iso_week_id(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def build_weekly_plan(
    snapshots: Iterable[LiveSnapshot],
    *,
    bankroll: float,
    niche_config: NicheConfig,
    n_legs: int = DEFAULT_N_LEGS,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    weekly_stake_cap_frac: float = 0.25,
    combo_ev_threshold: float = 0.05,
    top_k: int = 14,
    max_combos: int = 50,
    diversity_lambda: float = 0.5,
    cross_n_used: Optional[frozenset] = None,
    cross_n_lambda: float = 0.0,
    now: Optional[datetime] = None,
) -> PlanResult:
    snapshots = list(snapshots)
    qualified = qualify_candidates(snapshots, niche_config)

    tickets: List[TicketPlan] = []
    if qualified:
        # Single-leg edge floor is intentionally relaxed: niche legs run at
        # p×SP ≈ 1.07-1.20 (per-leg q), which is < 1/0.65 = 1.538 (single-leg
        # break-even), so single-leg edge is always negative. The +EV emerges
        # at the combo level where (mean_q)^N × 0.65 > 1 for N=4 and q ≥ 1.07.
        # We rely on ``combo_ev_threshold`` to filter at the combo stage.
        tickets = build_plan(
            [q.candidate for q in qualified],
            bankroll=bankroll,
            n_legs=n_legs,
            top_k=top_k,
            single_leg_edge_floor=-1.0,
            combo_ev_threshold=combo_ev_threshold,
            kelly_fraction=kelly_fraction,
            weekly_stake_cap_frac=weekly_stake_cap_frac,
            max_combos=max_combos,
            diversity_lambda=diversity_lambda,
            cross_n_used=cross_n_used,
            cross_n_lambda=cross_n_lambda,
        )

    rule_by_match = {q.candidate.match_id: q.rule_name for q in qualified}
    snap_by_match = {q.candidate.match_id: q.snap for q in qualified}
    now = now or datetime.now(timezone.utc)
    return PlanResult(
        plan_id=iso_week_id(now),
        generated_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        bankroll=float(bankroll),
        n_legs=n_legs,
        kelly_fraction=kelly_fraction,
        n_open_matches=len(snapshots),
        n_qualified_legs=len(qualified),
        tickets=tickets,
        rule_by_match=rule_by_match,
        snap_by_match=snap_by_match,
    )


def _fmt_match(snap: LiveSnapshot | None) -> str:
    if snap is None:
        return "?"
    h = snap.home or "?"
    a = snap.away or "?"
    line = "" if snap.handicap_line is None else f" ({snap.handicap_line:+g})"
    return f"{h} vs {a}{line}"


_SEL_LABEL = {3: "胜", 1: "平", 0: "负"}


def format_plan_markdown(plan: PlanResult) -> str:
    """Printable weekly bet plan."""
    lines: list[str] = []
    lines.append(f"# Phase 5a Weekly Bet Plan — {plan.plan_id}")
    lines.append("")
    lines.append(f"- Generated: {plan.generated_at}")
    lines.append(f"- Bankroll: {plan.bankroll:,.0f} yuan")
    lines.append(
        f"- Config: N={plan.n_legs} legs, Kelly={plan.kelly_fraction:g} "
        f"({plan.kelly_fraction * 100:.2f}%)"
    )
    lines.append(
        f"- Open matches in window: {plan.n_open_matches} | "
        f"qualified legs: {plan.n_qualified_legs}"
    )
    lines.append("")

    if not plan.tickets:
        lines.append("**No tickets generated.** "
                     "(Empty Live DB, no qualifying niches, or sub-2-yuan stakes.)")
        return "\n".join(lines)

    lines.append(
        "| # | Kickoff | Match | Sel | SP | Combo legs | Stake | n | Exp. prize | Tax-free? |"
    )
    lines.append("|---|---|---|---|---|---|---:|---:|---:|---|")
    for i, t in enumerate(plan.tickets, 1):
        first_leg = t.combo.legs[0]
        snap = plan.snap_by_match.get(first_leg.match_id)
        kickoff = (snap.kickoff_ts if snap else "?")
        match_str = _fmt_match(snap)
        sel = _SEL_LABEL.get(int(first_leg.selection), str(first_leg.selection))
        sp = first_leg.sp
        legs_repr = " + ".join(
            f"{leg.match_id}:{_SEL_LABEL.get(int(leg.selection), leg.selection)}@{leg.sp:.2f}"
            for leg in t.combo.legs
        )
        exp_prize = t.expected_total_return
        tax = "Y" if t.is_tax_free else "N"
        lines.append(
            f"| {i} | {kickoff} | {match_str} | {sel} | {sp:.2f} | {legs_repr} | "
            f"{t.stake_per_ticket} | {t.n_tickets} | {exp_prize:.1f} | {tax} |"
        )

    lines.append("")
    lines.append(f"**Total stake:** {plan.total_stake} yuan "
                 f"(= {plan.total_stake / plan.bankroll * 100:.2f}% of bankroll)")
    lines.append(f"**Expected total return:** {plan.expected_total_return:.1f} yuan")
    return "\n".join(lines)


def save_plan_json(plan: PlanResult, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{plan.plan_id}.json"
    p.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    return p
