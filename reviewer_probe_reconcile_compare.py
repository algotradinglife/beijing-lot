#!/usr/bin/env python3
"""Compare PnL-attribution semantics against the production reconcile semantics.

This is a reviewer-owned probe: it does not import scripts/analyze_pnl_attribution.py.
It reads webui.db and beidan_live.db directly and computes two ticket sets:
  1) attribution_all_legs_settled: requires every leg to have a settlement row
     (the submitted script's inclusion rule).
  2) reconcile_semantics: a ticket is settled lost as soon as any leg has lost;
     only tickets with no lost leg and missing legs remain pending, matching
     src/phase5a/reconcile.py.
"""
from __future__ import annotations

import json, math, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RR = 0.65
WEBUI = ROOT / "data" / "webui.db"
LIVE = ROOT / "data" / "beidan_live.db"


def load():
    w = sqlite3.connect(WEBUI)
    l = sqlite3.connect(LIVE)
    settle = {str(mid): (str(rc), float(wsp) if wsp is not None else None)
              for mid, rc, wsp in l.execute("select match_id,result_code,winning_sp from settlements where result_code is not null")}
    log = {str(week): {"stake": float(stake or 0), "payout": float(payout or 0), "hits": int(hits or 0), "combos": int(combos or 0)}
           for week, stake, payout, hits, combos in w.execute("select week_id,week_stake,week_payout,n_hits,n_combos from settlements_log")}
    plans = []
    for pid, plan_json in w.execute("select plan_id,plan_json from plans"):
        if str(pid) in log:
            plans.append((str(pid), json.loads(plan_json)))
    return settle, log, plans


def ticket_pay(tk, sp_kind, settle):
    joint = 1.0
    for leg in tk["legs"]:
        if sp_kind == "plan":
            sp = float(leg["sp"])
        else:
            sp = settle[str(leg["match_id"])][1]
        if sp is None or not math.isfinite(sp) or sp <= 0:
            return None
        joint *= sp
    return float(tk["stake_per_ticket"]) * int(tk.get("n_tickets") or 1) * joint * RR


def main():
    settle, log, plans = load()
    strict = []
    recon = []
    pending_recon = []
    strict_skips = []
    per_week_recon = defaultdict(lambda: {"stake": 0.0, "payout": 0.0, "hits": 0, "tickets": 0})
    for pid, obj in plans:
        for tk in obj.get("tickets", []):
            legs = tk.get("legs") or []
            stake = float(tk.get("total_stake") or 0)
            # strict all-legs-settled inclusion, matching submitted attribution script
            strict_ok = True
            strict_all_hit = True
            for leg in legs:
                mid = str(leg["match_id"])
                if mid not in settle:
                    strict_ok = False
                    break
                if settle[mid][0] != str(leg["selection"]):
                    strict_all_hit = False
            if strict_ok:
                strict.append((pid, tk, strict_all_hit, stake))
            else:
                strict_skips.append((pid, tk.get("ticket_no"), stake))
            # production reconcile semantics
            any_lost = False
            any_missing = False
            for leg in legs:
                mid = str(leg["match_id"])
                if mid not in settle:
                    any_missing = True
                elif settle[mid][0] != str(leg["selection"]):
                    any_lost = True
            if any_lost:
                all_hit = False
            elif any_missing:
                pending_recon.append((pid, tk.get("ticket_no"), stake))
                continue
            else:
                all_hit = True
            payout = ticket_pay(tk, "win", settle) if all_hit else 0.0
            if payout is None:
                pending_recon.append((pid, tk.get("ticket_no"), stake))
                continue
            recon.append((pid, tk, all_hit, stake, payout))
            per_week_recon[pid]["stake"] += stake
            per_week_recon[pid]["payout"] += payout
            per_week_recon[pid]["tickets"] += 1
            per_week_recon[pid]["hits"] += int(all_hit)

    def summarize(rows, strict_mode=False):
        stake = sum(r[3] for r in rows)
        if strict_mode:
            pay_win = sum(ticket_pay(r[1], "win", settle) or 0 for r in rows if r[2])
            pay_plan = sum(ticket_pay(r[1], "plan", settle) or 0 for r in rows if r[2])
        else:
            pay_win = sum(r[4] for r in rows)
            pay_plan = sum(ticket_pay(r[1], "plan", settle) or 0 for r in rows if r[2])
        return {"tickets": len(rows), "stake": stake, "hits": sum(1 for r in rows if r[2]),
                "payout_win": pay_win, "R_actual": pay_win/stake if stake else None,
                "R_planSP": pay_plan/stake if stake else None,
                "selection": (pay_plan/stake)/RR if stake else None,
                "drift": pay_win/pay_plan if pay_plan else None}

    log_totals = {"weeks": len(log), "stake": sum(x["stake"] for x in log.values()),
                  "payout": sum(x["payout"] for x in log.values()),
                  "hits": sum(x["hits"] for x in log.values()),
                  "combos": sum(x["combos"] for x in log.values())}
    week_mismatches = []
    for pid, calc in per_week_recon.items():
        lg = log[pid]
        if abs(calc["stake"] - lg["stake"]) > 1e-6 or abs(calc["payout"] - lg["payout"]) > 0.01 or calc["hits"] != lg["hits"]:
            week_mismatches.append({"week": pid, "calc": calc, "log": lg})

    print(json.dumps({
        "strict_all_legs_settled": summarize(strict, True),
        "reconcile_semantics": summarize(recon, False),
        "settlements_log_totals": log_totals,
        "strict_skipped_tickets": {"count": len(strict_skips), "stake": sum(x[2] for x in strict_skips), "examples": strict_skips[:10]},
        "reconcile_pending_tickets": {"count": len(pending_recon), "stake": sum(x[2] for x in pending_recon), "examples": pending_recon[:10]},
        "week_mismatches_count": len(week_mismatches),
        "week_mismatch_examples": week_mismatches[:10],
    }, indent=2, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
