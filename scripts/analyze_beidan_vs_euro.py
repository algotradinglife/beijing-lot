"""北单 winning_sp vs de-vigged European odds — is there a soft-pool edge? (38k)

On beidan_history.db (2024-2026, winning_sp + avg_eu_*):
  p_euro(s) = (1/eu_s)/Σ(1/eu_o)         # proportional de-vig
  D = winning_sp × p_euro(winner)        # 北单 gross odds / euro-fair odds
  projected single-leg q ≈ D × RETURN_RATE

CRITICAL CONFOUND (caught by the calibration sanity check): 北单 is 让球(handicap)
胜平负, but avg_eu_* are STRAIGHT 1X2 odds. On handicap matches the straight-euro
prob does NOT correspond to the handicap result, fabricating a spurious
"favorite" divergence. So we split:
  - ALL matches (naive): broken calibration + spurious monotonic +EV on big
    "favorites" — an ARTIFACT.
  - handicap_line=0 only (~23k): 北单 result = straight 1X2, comparable to euro.
    Here euro is well-calibrated AND D≈1.0 flat across all probability buckets →
    北单 is efficiently priced vs the sharp euro market; NO divergence edge.

Refunds (winning_sp<=1.0, ~0.2%, incl. result/score mismatches) are excluded.

Deterministic (ORDER BY, no sampling). Writes
docs/research/figures/beidan_vs_euro_divergence.png.
Run:  PYTHONPATH=".:src" .venv/bin/python scripts/analyze_beidan_vs_euro.py
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
HIST = "data/beidan_history.db"
CUTOFF = "2026-06-23"
BUCKETS = ["<0.2", "0.2-0.35", "0.35-0.5", ">=0.5"]
MID = {"<0.2": 0.1, "0.2-0.35": 0.275, "0.35-0.5": 0.425, ">=0.5": 0.6}
FIG = Path("docs/research/figures/beidan_vs_euro_divergence.png")


def devig(h, d, a):
    ih, idr, ia = 1 / h, 1 / d, 1 / a
    s = ih + idr + ia
    return {"3": ih / s, "1": idr / s, "0": ia / s}


def _bk(p):
    return ("<0.2" if p < 0.2 else "0.2-0.35" if p < 0.35
            else "0.35-0.5" if p < 0.5 else ">=0.5")


def analyse(rows, label):
    refunds = sum(1 for r in rows if r[1] <= 1.0)
    rows = [r for r in rows if r[1] > 1.0]              # exclude refunds/voids
    cal = defaultdict(lambda: [0, 0])
    byw = defaultdict(list)
    for rc, wsp, h, d, a in rows:
        p = devig(h, d, a)
        for s, ps in p.items():
            cal[_bk(ps)][0] += 1
            if s == rc:
                cal[_bk(ps)][1] += 1
        pw = p.get(rc)
        if pw and pw > 0:
            byw[_bk(pw)].append(wsp * pw)
    print(f"\n===== {label}  (n={len(rows)}, 已剔除退款 winning_sp<=1.0: {refunds}) =====")
    print("欧赔校准: euro_p桶  realized_hit  (桶中点)")
    cal_ok = True
    hit_by = {}
    for b in BUCKETS:
        n, w = cal[b]
        if n:
            hit = w / n
            hit_by[b] = hit
            off = abs(hit - MID[b]) >= 0.07
            cal_ok = cal_ok and not off
            print(f"  {b:9} n={n:6} hit={hit:.3f}  (mid {MID[b]})" + ("  <-- 偏离" if off else ""))
    print(f"  校准{'良好 ✓' if cal_ok else '破裂 ✗ → 不可比'}")
    print("北单 D by 赢家欧赔概率桶:  meanD  投影q   [break-even D=1.538]")
    D_by = {}
    for b in BUCKETS:
        v = byw[b]
        if v:
            mD = st.mean(v)
            D_by[b] = mD
            print(f"  {b:9} n={len(v):6} D={mD:.3f}  q={mD*RR:.3f}" + ("  <-- 看似+EV" if mD*RR > 1 else ""))
    return hit_by, D_by


def make_figure(stats_all, stats_z):
    FIG.parent.mkdir(parents=True, exist_ok=True)
    x = list(range(len(BUCKETS)))
    mids = [MID[b] for b in BUCKETS]
    fig, (axc, axd) = plt.subplots(1, 2, figsize=(11, 4.4))
    # calibration
    axc.plot(x, mids, "k:", label="perfect calib (mid)")
    axc.plot(x, [stats_all[0].get(b, float("nan")) for b in BUCKETS], "s-",
             color="#c0504d", label="all (handicap confound)")
    axc.plot(x, [stats_z[0].get(b, float("nan")) for b in BUCKETS], "o-",
             color="#4f81bd", label="line=0 (clean)")
    axc.set_xticks(x); axc.set_xticklabels(BUCKETS, fontsize=8)
    axc.set_xlabel("euro-implied prob bucket"); axc.set_ylabel("realized hit rate")
    axc.set_title("Euro calibration: line=0 on diagonal, all-sample broken")
    axc.legend(fontsize=8); axc.grid(alpha=0.3)
    # D by bucket
    axd.axhline(1.0, color="g", ls="-", lw=1, alpha=0.5, label="D=1 (北单=euro fair)")
    axd.axhline(1.538, color="k", ls=":", lw=1, label="break-even D=1.538")
    axd.plot(x, [stats_all[1].get(b, float("nan")) for b in BUCKETS], "s-",
             color="#c0504d", label="all (spurious +EV)")
    axd.plot(x, [stats_z[1].get(b, float("nan")) for b in BUCKETS], "o-",
             color="#4f81bd", label="line=0 (flat ≈1.0, no edge)")
    axd.set_xticks(x); axd.set_xticklabels(BUCKETS, fontsize=8)
    axd.set_xlabel("winner euro-prob bucket"); axd.set_ylabel("北单 D = wsp×p_euro")
    axd.set_title("北单 vs euro divergence D")
    axd.legend(fontsize=8); axd.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG, dpi=110)
    print(f"\nwrote {FIG}")


def main():
    c = sqlite3.connect(HIST)
    base = ("select result_code,winning_sp,avg_eu_home,avg_eu_draw,avg_eu_away "
            "from historical_matches where winning_sp>0 and avg_eu_home>0 and "
            "avg_eu_draw>0 and avg_eu_away>0 and kickoff_ts<=? ")
    allr = c.execute(base + "order by id", (CUTOFF,)).fetchall()
    z = c.execute(base + "and handicap_line=0 order by id", (CUTOFF,)).fetchall()
    s_all = analyse(allr, "全样本（含让球盘 — 直盘欧赔 vs 让球结果，错配）")
    s_z = analyse(z, "handicap_line=0（无让球，北单=直盘，与欧赔可比）")
    print("\n结论：全样本『大热门 +EV』是让球错配假象（校准破裂暴露）。line=0 干净比较上"
          "欧赔校准良好且北单 D≈1.0 全桶持平 → 北单相对 sharp 欧赔定价高效，无可利用偏离 edge。")
    make_figure(s_all, s_z)


if __name__ == "__main__":
    main()
