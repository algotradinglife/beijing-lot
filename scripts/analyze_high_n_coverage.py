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
from src.moonshot.coverage import RR, Leg, simulate_strategy

LIVE, WEBUI = "data/beidan_live.db", "data/webui.db"
CACHE = "data/derived/sp_drift/panel.parquet"
BUDGET = 1000.0
THR = [100_000.0, 1_000_000.0]
SEED, N_SIMS = 0, 300_000
FIG = Path("docs/research/figures/high_n_coverage.png")
CODES = ["3", "1", "0"]  # outcome index 0/1/2


def load_pool(decision_mtk: float):
    """Return (pool: list[Leg], drift_gm). Per match: gross decision SP per
    outcome (de-vigged to crowd p), payout drift-adjusted."""
    pan = P.build(LIVE, cache_path=CACHE, rebuild=False)
    dv = P.decision_view(pan, decision_mtk)
    # pivot long -> per-match {selection: sp}
    by_match: dict = {}
    for r in dv.itertuples(index=False):
        by_match.setdefault(r.match_id, {})[r.selection] = r.sp
    # realised settlement
    lc = sqlite3.connect(LIVE)
    settle = {str(m): (str(rc), float(ws)) for m, rc, ws in lc.execute(
        "SELECT match_id,result_code,winning_sp FROM settlements "
        "WHERE result_code IS NOT NULL AND winning_sp>0")}
    drifts = []
    raw = []  # (mid, sp3, sp1, sp0)
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
    drift_gm = (st.geometric_mean([d for d in drifts if d > 0])
                if drifts else 1.0)
    pool = []
    for mid, sp in raw:
        inv = [1.0 / s for s in sp]
        S = sum(inv)
        p = tuple(i / S for i in inv)             # crowd-implied prob
        sps = tuple(s * drift_gm for s in sp)     # drift-adjusted payout
        pool.append(Leg(probs=p, sps=sps))
    return pool, drift_gm, len(drifts)


def main():
    base = P.baseline_decision_mtk(WEBUI)
    pool, drift_gm, n_drift = load_pool(base)
    print(f"decision MTK={base:.0f}min; pool legs={len(pool)}; "
          f"drift_gm={drift_gm:.3f} (n={n_drift}); budget={BUDGET:.0f}; seed={SEED}\n")

    # near-kickoff decision shrinks drift -> lifts the high-N floor (why timing
    # matters MORE at high N). Cheap: just recompute drift_gm at 180min (3h).
    _, drift_near, n_near = load_pool(180.0)
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

    # ---- coverage frontier for N=7 and N=6 ----
    for N in [7, 6]:
        print(f"== N={N} 覆盖前沿（预算 {BUDGET:.0f} 元；单压最确定的、cover-3 最不确定的 n 条）==")
        print(f"  {'盖几条':>6} {'票数':>6} {'每票':>7} {'P(命中)':>9} {'EV/预算':>8} "
              f"{'中位奖':>10} {'P95奖':>11} {'最大奖':>12} {'P(≥10万)':>9} {'P(≥100万)':>10}")
        rows = []
        for nc in range(0, N + 1):
            s = simulate_strategy(pool, n_legs=N, n_cover3=nc, budget=BUDGET,
                                  n_sims=N_SIMS, seed=SEED, thresholds=THR)
            rows.append((nc, s))
            print(f"  {nc:>6} {s['tickets']:>6} {s['stake_per_ticket']:>7.1f} "
                  f"{s['hit_rate']:>8.4f} {100*(s['mean_roi']+1):>7.1f}% "
                  f"{s['median_jackpot']:>10.0f} {s['p95_jackpot']:>11.0f} "
                  f"{s['max_jackpot']:>12.0f} {s['p_threshold'][THR[0]]:>9.5f} "
                  f"{s['p_threshold'][THR[1]]:>10.6f}")
        if N == 7:
            rows7 = rows
    print("\n注：EV/预算 在各覆盖档基本恒为 RR×drift^N（覆盖只换命中率↔奖金形状，不改 EV）。")
    print("税务：单票奖金>1万触发 20% 税，需拆票；高 N 单压的稀有大奖必然破万→必须拆。")

    make_figure(rows7, drift_gm)


def make_figure(rows, drift_gm):
    FIG.parent.mkdir(parents=True, exist_ok=True)
    ncs = [r[0] for r in rows]
    hit = [r[1]["hit_rate"] for r in rows]
    p10w = [r[1]["p_threshold"][THR[0]] for r in rows]
    medj = [r[1]["median_jackpot"] for r in rows]
    fig, (axl, axr) = plt.subplots(1, 2, figsize=(11, 4.4))
    axl.plot(ncs, hit, "o-", label="P(hit any prize)")
    axl.plot(ncs, p10w, "s--", color="#c0504d", label="P(jackpot ≥ 100k)")
    axl.set_xlabel("# legs covered (cover-3)"); axl.set_ylabel("probability")
    axl.set_yscale("log"); axl.set_title("N=7: covering raises P(hit), shrinks jackpot")
    axl.legend(fontsize=8); axl.grid(alpha=0.3)
    axr.plot(ncs, medj, "o-", color="#4f81bd", label="median jackpot | hit")
    axr.set_xlabel("# legs covered (cover-3)"); axr.set_ylabel("yuan (budget=1000)")
    axr.set_yscale("log")
    axr.set_title(f"N=7 jackpot vs coverage (EV flat ≈ {100*RR*drift_gm**7:.1f}%)")
    axr.legend(fontsize=8); axr.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(FIG, dpi=110)
    print(f"\nwrote {FIG}")


if __name__ == "__main__":
    main()
