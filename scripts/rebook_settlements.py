"""Reconcile settlements_log against current `settlements` table.

Per-match settle path occasionally writes a transient/incorrect score
(zqdc page returns running score for status=4 rows, etc.). Kaijiang later
overwrites with the correct score, but `settlements_log` was already
booked using the wrong score → bankroll drifts.

This script:
  1. For each row in settlements_log, re-run `reconcile_plan` against
     the current settlements snapshot.
  2. If the recomputed n_hits / payout / pnl differs, rewrite the
     settlements_log row AND retroactively adjust `bankroll_after` for
     it AND every later row (so the cumulative curve stays consistent).
  3. Restore the LIVE bankroll state to the new last-row bankroll_after.

Dry-run by default; pass --apply to commit.
"""
from __future__ import annotations
import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.webui.db import WebuiDB  # noqa: E402
from src.webui import services  # noqa: E402
from src.phase5a.reconcile import reconcile_plan  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--webui-db", default=str(ROOT / "data" / "webui.db"))
    ap.add_argument("--live-db", default=str(ROOT / "data" / "beidan_live.db"))
    ap.add_argument("--plans-dir", default=str(ROOT / "data" / "phase5a_plans"))
    ap.add_argument("--pnl-log", default=str(ROOT / "data" / "phase5a_pnl" / "pnl.csv"))
    ap.add_argument("--apply", action="store_true",
                    help="Commit changes (default dry-run).")
    args = ap.parse_args()

    db = WebuiDB(args.webui_db)

    rows = db.list_settlements()
    if not rows:
        print("settlements_log is empty.")
        return 0

    # Sort by settled_ts ascending so bankroll cumulative re-roll is correct
    rows = sorted(rows, key=lambda r: r["settled_ts"])
    plans_dir = Path(args.plans_dir)

    state = services.get_state(db)
    # Walk backwards through settlements_log entries to find the bankroll
    # BEFORE the first booked plan (cumulative undo).
    cumulative_pnl_old = sum(float(r["week_pnl"]) for r in rows)
    bankroll_before_first = state.active - cumulative_pnl_old
    print(f"Current bankroll.active = {state.active:.2f}")
    print(f"Cumulative booked PnL  = {cumulative_pnl_old:+.2f}")
    print(f"→ bankroll before first booked plan = {bankroll_before_first:.2f}\n")

    new_bankroll = bankroll_before_first
    changed_rows = []
    fresh_rows = []

    for r in rows:
        pid = r["week_id"]
        plan_path = plans_dir / f"{pid}.json"
        if not plan_path.exists():
            print(f"⚠  {pid}: plan file missing, leaving unchanged")
            new_bankroll += float(r["week_pnl"])
            fresh_rows.append({**r, "bankroll_after": new_bankroll})
            continue

        try:
            res = reconcile_plan(plan_path, args.live_db, args.pnl_log)
        except Exception as e:
            print(f"⚠  {pid}: reconcile failed ({e})")
            new_bankroll += float(r["week_pnl"])
            fresh_rows.append({**r, "bankroll_after": new_bankroll})
            continue

        old_hits = r.get("n_hits", 0)
        old_pnl = float(r["week_pnl"])
        old_payout = float(r["week_payout"])
        old_stake = float(r["week_stake"])

        # SAFETY: if stake from plan file != stake in settlements_log, the
        # plan file has been overwritten since booking (e.g., the user hit
        # "立即生成" on dashboard which clobbered the original). Re-booking
        # with the new file would alter PnL based on a plan that was never
        # bet. Skip and warn instead.
        if abs(float(res.total_stake) - old_stake) > 0.01:
            print(f"⚠  {pid}: plan-file stake ({res.total_stake}) != logged "
                  f"stake ({old_stake:.0f}); plan file was overwritten — "
                  f"keeping original booking")
            new_bankroll += old_pnl
            fresh_rows.append({**r, "bankroll_after": new_bankroll})
            continue

        commission_rate = float(db.get_config("commission_rate") or 0.0)
        commission = float(res.total_stake) * commission_rate
        new_pnl = float(res.net_pnl) + commission
        new_bankroll += new_pnl

        changed = (
            int(res.n_winning_tickets) != int(old_hits)
            or abs(float(res.gross_payout) - old_payout) > 0.01
            or abs(new_pnl - old_pnl) > 0.01
        )

        if changed:
            print(f"✱  {pid}: hits {old_hits}→{int(res.n_winning_tickets)}  "
                  f"payout {old_payout:.2f}→{float(res.gross_payout):.2f}  "
                  f"PnL {old_pnl:+.2f}→{new_pnl:+.2f}  "
                  f"bankroll_after {float(r['bankroll_after']):.2f}→{new_bankroll:.2f}")
            changed_rows.append(pid)
        else:
            print(f"   {pid}: unchanged  bankroll_after "
                  f"{float(r['bankroll_after']):.2f}→{new_bankroll:.2f}")

        fresh_rows.append(dict(
            week_id=pid, settled_ts=r["settled_ts"],
            n_combos=int(res.n_tickets),
            n_hits=int(res.n_winning_tickets),
            week_stake=float(res.total_stake),
            week_payout=float(res.gross_payout),
            week_pnl=new_pnl,
            bankroll_after=new_bankroll,
            locked_after=r.get("locked_after", 0.0),
            skimmed=r.get("skimmed", 0.0),
        ))

    print(f"\nChanged rows: {len(changed_rows)} / {len(rows)}")
    print(f"New live bankroll.active = {new_bankroll:.2f} "
          f"(delta {new_bankroll - state.active:+.2f})")

    if not args.apply:
        print("\n[DRY RUN — pass --apply to commit]")
        return 0

    # Apply
    with db.tx() as cur:
        cur.execute("DELETE FROM settlements_log")
        for r in fresh_rows:
            cur.execute(
                "INSERT INTO settlements_log(week_id, settled_ts, n_combos, "
                "n_hits, week_stake, week_payout, week_pnl, bankroll_after, "
                "locked_after, skimmed) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (r["week_id"], r["settled_ts"], r["n_combos"], r["n_hits"],
                 r["week_stake"], r["week_payout"], r["week_pnl"],
                 r["bankroll_after"], r["locked_after"], r["skimmed"]),
            )

    # Update live bankroll state
    new_state = type(state)(
        initial=state.initial,
        active=new_bankroll,
        locked=state.locked,
        peak=max(float(state.peak or 0.0), new_bankroll),
    )
    services.persist_state(db, new_state)
    db.auto_log("autocheck", "warn",
                f"settlements_log re-reconciled; {len(changed_rows)} rows "
                f"changed; bankroll {state.active:.2f}→{new_bankroll:.2f}",
                services._utcnow_iso(),
                details=dict(changed_plans=changed_rows,
                             delta=new_bankroll - state.active))
    print(f"\n✅ Committed. settlements_log rewritten, bankroll updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
