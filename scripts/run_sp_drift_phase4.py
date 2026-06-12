"""Phase 4 counterfactual replay → docs/research/sp_drift_phase4.md + figure.

Compares the live baseline (decide ~18h-out, no haircut) against decision-
timing variants and a per-band haircut, on realized (settle-on-winning_sp)
PnL. Produces the GATE 3 go/no-go table.

Run: PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_phase4.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.phase5a.filter import NicheConfig
from src.sp_drift import panel as P
from src.sp_drift import replay as R

LIVE, WEBUI = "data/beidan_live.db", "data/webui.db"
CACHE = "data/derived/sp_drift/panel.parquet"
OUT = Path("docs/research/sp_drift_phase4.md")
FIGDIR = Path("docs/research/figures")

# GATE 1 per-band drift_bias (used as the haircut map).
BAND_BIAS = {"<3.5": 0.33, "3.5-4.5": -0.09, "4.5-5": -0.21, "5-8": -0.36, ">8": -0.81}


def main() -> None:
    pan = P.build(LIVE, cache_path=CACHE)
    cfg = NicheConfig.load()
    t_base = P.baseline_decision_mtk(WEBUI)

    variants = [
        ("baseline ~18h-out", R.Policy(mtk_target=t_base)),
        ("window 4h", R.Policy(mtk_target=240)),
        ("window 1h", R.Policy(mtk_target=60)),
        ("window 1h + band haircut", R.Policy(mtk_target=60, haircut=BAND_BIAS)),
    ]
    results = [(name, R.replay_policy(pan, LIVE, cfg, pol)) for name, pol in variants]

    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for name, res in results:
        ax.plot(range(len(res["equity"])), res["equity"], label=name)
    ax.set_xlabel("issue # (chronological)")
    ax.set_ylabel("bankroll")
    ax.set_title("Replay equity by policy (settle on real SP)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGDIR / "sp_drift_replay_equity.png", dpi=110)

    by_name = {name: r for name, r in results}
    base_roi = results[0][1]["roi"]
    # The honest GATE-3 metric is the CONSERVATIVE haircut variant, not the
    # highest-ROI variant: a no-haircut late-window run can post a huge ROI
    # driven by a handful of N=4 combo hits (variance), which is not a robust
    # expectation. The haircut variant prices the expected drift in, so its
    # realized ROI is the defensible number.
    conservative = by_name["window 1h + band haircut"]
    timing_only = by_name["window 1h"]
    house_edge_cleared = conservative["roi"] > 0

    lines = [
        "# SP 漂移 Phase 4 — 反事实重放与 GATE 3\n",
        f"基线决策 MTK = {t_base:.0f} 分钟; N={variants[0][1].n_legs}, "
        f"kelly={variants[0][1].kelly_fraction}, 起始 bankroll={variants[0][1].start_bankroll:,.0f}\n",
        "> 重放不变量：在**决策时刻 SP**（可选 haircut）上 qualify/sizing，在**真实结算 winning_sp** 上结算。\n",
        "## 各策略对比\n",
        "| 策略 | 周数 | 票数 | 命中 | 总投注 | ROI | MaxDD | 终值 bankroll |",
        "|------|------|------|------|--------|-----|-------|----------------|",
        *[f"| {name} | {r['n_weeks']} | {r['n_tickets']} | {r.get('n_hits', 0)} | "
          f"{r['total_stake']:,.0f} | **{r['roi']*100:+.1f}%** | {r['max_dd']*100:.0f}% | "
          f"{r['final_bankroll']:,.0f} |"
          for name, r in results],
        "",
        "## GATE 3 决策\n",
        f"- **时机方向（核心信号）**：决策从 ~18h-out 移到 1h-out，ROI "
        f"{base_roi*100:+.0f}% → {timing_only['roi']*100:+.0f}%——巨大且方向明确。"
        f"但 window-1h 的高 ROI 由仅 {timing_only.get('n_hits',0)} 注 N=4 命中驱动（方差大），**量级不可信**。",
        f"- **保守判据（按档 haircut，把预期漂移计入 EV）**：ROI = "
        f"**{conservative['roi']*100:+.1f}%**（命中 {conservative.get('n_hits',0)} 注，MaxDD "
        f"{conservative['max_dd']*100:.0f}%）→ **{'扣房费后为正' if house_edge_cleared else '仍为负'}**",
        "",
        "**判定**："
        + ("**方向性 Go**：时机是巨大的真实杠杆，且把漂移计入 EV 后保守 ROI 仍为正。"
           "但样本太薄（~5.5 周 / 个位数命中 / in-sample haircut），**量级不可信**，"
           "不能据此承诺收益。建议落地两项改动（`kickoff_window` 移到临近开赛 + 按档 haircut）"
           "并写**上线前 forward-test spec**，用时间外样本验证后再加注。" if house_edge_cleared
           else "保守判据下真实 ROI 仍为负 → 漂移缓解不足以稳健跨过 35% 房费，"
                "需重审玩法/N/SP 区间（时机方向虽好但 haircut 后吃不到）。"),
        "",
        "> ⚠️ 局限：样本仅 ~5.5 周（单赛季切片）、N=4 命中个位数（ROI 方差极大）；"
        "baseline 用统一 MTK 比实盘更早（实盘 +4.3% 是混合时点），故 baseline −100% 偏悲观、"
        "不能与实盘直接比；haircut 用同期 GATE 1 估计（in-sample），上线前须时间外样本复核。",
        "\n![replay equity](figures/sp_drift_replay_equity.png)\n",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
