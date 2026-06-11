"""Phase 0 substrate health report → docs/research/sp_drift_phase0.md.

Run: PYTHONPATH=".:src" .venv/bin/python scripts/run_sp_drift_phase0.py
"""
from pathlib import Path

import numpy as np

from src.sp_drift import panel as P

LIVE = "data/beidan_live.db"
WEBUI = "data/webui.db"
CACHE = "data/derived/sp_drift/panel.parquet"
OUT = Path("docs/research/sp_drift_phase0.md")


def main() -> None:
    pan = P.build(LIVE, cache_path=CACHE, rebuild=True)
    dec = P.attach_final_and_settlement(pan, LIVE)
    t_base = P.baseline_decision_mtk(WEBUI)

    n_matches = pan["match_id"].nunique()
    snaps_per = pan.groupby(["match_id", "selection"]).size()
    win = dec[dec["is_winner"] & dec["winning_sp"].notna() & (dec["winning_sp"] > 0)]
    rel = (win["final_sp"] - win["winning_sp"]).abs() / win["winning_sp"]
    anchor_ok = float((rel < 0.05).mean()) * 100

    lines = [
        "# SP 漂移 Phase 0 — 面板体检\n",
        f"- 面板行数（pre-kickoff）: {len(pan):,}",
        f"- match 数: {n_matches:,}",
        f"- pre-kickoff 快照/腿: 中位 {int(snaps_per.median())}, 均值 {snaps_per.mean():.1f}, 最大 {snaps_per.max()}",
        f"- 基线决策 MTK（plan 实际生成时刻中位）: {t_base:.0f} 分钟 (~{t_base/60:.1f}h before kickoff)",
        f"- 锚点：中奖腿 final_sp 与 winning_sp 相对差 <5% 占比: **{anchor_ok:.1f}%**",
        f"- MTK 分布: P10={np.percentile(pan['mtk'],10):.0f} 中位={pan['mtk'].median():.0f} P90={np.percentile(pan['mtk'],90):.0f} 分钟",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
