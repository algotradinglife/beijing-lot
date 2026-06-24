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

    # ---- coverage frontier: cover-2 ladder AND cover-3 ladder, N=7 then N=6 ----
    def run_ladder(N, mode):
        """mode='cover3' or 'cover2': cover n least-confident legs at all-3 / top-2."""
        rows = []
        for nc in range(0, N + 1):
            kw = {"n_cover3": nc} if mode == "cover3" else {"n_cover2": nc}
            s = simulate_strategy(pool, n_legs=N, budget=BUDGET, n_sims=N_SIMS,
                                  seed=SEED, thresholds=THR, **kw)
            rows.append((nc, s))
        return rows

    def print_ladder(title, rows):
        print(title)
        print(f"  {'盖几条':>6} {'票数':>6} {'每票':>7} {'P(命中)':>9} {'EV/预算':>8} "
              f"{'中位奖':>10} {'P95奖':>11} {'最大奖':>12} {'P(≥10万)':>9} {'P(≥100万)':>10}")
        for nc, s in rows:
            print(f"  {nc:>6} {s['tickets']:>6} {s['stake_per_ticket']:>7.1f} "
                  f"{s['hit_rate']:>8.4f} {100*(s['mean_roi']+1):>7.1f}% "
                  f"{s['median_jackpot']:>10.0f} {s['p95_jackpot']:>11.0f} "
                  f"{s['max_jackpot']:>12.0f} {s['p_threshold'][THR[0]]:>9.5f} "
                  f"{s['p_threshold'][THR[1]]:>10.6f}")

    rows7_c3 = run_ladder(7, "cover3")
    rows7_c2 = run_ladder(7, "cover2")
    print_ladder(f"== N=7 覆盖前沿 · cover-3 梯度（全包不确定的 n 条；预算 {BUDGET:.0f}）==", rows7_c3)
    print_ladder("== N=7 覆盖前沿 · cover-2 梯度（只包不确定腿的 top-2，丢最不可能结果）==", rows7_c2)
    print_ladder(f"== N=6 覆盖前沿 · cover-3 梯度（预算 {BUDGET:.0f}）==", run_ladder(6, "cover3"))

    print("\n注：EV/预算 在各覆盖档基本恒为 RR×drift^N（覆盖只换命中率↔奖金形状，不改 EV）。")
    print("cover-2 vs cover-3：同样盖 n 条，cover-2 票更少(2^n vs 3^n)、每票更大、命中率增益较小但"
          "**奖金保留更多**——丢掉的是各腿最不可能的结果，是更 EV/奖金高效的覆盖。")
    print("税务：单票奖金>1万触发 20% 税，需拆票；高 N 单压的稀有大奖必然破万→必须拆。")

    make_figure(rows7_c3, rows7_c2, drift_gm)


def make_figure(rows_c3, rows_c2, drift_gm):
    FIG.parent.mkdir(parents=True, exist_ok=True)
    ncs = [r[0] for r in rows_c3]
    fig, (axl, axr) = plt.subplots(1, 2, figsize=(11, 4.4))
    axl.plot(ncs, [r[1]["hit_rate"] for r in rows_c3], "o-", color="#4f81bd",
             label="cover-3 P(hit)")
    axl.plot(ncs, [r[1]["hit_rate"] for r in rows_c2], "o--", color="#9bbb59",
             label="cover-2 P(hit)")
    axl.plot(ncs, [r[1]["p_threshold"][THR[0]] for r in rows_c3], "s:", color="#c0504d",
             label="cover-3 P(jackpot ≥ 100k)")
    axl.set_xlabel("# uncertain legs covered"); axl.set_ylabel("probability")
    axl.set_yscale("log"); axl.set_title("N=7: covering raises P(hit), shrinks jackpot")
    axl.legend(fontsize=8); axl.grid(alpha=0.3)
    axr.plot(ncs, [r[1]["median_jackpot"] for r in rows_c3], "o-", color="#4f81bd",
             label="cover-3 median jackpot")
    axr.plot(ncs, [r[1]["median_jackpot"] for r in rows_c2], "o--", color="#9bbb59",
             label="cover-2 median jackpot (more retained)")
    axr.set_xlabel("# uncertain legs covered"); axr.set_ylabel("yuan (budget=1000)")
    axr.set_yscale("log")
    axr.set_title(f"N=7 jackpot vs coverage (EV flat ≈ {100*RR*drift_gm**7:.1f}%)")
    axr.legend(fontsize=8); axr.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(FIG, dpi=110)
    print(f"\nwrote {FIG}")


if __name__ == "__main__":
    main()
