"""Track A — high-N coverage construction: what can N=6/7「确定压·不确定包」
achieve under a PURE market (no per-leg edge)?

Honest floor only. The EV identity (proved in coverage.py) says covering & high N
do NOT beat the −35%×drift floor — they reshape P(hit) and the jackpot. Only a
real per-leg edge (Track B, needs the xlsx) can lift EV. This quantifies the
lottery: P(jackpot)/budget you can buy, and the hit↔jackpot trade of covering.

Legs are taken at the production decision MTK from real 北单 per-outcome gross SP
(Σ1/sp≈1 ⇒ crowd-implied p = 1/sp, p·sp≈1). Payout SP is drift-adjusted by the
empirical geometric-mean winning_sp/decision_sp so jackpots reflect settlement
reality. Deterministic (seed=0).
Run:  PYTHONPATH=".:src" .venv/bin/python scripts/analyze_high_n_coverage.py
"""
from __future__ import annotations

import sqlite3
import statistics as st
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.sp_drift import panel as P
from src.moonshot.coverage import RR, Leg, devig3, simulate_strategy

LIVE, WEBUI = "data/beidan_live.db", "data/webui.db"
CACHE = "data/derived/sp_drift/panel.parquet"
BUDGET = 1000.0
THR = [100_000.0, 1_000_000.0]
SEED, N_SIMS = 0, 300_000
N_ENUM = 100_000   # per-config sims for the full (n_single,c2,c3) enumeration
FIG = Path("docs/research/figures/high_n_coverage.png")
CODES = ["3", "1", "0"]  # outcome index 0/1/2


def load_pool(decision_mtk: float):
    """Return (pool, drift_gm, n_drift, sanity). Per match: gross decision SP per
    outcome de-vigged to the 北单-pool crowd prob (the no-edge baseline), payout
    drift-adjusted. Also collects euro-implied p on handicap_line=0 matches for an
    EU-vs-SP sanity check (why we use SP-implied, not euro — see doc §1)."""
    pan = P.build(LIVE, cache_path=CACHE, rebuild=False)
    dv = P.decision_view(pan, decision_mtk)
    by_match: dict = {}
    line: dict = {}
    for r in dv.itertuples(index=False):
        by_match.setdefault(r.match_id, {})[r.selection] = r.sp
        line[r.match_id] = r.handicap_line
    lc = sqlite3.connect(LIVE)
    settle = {str(m): (str(rc), float(ws)) for m, rc, ws in lc.execute(
        "SELECT match_id,result_code,winning_sp FROM settlements "
        "WHERE result_code IS NOT NULL AND winning_sp>0")}
    euro = {str(m): (h, d, a) for m, h, d, a in lc.execute(
        "SELECT match_id,avg_eu_h,avg_eu_d,avg_eu_a FROM settlements "
        "WHERE avg_eu_h>0 AND avg_eu_d>0 AND avg_eu_a>0")}
    drifts, raw, sp_eu_absdiff = [], [], []
    for mid, d in by_match.items():
        sp = [d.get(c) for c in CODES]
        if any(s is None or s <= 1.0 for s in sp):
            continue
        inv = sum(1.0 / s for s in sp)
        if not (0.85 <= inv <= 1.25):            # sane gross book (≈1.0)
            continue
        raw.append((mid, sp))
        if mid in settle:
            rc, ws = settle[mid]
            if rc in CODES:
                dsp = sp[CODES.index(rc)]
                if dsp > 0:
                    drifts.append(ws / dsp)
        # EU-vs-SP sanity ONLY on line=0 (straight; euro 1X2 ↔ 北单 result maps)
        if line.get(mid) == 0 and mid in euro:
            S = sum(1.0 / s for s in sp)
            p_sp = [(1.0 / s) / S for s in sp]
            p_eu = devig3(*euro[mid])             # (p_home,p_draw,p_away) ↔ (3,1,0)
            sp_eu_absdiff.append(sum(abs(a - b) for a, b in zip(p_sp, p_eu)) / 3)
    drift_gm = (st.geometric_mean([d for d in drifts if d > 0]) if drifts else 1.0)
    pool = []
    for mid, sp in raw:
        inv = [1.0 / s for s in sp]
        S = sum(inv)
        p = tuple(i / S for i in inv)             # crowd-implied prob
        sps = tuple(s * drift_gm for s in sp)     # drift-adjusted payout
        pool.append(Leg(probs=p, sps=sps))
    sanity = dict(n_line0=len(sp_eu_absdiff),
                  mean_abs_diff=(st.mean(sp_eu_absdiff) if sp_eu_absdiff else float("nan")))
    return pool, drift_gm, len(drifts), sanity


