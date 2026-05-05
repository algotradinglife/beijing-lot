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
from datetime import datetime, timedelta, timezone

HK_TZ = timezone(timedelta(hours=8))


def fmt_hk(ts) -> str:
    """Format an ISO kickoff_ts (assumed HK if naive) as `MM-DD HH:MM HKT`."""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return str(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=HK_TZ)
    dt = dt.astimezone(HK_TZ)
    return dt.strftime("%m-%d %H:%M +08:00")
from io import BytesIO
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

    # League q-filter persisted in DB (per-preset; 高 Sharpe N=5 用 0.65, 其他默认 0)
    league_q_min = float(db.get_config("league_q_min") or 0.0)
    cfg = niche_config or NicheConfig.load(league_q_min=league_q_min)
    snapshots = load_open_matches(live_db_path, now=now)
    # Read user-tunable strategy params from config (defaults locked from analysis)
    n_legs = int(db.get_config("n_legs") or N_LEGS)
    kelly_fraction = float(db.get_config("kelly_fraction") or KELLY_FRACTION)
    diversity_lambda = float(db.get_config("diversity_lambda") or 0.5)
    max_combos = int(db.get_config("max_combos") or 50)
    # Mix mode: split bankroll across N=2 / N=3 / N=4 / N=5 by 4 weights (sum auto-norm)
    mix_enabled = bool(int(db.get_config("mix_enabled") or 0))
    w2 = float(db.get_config("mix_weight_n2") or 0.0)
    w3 = float(db.get_config("mix_weight_n3") or 0.0)
    w4 = float(db.get_config("mix_weight_n4") or 1.0)
    w5 = float(db.get_config("mix_weight_n5") or 0.0)
    # Legacy 2-way fallback
    n_legs_secondary = int(db.get_config("n_legs_secondary") or 2)
    weight_primary_legacy = float(db.get_config("weight_primary") or 0.7)
    if mix_enabled and (w2 + w3 + w4 + w5) > 0:
        # 4-way mix path with per-N Kelly + lambda overrides + max_combos auto-allocation
        wsum = w2 + w3 + w4 + w5
        w2, w3, w4, w5 = w2/wsum, w3/wsum, w4/wsum, w5/wsum
        # Per-N overrides (fall back to global if not set)
        kelly_n2 = float(db.get_config("kelly_n2") or kelly_fraction)
        kelly_n3 = float(db.get_config("kelly_n3") or kelly_fraction)
        kelly_n4 = float(db.get_config("kelly_n4") or kelly_fraction)
        kelly_n5 = float(db.get_config("kelly_n5") or 0.125)
        lambda_n2 = float(db.get_config("lambda_n2") if db.get_config("lambda_n2") is not None else diversity_lambda)
        lambda_n3 = float(db.get_config("lambda_n3") if db.get_config("lambda_n3") is not None else diversity_lambda)
        lambda_n4 = float(db.get_config("lambda_n4") if db.get_config("lambda_n4") is not None else diversity_lambda)
        lambda_n5 = float(db.get_config("lambda_n5") if db.get_config("lambda_n5") is not None else 0.0)
        per_n_params = {
            2: (w2, kelly_n2, lambda_n2),
            3: (w3, kelly_n3, lambda_n3),
            4: (w4, kelly_n4, lambda_n4),
            5: (w5, kelly_n5, lambda_n5),
        }
        merged_tickets = []
        total_stake = 0
        expected_return = 0.0
        n_qual_legs = 0
        for n_val, (weight, k_n, lam_n) in per_n_params.items():
            if weight <= 0:
                continue
            sub_bankroll = state.active * weight
            sub_max_combos = max(1, int(round(max_combos * weight)))
            if sub_bankroll < 100:
                continue
            plan_n = build_weekly_plan(
                snapshots, bankroll=sub_bankroll, niche_config=cfg,
                n_legs=n_val, kelly_fraction=k_n,
                weekly_stake_cap_frac=WEEKLY_STAKE_CAP_FRAC,
                diversity_lambda=lam_n, max_combos=sub_max_combos, now=now,
            )
            pn = plan_n.to_dict()
            for t in pn.get("tickets", []):
                t["leg_source"] = f"N={n_val}"
                t["mix_weight"] = round(weight, 2)
                t["leg_kelly"] = k_n
                t["leg_lambda"] = lam_n
                merged_tickets.append(t)
            total_stake += int(pn.get("total_stake", 0))
            expected_return += float(pn.get("expected_total_return", 0))
            n_qual_legs = max(n_qual_legs, pn.get("n_qualified_legs", 0))
        # Build merged plan dict — id = 北单 issue (e.g. "26052") with
        # collision suffix `-2` / `-3` for re-generations of the same issue.
        # Falls back to YYYY-MM-DD if no snapshot is available.
        base = None
        for snap in snapshots:
            iss = getattr(snap, "issue", None)
            if iss:
                base = str(iss)
                break
        if not base:
            base = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        existing = {p["plan_id"] for p in db.list_plans()}
        wk = base
        i = 2
        while wk in existing:
            wk = f"{base}-{i}"
            i += 1
        plan_dict = dict(
            plan_id=wk,
            generated_at=(now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            bankroll=float(state.active),
            n_legs=n_legs,  # primary for legacy compat
            kelly_fraction=kelly_fraction,
            n_open_matches=len(snapshots),
            n_qualified_legs=n_qual_legs,
            total_stake=total_stake,
            expected_total_return=expected_return,
            tickets=merged_tickets,
            mix_enabled=True,
            mix_weights=dict(n2=round(w2, 3), n3=round(w3, 3), n4=round(w4, 3), n5=round(w5, 3)),
            mix_kelly=dict(n2=kelly_n2, n3=kelly_n3, n4=kelly_n4, n5=kelly_n5),
            mix_lambda=dict(n2=lambda_n2, n3=lambda_n3, n4=lambda_n4, n5=lambda_n5),
            league_q_min=league_q_min,
        )
        # Persist merged plan to disk for reconcile
        plans_dir = Path(plans_dir)
        plans_dir.mkdir(parents=True, exist_ok=True)
        import json as _json
        (plans_dir / f"{wk}.json").write_text(_json.dumps(plan_dict, ensure_ascii=False))
        db.upsert_plan(wk, plan_dict["generated_at"], plan_dict)
        plan_dict["live_db_empty"] = len(snapshots) == 0
    elif mix_enabled and abs(weight_primary_legacy - 1.0) > 1e-6:
        weight_primary = weight_primary_legacy
        # Run primary leg with bankroll * weight, secondary with bankroll * (1-weight)
        bankroll_p = state.active * weight_primary
        bankroll_s = state.active * (1.0 - weight_primary)
        plan_p = build_weekly_plan(
            snapshots, bankroll=bankroll_p, niche_config=cfg,
            n_legs=n_legs, kelly_fraction=kelly_fraction,
            weekly_stake_cap_frac=WEEKLY_STAKE_CAP_FRAC,
            diversity_lambda=diversity_lambda, max_combos=max_combos, now=now,
        )
        plan_s = build_weekly_plan(
            snapshots, bankroll=bankroll_s, niche_config=cfg,
            n_legs=n_legs_secondary, kelly_fraction=kelly_fraction,
            weekly_stake_cap_frac=WEEKLY_STAKE_CAP_FRAC,
            diversity_lambda=diversity_lambda, max_combos=max_combos, now=now,
        )
        # Merge: tag tickets with their N, combine
        plan_p_dict = plan_p.to_dict()
        plan_s_dict = plan_s.to_dict()
        for t in plan_p_dict.get("tickets", []):
            t["leg_source"] = f"N={n_legs}"
        for t in plan_s_dict.get("tickets", []):
            t["leg_source"] = f"N={n_legs_secondary}"
        plan_dict = dict(plan_p_dict)
        plan_dict["tickets"] = plan_p_dict.get("tickets", []) + plan_s_dict.get("tickets", [])
        plan_dict["total_stake"] = (
            int(plan_p_dict.get("total_stake", 0)) + int(plan_s_dict.get("total_stake", 0))
        )
        plan_dict["expected_total_return"] = (
            float(plan_p_dict.get("expected_total_return", 0))
            + float(plan_s_dict.get("expected_total_return", 0))
        )
        plan_dict["n_qualified_legs"] = max(
            plan_p_dict.get("n_qualified_legs", 0),
            plan_s_dict.get("n_qualified_legs", 0),
        )
        plan_dict["mix_enabled"] = True
        plan_dict["weight_primary"] = weight_primary
        plan_dict["n_legs_primary"] = n_legs
        plan_dict["n_legs_secondary"] = n_legs_secondary
        plan_dict["primary_stake"] = int(plan_p_dict.get("total_stake", 0))
        plan_dict["secondary_stake"] = int(plan_s_dict.get("total_stake", 0))
        # Persist primary plan json (reconcile uses it as base)
        save_plan_json(plan_p, plans_dir)
        # Save secondary alongside with suffix for traceability
        from src.phase5a.planner import PlanResult  # noqa
        # Save secondary plan separately
        sec_path = Path(plans_dir) / f"{plan_s.plan_id}_secondary.json"
        sec_path.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        sec_path.write_text(_json.dumps(plan_s_dict, ensure_ascii=False))
        db.upsert_plan(plan_p.plan_id, plan_p.generated_at, plan_dict)
        plan_dict["live_db_empty"] = len(snapshots) == 0
    else:
        plan = build_weekly_plan(
            snapshots,
            bankroll=state.active,
            niche_config=cfg,
            n_legs=n_legs,
            kelly_fraction=kelly_fraction,
            weekly_stake_cap_frac=WEEKLY_STAKE_CAP_FRAC,
            diversity_lambda=diversity_lambda,
            max_combos=max_combos,
            now=now,
        )
        plan_dict = plan.to_dict()
        plan_dict["live_db_empty"] = len(snapshots) == 0
        plan_dict["mix_enabled"] = False
    # Diagnostic: per-leg appearance counts for diversity visualization
    leg_counts: Dict[str, Dict[str, Any]] = {}
    for ticket in plan_dict.get("tickets", []):
        for leg in ticket.get("legs", []):
            key = f"{leg.get('match_id')}:{leg.get('selection')}"
            entry = leg_counts.setdefault(key, dict(
                key=key,
                match_id=leg.get("match_id"),
                selection=leg.get("selection"),
                home=leg.get("home"),
                away=leg.get("away"),
                sp=leg.get("sp"),
                count=0,
            ))
            entry["count"] += 1
    plan_dict["leg_appearance"] = sorted(
        leg_counts.values(), key=lambda x: x["count"], reverse=True
    )
    n_tickets = len(plan_dict.get("tickets", []))
    if leg_counts and n_tickets:
        max_count = max(e["count"] for e in leg_counts.values())
        plan_dict["concentration_max_pct"] = round(100 * max_count / n_tickets, 1)
        # Herfindahl–Hirschman Index on shares
        shares = [e["count"] / n_tickets for e in leg_counts.values()]
        plan_dict["hhi"] = round(sum(s * s for s in shares), 4)
        plan_dict["effective_n_legs"] = round(1.0 / plan_dict["hhi"], 2) if plan_dict["hhi"] > 0 else 0
    else:
        plan_dict["concentration_max_pct"] = 0
        plan_dict["hhi"] = 0
        plan_dict["effective_n_legs"] = 0
    plan_dict["diversity_lambda"] = diversity_lambda
    plan_dict["n_legs_config"] = n_legs
    plan_dict["kelly_fraction"] = kelly_fraction
    plan_dict["max_combos"] = max_combos

    # Persist to disk (so reconcile can read it later) AND to webui DB.
    if not mix_enabled:
        save_plan_json(plan, plans_dir)
    # Re-upsert with augmented fields (leg_appearance, hhi, …). Mix path
    # already wrote a slim version earlier; this overwrite keeps the DB in
    # sync with the dict the templates expect.
    pid = plan_dict.get("plan_id")
    gen = plan_dict.get("generated_at")
    if pid and gen:
        db.upsert_plan(pid, gen, plan_dict)
        # Also rewrite the JSON file in mix mode so reconcile sees the same dict
        if mix_enabled:
            import json as _json
            (Path(plans_dir) / f"{pid}.json").write_text(
                _json.dumps(plan_dict, ensure_ascii=False)
            )
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
        if not plan_meta.get("placed_ts"):
            # Skip plans that were never marked placed — settling them
            # would pollute equity curve with hypothetical PnL.
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
        # Apply optional commission rebate (彩票站佣金) on top of net PnL.
        commission_rate = float(db.get_config("commission_rate") or 0.0)
        commission = float(res.total_stake) * commission_rate
        new_active = state.active + res.net_pnl + commission
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
            week_pnl=float(res.net_pnl) + commission,
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
    """Return list of {ts, week_id, active, locked, total} sorted by
    settled_ts (true chronology). Each entry carries:
      - ts:       ISO date string used as x-axis (calendar time)
      - week_id:  the 北单 issue (used as point label / hover only)
    """
    # Sort by settled_ts so non-monotonic plan_id alphabets don't reorder
    rows = sorted(db.list_settlements(),
                  key=lambda r: r.get("settled_ts") or "")
    state = get_state(db)
    series: List[Dict[str, Any]] = []
    if state.initial > 0:
        first_ts = rows[0]["settled_ts"][:10] if rows and rows[0].get("settled_ts") \
                   else None
        series.append(dict(ts=first_ts or "START",
                           week_id="START", active=state.initial,
                           locked=0.0, total=state.initial))
    for r in rows:
        ts_full = r.get("settled_ts") or ""
        series.append(dict(
            ts=ts_full[:16].replace("T", " ") if ts_full else r["week_id"],
            week_id=r["week_id"],
            active=float(r["bankroll_after"] or 0.0),
            locked=float(r["locked_after"] or 0.0),
            total=float(r["bankroll_after"] or 0.0)
                  + float(r["locked_after"] or 0.0),
        ))
    return series


def compute_q_drift(
    db: WebuiDB, *, live_db_path: str | Path, days: int = 90,
) -> Dict[str, Any]:
    """Compute leg-level q on actually-placed legs over the last N days,
    using live_db settlements to determine hit. Returns
    ``dict(n_legs, hit_rate, implied_p, q, baseline_q, drift)``.

    baseline_q = 0.71 (overall STRAT measure on historical data).
    """
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    live_path = Path(live_db_path)
    if not live_path.exists():
        return dict(n_legs=0, q=None, drift=None, days=days)
    conn = sqlite3.connect(str(live_path))
    legs_total = 0; legs_hit = 0; sum_implied_p = 0.0
    try:
        for plan_meta in db.list_plans():
            wk = plan_meta["plan_id"]
            full = db.get_plan(wk)
            if not full or not full.get("plan", {}).get("tickets"):
                continue
            placed_ts = plan_meta.get("placed_ts") or full.get("created_ts") or ""
            if placed_ts and placed_ts < cutoff:
                continue
            seen = set()  # uniq legs per plan
            for ticket in full["plan"]["tickets"]:
                for leg in ticket.get("legs", []):
                    key = (leg.get("match_id"), leg.get("selection"))
                    if not key[0] or key in seen: continue
                    seen.add(key)
                    sp = float(leg.get("sp") or 0)
                    if sp < 1.01: continue
                    row = conn.execute(
                        "SELECT result_code FROM settlements WHERE match_id=?",
                        (key[0],)).fetchone()
                    if not row or row[0] is None: continue
                    legs_total += 1
                    sum_implied_p += 1 / (sp * 0.65)
                    if str(row[0]) == str(key[1]):
                        legs_hit += 1
    finally:
        conn.close()
    if legs_total == 0:
        return dict(n_legs=0, q=None, drift=None, days=days,
                    baseline_q=0.71)
    hit_rate = legs_hit / legs_total
    avg_implied = sum_implied_p / legs_total
    q = hit_rate / avg_implied if avg_implied > 0 else 0
    baseline = 0.71
    return dict(n_legs=legs_total, n_hits=legs_hit, hit_rate=hit_rate,
                implied_p=avg_implied, q=q, baseline_q=baseline,
                drift=q - baseline, days=days)


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

    # 当前 drawdown（实时 — 用于警报）
    current_total = state.active + state.locked
    all_time_peak = max((s["total"] for s in series), default=current_total)
    current_dd = (all_time_peak - current_total) / all_time_peak if all_time_peak > 0 else 0.0

    return dict(
        n_weeks=n_weeks,
        n_hits=n_hits,
        current_dd=current_dd,
        peak_bankroll=all_time_peak,
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


def settlement_progress(
    db: WebuiDB,
    live_db_path: str | Path,
) -> Dict[str, Dict[str, int]]:
    """For each plan that's been placed but not booked, count how many of its
    matches are settled. Returns ``{plan_id: {settled, total, pct}}``."""
    out: Dict[str, Dict[str, int]] = {}
    live_path = Path(live_db_path)
    if not live_path.exists():
        return out
    conn = sqlite3.connect(str(live_path))
    try:
        for plan_meta in db.list_plans():
            week_id = plan_meta["plan_id"]
            if db.has_settlement(week_id):
                continue
            full = db.get_plan(week_id)
            if not full or not full.get("plan", {}).get("tickets"):
                continue
            mids = set()
            for t in full["plan"]["tickets"]:
                for leg in t.get("legs", []):
                    if leg.get("match_id"):
                        mids.add(leg["match_id"])
            if not mids:
                continue
            placeholders = ",".join("?" * len(mids))
            row = conn.execute(
                f"SELECT COUNT(*) FROM settlements WHERE match_id IN ({placeholders})",
                tuple(mids),
            ).fetchone()
            settled = int(row[0]) if row else 0
            total = len(mids)
            out[week_id] = dict(settled=settled, total=total,
                                 pct=round(100 * settled / total, 0) if total else 0)
    finally:
        conn.close()
    return out


def match_status_for_plan(
    db: WebuiDB,
    live_db_path: str | Path,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """For the most recent placed/unsettled plan, return per-match status grouped
    into ``completed`` / ``live`` / ``upcoming`` lists.

    Each match dict includes:
      match_id, kickoff_ts, league, home, away, handicap, our_pick (selection),
      our_pick_label (胜/平/负), status, score (if completed), result_code,
      hit (bool, if completed), winning_sp.
    """
    now = now or datetime.now(timezone.utc)
    out: Dict[str, Any] = {"completed": [], "live": [], "upcoming": [],
                            "plan_id": None, "placed_ts": None,
                            "n_tickets": 0, "empty_placed": False}

    # Prefer the latest placed-but-unsettled plan (so dashboard matches history).
    # Fall back to latest *unsettled* plan with tickets. Already-settled plans
    # belong to history, not current status.
    plan_meta = None
    for p in db.list_plans():
        if p.get("placed_ts") and not db.has_settlement(p["plan_id"]):
            plan_meta = db.get_plan(p["plan_id"])
            break
    if plan_meta is None:
        for p in db.list_plans():
            if db.has_settlement(p["plan_id"]):
                continue
            meta = db.get_plan(p["plan_id"])
            if meta and meta.get("plan", {}).get("tickets"):
                plan_meta = meta
                break
    if not plan_meta:
        return out

    plan = plan_meta["plan"]
    tickets = plan.get("tickets", []) or []
    out["plan_id"] = plan_meta.get("plan_id")
    out["placed_ts"] = plan_meta.get("placed_ts")
    out["n_tickets"] = len(tickets)
    out["empty_placed"] = bool(plan_meta.get("placed_ts")) and len(tickets) == 0

    # Gather (match_id, our_pick) for this plan
    picks_by_match: Dict[str, set] = {}
    leg_meta_by_match: Dict[str, Dict[str, Any]] = {}
    for ticket in plan.get("tickets", []):
        for leg in ticket.get("legs", []):
            mid = leg.get("match_id")
            if not mid:
                continue
            picks_by_match.setdefault(mid, set()).add(int(leg.get("selection", -1)))
            leg_meta_by_match.setdefault(mid, dict(
                match_id=mid, kickoff_ts=leg.get("kickoff_ts"),
                league=leg.get("league"), home=leg.get("home"),
                away=leg.get("away"), handicap=leg.get("handicap"),
                sp=leg.get("sp"),
            ))

    if not picks_by_match:
        return out

    # Query Live Collector for match status + settlement
    live_path = Path(live_db_path)
    if not live_path.exists():
        # No live data — everything is "unknown" upcoming
        for mid, meta in leg_meta_by_match.items():
            meta["our_picks"] = sorted(picks_by_match[mid])
            meta["status"] = "upcoming"
            out["upcoming"].append(meta)
        out["upcoming"].sort(key=lambda x: x.get("kickoff_ts") or "")
        return out

    sel_label = {3: "胜", 1: "平", 0: "负"}
    conn = sqlite3.connect(str(live_path))
    try:
        for mid, meta in leg_meta_by_match.items():
            picks = sorted(picks_by_match[mid])
            meta["our_picks"] = picks
            meta["our_picks_label"] = "/".join(sel_label.get(p, str(p)) for p in picks)
            # Try settlement first
            row = conn.execute(
                "SELECT fthg, ftag, result_code, winning_sp FROM settlements WHERE match_id=?",
                (mid,)
            ).fetchone()
            if row and row[0] is not None:
                fthg, ftag, result_code, winning_sp = row
                meta["score"] = f"{int(fthg)}-{int(ftag)}"
                try:
                    rcode = int(result_code) if result_code is not None else None
                except (TypeError, ValueError):
                    rcode = None
                meta["result_code"] = rcode
                meta["result_label"] = sel_label.get(rcode, str(result_code))
                meta["winning_sp"] = winning_sp
                meta["hit"] = rcode in picks if rcode is not None else None
                meta["status"] = "completed"
                out["completed"].append(meta)
                continue
            # Otherwise classify by kickoff time
            kt_str = meta.get("kickoff_ts")
            if kt_str:
                try:
                    kt = datetime.fromisoformat(kt_str.replace("Z", "+00:00"))
                    if kt.tzinfo is None:
                        # Scraper stores naive kickoff in HK time (UTC+8).
                        kt = kt.replace(tzinfo=timezone(timedelta(hours=8)))
                except ValueError:
                    kt = None
                if kt:
                    delta_min = (now - kt).total_seconds() / 60
                    if delta_min < 0:
                        meta["status"] = "upcoming"
                        meta["minutes_to_start"] = -int(delta_min)
                        out["upcoming"].append(meta)
                    elif delta_min < 130:  # 90 min + ~40 min buffer for settlement
                        meta["status"] = "live"
                        meta["minutes_in"] = int(delta_min)
                        out["live"].append(meta)
                    else:
                        meta["status"] = "pending_settlement"
                        meta["minutes_since_kickoff"] = int(delta_min)
                        out["live"].append(meta)
                    continue
            # No kickoff info
            meta["status"] = "unknown"
            out["upcoming"].append(meta)
    finally:
        conn.close()

    # Sort each group
    out["completed"].sort(key=lambda x: x.get("kickoff_ts") or "", reverse=True)
    out["live"].sort(key=lambda x: x.get("kickoff_ts") or "")
    out["upcoming"].sort(key=lambda x: x.get("kickoff_ts") or "")
    return out


# ----------------------------------------------------------------------
# XLSX export of recommended plan
# ----------------------------------------------------------------------

def plan_to_xlsx(plan: Dict[str, Any], week_id: str) -> bytes:
    """Render a recommended plan to xlsx bytes for printing or sharing.

    Layout:
      Sheet 1 "汇总" — meta + stats per ticket (one row per ticket)
      Sheet 2 "下注单" — one row per leg, grouped by ticket (for filling
                       投注单 at彩票站)
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    SEL_LABEL = {"3": "胜", "1": "平", "0": "负", 3: "胜", 1: "平", 0: "负"}
    HEADER_FILL = PatternFill("solid", fgColor="B04A2F")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
    THIN = Side(border_style="thin", color="C8C2B3")
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    CENTER = Alignment(horizontal="center", vertical="center")
    LEFT = Alignment(horizontal="left", vertical="center")

    def _style_header_row(ws, row_idx: int, n_cols: int):
        for c in range(1, n_cols + 1):
            cell = ws.cell(row=row_idx, column=c)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = CENTER
            cell.border = BORDER

    def _border_range(ws, r1, c1, r2, c2):
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                ws.cell(row=r, column=c).border = BORDER

    wb = Workbook()

    # --- Sheet 1: 汇总 ---
    ws1 = wb.active
    ws1.title = "汇总"
    ws1["A1"] = f"北单组合票推荐 · {week_id}"
    ws1["A1"].font = Font(bold=True, size=14, color="B04A2F")
    ws1.merge_cells("A1:H1")

    meta_rows = [
        ("候选场次", plan.get("n_open_matches", 0)),
        ("合格腿数", plan.get("n_qualified_legs", 0)),
        ("推荐组合票数", len(plan.get("tickets", []))),
        ("总下注", f"{plan.get('total_stake', 0)} 元"),
        ("期望回收", f"{plan.get('expected_total_return', 0):,.0f} 元"),
        ("生成时间", plan.get("generated_ts", "")),
    ]
    for i, (k, v) in enumerate(meta_rows, start=3):
        ws1.cell(row=i, column=1, value=k).font = Font(bold=True)
        ws1.cell(row=i, column=2, value=v)

    headers = ["#", "组合腿（场次:选项@SP）", "联合 SP",
               "单注", "倍数 (n_tickets)", "总下注", "单票奖金", "免税?", "EV"]
    start_row = len(meta_rows) + 5
    for c, h in enumerate(headers, start=1):
        ws1.cell(row=start_row, column=c, value=h)
    _style_header_row(ws1, start_row, len(headers))

    for i, t in enumerate(plan.get("tickets", []), start=1):
        row = start_row + i
        legs_str = " + ".join(
            f"{leg.get('match_id')}:{SEL_LABEL.get(leg.get('selection'), leg.get('selection'))}@{leg.get('sp'):.2f}"
            for leg in t.get("legs", [])
        )
        ws1.cell(row=row, column=1, value=i).alignment = CENTER
        ws1.cell(row=row, column=2, value=legs_str).alignment = LEFT
        ws1.cell(row=row, column=3, value=round(t.get("joint_sp", 0), 2)).alignment = CENTER
        ws1.cell(row=row, column=4, value=t.get("stake_per_ticket", 0)).alignment = CENTER
        ws1.cell(row=row, column=5, value=t.get("n_tickets", 0)).alignment = CENTER
        ws1.cell(row=row, column=6, value=t.get("total_stake", 0)).alignment = CENTER
        ws1.cell(row=row, column=7, value=round(t.get("prize_per_ticket", 0), 0)).alignment = CENTER
        ws1.cell(row=row, column=8, value="✓" if t.get("is_tax_free") else "✗ 税").alignment = CENTER
        ws1.cell(row=row, column=9, value=round(t.get("ev", 0), 3)).alignment = CENTER

    n_tickets = len(plan.get("tickets", []))
    if n_tickets:
        _border_range(ws1, start_row + 1, 1, start_row + n_tickets, len(headers))

    # Set column widths
    widths = [5, 60, 10, 8, 18, 10, 12, 9, 8]
    for c, w in enumerate(widths, start=1):
        ws1.column_dimensions[get_column_letter(c)].width = w

    # --- Sheet 2: 下注单（leg-level for filling 投注单） ---
    ws2 = wb.create_sheet("下注单")
    ws2["A1"] = f"实际下注操作清单 · {week_id} · 按此填投注单"
    ws2["A1"].font = Font(bold=True, size=14, color="B04A2F")
    ws2.merge_cells("A1:I1")

    headers2 = ["票#", "期号", "场次序号", "联赛", "主队", "客队",
                "开赛时间", "选项", "SP"]
    start2 = 3
    for c, h in enumerate(headers2, start=1):
        ws2.cell(row=start2, column=c, value=h)
    _style_header_row(ws2, start2, len(headers2))

    cur_row = start2 + 1
    for ticket_no, t in enumerate(plan.get("tickets", []), start=1):
        for leg in t.get("legs", []):
            mid = str(leg.get("match_id", ""))
            # match_id is typically "期号_序号"
            if "_" in mid:
                expect, match_no = mid.split("_", 1)
            else:
                expect, match_no = "", mid
            ws2.cell(row=cur_row, column=1, value=ticket_no).alignment = CENTER
            ws2.cell(row=cur_row, column=2, value=expect).alignment = CENTER
            ws2.cell(row=cur_row, column=3, value=match_no).alignment = CENTER
            ws2.cell(row=cur_row, column=4, value=leg.get("league", "")).alignment = LEFT
            ws2.cell(row=cur_row, column=5, value=leg.get("home", "")).alignment = LEFT
            ws2.cell(row=cur_row, column=6, value=leg.get("away", "")).alignment = LEFT
            ws2.cell(row=cur_row, column=7, value=fmt_hk(leg.get("kickoff_ts"))).alignment = CENTER
            sel_cell = ws2.cell(row=cur_row, column=8,
                                value=SEL_LABEL.get(leg.get("selection"), leg.get("selection")))
            sel_cell.alignment = CENTER
            sel_cell.font = Font(bold=True, size=12, color="B04A2F")
            ws2.cell(row=cur_row, column=9, value=round(leg.get("sp", 0), 2)).alignment = CENTER
            cur_row += 1
        # blank separator row between tickets
        cur_row += 1

    if cur_row > start2 + 1:
        _border_range(ws2, start2 + 1, 1, cur_row - 1, len(headers2))

    widths2 = [6, 8, 8, 16, 22, 22, 22, 8, 8]
    for c, w in enumerate(widths2, start=1):
        ws2.column_dimensions[get_column_letter(c)].width = w

    # Footer note on sheet 2
    note_row = cur_row + 2
    note_text = (
        f"说明：每个 票# 内多行 = 该票的 4 关组合。"
        f"在彩票站填投注单时按 过关方式 选 4 串 1，"
        f"每行勾选对应的选项（胜/平/负）。倍数 = 单票 倍数 列。"
        f"共 {n_tickets} 张票需购买。"
    )
    ws2.cell(row=note_row, column=1, value=note_text).font = Font(italic=True, color="666666")
    ws2.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=9)

    # --- Sheet 3: 按比赛分组（打票顺序优化） ---
    ws3 = wb.create_sheet("按比赛分组")
    ws3["A1"] = f"打票顺序参考（同场比赛连续填）· {week_id}"
    ws3["A1"].font = Font(bold=True, size=14, color="B04A2F")
    ws3.merge_cells("A1:G1")

    headers3 = ["序号", "场次", "联赛", "主队 vs 客队", "开赛", "出现票#", "勾"]
    start3 = 3
    for c, h in enumerate(headers3, start=1):
        ws3.cell(row=start3, column=c, value=h)
    _style_header_row(ws3, start3, len(headers3))

    # collect: match_id → list of (ticket_no, selection)
    match_to_tickets: dict = {}
    match_meta: dict = {}
    for ticket_no, t in enumerate(plan.get("tickets", []), start=1):
        for leg in t.get("legs", []):
            mid = str(leg.get("match_id") or "")
            if not mid: continue
            match_to_tickets.setdefault(mid, []).append(
                (ticket_no, SEL_LABEL.get(leg.get("selection"), str(leg.get("selection")))))
            match_meta.setdefault(mid, dict(
                league=leg.get("league") or "", home=leg.get("home") or "",
                away=leg.get("away") or "", kickoff=leg.get("kickoff_ts") or "",
                handicap=leg.get("handicap")))
    # sort by kickoff
    sorted_mids = sorted(match_to_tickets.keys(),
                         key=lambda m: match_meta[m].get("kickoff", "") or "")
    cur_row = start3 + 1
    for i, mid in enumerate(sorted_mids, start=1):
        m = match_meta[mid]
        tickets_str = ", ".join(f"#{tn}({sel})" for tn, sel in match_to_tickets[mid])
        ws3.cell(row=cur_row, column=1, value=i).alignment = CENTER
        ws3.cell(row=cur_row, column=2, value=mid).alignment = CENTER
        ws3.cell(row=cur_row, column=3, value=m["league"]).alignment = LEFT
        match_str = f"{m['home']} vs {m['away']}"
        if m.get("handicap") is not None:
            match_str += f" ({m['handicap']:+g})"
        ws3.cell(row=cur_row, column=4, value=match_str).alignment = LEFT
        ws3.cell(row=cur_row, column=5, value=fmt_hk(m["kickoff"])).alignment = CENTER
        ws3.cell(row=cur_row, column=6, value=tickets_str).alignment = LEFT
        ws3.cell(row=cur_row, column=7, value="☐").alignment = CENTER  # 已打勾位
        cur_row += 1
    if cur_row > start3 + 1:
        _border_range(ws3, start3 + 1, 1, cur_row - 1, len(headers3))
    widths3 = [6, 14, 14, 36, 18, 30, 6]
    for c, w in enumerate(widths3, start=1):
        ws3.column_dimensions[get_column_letter(c)].width = w
    ws3.cell(row=cur_row + 1, column=1,
             value=f"共 {len(sorted_mids)} 场比赛 → 同场所有票连续填写，操作员可逐场打勾。"
                   ).font = Font(italic=True, color="666666")
    ws3.merge_cells(start_row=cur_row+1, start_column=1, end_row=cur_row+1, end_column=7)

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
