"""Issue #208: frozen incumbent N7/K8/native-¥2 capital path.

REWORK v3 (PI payout-economics 2026-08-15): the incumbent path is
RECONSTRUCTED from the frozen #207 CONTROLLING ticket identities under the
corrected pre-tax formula for ALL development splits.  Upstream #206
`realized_gross` already includes the Beijing payout coefficient exactly once
(realized_gross = 0.65 * prod(official_sp)), so per-ticket native-¥2 payout =
realized_gross * ¥2.  The superseded #207 ledger `gross_payout_yuan` (which
derives "pre-tax" by dividing the correct 0.65-adjusted value by 0.65) is NOT
an admissible baseline and is never read here.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .contract import (
    INCUMBENT_K,
    INCUMBENT_LANE,
    INITIAL_BANKROLL_YUAN,
    TICKET_STAKE_YUAN,
)


class IncumbentError(RuntimeError):
    """Raised when the frozen incumbent path cannot be reconstructed."""


def build_incumbent_paths(
    upstream_ledger: pd.DataFrame,
    upstream_tickets: pd.DataFrame,
) -> pd.DataFrame:
    """Per-issue frozen incumbent N7/K8/native-¥2 capital rows (all dev splits).

    REWORK v3: the #207 ledger is intentionally NOT used as the payout source —
    its `gross_payout_yuan` was computed under the superseded interpretation
    (pre-tax = realized_gross / 0.65), which inflates every winning payout.
    Instead every split is reconstructed from the frozen CONTROLLING ticket
    identities with the corrected economics: payout = realized_gross * ¥2,
    funded = K * ¥2, post = pre - funded + payout.
    """
    rows: list[dict[str, Any]] = []
    tickets = upstream_tickets[
        (upstream_tickets["panel_role"] == "CONTROLLING")
        & (upstream_tickets["policy"] == INCUMBENT_LANE)
        & (upstream_tickets["k"] == INCUMBENT_K)
    ].copy()
    if tickets.empty:
        raise IncumbentError("incumbent CONTROLLING tickets missing")
    for split, split_tickets in tickets.groupby("split", sort=True):
        if split not in ("CV_2021", "CV_2022", "CV_2023"):
            continue
        bankroll = INITIAL_BANKROLL_YUAN
        for issue, group in split_tickets.groupby("issue", sort=True):
            funded = float(len(group) * TICKET_STAKE_YUAN)
            # Corrected economics: realized_gross already = 0.65*prod(SP);
            # native ¥2 per ticket. Never divide the coefficient out.
            payout = float(
                group["realized_gross"].fillna(0.0).sum() * TICKET_STAKE_YUAN
            )
            post = bankroll - funded + payout
            rows.append(
                {
                    "split": str(split),
                    "issue": str(issue),
                    "year": int(group["year"].iloc[0]),
                    "pre_issue_bankroll_yuan": bankroll,
                    "funded_stake_yuan": funded,
                    "gross_payout_yuan": payout,
                    "post_issue_bankroll_yuan": post,
                    "source": "RECONSTRUCTED_CORRECTED_ECONOMICS",
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
    """Strictly prior bankroll/path state from the incumbent path.

    REWORK v4 (EV D1, 2026-08-15): the running peak anchors at the
    time-zero ¥100,000 initial bankroll (method.yaml `max_drawdown_pct`
    definition includes the anchor).  The old peak = cummax(prior posts)
    understated drawdown whenever the first prior post fell below the
    initial capital.  Loss streaks use the economic definition (net
    P&L < 0, i.e. payout < funded) rather than gross payout == 0, which
    misclassified positive-but-insufficient payouts.
    """
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
    posts = sub["post_issue_bankroll_yuan"].to_numpy(dtype=float)
    # Match live inference exactly: a lag-N value is available only after N
    # completed issues; otherwise the causal anchor is time-zero capital.
    trail5 = (
        float(posts[-5]) if len(posts) >= 5 else INITIAL_BANKROLL_YUAN
    )
    trail10 = (
        float(posts[-10]) if len(posts) >= 10 else INITIAL_BANKROLL_YUAN
    )
    peak = float(
        max(INITIAL_BANKROLL_YUAN, sub["post_issue_bankroll_yuan"].cummax().iloc[-1])
    )
    drawdown = (peak - bankroll) / peak if peak else 0.0
    # Economic loss definition: net P&L < 0 (payout < funded).  A positive
    # gross payout that is smaller than the funded stake is still a loss
    # (method.yaml `max_consecutive_losing_issues`).
    losses = 0
    for _, row in reversed(list(sub.iterrows())):
        net = float(row["gross_payout_yuan"]) - float(row["funded_stake_yuan"])
        if net < 0:
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
