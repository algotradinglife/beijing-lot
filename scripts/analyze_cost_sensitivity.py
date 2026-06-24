"""Cost / rebate / tax sensitivity: can cost structure turn the strategy positive?

Pure accounting on the 3093 settled tickets (same population as pnl_attribution):

- Rebate is paid on STAKE (services.reconcile_pending: commission = total_stake ×
  commission_rate), so realized ROI shifts by +r:  ROI(r) = base_ROI + r.
  Break-even rebate  r* = −base_ROI  (per N).
- Tax: a single-ticket prize ≥10000 is taxed 20%. The sizer AVOIDS this by
  splitting (cap = floor_to_even(9999 / payout_per_yuan), n_tickets =
  ceil(raw/cap)), so realized PnL already pays NO tax. We quantify how often the
  cap bites and the 20%-tax it saves vs a hypothetical 1-ticket world.

Deterministic. Writes docs/research/figures/cost_sensitivity.png.
Run:  PYTHONPATH=".:src" .venv/bin/python scripts/analyze_cost_sensitivity.py
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RR = 0.65
TAX_CLIFF = 10000.0
TAX_RATE = 0.20
WEBUI, LIVE = "data/webui.db", "data/beidan_live.db"
REBATES = [0.0, 0.02, 0.05, 0.07, 0.10]
FIG = Path("docs/research/figures/cost_sensitivity.png")


def load_tickets():
    """settled tickets: (n_legs, stake, all_hit, win_prod, spt, nt)."""
    from src.webui.db import WebuiDB
    db = WebuiDB(WEBUI)
    lc = sqlite3.connect(LIVE)
    settle = {}
    for mid, rc, wsp in lc.execute(
        "select match_id,result_code,winning_sp from settlements "
        "where result_code is not null order by match_id"):
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
            all_hit, win_prod, ok = True, 1.0, True
            for lg in legs:
                mid, sel = str(lg.get("match_id")), lg.get("selection")
                if sel is None or mid not in settle:
                    ok = False
                    break
                rc, wsp = settle[mid]
                if rc == str(sel):
                    if wsp is None:
                        ok = False
                        break
                    win_prod *= wsp
                else:
                    all_hit = False
            if not ok:
                continue
            try:
                spt = float(tk.get("stake_per_ticket", 0))
                nt = int(tk.get("n_tickets", 1))
                stake = float(tk.get("total_stake", 0))
            except (TypeError, ValueError):
                continue
            if stake <= 0:
                continue
            out.append(dict(n_legs=len(legs), stake=stake, all_hit=all_hit,
                            win_prod=win_prod, spt=spt, nt=nt))
    return out


def roi(ts):
    s = sum(t["stake"] for t in ts)
    pay = sum(t["spt"] * t["win_prod"] * RR * t["nt"] for t in ts if t["all_hit"])
    return (pay / s - 1) if s else float("nan"), s


def main():
    ts = load_tickets()
    byN = defaultdict(list)
    for t in ts:
        byN[t["n_legs"]].append(t)
    print(f"settled tickets={len(ts)}\n")

    print("== 返点敏感性: ROI(r)=base+r (返点按投注额) ==")
    hdr = "  ".join(f"r={int(r*100)}%" for r in REBATES)
    print(f"  {'N':>3} {'票':>5} {'baseROI':>8}  {hdr}  {'盈亏平衡返点r*':>14}")
    rows = []
    for N in sorted(byN):
        base, _ = roi(byN[N])
        cells = "  ".join(f"{100*(base+r):>5.0f}%" for r in REBATES)
        print(f"  {N:>3} {len(byN[N]):>5} {100*base:>7.1f}%  {cells}  {-100*base:>13.1f}%")
        rows.append((N, base))
    allbase, _ = roi(ts)
    print(f"  {'all':>3} {len(ts):>5} {100*allbase:>7.1f}%  "
          + "  ".join(f"{100*(allbase+r):>5.0f}%" for r in REBATES)
          + f"  {-100*allbase:>13.1f}%")
    print("  → 返点按投注额只把 ROI 平移 +r；盈亏平衡返点 r* = −baseROI\n")

    # tax / splitting: how often the 10k cap bites + the 20% tax it saves
    bite = 0
    tax_saved = 0.0
    for t in ts:
        if not t["all_hit"]:
            continue
        intended_stake = t["spt"] * t["nt"]
        prize_one_ticket = intended_stake * t["win_prod"] * RR
        if prize_one_ticket > TAX_CLIFF:
            bite += 1
            tax_saved += (prize_one_ticket - TAX_CLIFF) * TAX_RATE
    nhit = sum(1 for t in ts if t["all_hit"])
    print("== 税务封顶 / 拆票 ==")
    print(f"  中奖票 {nhit} 张；若按1张投注、单票奖金>1万会被20%税的 = {bite} 张")
    print(f"  拆票避开的总税额 ≈ {tax_saved:,.0f} 元（现有 sizer 已自动拆票避税）")
    print("  → 税务现已被拆票规避；当前玩法奖金稀疏，封顶很少触发。高SP/高N/登月才需重点建模。")

    # figure
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    Ns = [N for N, _ in rows]
    x = range(len(Ns))
    for r in REBATES:
        ax.plot(x, [100 * (b + r) for _, b in rows], "o-", label=f"rebate {int(r*100)}%")
    ax.axhline(0, color="k", lw=1)
    ax.set_xticks(list(x)); ax.set_xticklabels([f"N={N}" for N in Ns])
    ax.set_ylabel("ROI %"); ax.set_title("ROI by N at various stake-rebate rates")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(FIG, dpi=110)
    print(f"\nwrote {FIG}")


if __name__ == "__main__":
    main()
