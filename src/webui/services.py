"""Business logic for the webui.

Wraps Phase 5a (planning + reconcile + PnL log) and adds the
ProfitLock skim policy + persistent bankroll state.

Constants (locked from prior analysis):
    N_LEGS                   = 4
    KELLY_FRACTION           = 1/16  (0.0625)
    PER_COMBO_STAKE_CAP_FRAC = 0.005 (0.5% bankroll)
    WEEKLY_STAKE_CAP_FRAC    = 0.25  (25% bankroll)
    PROFIT_LOCK_TRIGGER      = 2.0   (skim when active ≥ peak × 2)
    PROFIT_LOCK_SKIM_FRAC    = 0.30  (skim 30% of active to locked)
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.phase5a import (
    NicheConfig,
    build_weekly_plan,
    load_open_matches,
    read_pnl_log,
    reconcile_plan,
)
from src.phase5a.planner import save_plan_json

from .db import WebuiDB

# Strategy constants
N_LEGS = 4
KELLY_FRACTION = 1 / 16
PER_COMBO_STAKE_CAP_FRAC = 0.005
WEEKLY_STAKE_CAP_FRAC = 0.25
PROFIT_LOCK_TRIGGER = 2.0
PROFIT_LOCK_SKIM_FRAC = 0.30


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class BankrollState:
    initial: float
    active: float
    locked: float
    peak: float

    @property
    def total(self) -> float:
        return self.active + self.locked

    @property
    def cumulative_pnl(self) -> float:
        return self.total - self.initial

    @property
    def cumulative_roi(self) -> float:
        return self.cumulative_pnl / self.initial if self.initial > 0 else 0.0


def get_state(db: WebuiDB) -> BankrollState:
    return BankrollState(
        initial=db.get_float("initial_bankroll", 0.0),
        active=db.get_float("current_active", 0.0),
        locked=db.get_float("locked_pile", 0.0),
        peak=db.get_float("peak_high_water", 0.0),
    )


def apply_profit_lock(state: BankrollState) -> Tuple[BankrollState, float]:
    """Maybe skim 30% of active to locked when active ≥ peak × 2.

    Returns (new_state, skimmed_amount). The peak is updated to the
    *post-skim* active so the next trigger requires a fresh 2× run-up.
    """
    skimmed = 0.0
    new_peak = max(state.peak, state.active)
    if state.peak > 0 and state.active >= state.peak * PROFIT_LOCK_TRIGGER:
        skimmed = state.active * PROFIT_LOCK_SKIM_FRAC
        new_active = state.active - skimmed
        new_locked = state.locked + skimmed
        new_peak = new_active  # reset high-water to post-skim
        return BankrollState(initial=state.initial, active=new_active,
                             locked=new_locked, peak=new_peak), skimmed
    return BankrollState(initial=state.initial, active=state.active,
                         locked=state.locked, peak=new_peak), 0.0


def persist_state(db: WebuiDB, state: BankrollState) -> None:
    db.set_config("current_active", state.active)
    db.set_config("locked_pile", state.locked)
    db.set_config("peak_high_water", state.peak)


# ---------------------------------------------------------------------------
# Planning

def generate_plan(
    db: WebuiDB,
    *,
    live_db_path: str | Path,
    plans_dir: str | Path,
    niche_config: Optional[NicheConfig] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Run the planner against current Live Collector data and persist.

    Returns the plan dict (same shape as ``PlanResult.to_dict()``) plus
    a ``live_db_empty`` flag the UI uses for the empty-state banner.
    """
    state = get_state(db)
    if state.active <= 0:
        return dict(error="bankroll_not_initialized")

    cfg = niche_config or NicheConfig.load()
    snapshots = load_open_matches(live_db_path, now=now)
    plan = build_weekly_plan(
        snapshots,
        bankroll=state.active,
        niche_config=cfg,
        n_legs=N_LEGS,
        kelly_fraction=KELLY_FRACTION,
        weekly_stake_cap_frac=WEEKLY_STAKE_CAP_FRAC,
        now=now,
    )
    plan_dict = plan.to_dict()
    plan_dict["live_db_empty"] = len(snapshots) == 0

    # Persist to disk (so reconcile can read it later) AND to webui DB.
    save_plan_json(plan, plans_dir)
    db.upsert_plan(plan.plan_id, plan.generated_at, plan_dict)
    return plan_dict


# ---------------------------------------------------------------------------
# Reconcile

