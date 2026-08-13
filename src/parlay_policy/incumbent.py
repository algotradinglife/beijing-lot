"""Issue #208: frozen incumbent N7/K8/native-¥2 capital path.

For CV_2022/CV_2023 the #207 ledger is authoritative. For CV_2021 (the #207
fit fold, which had no Stage-4 capital replay) the incumbent path is
reconstructed from the frozen CONTROLLING ticket identities with the identical
native ¥2 rule. The result is one consistent frozen incumbent path per issue
for matched-lift accounting and prior bankroll state.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .contract import (
    INCUMBENT_CAPITAL,
    INCUMBENT_K,
    INCUMBENT_LANE,
    INCUMBENT_N,
    INITIAL_BANKROLL_YUAN,
    TICKET_STAKE_YUAN,
)


class IncumbentError(RuntimeError):
    """Raised when the frozen incumbent path cannot be reconstructed."""


def build_incumbent_paths(
    upstream_ledger: pd.DataFrame,
    upstream_tickets: pd.DataFrame,
) -> pd.DataFrame:
    """Per-issue frozen incumbent N7/K8/native-¥2 capital rows (all dev splits)."""
    rows: list[dict[str, Any]] = []
    # Authoritative ledger rows first (CV_2022/CV_2023).
    for _, row in upstream_ledger.iterrows():
        if (
            row["policy"] != INCUMBENT_LANE
            or row["k"] != INCUMBENT_K
            or row["controller"] != INCUMBENT_CAPITAL
        ):
            continue
        rows.append(
            {
                "split": str(row["split"]),
                "issue": str(row["issue"]),
                "year": int(row["year"]),
                "pre_issue_bankroll_yuan": float(row["pre_issue_bankroll_yuan"]),
                "funded_stake_yuan": float(row["funded_stake_yuan"]),
                "gross_payout_yuan": float(row["gross_payout_yuan"]),
                "post_issue_bankroll_yuan": float(row["post_issue_bankroll_yuan"]),
                "source": "207_LEDGER",
            }
        )
    # CV_2021 reconstruction from frozen CONTROLLING identities.
    tickets = upstream_tickets[
        (upstream_tickets["split"] == "CV_2021")
        & (upstream_tickets["panel_role"] == "CONTROLLING")
        & (upstream_tickets["policy"] == INCUMBENT_LANE)
        & (upstream_tickets["k"] == INCUMBENT_K)
    ].copy()
    if tickets.empty:
        raise IncumbentError("CV_2021 incumbent CONTROLLING tickets missing")
    bankroll = INITIAL_BANKROLL_YUAN
    for issue, group in tickets.groupby("issue", sort=True):
        funded = float(len(group) * TICKET_STAKE_YUAN)
        payout = float(
            group["pre_tax_gross_multiple"].fillna(0.0).sum() * TICKET_STAKE_YUAN
        )
        post = bankroll - funded + payout
        rows.append(
            {
                "split": "CV_2021",
                "issue": str(issue),
                "year": int(group["year"].iloc[0]),
                "pre_issue_bankroll_yuan": bankroll,
                "funded_stake_yuan": funded,
                "gross_payout_yuan": payout,
                "post_issue_bankroll_yuan": post,
                "source": "CV2021_RECONSTRUCTED_FROM_FROZEN_IDENTITIES",
            }
        )
        bankroll = post
    frame = pd.DataFrame(rows)
    frame = frame.drop_duplicates(subset=["split", "issue"], keep="first")
    return frame.sort_values(["split", "issue"]).reset_index(drop=True)


def incumbent_row(
    incumbent_paths: pd.DataFrame, split: str, issue: str
) -> dict[str, float]:
    sub = incumbent_paths[
        (incumbent_paths["split"] == split) & (incumbent_paths["issue"] == issue)
    ]
    if sub.empty:
        raise IncumbentError(f"incumbent path row missing: {split}/{issue}")
    row = sub.iloc[0]
    return {
        "pre": float(row["pre_issue_bankroll_yuan"]),
        "post": float(row["post_issue_bankroll_yuan"]),
        "payout": float(row["gross_payout_yuan"]),
        "funded": float(row["funded_stake_yuan"]),
    }


def incumbent_prior_state(
    incumbent_paths: pd.DataFrame, split: str, issue: str
) -> dict[str, float]:
    """Strictly prior bankroll/path state from the incumbent path."""
    sub = incumbent_paths[
        (incumbent_paths["split"] == split)
        & (incumbent_paths["issue"] < issue)
    ].copy()
    sub = sub.sort_values("issue")
    if sub.empty:
        return {
            "prior_bankroll_yuan": INITIAL_BANKROLL_YUAN,
            "prior_trail5_bankroll_yuan": INITIAL_BANKROLL_YUAN,
            "prior_trail10_bankroll_yuan": INITIAL_BANKROLL_YUAN,
            "prior_running_drawdown_pct": 0.0,
            "prior_consecutive_losses": 0,
        }
    bankroll = float(sub.iloc[-1]["post_issue_bankroll_yuan"])
    trail5 = float(sub.tail(5).iloc[0]["post_issue_bankroll_yuan"])
    trail10 = float(sub.tail(10).iloc[0]["post_issue_bankroll_yuan"])
    peak = float(sub["post_issue_bankroll_yuan"].cummax().iloc[-1])
    drawdown = (peak - bankroll) / peak if peak else 0.0
    losses = 0
    for value in reversed(sub["gross_payout_yuan"].tolist()):
        if value == 0:
            losses += 1
        else:
            break
    return {
        "prior_bankroll_yuan": bankroll,
        "prior_trail5_bankroll_yuan": trail5,
        "prior_trail10_bankroll_yuan": trail10,
        "prior_running_drawdown_pct": float(drawdown),
        "prior_consecutive_losses": int(losses),
    }


__all__ = [
    "build_incumbent_paths", "incumbent_prior_state", "incumbent_row",
]
