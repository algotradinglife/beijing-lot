"""Phase 4 counterfactual replay.

Invariant: qualify/size on the decision-time SP (optionally drift-haircut
adjusted), but settle on the real final SP (settlement winning_sp). This is
what makes "deciding too early → shrunken payout" show up as realized loss.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

import pandas as pd

from src.phase5a.data_loader import LiveSnapshot
from src.sp_drift import panel as P


def decision_snapshots(panel: pd.DataFrame, mtk_target: float) -> List[LiveSnapshot]:
    """Reconstruct one LiveSnapshot per match using the SP observed at decision
    MTK=mtk_target (the latest snapshot at least that long before kickoff)."""
    dec = P.decision_view(panel, mtk_target=mtk_target)
    out: List[LiveSnapshot] = []
    for mid, grp in dec.groupby("match_id"):
        by_sel = {str(r["selection"]): r for _, r in grp.iterrows()}
        any_row = grp.iloc[0]
        out.append(LiveSnapshot(
            match_id=str(mid),
            issue=str(any_row["issue"]),
            match_idx=int(any_row["match_idx"]),
            league=any_row["league"],
            kickoff_ts=str(any_row["kickoff_ts"]),
            home=None, away=None,
            handicap_line=(None if pd.isna(any_row["handicap_line"])
                           else float(any_row["handicap_line"])),
            sp_3=(float(by_sel["3"]["sp"]) if "3" in by_sel else None),
            sp_1=(float(by_sel["1"]["sp"]) if "1" in by_sel else None),
            sp_0=(float(by_sel["0"]["sp"]) if "0" in by_sel else None),
            snapshot_ts=None,
        ))
    return out