def reconcile_pending(
    db: WebuiDB,
    *,
    live_db_path: str | Path,
    plans_dir: str | Path,
    pnl_log: str | Path,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Reconcile every placed-but-unsettled plan against Live Collector.

    For each plan that now has full settlement coverage, compute PnL,
    update bankroll, run the ProfitLock check, and write a row to
    settlements_log. Already-recorded weeks are skipped (idempotent).
    """
    out: List[Dict[str, Any]] = []
    plans_dir = Path(plans_dir)

    for plan_meta in db.list_plans():
        week_id = plan_meta["plan_id"]
        if db.has_settlement(week_id):
            continue
        plan_path = plans_dir / f"{week_id}.json"
        if not plan_path.exists():
            continue
        try:
            res = reconcile_plan(plan_path, live_db_path, pnl_log, now=now)
        except (sqlite3.OperationalError, FileNotFoundError):
            continue
        if res.n_tickets == 0 or res.pending > 0:
            # Wait until all legs are settled before booking the week.
            continue

        state = get_state(db)
        new_active = state.active + res.net_pnl
        new_state = BankrollState(
            initial=state.initial, active=new_active,
            locked=state.locked, peak=state.peak,
        )
        new_state, skimmed = apply_profit_lock(new_state)
        persist_state(db, new_state)

        db.record_settlement(
            week_id=week_id,
            settled_ts=res.reconciled_at,
            n_combos=res.n_tickets,
            n_hits=res.n_winning_tickets,
            week_stake=float(res.total_stake),
            week_payout=float(res.gross_payout),
            week_pnl=float(res.net_pnl),
            bankroll_after=new_state.active,
            locked_after=new_state.locked,
            skimmed=skimmed,
        )
        out.append(dict(week_id=week_id, n_tickets=res.n_tickets,
                        n_hits=res.n_winning_tickets,
                        week_pnl=float(res.net_pnl), skimmed=skimmed,
                        bankroll_after=new_state.active,
                        locked_after=new_state.locked))
    return out


# ---------------------------------------------------------------------------
# Statistics for dashboard

def equity_series(db: WebuiDB) -> List[Dict[str, Any]]:
    """Return list of {week_id, active, locked, total} sorted by week."""
    rows = db.list_settlements()
    state = get_state(db)
    series: List[Dict[str, Any]] = []
    if state.initial > 0:
        # Prepend the starting point (no week_id).
        series.append(dict(week_id="START", active=state.initial,
                           locked=0.0, total=state.initial))
    for r in rows:
        series.append(dict(
            week_id=r["week_id"],
            active=float(r["bankroll_after"] or 0.0),
            locked=float(r["locked_after"] or 0.0),
            total=float(r["bankroll_after"] or 0.0)
                  + float(r["locked_after"] or 0.0),
        ))
    return series


def compute_stats(db: WebuiDB) -> Dict[str, Any]:
    """Cumulative PnL, Sharpe (per-week), max drawdown, hit rate."""
    rows = db.list_settlements()
    state = get_state(db)
    n_weeks = len(rows)
    n_hits = sum(int(r["n_hits"] or 0) for r in rows)
    n_combos = sum(int(r["n_combos"] or 0) for r in rows)
    hit_rate = (n_hits / n_combos) if n_combos > 0 else 0.0

    # Sharpe on weekly returns (active+locked vs prev). Risk-free=0.
    series = equity_series(db)
    rets: List[float] = []
    for prev, cur in zip(series[:-1], series[1:]):
        if prev["total"] > 0:
            rets.append((cur["total"] - prev["total"]) / prev["total"])
    if len(rets) >= 2:
        mu = sum(rets) / len(rets)
        var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
        sd = math.sqrt(var)
        sharpe = (mu / sd * math.sqrt(52)) if sd > 0 else 0.0
    else:
        sharpe = 0.0

    # Max drawdown on total equity
    peak = -math.inf
    max_dd = 0.0
    for s in series:
        peak = max(peak, s["total"])
        if peak > 0:
            dd = (peak - s["total"]) / peak
            max_dd = max(max_dd, dd)

    return dict(
        n_weeks=n_weeks,
        n_hits=n_hits,
        n_combos=n_combos,
        hit_rate=hit_rate,
        cumulative_pnl=state.cumulative_pnl,
        cumulative_roi=state.cumulative_roi,
        sharpe=sharpe,
        max_drawdown=max_dd,
    )


def recent_settlements(db: WebuiDB, n: int = 5) -> List[Dict[str, Any]]:
    rows = db.list_settlements()
    return list(reversed(rows))[:n]
