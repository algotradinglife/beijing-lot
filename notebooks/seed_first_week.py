"""Seed dashboard with first-week test result.

Pulls all matches with kickoff in [2026-05-02, 2026-05-04) (yesterday + today),
runs the active strategy filter (build_weekly_plan with mix3 + per-N params,
total max_combos=100), saves as plan 2026-W18, marks placed, then reconciles
against Live Collector settlements to produce a real PnL row.

Idempotent — wipes existing 2026-W18 plan + settlement before re-seeding.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.phase5a.data_loader import LiveSnapshot
from src.phase5a.filter import NicheConfig
from src.phase5a.planner import build_weekly_plan
from src.webui.db import WebuiDB
from src.webui.services import (
    KELLY_FRACTION, N_LEGS, WEEKLY_STAKE_CAP_FRAC,
    get_state, persist_state, reconcile_pending, save_plan_json,
)

ROOT = Path(__file__).resolve().parents[1]
LIVE_DB = ROOT / "data" / "beidan_live.db"
WEBUI_DB = ROOT / "data" / "webui.db"
PLANS_DIR = ROOT / "data" / "phase5a_plans"
PNL_LOG = ROOT / "data" / "phase5a_pnl" / "pnl.csv"
WEEK_ID = "2026-W18"
DATE_LO = "2026-05-02T00:00:00"
DATE_HI = "2026-05-04T00:00:00"
TARGET_TICKETS = 100


def load_snapshots_in_range(db_path: Path, lo: str, hi: str) -> list[LiveSnapshot]:
    conn = sqlite3.connect(str(db_path))
    # Only matches that have already settled — so reconcile finds outcomes.
    # Pick the latest pre-settlement snapshot with non-null SP per match.
    sql = """
    SELECT m.match_id, m.issue, m.match_idx, m.league, m.kickoff_ts,
           m.home, m.away, m.handicap_line,
           s.sp_3, s.sp_1, s.sp_0, s.snapshot_ts
    FROM matches m
    JOIN settlements x ON x.match_id = m.match_id
    JOIN (
        SELECT s1.* FROM snapshots s1
        JOIN (
            SELECT match_id, MAX(snapshot_ts) AS mts
            FROM snapshots
            WHERE sp_3 IS NOT NULL AND sp_1 IS NOT NULL AND sp_0 IS NOT NULL
            GROUP BY match_id
        ) s2 ON s1.match_id = s2.match_id AND s1.snapshot_ts = s2.mts
    ) s ON s.match_id = m.match_id
    WHERE m.kickoff_ts >= ? AND m.kickoff_ts < ?
    ORDER BY m.kickoff_ts ASC, m.match_idx ASC
    """
    try:
        rows = conn.execute(sql, (lo, hi)).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        out.append(LiveSnapshot(
            match_id=r[0], issue=r[1], match_idx=int(r[2]),
            league=r[3], kickoff_ts=r[4], home=r[5], away=r[6],
            handicap_line=(float(r[7]) if r[7] is not None else None),
            sp_3=float(r[8]), sp_1=float(r[9]), sp_0=float(r[10]),
            snapshot_ts=r[11],
        ))
    return out


def main() -> None:
    db = WebuiDB(str(WEBUI_DB))
    state = get_state(db)
    print(f"Initial bankroll: {state.active:,.0f}")

    snapshots = load_snapshots_in_range(LIVE_DB, DATE_LO, DATE_HI)
    print(f"Loaded {len(snapshots)} matches in [{DATE_LO}, {DATE_HI})")

    cfg = NicheConfig.load()

    # Read strategy config (defaults if not set)
    n_legs = int(db.get_config("n_legs") or N_LEGS)
    kelly_fraction = float(db.get_config("kelly_fraction") or KELLY_FRACTION)
    diversity_lambda = float(db.get_config("diversity_lambda") or 0.5)

    w2 = float(db.get_config("mix_weight_n2") or 0.30)
    w3 = float(db.get_config("mix_weight_n3") or 0.40)
    w4 = float(db.get_config("mix_weight_n4") or 0.30)
    wsum = w2 + w3 + w4
    w2, w3, w4 = w2/wsum, w3/wsum, w4/wsum

    k2 = float(db.get_config("kelly_n2") or kelly_fraction)
    k3 = float(db.get_config("kelly_n3") or kelly_fraction)
    k4 = float(db.get_config("kelly_n4") or kelly_fraction)
    lam = lambda key, default: float(db.get_config(key) if db.get_config(key) is not None else default)
    l2 = lam("lambda_n2", diversity_lambda)
    l3 = lam("lambda_n3", diversity_lambda)
    l4 = lam("lambda_n4", diversity_lambda)

    per_n = {2: (w2, k2, l2), 3: (w3, k3, l3), 4: (w4, k4, l4)}
    print(f"Mix: N=2 ({w2:.2f}, K={k2}, λ={l2}) · "
          f"N=3 ({w3:.2f}, K={k3}, λ={l3}) · "
          f"N=4 ({w4:.2f}, K={k4}, λ={l4})")

    # Allocate target tickets across N by weight
    merged_tickets = []
    total_stake = 0
    expected_return = 0.0
    n_qual_legs = 0
    for n_val, (weight, k_n, lam_n) in per_n.items():
        if weight <= 0:
            continue
        sub_bankroll = state.active * weight
        sub_max_combos = max(1, int(round(TARGET_TICKETS * weight)))
        if sub_bankroll < 100:
            continue
        plan_n = build_weekly_plan(
            snapshots, bankroll=sub_bankroll, niche_config=cfg,
            n_legs=n_val, kelly_fraction=k_n,
            weekly_stake_cap_frac=WEEKLY_STAKE_CAP_FRAC,
            diversity_lambda=lam_n, max_combos=sub_max_combos,
            now=datetime.now(timezone.utc),
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
        print(f"  N={n_val}: {len(pn.get('tickets', []))} tickets, stake={pn.get('total_stake', 0)}")

    if not merged_tickets:
        raise SystemExit("No tickets generated — check filter / data.")

    print(f"Total tickets: {len(merged_tickets)}, stake={total_stake}")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Per-leg appearance counts for diversity viz
    leg_counts: dict = {}
    for ticket in merged_tickets:
        for leg in ticket.get("legs", []):
            key = f"{leg.get('match_id')}:{leg.get('selection')}"
            entry = leg_counts.setdefault(key, dict(
                key=key, match_id=leg.get("match_id"),
                selection=leg.get("selection"),
                home=leg.get("home"), away=leg.get("away"),
                sp=leg.get("sp"), count=0,
            ))
            entry["count"] += 1
    leg_appearance = sorted(leg_counts.values(), key=lambda x: x["count"], reverse=True)
    n_tickets = len(merged_tickets)
    if leg_counts and n_tickets:
        max_count = max(e["count"] for e in leg_counts.values())
        concentration_max_pct = round(100 * max_count / n_tickets, 1)
        shares = [e["count"] / n_tickets for e in leg_counts.values()]
        hhi = round(sum(s * s for s in shares), 4)
        effective_n_legs = round(1.0 / hhi, 2) if hhi > 0 else 0
    else:
        concentration_max_pct = 0
        hhi = 0
        effective_n_legs = 0

    plan_dict = dict(
        plan_id=WEEK_ID,
        generated_at=now_iso,
        bankroll=float(state.active),
        n_legs=n_legs,
        kelly_fraction=kelly_fraction,
        diversity_lambda=diversity_lambda,
        max_combos=TARGET_TICKETS,
        n_legs_config=n_legs,
        n_open_matches=len(snapshots),
        n_qualified_legs=n_qual_legs,
        total_stake=total_stake,
        expected_total_return=expected_return,
        tickets=merged_tickets,
        leg_appearance=leg_appearance,
        concentration_max_pct=concentration_max_pct,
        hhi=hhi,
        effective_n_legs=effective_n_legs,
        mix_enabled=True,
        mix_weights=dict(n2=round(w2, 3), n3=round(w3, 3), n4=round(w4, 3)),
        mix_kelly=dict(n2=k2, n3=k3, n4=k4),
        mix_lambda=dict(n2=l2, n3=l3, n4=l4),
        seeded=True,
    )

    # Wipe existing seed
    with db.tx() as cur:
        cur.execute("DELETE FROM settlements_log WHERE week_id=?", (WEEK_ID,))
        cur.execute("DELETE FROM plans WHERE plan_id=?", (WEEK_ID,))
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    (PLANS_DIR / f"{WEEK_ID}.json").write_text(
        json.dumps(plan_dict, ensure_ascii=False)
    )
    db.upsert_plan(WEEK_ID, now_iso, plan_dict)
    db.mark_placed(WEEK_ID, now_iso)
    print(f"Saved plan {WEEK_ID} with placed_ts={now_iso}")

    # Reset bankroll state to clean baseline (in case prior runs touched it)
    from src.webui.services import BankrollState
    persist_state(db, BankrollState(
        initial=state.initial, active=state.initial,
        locked=0.0, peak=state.initial,
    ))

    # Reconcile against Live Collector settlements
    results = reconcile_pending(
        db, live_db_path=LIVE_DB, plans_dir=PLANS_DIR, pnl_log=PNL_LOG,
    )
    if not results:
        print("⚠ Reconcile produced no settlement — likely some matches still pending.")
        # Diagnose
        conn = sqlite3.connect(str(LIVE_DB))
        mids = {leg["match_id"] for t in merged_tickets for leg in t["legs"]
                if leg.get("match_id")}
        ph = ",".join("?" * len(mids))
        n_settled = conn.execute(
            f"SELECT COUNT(*) FROM settlements WHERE match_id IN ({ph})",
            tuple(mids)).fetchone()[0]
        conn.close()
        print(f"   {n_settled}/{len(mids)} legs have settlements in live DB")
    else:
        for r in results:
            print(f"✓ Settled {r['week_id']}: {r['n_hits']}/{r['n_tickets']} hits, "
                  f"PnL={r['week_pnl']:+,.0f}, bankroll={r['bankroll_after']:,.0f}, "
                  f"locked={r['locked_after']:,.0f}")


if __name__ == "__main__":
    main()
