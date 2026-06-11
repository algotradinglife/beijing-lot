"""Phase 1 drift quantification → docs/research/sp_drift_phase1.md + figures.

Builds the decision view at the baseline MTK, computes drift_bias /
residual_drift overall, by MTK bucket, by niche cell, winners-vs-all, and
vol% predictivity, then prints a GATE 1 decision table.

Run: PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_phase1.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.sp_drift import drift_stats as D
from src.sp_drift import panel as P

LIVE, WEBUI = "data/beidan_live.db", "data/webui.db"
CACHE = "data/derived/sp_drift/panel.parquet"
OUT = Path("docs/research/sp_drift_phase1.md")
FIGDIR = Path("docs/research/figures")


def _decision_legs(pan: pd.DataFrame, settle: pd.DataFrame, t: float) -> pd.DataFrame:
    """Legs at decision MTK=t joined with final_sp / outcome, ready for drift_stats."""
    dec = P.decision_view(pan, mtk_target=t).rename(
        columns={"sp": "decision_sp", "mtk": "decision_mtk", "vol_pct": "decision_vol_pct"})
    dec["sp_band"] = dec["decision_sp"].map(D.sp_band)
    legs = dec.merge(
        settle[["match_id", "selection", "final_sp", "is_winner", "winning_sp", "result_code"]],
        on=["match_id", "selection"], how="inner")
    return legs[(legs["decision_sp"] > 0) & (legs["final_sp"] > 0)]


def main() -> None:
    pan = P.build(LIVE, cache_path=CACHE)
    settle = P.attach_final_and_settlement(pan, LIVE)
    t_base = P.baseline_decision_mtk(WEBUI)
    legs = _decision_legs(pan, settle, t_base)

    overall = D.drift_metrics(legs)
    # MTK curve: EVERY pre-kickoff snapshot vs its match's closing final_sp,
    # bucketed by the snapshot's own MTK (not a single decision view, which
    # would collapse all legs into one bucket).
    full = pan.merge(
        settle[["match_id", "selection", "final_sp"]],
        on=["match_id", "selection"], how="inner",
    ).rename(columns={"sp": "decision_sp", "mtk": "decision_mtk"})
    by_mtk = D.drift_by_mtk_bucket(full, edges=[0, 30, 60, 120, 240, 480, 1440])
    cells = D.drift_by_cell(
        legs, by=["selection", "hcp_class", "sp_band", "league_bucket", "comp_type"], min_n=20)
    wva = D.winners_vs_all_bias(legs)
    volp = D.vol_imbalance_predictivity(legs)
    league_consist = D.slice_consistency(legs, "league_bucket", min_n=20)
    band_consist = D.slice_consistency(legs, "sp_band", min_n=20)

    # --- figure: residual drift vs MTK ---
    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(range(len(by_mtk)), by_mtk["residual_drift"], "o-")
    ax.set_xticks(range(len(by_mtk)))
    ax.set_xticklabels(by_mtk["mtk_bucket"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("residual_drift (|final/decision-1|)")
    ax.set_title("Residual SP drift vs minutes-to-kickoff")
    fig.tight_layout()
    fig.savefig(FIGDIR / "sp_drift_mtk_curve.png", dpi=110)

    # --- GATE 1 decision table ---
    big = abs(overall["drift_bias"]) > 0.05
    systematic = league_consist["consistent"] and band_consist["consistent"]
    predictable = abs(volp["spread"]) > 0.03

    lines = [
        "# SP 漂移 Phase 1 — 量化与 GATE 1\n",
        f"基线决策 MTK = {t_base:.0f} 分钟; 决策腿 n = {overall['n']:,}\n",
        "## 总体漂移",
        f"- drift_bias（有符号）= **{overall['drift_bias']*100:+.1f}%**",
        f"- residual_drift（幅度）= {overall['residual_drift']*100:.1f}%",
        f"- 不利 / 稳定 / 有利 = {overall['unfavorable_share']*100:.0f}% / "
        f"{overall['stable_share']*100:.0f}% / {overall['favorable_share']*100:.0f}%\n",
        "## Q1.4 选择偏差（仅中奖腿 vs 全腿）",
        f"- winners_bias = {wva['winners_bias']*100:+.1f}% (n={wva['winners_n']})",
        f"- all_bias = {wva['all_bias']*100:+.1f}% (n={wva['all_n']})",
        f"- gap = {wva['bias_gap']*100:+.1f}pp（gap 越负说明 −16.5% 越被中奖腿高估）\n",
        "## Q1.3 vol% 可预判性",
        f"- 高 vol% 腿 bias = {volp['high_vol_bias']*100:+.1f}% (n={volp['high_vol_n']})",
        f"- 低 vol% 腿 bias = {volp['low_vol_bias']*100:+.1f}% (n={volp['low_vol_n']})",
        f"- spread = {volp['spread']*100:+.1f}pp\n",
        "## Q1.2 多切片一致",
        f"- 按联赛: {league_consist}",
        f"- 按 SP 档: {band_consist}\n",
        "## 最差格子（drift_bias 升序前 10）\n",
        "```",
        cells.head(10).to_string(index=False) if len(cells) else "(无足够样本的格子)",
        "```",
        "\n## GATE 1 决策\n",
        f"- (a) 大？ |drift_bias|>5% → **{big}**",
        f"- (b) 系统？ 多切片一致 → **{systematic}**",
        f"- (c) 可预判？ vol% spread>3pp → **{predictable}**",
        "",
        "**判定**："
        + ("系统且可预判 → 进 Phase 2 建模。" if (big and systematic and predictable)
           else "大但方向随机/不可预判 → 跳过 Phase 2，直奔 Phase 3 的开窗+时机。" if big
           else "漂移不大 → 重新审视诊断口径（可能 −16.5% 是中奖腿偏差所致）。"),
        "\n![residual drift vs MTK](figures/sp_drift_mtk_curve.png)\n",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
