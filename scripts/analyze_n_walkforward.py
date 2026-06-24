"""A1 —降N walk-forward: does N3's in-sample +19.7% (pnl_attribution) hold
out-of-time, and is any per-N ROI statistically distinguishable on 16 live weeks?

N is structural (not a fitted parameter), so this is out-of-time realized
performance + per-week stability + block-bootstrap CI + leave-one-week-out
fragility — NOT a train/test parameter search. replay_policy qualifies/sizes on
the decision-time SP (production baseline MTK) and settles on the real
winning_sp, rolling a bankroll issue-by-issue; pure-N has no fitted params, so
no leakage.

Deterministic (fixed seed, sorted issues). Writes
docs/research/figures/n_walkforward.png.
Run:  PYTHONPATH=".:src" .venv/bin/python scripts/analyze_n_walkforward.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.sp_drift import panel as P
from src.sp_drift.replay import Policy, replay_policy
from src.sp_drift.walkforward import bootstrap_roi_ci, leave_one_week_out
from src.phase5a.filter import NicheConfig

LIVE, WEBUI = "data/beidan_live.db", "data/webui.db"
CACHE = "data/derived/sp_drift/panel.parquet"
NS = [2, 3, 4, 5]
N_BOOT, SEED = 20000, 0
FIG = Path("docs/research/figures/n_walkforward.png")
# pnl_attribution realized ROI on actually-booked tickets (in-sample reference)
REALIZED = {2: 1.2, 3: 19.7, 4: -52.7}


def main():
    pan = P.build(LIVE, cache_path=CACHE, rebuild=False)
    base = P.baseline_decision_mtk(WEBUI)
    cfg = NicheConfig.load()
    print(f"baseline decision MTK = {base:.0f} min (~{base/60:.1f}h out); "
          f"bootstrap n={N_BOOT} seed={SEED}\n")

    res = {}
    for n in NS:
        res[n] = replay_policy(pan, LIVE, cfg, Policy(mtk_target=base, n_legs=n))

    # ---- table 1: headline + uncertainty ----
    print("== 全样本 replay（决策SP qualify, 真实 winning_sp 结算） ==")
    print("  注: ROI 是 Σpnl/Σstake，stake 受 Kelly 在小 edge 上压得很小；'账户Δ' 是 "
          "16周后 bankroll 净变化（10万本金），才是经济上真实的量级。")
    print(f"  {'N':>2} {'票':>5} {'中':>4} {'命中%':>6} {'ROI':>8} "
          f"{'boot中位':>8} {'P(ROI>0)':>8} {'boot95%CI':>18} {'账户Δ(元)':>10} {'实盘ROI':>8}")
    cis = {}
    for n in NS:
        r = res[n]
        wk = r["weeks"]
        roi = 100 * r["roi"]
        hr = 100 * r["n_hits"] / r["n_tickets"] if r["n_tickets"] else 0.0
        ci = bootstrap_roi_ci(wk, n_boot=N_BOOT, seed=SEED)
        cis[n] = ci
        acct = r["final_bankroll"] - 100000.0
        real = f"{REALIZED[n]:+.1f}%" if n in REALIZED else "—"
        print(f"  {n:>2} {r['n_tickets']:>5} {r['n_hits']:>4} {hr:>5.1f}% "
              f"{roi:>7.1f}% {100*ci['median']:>7.1f}% {ci['p_positive']:>8.2f} "
              f"[{100*ci['lo']:>6.1f}%,{100*ci['hi']:>6.1f}%] {acct:>+10.0f} {real:>8}")

    # ---- table 2: leave-one-week-out fragility ----
    print("\n== leave-one-week-out 脆弱性（去掉单周后 ROI 摆动）==")
    print(f"  {'N':>2} {'base':>8} {'去最佳周→':>12} {'去最差周→':>12} {'摆幅(pp)':>9}")
    for n in NS:
        j = leave_one_week_out(res[n]["weeks"])
        drop_iss, drop_sw = j["max_drop"]   # removing this week lowers ROI most
        rise_iss, rise_sw = j["max_rise"]
        roi_wo_best = 100 * (j["base"] + drop_sw)
        roi_wo_worst = 100 * (j["base"] + rise_sw)
        span = 100 * (rise_sw - drop_sw)
        print(f"  {n:>2} {100*j['base']:>7.1f}% "
              f"{roi_wo_best:>7.1f}%({drop_iss}) {roi_wo_worst:>7.1f}%({rise_iss}) "
              f"{span:>8.1f}")

    # ---- separability check vs N4 (pre-registered criterion) ----
    print("\n== 预注册裁决：N3 的 ROI bootstrap CI 是否排除 N4 点估？==")
    n3, n4 = cis[3], cis[4]
    sep = n3["lo"] > 100 * 0 and (n3["lo"] > res[4]["roi"] or n4["hi"] < res[3]["roi"])
    overlap = not (n3["hi"] < n4["lo"] or n4["hi"] < n3["lo"])
    print(f"  N3 CI=[{100*n3['lo']:.1f}%,{100*n3['hi']:.1f}%], "
          f"N4 CI=[{100*n4['lo']:.1f}%,{100*n4['hi']:.1f}%] → "
          f"{'重叠（不可区分）' if overlap else '分离'}")

    make_figure(res, cis)


def make_figure(res, cis):
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig, (axl, axr) = plt.subplots(1, 2, figsize=(11, 4.4))
    for n in NS:
        eq = res[n]["equity"]
        axl.plot(range(len(eq)), eq, "o-", ms=3, label=f"N={n}")
    axl.axhline(100000, color="k", lw=1, alpha=0.4)
    axl.set_xlabel("week (issue index)"); axl.set_ylabel("bankroll")
    axl.set_title("Equity by N (pure-N replay, 16 weeks)")
    axl.legend(fontsize=8); axl.grid(alpha=0.3)

    x = list(range(len(NS)))
    pts = [100 * res[n]["roi"] for n in NS]
    lo = [100 * res[n]["roi"] - 100 * cis[n]["lo"] for n in NS]
    hi = [100 * cis[n]["hi"] - 100 * res[n]["roi"] for n in NS]
    axr.errorbar(x, pts, yerr=[lo, hi], fmt="o", capsize=5, color="#4f81bd")
    axr.axhline(0, color="k", lw=1)
    axr.set_xticks(x); axr.set_xticklabels([f"N={n}" for n in NS])
    axr.set_ylabel("ROI % (point + bootstrap 95% CI)")
    axr.set_title("Per-N ROI with bootstrap CI (wide = small-sample noise)")
    axr.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(FIG, dpi=110)
    print(f"\nwrote {FIG}")


if __name__ == "__main__":
    main()
