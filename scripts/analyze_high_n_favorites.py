"""High-N favorite parlay: does the per-ticket rake dilution + favorite-longshot
bias make high N profitable, and where does leg correlation kill it?

Per match we take the market favorite (lowest near-kickoff SP). The parimutuel
rake (0.65) is paid ONCE per ticket, so the per-leg break-even edge falls with
N (1.538^(1/N)). Favorites have realized p×SP ≈ 1.08 > 1 (favorite-longshot
bias), so the INDEPENDENCE bound EV = 0.65·v^N rises with N and crosses 0 ~N=6.
This script also SIMULATES real same-issue favorite parlays (capturing leg
correlation) to show where reality diverges from the independence bound.

Run:  PYTHONPATH=".:src" .venv/bin/python scripts/analyze_high_n_favorites.py
"""
from __future__ import annotations

import math
import random
import sqlite3
from collections import defaultdict

RR = 0.65
LIVE = "data/beidan_live.db"
SAMPLES = 3000
SEED = 42


def main():
    rng = random.Random(SEED)
    lc = sqlite3.connect(LIVE)
    settle = {}
    for m, rc, wsp in lc.execute(
        "select match_id,result_code,winning_sp from settlements "
        "where result_code is not null and winning_sp>0"):
        settle[str(m)] = (str(rc), float(wsp))
    # last (near-kickoff) snapshot's three SPs per match → favorite = min SP
    sp3 = {}
    for m, ts, a, b, c in lc.execute(
        "select match_id,snapshot_ts,sp_3,sp_1,sp_0 from snapshots "
        "where sp_3 is not null and sp_1 is not null and sp_0 is not null"):
        m = str(m)
        if m not in sp3 or ts > sp3[m][0]:
            sp3[m] = (ts, float(a), float(b), float(c))

    by_issue = defaultdict(list)   # issue -> [(hit, win_sp_if_hit)]
    vlist = []
    for m, (rc, wsp) in settle.items():
        v = sp3.get(m)
        if not v:
            continue
        _, a, b, c = v
        d = {"3": a, "1": b, "0": c}
        fav = min(d, key=d.get)
        hit = (fav == rc)
        by_issue[m.split("_")[0]].append((hit, wsp if hit else None))
        vlist.append((hit, wsp if hit else None))

    n = len(vlist)
    hits = sum(1 for h, _ in vlist if h)
    sw = sum(w for h, w in vlist if h)
    v_leg = sw / n   # realized per-leg p×SP (= hit_rate × avg winning SP)
    print(f"favorite legs: n={n}  hit_rate={hits/n:.3f}  avg_win_sp={sw/hits:.2f}  "
          f"realized v=p×SP={v_leg:.3f}")
    print(f"issues={len(by_issue)}  median favorites/issue="
          f"{sorted(len(x) for x in by_issue.values())[len(by_issue)//2]}\n")

    print(f"{'N':>2} {'breakeven_v':>11} {'indep_EV':>10} {'sim_ROI':>10} "
          f"{'corr_drag':>9} {'geomeanSP':>9}")
    issues = list(by_issue.items())
    for N in (2, 3, 4, 5, 6, 7, 8, 10):
        be_v = 1.538 ** (1.0 / N)
        indep = RR * (v_leg ** N)
        elig = [(iss, legs) for iss, legs in issues if len(legs) >= N]
        tot_stake = tot_pay = 0.0
        win_sps = []
        for _ in range(SAMPLES):
            iss, legs = rng.choice(elig)
            idx = rng.sample(range(len(legs)), N)
            tot_stake += 1.0
            if all(legs[i][0] for i in idx):
                prod = 1.0
                for i in idx:
                    prod *= legs[i][1]
                tot_pay += RR * prod
                win_sps.append(prod ** (1.0 / N))
        roi = tot_pay / tot_stake - 1
        drag = (roi + 1) / indep if indep else 0.0
        gm = (sum(win_sps) / len(win_sps)) if win_sps else 0.0
        print(f"{N:>2} {be_v:>11.3f} {100*(indep-1):>+9.1f}% {100*roi:>+9.1f}% "
              f"{drag:>9.2f} {gm:>9.2f}")
    print("\nindep_EV = 0.65·v^N (legs independent); sim_ROI = real same-issue "
          "favorite parlays; corr_drag = sim/indep (<1 ⇒ positive leg correlation "
          "eats the edge). Settlement winning_sp used (favourites drift UP, so "
          "this already includes favourable drift).")


if __name__ == "__main__":
    main()