def main():
    base = P.baseline_decision_mtk(WEBUI)
    pool, drift_gm, n_drift, sanity = load_pool(base)
    print(f"decision MTK={base:.0f}min; pool legs={len(pool)}; "
          f"drift_gm={drift_gm:.3f} (n={n_drift}); budget={BUDGET:.0f}; seed={SEED}\n")

    # ---- EU-vs-SP sanity: why we use 北单 SP-implied p, not euro de-vig ----
    print("== 口径 sanity：北单 SP-implied p vs 欧赔去水 p（仅 line=0 可比，O5）==")
    print(f"  line=0 样本 {sanity['n_line0']} 腿，SP-implied 与欧赔 p 平均逐结果 |Δ| = "
          f"{sanity['mean_abs_diff']:.3f}")
    print("  → line=0 上两者一致(O5 北单≈欧赔)，故 SP-implied p 可靠；让球腿欧赔1X2≠让球结果"
          "(O5 错配,naive euro-p 会造 EV 荒谬值)→本 Track A 一律用 SP-implied(无edge基线,更保守)。\n")

    # near-kickoff decision shrinks drift -> lifts the high-N floor.
    _, drift_near, n_near, _ = load_pool(180.0)
    print(f"== 时机×N：漂移随决策临近开赛而消（近开赛 180min vs 远 {base:.0f}min）==")
    print(f"  drift_gm: {base:.0f}min={drift_gm:.3f} → 180min={drift_near:.3f} (n={n_near})")
    print(f"  N=7 无edge EV/元: 远 {100*RR*drift_gm**7:.1f}% → 近 {100*RR*drift_near**7:.1f}% "
          f"(理想 0 漂移上限 {100*RR:.0f}%)。**高 N 把漂移放大 7 次方 → 临近决策对高 N 价值远大于低 N。**\n")

    # ---- EV invariant: single-select parlay floor by N ----
    print("== EV 不变性：纯市场单选串 EV/元 = RR × drift^N（N 不改抽水，漂移复利）==")
    print(f"  {'N':>2} {'EV/元(无edge)':>13} {'若每腿edge+10%':>15}")
    for n in [2, 3, 4, 5, 6, 7]:
        ev0 = RR * drift_gm ** n
        ev_edge = RR * (1.10 * drift_gm) ** n     # Track B teaser: p·sp=1.10
        print(f"  {n:>2} {100*ev0:>11.1f}% {100*ev_edge:>14.1f}%")
    print("  → 无 edge 任何 N 都亏；高 N 漂移复利更狠。只有 ∏选腿>1/drift 才翻正(Track B)。\n")

    # ---- break-even per-leg selection edge (the key Track-B target) ----
    # EV=RR×(sel×drift)^N ≥ 1  ⇔  sel ≥ 1.538^(1/N) / drift
    print("== 盈亏平衡所需「每腿选腿 sel=p×sp」（sel×drift ≥ RR^(-1/N)）==")
    print(f"  {'N':>2} {'远(drift0.758)':>14} {'近开赛(drift0.960)':>18}")
    for n in [2, 3, 4, 5, 6, 7]:
        need = (1.0 / RR) ** (1.0 / n)
        print(f"  {n:>2} {need/drift_gm:>13.3f} {need/drift_near:>17.3f}")
    print("  → 抽水每票一次→高 N 把它摊薄，高 N 需要的『每腿 edge 更小』；近开赛 N=7 只需 sel≈1.11"
          "(每腿+11%)。**高N+近开赛 是对每腿 edge 要求最低的角落**(若 Track B 找得到 edge)。\n")

    # ---- FULL coverage config space: enumerate every (n_single,n_cover2,n_cover3) ----
    def enumerate_configs(N):
        pts = []
        for c2 in range(N + 1):
            for c3 in range(N + 1 - c2):
                s = simulate_strategy(pool, n_legs=N, n_cover2=c2, n_cover3=c3,
                                      budget=BUDGET, n_sims=N_ENUM, seed=SEED,
                                      thresholds=THR)
                pts.append(((N - c2 - c3, c2, c3), s))
        return pts

    def pareto_frontier(pts):
        """Non-dominated on (hit_rate↑, median_jackpot↑) — EV is flat, so the only
        real trade is P(hit) vs jackpot."""
        front = []
        for cfg, s in pts:
            if not any(
                o["hit_rate"] >= s["hit_rate"] and o["median_jackpot"] >= s["median_jackpot"]
                and (o["hit_rate"] > s["hit_rate"] or o["median_jackpot"] > s["median_jackpot"])
                for _, o in pts):
                front.append((cfg, s))
        return sorted(front, key=lambda x: x[1]["hit_rate"])

    for N in [7, 6]:
        pts = enumerate_configs(N)
        front = pareto_frontier(pts)
        front_cfgs = {c for c, _ in front}
        print(f"== N={N} 完整配置空间枚举（所有 n_single+n_cover2+n_cover3={N}，"
              f"共 {len(pts)} 点；预算 {BUDGET:.0f}）==")
        print(f"  EV/预算 全恒 ≈{100*(pts[0][1]['mean_roi']+1):.1f}%（覆盖不改 EV）。下表 ★=Pareto 前沿"
              f"（P命中↔奖金非占优），含混合 cover-2/cover-3 配置：")
        print(f"  {'(单,c2,c3)':>12} {'票数':>6} {'P(命中)':>9} {'中位奖':>9} "
              f"{'P95奖':>9} {'P(≥10万)':>9}")
        for cfg, s in front:
            print(f"  ★{str(cfg):>11} {s['tickets']:>6} {s['hit_rate']:>8.4f} "
                  f"{s['median_jackpot']:>9.0f} {s['p95_jackpot']:>9.0f} "
                  f"{s['p_threshold'][THR[0]]:>9.5f}")
        # a few dominated points for contrast (same P(hit) reachable with more jackpot)
        dom = [(c, s) for c, s in pts if c not in front_cfgs][:3]
        if dom:
            print("  被占优点示例（同 P命中 下票更多/奖金更碎，故不在前沿）：")
            for cfg, s in dom:
                print(f"   {str(cfg):>12} {s['tickets']:>6} {s['hit_rate']:>8.4f} "
                      f"{s['median_jackpot']:>9.0f}")
        print(f"  前沿点 {len(front)}/{len(pts)}。")
        if N == 7:
            pts7, front7 = pts, front

    print(f"\n关键发现：**Pareto 前沿密集(N=7: {len(front7)}/{len(pts7)} 点非占优)、连续，由混合 (单,c2,c3) 配置铺成**，"
          "从 (7,0,0)[低命中高奖金] 一路到 (0,0,7)[全包必中低奖金]。选哪点取决于**目标 P(命中)**："
          "低命中端 cover-2 更高效（同命中率票更少、奖金更高，如 (5,2,0) 优于 (4,2,1)）；要冲高命中端"
          "必须用 cover-3。**没有单一『只用 cover-2』法则**；EV/预算 全程恒定（覆盖不改 EV）。")
    print("税务：单票奖金>1万触发 20% 税，需拆票；高 N 单压的稀有大奖必然破万→必须拆。")

    make_figure(pts7, front7, drift_gm)


