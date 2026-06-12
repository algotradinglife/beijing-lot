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

    base_roi = results[0][1]["roi"]
    best = max(results, key=lambda r: r[1]["roi"])
    house_edge_cleared = best[1]["roi"] > 0  # ROI on staked money > 0 after the 35% take

    lines = [
        "# SP 漂移 Phase 4 — 反事实重放与 GATE 3\n",
        f"基线决策 MTK = {t_base:.0f} 分钟; N={variants[0][1].n_legs}, "
        f"kelly={variants[0][1].kelly_fraction}, 起始 bankroll={variants[0][1].start_bankroll:,.0f}\n",
        "> 重放不变量：在**决策时刻 SP**（可选 haircut）上 qualify/sizing，在**真实结算 winning_sp** 上结算。\n",
        "## 各策略对比\n",
        "| 策略 | 周数 | 票数 | 总投注 | ROI | MaxDD | 终值 bankroll |",
        "|------|------|------|--------|-----|-------|----------------|",
        *[f"| {name} | {r['n_weeks']} | {r['n_tickets']} | {r['total_stake']:,.0f} | "
          f"**{r['roi']*100:+.1f}%** | {r['max_dd']*100:.0f}% | {r['final_bankroll']:,.0f} |"
          for name, r in results],
        "",
        f"基线 ROI = {base_roi*100:+.1f}%；最优 = **{best[0]}** ROI {best[1]['roi']*100:+.1f}%。\n",
        "## GATE 3 决策\n",
        f"- 最优策略 ROI（扣 35% 房费后，即重放净 ROI）= {best[1]['roi']*100:+.1f}% → "
        f"**{'跨过房费为正' if house_edge_cleared else '仍为负'}**",
        f"- 相对基线改善 = {(best[1]['roi']-base_roi)*100:+.1f}pp",
        "",
        "**判定**："
        + ("最优策略真实 ROI 为正且优于基线 → 推荐落地（kickoff_window 默认值 + 按档 haircut），"
           "交付上线前实盘验证 spec。" if house_edge_cleared
           else "即便最优策略真实 ROI 仍为负 → SP 漂移缓解不足以跨过 35% 房费，"
                "N=4 让球当前不可行，触发对玩法/N/SP 区间的重审。"),
        "",
        "> ⚠️ 局限：样本仅 ~5.5 周（单赛季切片）；重放用面板覆盖的比赛；"
        "haircut 用的是同期 GATE 1 估计（in-sample），上线前需用时间外样本复核。",
        "\n![replay equity](figures/sp_drift_replay_equity.png)\n",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
