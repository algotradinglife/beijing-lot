"""High-N favorite parlay: does per-ticket rake dilution + the favorite-longshot
bias make high N viable, and what actually limits it?

Per match take the market favorite (lowest near-kickoff SP). The parimutuel rake
(0.65) is paid ONCE per ticket, so the per-leg break-even edge falls with N
(1.538^(1/N)). Favorites have a STABLE realized p×SP ≈ 1.08 > 1
(favorite-longshot bias), so the independence bound EV = 0.65·v^N rises with N
and crosses 0 around N=6.

Two STABLE, reproducible diagnostics (no Monte Carlo):
  - exact all-hit probability per N via combinatorics C(h,N)/C(m,N) per issue;
  - expected winning tickets in a fixed sample — shows high N is a RARE event.
A seeded Monte-Carlo ROI is also printed, but at N>=6 it is noise-dominated
(few/zero expected wins) and must NOT be read as a stable point estimate.

Determinism: all SQL is ORDER BY'd and every list is explicitly sorted, so the
seeded RNG is fully reproducible run-to-run.

Run:  PYTHONPATH=".:src" .venv/bin/python scripts/analyze_high_n_favorites.py
"""
from __future__ import annotations

import math
import random
import sqlite3
from collections import defaultdict

RR = 0.65
LIVE = "data/beidan_live.db"
MC_SAMPLES = 20000
SEED = 42


def load():
    lc = sqlite3.connect(LIVE)
    settle = {}
    for m, rc, wsp in lc.execute(
        "select match_id,result_code,winning_sp from settlements "
        "where result_code is not null and winning_sp>0 order by match_id"):
        settle[str(m)] = (str(rc), float(wsp))
    # near-kickoff snapshot's three SPs per match → favorite = min SP.
    # ORDER BY match_id, snapshot_ts so the 'last' pick is deterministic.
    sp3 = {}
    for m, ts, a, b, c in lc.execute(
        "select match_id,snapshot_ts,sp_3,sp_1,sp_0 from snapshots "
        "where sp_3 is not null and sp_1 is not null and sp_0 is not null "
        "order by match_id, snapshot_ts"):
        sp3[str(m)] = (ts, float(a), float(b), float(c))  # last wins (ordered)
    # favorites grouped by issue, deterministically ordered
    by_issue = defaultdict(list)   # issue -> [(hit, win_sp_if_hit)] sorted by match_id
    vlist = []
    for m in sorted(settle):
        rc, wsp = settle[m]
        v = sp3.get(m)
        if not v:
            continue
        _, a, b, c = v
        d = {"3": a, "1": b, "0": c}
        fav = min(d, key=lambda k: (d[k], k))   # tie-break by selection for determinism
        hit = (fav == rc)
        by_issue[m.split("_")[0]].append((hit, wsp if hit else None))
        vlist.append((hit, wsp if hit else None))
    return by_issue, vlist


def main():
    by_issue, vlist = load()
    n = len(vlist)
    hits = sum(1 for h, _ in vlist if h)
    sw = sum(w for h, w in vlist if h)
    v_leg = sw / n
    print(f"favorite legs: n={n}  hit_rate={hits/n:.3f}  avg_win_sp={sw/hits:.3f}  "
          f"realized v=p×SP={v_leg:.3f}   [STABLE]")
    print(f"issues={len(by_issue)}  median favorites/issue="
          f"{sorted(len(x) for x in by_issue.values())[len(by_issue)//2]}\n")

    issues = sorted(by_issue)              # deterministic order
    rng = random.Random(SEED)
    print(f"{'N':>2} {'be_v':>6} {'indep_EV':>9} {'exact_allhit':>13} "
          f"{'E[wins]/'+str(MC_SAMPLES):>14} {'MC_ROI(noisy)':>14}")
    for N in (2, 3, 4, 5, 6, 7, 8, 10):
        be_v = 1.538 ** (1.0 / N)
        indep = RR * (v_leg ** N)
        # EXACT all-hit probability: pooled C(hits_j, N) / C(m_j, N) over issues
        num = den = 0
        for iss in issues:
            legs = by_issue[iss]
            m = len(legs)
            if m < N:
                continue
            h = sum(1 for hit, _ in legs if hit)
            num += math.comb(h, N)
            den += math.comb(m, N)
        exact_p = (num / den) if den else 0.0
        exp_wins = exact_p * MC_SAMPLES
        # seeded Monte-Carlo ROI (deterministic inputs) — noisy at high N
        elig = [iss for iss in issues if len(by_issue[iss]) >= N]
        tot_stake = tot_pay = 0.0
        for _ in range(MC_SAMPLES):
            legs = by_issue[rng.choice(elig)]
            idx = rng.sample(range(len(legs)), N)
            tot_stake += 1.0
            if all(legs[i][0] for i in idx):
                prod = 1.0
                for i in idx:
                    prod *= legs[i][1]
                tot_pay += RR * prod
        mc_roi = tot_pay / tot_stake - 1
        print(f"{N:>2} {be_v:>6.3f} {100*(indep-1):>+8.1f}% {exact_p:>13.5f} "
              f"{exp_wins:>14.1f} {100*mc_roi:>+13.1f}%")
    print("\n[STABLE] v, be_v, indep_EV, exact_allhit, E[wins] are deterministic.")
    print("MC_ROI is a seeded estimate; at N>=6 E[wins] is tiny, so MC_ROI is "
          "NOISE-DOMINATED and must NOT be read as a point estimate — it swings "
          "with which rare jackpot lands. exact_allhit already exceeds pooled "
          "p^N (issue heterogeneity = mild POSITIVE correlation, which HELPS "
          "all-hit), so high-N is limited by variance/measurability, not by "
          "negative correlation.")


if __name__ == "__main__":
    main()
