"""SP-drift forward-test runner → ledger + docs/research/sp_drift_forward.md.

Run weekly (systemd timer) or manually:
  PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_forward.py
"""
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.phase5a.filter import NicheConfig
from src.sp_drift import forward as F
from src.sp_drift import panel as P

LIVE, WEBUI = "data/beidan_live.db", "data/webui.db"
CACHE = "data/derived/sp_drift/panel.parquet"
LEDGER = "data/derived/sp_drift/forward_ledger.csv"
OUT = Path("docs/research/sp_drift_forward.md")
FIGDIR = Path("docs/research/figures")


def main() -> None:
    today = date.today().isoformat()
    pan = P.build(LIVE, cache_path=CACHE, rebuild=True)
    cfg = NicheConfig.load()
    baseline = P.baseline_decision_mtk(WEBUI)
    arms = F.build_arms(baseline_mtk=baseline, haircut_map=F.HAIRCUT_MAP)
    rows = F.run_forward(pan, LIVE, cfg, arms, run_date=today, forward_start=F.FORWARD_START)
    # FAV5: descriptive 'bet the favorite, N=5' arm (flat-staked, not GATE-FT).
    rows.append(F.favorite_arm_row(pan, LIVE, today, forward_start=F.FORWARD_START,
                                   n_legs=5, mtk_target=baseline))
    ledger = F.append_ledger(rows, LEDGER)
    status = F.check_stopping_rule(ledger, F.FORWARD_START, today)

    # arms present in this run, in build order (C0/C1/C2 then N-sweep N3/N5)
    arm_names = [r["arm"] for r in rows]

    # cumulative ROI-by-arm over run_dates
    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for arm in arm_names:
        sub = ledger[ledger["arm"] == arm].sort_values("run_date")
        ax.plot(sub["run_date"], sub["roi"] * 100, "o-", label=arm)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("cumulative ROI %")
    ax.set_title("Forward-test ROI by arm (OOS, paper)")
    ax.legend(); ax.grid(alpha=0.3)
    plt.xticks(rotation=45, ha="right", fontsize=7)
    fig.tight_layout()
    fig.savefig(FIGDIR / "sp_drift_forward_roi.png", dpi=110)

    latest = {r["arm"]: r for r in rows}
    lines = [
        "# SP 漂移 Forward-Test（纸面 · OOS）\n",
        f"run_date={today}; FORWARD_START={F.FORWARD_START}; "
        f"weeks_elapsed={status['weeks_elapsed']:.1f}\n",
        "## 各 arm 累计（FORWARD_START 至今的样本外切片）\n",
        *F.render_arm_table(latest, arm_names),
        "",
        "## 停止规则 / GATE-FT 状态\n",
        f"- stop={status['stop']}  reason={status['reason']}  **verdict={status['verdict']}**",
        f"- C2 组合数 {status['c2_n_combos']}/200 · 周数 {status['weeks_elapsed']:.1f}/12 · "
        f"C2 MaxDD {status['c2_max_dd']*100:.0f}%/50%",
        f"- ROI: C0 {status['c0_roi']*100:+.1f}% / C1 {status['c1_roi']*100:+.1f}% / "
        f"C2 {status['c2_roi']*100:+.1f}%（go 需 C2>0 且 C2−C0≥5pp 且 C1−C0≥5pp）",
        "",
        "> 纸面、样本外、haircut 冻结在 GATE 1 值。样本初期很小，勿据早期数据下结论。",
        "> **N3 / N5 是描述性 N-sweep arm**（与 C0 同决策时机、仅 n_legs 不同），"
        "用于观察腿数对 ROI/漂移的影响（盈亏归因显示漂移随 N 乘法放大）；"
        "**不参与 GATE-FT 判定**（judging 仍只看 C0/C1/C2）。",
        "> **FAV5 是「押每场最热门(最低SP)、N=5」arm**（平注，非 Kelly）：检验"
        "「抽水每票一次×热门 realized p×SP>1×中等N」的假说（见 high_n_favorite_parlay 研究）；"
        "roi/命中率/周σ 为有效指标，其 MaxDD 与 Kelly-sized 的 C/N arm 不可直接比；不进 GATE-FT。",
        "> ⚠️ **运营口径差**：C1/C2 的 window 是按期次池化、每场各取其「距开赛 180min」的 SP；"
        "实盘 `kickoff_window_hours` 是「距现在 N 小时内开赛」的同时性过滤，二者不等价。"
        "经 P1 权衡分析（2026-06-14）：受 N=4 需 ≥30 场同时在池约束，任何窗口值都无法两全"
        "（紧→autoplan 饿死、松→漂移不降），故实盘窗口已改回 0。本 test 量化的是「理想临近决策」"
        "的上界，落地需运营机制重设计（已搁置）。",
        "\n![forward roi](figures/sp_drift_forward_roi.png)\n",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT} and appended {LEDGER}")


if __name__ == "__main__":
    main()
