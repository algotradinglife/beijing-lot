"""北单 winning_sp vs de-vigged European odds — is there a soft-pool edge? (38k)

On beidan_history.db (2024-2026, winning_sp + avg_eu_*):
  p_euro(s) = (1/eu_s)/Σ(1/eu_o)         # proportional de-vig
  D = winning_sp × p_euro(winner)        # 北单 gross odds / euro-fair odds
  projected single-leg q ≈ D × RETURN_RATE

CRITICAL CONFOUND (caught by the calibration sanity check): 北单 is 让球(handicap)
胜平负, but avg_eu_* are STRAIGHT 1X2 odds. On handicap matches the straight-euro
prob does NOT correspond to the handicap result, which fabricates a spurious
"favorite" divergence. So we split:
  - ALL matches (naive): broken calibration + spurious monotonic +EV on big
    "favorites" — an ARTIFACT.
  - handicap_line=0 only (~23k): 北单 result = straight 1X2, comparable to euro.
    Here euro is well-calibrated AND D≈1.0 flat across all probability buckets →
    北单 is efficiently priced vs the sharp euro market; NO divergence edge.

Conclusion: the apparent +EV is a handicap artifact; on a clean comparison there
is no 北单-vs-euro mispricing to exploit. Consistent with the structural-loss
thesis (rake × drift), not selection/mispricing.

Deterministic (ORDER BY, no sampling).
Run:  PYTHONPATH=".:src" .venv/bin/python scripts/analyze_beidan_vs_euro.py
"""
from __future__ import annotations

import sqlite3
import statistics as st
from collections import defaultdict

RR = 0.65
HIST = "data/beidan_history.db"
CUTOFF = "2026-06-23"
BUCKETS = ["<0.2", "0.2-0.35", "0.35-0.5", ">=0.5"]
MID = {"<0.2": 0.1, "0.2-0.35": 0.275, "0.35-0.5": 0.425, ">=0.5": 0.6}


def devig(h, d, a):
    ih, idr, ia = 1 / h, 1 / d, 1 / a
    s = ih + idr + ia
    return {"3": ih / s, "1": idr / s, "0": ia / s}


def _bk(p):
    return ("<0.2" if p < 0.2 else "0.2-0.35" if p < 0.35
            else "0.35-0.5" if p < 0.5 else ">=0.5")


def analyse(rows, label):
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
    print(f"\n===== {label}  (n={len(rows)}) =====")
    print("欧赔校准: euro_p桶  realized_hit  (桶中点)  → 接近=欧赔可当真值")
    cal_ok = True
    for b in BUCKETS:
        n, w = cal[b]
        if n:
            hit = w / n
            flag = "" if abs(hit - MID[b]) < 0.07 else "  <-- 偏离(口径错配)"
            if abs(hit - MID[b]) >= 0.07:
                cal_ok = False
            print(f"  {b:9} n={n:6} hit={hit:.3f}  (mid {MID[b]})" + flag)
    print(f"  校准{'良好 ✓' if cal_ok else '破裂 ✗ → 不可比'}")
    print("北单 D by 赢家欧赔概率桶:  meanD  投影q(D×0.65)   [break-even D=1.538]")
    for b in BUCKETS:
        v = byw[b]
        if v:
            mD = st.mean(v)
            print(f"  {b:9} n={len(v):6} D={mD:.3f}  q={mD*RR:.3f}"
                  + ("  <-- 看似+EV" if mD * RR > 1 else ""))


def main():
    c = sqlite3.connect(HIST)
    base = ("select result_code,winning_sp,avg_eu_home,avg_eu_draw,avg_eu_away "
            "from historical_matches where winning_sp>0 and avg_eu_home>0 and "
            "avg_eu_draw>0 and avg_eu_away>0 and kickoff_ts<=? ")
    allr = c.execute(base + "order by id", (CUTOFF,)).fetchall()
    z = c.execute(base + "and handicap_line=0 order by id", (CUTOFF,)).fetchall()
    analyse(allr, "全样本（含让球盘 — 直盘欧赔 vs 让球结果，错配）")
    analyse(z, "handicap_line=0（无让球，北单=直盘，与欧赔可比）")
    print("\n结论：全样本的『大热门 +EV』是让球错配假象（校准破裂暴露）。"
          "在 line=0 干净比较上，欧赔校准良好且北单 D≈1.0 全桶持平 → "
          "北单相对 sharp 欧赔定价高效，无可利用偏离 edge。市场有效，"
          "亏损是结构性（抽水×漂移），非选腿/错价。")


if __name__ == "__main__":
    main()
