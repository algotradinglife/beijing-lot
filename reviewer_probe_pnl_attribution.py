#!/usr/bin/env python3
"""Reviewer-owned independent probe for t_b439ab20 / PnL attribution.

Reads the SQLite DBs directly (no import from scripts/analyze_pnl_attribution.py)
and recomputes the headline ticket-level attribution plus several sanity checks.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBUI = ROOT / "data" / "webui.db"
LIVE = ROOT / "data" / "beidan_live.db"
RR = 0.65
RECENT_FROM_ISSUE = "26057"


def fetch_tickets():
    wcon = sqlite3.connect(WEBUI)
    lcon = sqlite3.connect(LIVE)
    settlements = {
        str(mid): (str(rc), float(wsp) if wsp is not None else None)
        for mid, rc, wsp in lcon.execute(
            "select match_id,result_code,winning_sp from settlements where result_code is not null"
        )
    }
    settled_weeks = {str(r[0]) for r in wcon.execute("select week_id from settlements_log")}
    rows = []
    skipped = defaultdict(int)
    stake_mismatch = []
    issue_lengths = defaultdict(int)
    for plan_id, plan_json in wcon.execute("select plan_id, plan_json from plans"):
        if str(plan_id) not in settled_weeks:
            skipped["unsettled_plan"] += 1
            continue
        obj = json.loads(plan_json)
        # plan_json stores the generated plan itself at top-level; WebuiDB.get_plan()
        # wraps it under a "plan" key, but direct SQLite reads do not.
        for tk_i, tk in enumerate(obj.get("tickets", [])):
            legs = tk.get("legs") or []
            if not legs:
                skipped["empty_ticket"] += 1
                continue
            issue = str(legs[0].get("match_id", "")).split("_")[0]
            issue_lengths[len(issue)] += 1
            stake = float(tk.get("total_stake") or 0)
            spt = float(tk.get("stake_per_ticket") or 0)
            nt = int(tk.get("n_tickets") or 1)
            if stake <= 0 or spt <= 0 or nt <= 0:
                skipped["bad_stake"] += 1
                continue
            if abs(stake - spt * nt) > 1e-9:
                stake_mismatch.append((plan_id, tk_i, stake, spt, nt))
            plan_prod = 1.0
            win_prod = 1.0
            hit_list = []
            ok = True
            for lg in legs:
                mid = str(lg.get("match_id"))
                sel = str(lg.get("selection"))
                if mid not in settlements:
                    skipped["missing_settlement_leg"] += 1
                    ok = False
                    break
                rc, wsp = settlements[mid]
                try:
                    plan_sp = float(lg.get("sp"))
                except Exception:
                    skipped["bad_plan_sp"] += 1
                    ok = False
                    break
                if not math.isfinite(plan_sp) or plan_sp <= 0:
                    skipped["bad_plan_sp"] += 1
                    ok = False
                    break
                plan_prod *= plan_sp
                hit = (rc == sel)
                hit_list.append(hit)
                if hit:
                    if wsp is None or not math.isfinite(wsp) or wsp <= 0:
                        skipped["hit_without_valid_winning_sp"] += 1
                        ok = False
                        break
                    win_prod *= wsp
            if not ok:
                continue
            rows.append({
                "plan_id": str(plan_id),
                "issue": issue,
                "n": len(legs),
                "stake": stake,
                "spt": spt,
                "nt": nt,
                "all_hit": all(hit_list),
                "leg_hits": hit_list,
                "plan_prod": plan_prod,
                "win_prod": win_prod,
            })
    return rows, dict(skipped), stake_mismatch, dict(issue_lengths)


def metrics(rows):
    stake = sum(r["stake"] for r in rows)
    pay_win = sum(r["spt"] * r["nt"] * r["win_prod"] * RR for r in rows if r["all_hit"])
    pay_plan = sum(r["spt"] * r["nt"] * r["plan_prod"] * RR for r in rows if r["all_hit"])
    all_hit = sum(1 for r in rows if r["all_hit"])
    out = {
        "tickets": len(rows),
        "stake": stake,
        "all_hit": all_hit,
        "R_actual": pay_win / stake if stake else None,
        "R_planSP": pay_plan / stake if stake else None,
        "selection": (pay_plan / stake) / RR if stake else None,
        "drift": pay_win / pay_plan if pay_plan else None,
    }
    out["roi_pct"] = 100 * (out["R_actual"] - 1) if out["R_actual"] is not None else None
    return out


def by_n(rows):
    legs_global = [h for r in rows for h in r["leg_hits"]]
    global_hr = sum(legs_global) / len(legs_global)
    result = {"global_leg_hit_rate": global_hr, "rows": []}
    buckets = defaultdict(list)
    for r in rows:
        buckets[r["n"]].append(r)
    for n in sorted(buckets):
        rs = buckets[n]
        m = metrics(rs)
        legs = [h for r in rs for h in r["leg_hits"]]
        leg_hr = sum(legs) / len(legs)
        actual_ah = sum(1 for r in rs if r["all_hit"]) / len(rs)
        exp_global = global_hr ** n
        exp_within = leg_hr ** n
        # binomial z-scores under global and within-N leg-hit independence approximations
        z_global = (sum(1 for r in rs if r["all_hit"]) - len(rs) * exp_global) / math.sqrt(max(1e-12, len(rs) * exp_global * (1 - exp_global)))
        z_within = (sum(1 for r in rs if r["all_hit"]) - len(rs) * exp_within) / math.sqrt(max(1e-12, len(rs) * exp_within * (1 - exp_within)))
        result["rows"].append({
            "N": n,
            "tickets": len(rs),
            "roi_pct": m["roi_pct"],
            "drift": m["drift"],
            "all_hit_rate": actual_ah,
            "leg_hit_rate_within_N": leg_hr,
            "indep_global": exp_global,
            "indep_within_N": exp_within,
            "z_vs_global_indep": z_global,
            "z_vs_within_indep": z_within,
        })
    return result


def main():
    rows, skipped, stake_mismatch, issue_lengths = fetch_tickets()
    full = metrics(rows)
    recent = metrics([r for r in rows if r["issue"] >= RECENT_FROM_ISSUE])
    result = {
        "full": full,
        "recent": recent,
        "by_N": by_n(rows),
        "skipped": skipped,
        "stake_mismatch_count": len(stake_mismatch),
        "stake_mismatch_examples": stake_mismatch[:5],
        "issue_length_distribution": issue_lengths,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
