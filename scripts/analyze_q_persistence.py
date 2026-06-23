"""Is realized q a timing edge? — persistence / mean-reversion analysis.

q (per leg, realized return multiple) = RETURN_RATE × Σ(winning-leg SP) / n.
This script tests whether q has exploitable time-structure at the overall,
per-league and per-option levels, and runs a contrarian mean-reversion
backtest. Reproduces docs/research/q_persistence_analysis.md.

Run:  PYTHONPATH=".:src" .venv/bin/python scripts/analyze_q_persistence.py
"""
from __future__ import annotations

import sqlite3
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RR = 0.65
WEBUI, LIVE = "data/webui.db", "data/beidan_live.db"
FIG = Path("docs/research/figures/q_persistence.png")


def load_legs():
    from src.webui.db import WebuiDB
    db = WebuiDB(WEBUI)
    lc = sqlite3.connect(LIVE)
    settle = {str(m): str(rc) for m, rc in lc.execute(
        "select match_id,result_code from settlements where result_code is not null")}
    legs = []  # (issue, league, selection, sp, hit)
    for p in db.list_plans():
        pid = p["plan_id"]
        if not db.has_settlement(pid):
            continue
        meta = db.get_plan(pid)
        if not meta:
            continue
        seen = set()
        for t in meta.get("plan", {}).get("tickets", []):
            for lg in t.get("legs", []):
                mid, sel = lg.get("match_id"), lg.get("selection")
                if mid is None or sel is None:
                    continue
                mid = str(mid)
                if (pid, mid) in seen or mid not in settle:
                    continue
                try:
                    sp = float(lg.get("sp") or 0)
                except (TypeError, ValueError):
                    continue
                if sp <= 0:
                    continue
                seen.add((pid, mid))
                legs.append((mid.split("_")[0], lg.get("league") or "",
                             str(sel), sp, settle[mid] == str(sel)))
    return legs


def q(rows):
    n = len(rows)
    return RR * sum(r[3] for r in rows if r[4]) / n if n else None


def autocorr(x, lag=1):
    x = [v for v in x if v is not None]
    n, m = len(x), st.mean(x)
    den = sum((v - m) ** 2 for v in x)
    return (sum((x[i] - m) * (x[i + lag] - m) for i in range(n - lag)) / den
            ) if den else float("nan")


def main():
    legs = load_legs()
    issues = sorted({r[0] for r in legs})
    GM = q(legs)
    print(f"total settled legs={len(legs)}  issues={len(issues)}  grand-mean q={GM:.3f}\n")

    # 1) overall q by issue
    overall = [q([r for r in legs if r[0] == iss]) for iss in issues]
    print("== overall q by issue ==")
    for iss, v in zip(issues, overall):
        print(f"  {iss}  q={v:.3f}")
    print(f"  mean={st.mean(overall):.3f} sd={st.pstdev(overall):.3f} "
          f"CV={st.pstdev(overall)/st.mean(overall):.2f} lag1={autocorr(overall):+.3f}\n")

    # 2) per-league split-half persistence
    half = len(issues) // 2
    early, late = set(issues[:half]), set(issues[half:])
    le, ll = defaultdict(list), defaultdict(list)
    for r in legs:
        (le if r[0] in early else ll)[r[1]].append(r)
    pairs = []
    print("== per-league q early vs late (>=5 legs each half) ==")
    for lg in sorted(set(le) | set(ll)):
        a, b = le.get(lg, []), ll.get(lg, [])
        if len(a) >= 5 and len(b) >= 5:
            pairs.append((q(a), q(b)))
            print(f"  {lg:8} early n={len(a):2} q={q(a):.2f}  late n={len(b):2} q={q(b):.2f}")
    if len(pairs) >= 3:
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        mx, my = st.mean(xs), st.mean(ys)
        den = (sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys)) ** 0.5
        corr = sum((x-mx)*(y-my) for x, y in pairs) / den if den else float("nan")
        print(f"  early-vs-late corr = {corr:+.3f} (n={len(pairs)} leagues)\n")

    # 3) option-level
    print("== per-option q ==")
    opt_series = {}
    for s in ("3", "1", "0"):
        ser = [q([r for r in legs if r[0] == iss and r[2] == s]) for iss in issues]
        opt_series[s] = ser
        vals = [v for v in ser if v is not None]
        if vals:
            print(f"  option {s}: mean={st.mean(vals):.3f} sd={st.pstdev(vals):.3f} "
                  f"lag1={autocorr(ser):+.3f}  (bet in {len(vals)}/{len(issues)} issues)")
        else:
            print(f"  option {s}: never bet")
    print()

    # 4) contrarian mean-reversion backtest
    pil = defaultdict(list)
    for r in legs:
        pil[(r[0], r[1])].append(r)
    qil = {k: q(v) for k, v in pil.items() if len(v) >= 4}
    low, high = [], []
    for idx, iss in enumerate(issues):
        if idx == 0:
            continue
        for r in [x for x in legs if x[0] == iss]:
            pq = None
            for pj in reversed(issues[:idx]):
                if (pj, r[1]) in qil:
                    pq = qil[(pj, r[1])]
                    break
            if pq is None:
                continue
            (low if pq < GM else high).append(r)
    print("== contrarian mean-reversion backtest ==")
    print(f"  prior-low  league -> this-period q={q(low):.3f} (n={len(low)})")
    print(f"  prior-high league -> this-period q={q(high):.3f} (n={len(high)})")
    print(f"  gap={q(low)-q(high):+.3f}  (both < 1.0 breakeven => not profitable)\n")

    # figure: overall + option q by issue
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = range(len(issues))
    ax.plot(x, overall, "o-", lw=2, label="overall q")
    ax.plot(x, [v if v is not None else float("nan") for v in opt_series["3"]],
            "s--", alpha=0.6, label="q option win(3)")
    ax.plot(x, [v if v is not None else float("nan") for v in opt_series["0"]],
            "^--", alpha=0.6, label="q option lose(0)")
    ax.axhline(1.0, color="g", lw=1, ls=":", label="break-even q=1.0")
    ax.axhline(GM, color="r", lw=1, ls="-", alpha=0.5, label=f"grand mean {GM:.2f}")
    ax.set_xticks(list(x))
    ax.set_xticklabels(issues, rotation=45, fontsize=8)
    ax.set_ylabel("realized q")
    ax.set_title("q oscillates around a sub-breakeven mean (no trend)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG, dpi=110)
    print(f"wrote {FIG}")


if __name__ == "__main__":
    main()