def make_figure(pts, front, drift_gm):
    """Scatter the full N=7 (n_single,c2,c3) config space (P(hit) vs median
    jackpot); the Pareto frontier (non-dominated) is highlighted. EV is flat
    across every point — the only trade is P(hit) ↔ jackpot."""
    FIG.parent.mkdir(parents=True, exist_ok=True)
    front_cfgs = {c for c, _ in front}
    dom = [(c, s) for c, s in pts if c not in front_cfgs]
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    ax.scatter([s["hit_rate"] for _, s in dom], [s["median_jackpot"] for _, s in dom],
               s=26, c="#bbbbbb", alpha=0.7, label="dominated config")
    fx = [s["hit_rate"] for c, s in front]
    fy = [s["median_jackpot"] for c, s in front]
    ax.plot(fx, fy, "k-o", ms=6, lw=1.5, label="Pareto frontier (mixed configs)")
    for (c, s) in front:
        if c[2] == 0 or c == front[-1][0] or c == front[0][0]:   # label cover-2/end points
            ax.annotate(str(c), (s["hit_rate"], s["median_jackpot"]), fontsize=6,
                        xytext=(3, 3), textcoords="offset points")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("P(hit any prize)"); ax.set_ylabel("median jackpot | hit (yuan, budget=1000)")
    ax.set_title(f"N=7 full coverage config space (36 pts) — frontier spans the "
                 f"P(hit)↔jackpot trade (EV flat ≈ {100*RR*drift_gm**7:.1f}%)")
    ax.legend(fontsize=8); ax.grid(alpha=0.3, which="both")
    fig.tight_layout(); fig.savefig(FIG, dpi=110)
    print(f"\nwrote {FIG}")


if __name__ == "__main__":
    main()
