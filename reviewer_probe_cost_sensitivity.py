#!/usr/bin/env python3
"""Reviewer-owned independent probe for A3 cost/rebate/tax sensitivity.

Reads SQLite JSON directly; does not import scripts/analyze_cost_sensitivity.py or WebuiDB.
"""
import json
import sqlite3
from collections import defaultdict

RR = 0.65
TAX_CLIFF = 10000.0
TAX_RATE = 0.20
WEBUI = "data/webui.db"
LIVE = "data/beidan_live.db"
REBATES = [0.0, 0.02, 0.05, 0.07, 0.10]

settle = {}
with sqlite3.connect(LIVE) as con:
    for match_id, result_code, winning_sp in con.execute(
        "select match_id, result_code, winning_sp from settlements where result_code is not null order by match_id"
    ):
        settle[str(match_id)] = (str(result_code), None if winning_sp is None else float(winning_sp))

tickets = []
plans_seen = 0
with sqlite3.connect(WEBUI) as con:
    for plan_id, raw in con.execute("select plan_id, plan_json from plans order by plan_id"):
        plans_seen += 1
        obj = json.loads(raw)
        # Handle both current raw shape and wrapped shape defensively.
        plan = obj.get("plan", obj)
        for tk in plan.get("tickets", []):
            legs = tk.get("legs") or []
            if not legs:
                continue
            all_hit = True
            win_prod = 1.0
            settled = True
            for leg in legs:
                mid = str(leg.get("match_id"))
                sel = leg.get("selection")
                if sel is None or mid not in settle:
                    settled = False
                    break
                result_code, winning_sp = settle[mid]
                if result_code == str(sel):
                    if winning_sp is None:
                        settled = False
                        break
                    win_prod *= winning_sp
                else:
                    all_hit = False
            if not settled:
                continue
            stake = float(tk.get("total_stake") or 0)
            spt = float(tk.get("stake_per_ticket") or 0)
            nt = int(tk.get("n_tickets") or 1)
            if stake <= 0:
                continue
            tickets.append({
                "n": len(legs),
                "stake": stake,
                "spt": spt,
                "nt": nt,
                "all_hit": all_hit,
                "win_prod": win_prod,
            })

by_n = defaultdict(list)
for t in tickets:
    by_n[t["n"]].append(t)

def calc(rows):
    stake = sum(t["stake"] for t in rows)
    payout = sum(t["spt"] * t["nt"] * t["win_prod"] * RR for t in rows if t["all_hit"])
    roi = payout / stake - 1 if stake else float("nan")
    return stake, payout, roi

summary = {
    "plans_seen": plans_seen,
    "settled_ticket_count": len(tickets),
    "all_hit_count": sum(t["all_hit"] for t in tickets),
    "by_n": {},
}
for n in sorted(by_n):
    stake, payout, base_roi = calc(by_n[n])
    summary["by_n"][str(n)] = {
        "tickets": len(by_n[n]),
        "stake": round(stake, 6),
        "payout": round(payout, 6),
        "base_roi_pct": round(base_roi * 100, 6),
        "break_even_rebate_pct": round(max(0.0, -base_roi) * 100, 6),
        "roi_with_rebates_pct": {str(int(r*100)): round((base_roi + r) * 100, 6) for r in REBATES},
    }
stake, payout, base_roi = calc(tickets)
summary["all"] = {
    "tickets": len(tickets),
    "stake": round(stake, 6),
    "payout": round(payout, 6),
    "base_roi_pct": round(base_roi * 100, 6),
    "break_even_rebate_pct": round(max(0.0, -base_roi) * 100, 6),
    "roi_with_rebates_pct": {str(int(r*100)): round((base_roi + r) * 100, 6) for r in REBATES},
}

# Tax/splitting probes. Report both the submitted "tax on excess above 10k" convention and
# the stricter full-prize tax convention; both are zero in this data because no winning ticket exceeds the cliff.
bite_gt = 0
bite_ge = 0
tax_excess_saved = 0.0
tax_full_prize_saved = 0.0
max_one_ticket_prize = 0.0
for t in tickets:
    if not t["all_hit"]:
        continue
    intended_stake = t["spt"] * t["nt"]
    prize_one_ticket = intended_stake * t["win_prod"] * RR
    max_one_ticket_prize = max(max_one_ticket_prize, prize_one_ticket)
    if prize_one_ticket > TAX_CLIFF:
        bite_gt += 1
        tax_excess_saved += (prize_one_ticket - TAX_CLIFF) * TAX_RATE
        tax_full_prize_saved += prize_one_ticket * TAX_RATE
    if prize_one_ticket >= TAX_CLIFF:
        bite_ge += 1
summary["tax"] = {
    "winning_tickets": sum(t["all_hit"] for t in tickets),
    "one_ticket_prize_gt_10000": bite_gt,
    "one_ticket_prize_ge_10000": bite_ge,
    "max_one_ticket_prize": round(max_one_ticket_prize, 6),
    "tax_saved_excess_only": round(tax_excess_saved, 6),
    "tax_saved_full_prize_basis": round(tax_full_prize_saved, 6),
}

print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
