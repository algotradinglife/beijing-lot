"""Realized-PnL attribution: where does the parlay loss actually come from?

Multiplicative decomposition on settled tickets (all_hit is fixed by
result_code, independent of which SP we value the payout at):

  R_actual  = Σ payout(winning_sp) / Σ stake      # real realized return
  R_planSP  = Σ payout(plan_sp)    / Σ stake      # counterfactual: no SP drift
  R_actual  = rake(0.65) × selection × drift
      selection = R_planSP / 0.65   (>1 favourable pricing/selection, <1 not)
      drift     = R_actual / R_planSP (<1 = settlement SP below plan SP)

Plus a leg-correlation check: actual all-hit rate vs (per-leg hit rate)^N.

Run:  PYTHONPATH=".:src" .venv/bin/python scripts/analyze_pnl_attribution.py
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict

RR = 0.65
WEBUI, LIVE = "data/webui.db", "data/beidan_live.db"
RECENT_FROM_ISSUE = "26057"  # ~2026-05-22 onward


def load_tickets():
    """Return list of settled tickets: (issue, n_legs, stake, all_hit,
    plan_prod, win_prod, leg_hits[list[bool]]). Only tickets whose every leg is
    settled (and, if all_hit, has winning_sp) are included."""
    from src.webui.db import WebuiDB
    db = WebuiDB(WEBUI)
    lc = sqlite3.connect(LIVE)
    settle = {}
    for mid, rc, wsp in lc.execute(
        "select match_id,result_code,winning_sp from settlements "
        "where result_code is not null"):
        settle[str(mid)] = (str(rc), (float(wsp) if wsp else None))
    out = []
    for p in db.list_plans():
        pid = p["plan_id"]
        if not db.has_settlement(pid):
            continue
        meta = db.get_plan(pid)
        if not meta:
            continue
        for tk in meta.get("plan", {}).get("tickets", []):
            legs = tk.get("legs", [])
            if not legs:
                continue
            issue = str(legs[0].get("match_id", "")).split("_")[0]
            all_settled = True
            all_hit = True
            plan_prod = 1.0
            win_prod = 1.0
            leg_hits = []
            ok = True
            for lg in legs:
                mid = str(lg.get("match_id"))
                sel = lg.get("selection")
                if sel is None or mid not in settle:
                    all_settled = False
                    break
                rc, wsp = settle[mid]
                try:
                    psp = float(lg.get("sp") or 0)
                except (TypeError, ValueError):
                    ok = False
                    break
                if psp <= 0:
                    ok = False
                    break
                hit = (rc == str(sel))
                leg_hits.append(hit)
                plan_prod *= psp
                if hit:
                    if wsp is None:
                        ok = False  # winning leg without settlement SP -> skip
                        break
                    win_prod *= wsp
                else:
                    all_hit = False
            if not (all_settled and ok):
                continue
            try:
                spt = float(tk.get("stake_per_ticket", 0))
                nt = int(tk.get("n_tickets", 1))
                stake = float(tk.get("total_stake", 0))
            except (TypeError, ValueError):
                continue
            if stake <= 0:
                continue
            out.append(dict(issue=issue, n_legs=len(legs), stake=stake,
                            all_hit=all_hit, spt=spt, nt=nt,
                            plan_prod=plan_prod, win_prod=win_prod,
                            leg_hits=leg_hits))
    return out


def attribute(tickets, label):
    S = sum(t["stake"] for t in tickets)
    if S <= 0:
        print(f"[{label}] no stake"); return
    pay_win = sum(t["spt"] * t["win_prod"] * RR * t["nt"]
                  for t in tickets if t["all_hit"])
    pay_plan = sum(t["spt"] * t["plan_prod"] * RR * t["nt"]
                   for t in tickets if t["all_hit"])
    R_actual = pay_win / S
    R_plan = pay_plan / S
    rake = RR
    selection = R_plan / rake if rake else float("nan")
    drift = R_actual / R_plan if R_plan else float("nan")
    n_hit = sum(1 for t in tickets if t["all_hit"])
    print(f"\n===== {label} =====")
    print(f"tickets={len(tickets)} all-hit={n_hit} ({100*n_hit/len(tickets):.1f}%) "
          f"stake={S:,.0f}")
    print(f"R_actual (settle@winning_sp) = {R_actual:.3f}  (ROI {100*(R_actual-1):+.1f}%)")
    print(f"R_planSP (settle@plan_sp)    = {R_plan:.3f}  (ROI {100*(R_plan-1):+.1f}%)")
    print(f"  decomposition  R_actual = rake × selection × drift")
    print(f"    rake      = {rake:.3f}   (structural -35% floor, once/ticket)")
    print(f"    selection = {selection:.3f}   ({'favourable' if selection>1 else 'UNFAVOURABLE'} pricing/selection/corr at plan SP)")
    print(f"    drift     = {drift:.3f}   (settlement SP vs plan SP)")
    print(f"    check rake*sel*drift = {rake*selection*drift:.3f}")
    # per-N drift compounding + correlation
    byN = defaultdict(list)
    for t in tickets:
        byN[t["n_legs"]].append(t)
    print("  per-N:")
    # global per-leg hit rate
    all_legs = [h for t in tickets for h in t["leg_hits"]]
    leg_hr = sum(all_legs) / len(all_legs) if all_legs else 0
    print(f"    (global per-leg hit rate = {leg_hr:.3f})")
    for N in sorted(byN):
        ts = byN[N]
        s = sum(t["stake"] for t in ts)
        pw = sum(t["spt"]*t["win_prod"]*RR*t["nt"] for t in ts if t["all_hit"])
        pp = sum(t["spt"]*t["plan_prod"]*RR*t["nt"] for t in ts if t["all_hit"])
        ra = pw/s if s else float("nan")
        dr = (pw/pp) if pp else float("nan")
        ah = sum(1 for t in ts if t["all_hit"]) / len(ts)
        indep = leg_hr ** N
        print(f"    N={N}: tk={len(ts):4d} ROI={100*(ra-1):+6.1f}% drift={dr:.3f} "
              f"allhit={ah:.3f} vs indep={indep:.3f} "
              f"({'+corr' if ah>indep else '-corr'})")


def _figure(tickets):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pathlib import Path
    byN = defaultdict(list)
    for t in tickets:
        byN[t["n_legs"]].append(t)
    Ns = sorted(byN)
    rois, drifts = [], []
    for N in Ns:
        ts = byN[N]
        s = sum(t["stake"] for t in ts)
        pw = sum(t["spt"]*t["win_prod"]*RR*t["nt"] for t in ts if t["all_hit"])
        pp = sum(t["spt"]*t["plan_prod"]*RR*t["nt"] for t in ts if t["all_hit"])
        rois.append(100*(pw/s-1) if s else 0)
        drifts.append(pw/pp if pp else 0)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))
    ax1.bar([str(n) for n in Ns], drifts, color="#c0504d")
    ax1.axhline(1.0, color="k", lw=0.8, ls=":")
    ax1.set_title("SP-drift factor compounds with N")
    ax1.set_xlabel("legs N"); ax1.set_ylabel("realized/plan payout")
    for i, v in enumerate(drifts):
        ax1.text(i, v+0.01, f"{v:.2f}", ha="center", fontsize=9)
    ax2.bar([str(n) for n in Ns], rois,
            color=["#4f81bd" if r >= 0 else "#c0504d" for r in rois])
    ax2.axhline(0, color="k", lw=0.8)
    ax2.set_title("ROI by N (full sample)")
    ax2.set_xlabel("legs N"); ax2.set_ylabel("ROI %")
    for i, v in enumerate(rois):
        ax2.text(i, v + (2 if v >= 0 else -6), f"{v:+.0f}%", ha="center", fontsize=9)
    fig.tight_layout()
    out = Path("docs/research/figures/pnl_attribution.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    print(f"\nwrote {out}")


def main():
    tickets = load_tickets()
    print(f"loaded {len(tickets)} settled tickets")
    attribute(tickets, "FULL SAMPLE")
    recent = [t for t in tickets if t["issue"] >= RECENT_FROM_ISSUE]
    attribute(recent, f"RECENT (issue>={RECENT_FROM_ISSUE})")
    _figure(tickets)


if __name__ == "__main__":
    main()
