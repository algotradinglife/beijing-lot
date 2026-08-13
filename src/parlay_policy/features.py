"""Issue #208: pre-event issue state x.

State is built only from causal pre-event M×3 tensor summaries, issue-level
market/SP distribution summaries, frozen upstream outputs and strictly prior
bankroll/path state. Outcome fields are excluded by the forbidden-name checker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .census import IssuePanel, issue_summary
from .contract import FORBIDDEN_INFERENCE_PARTS


class StateError(RuntimeError):
    """Raised when a state vector crosses the outcome boundary."""


STATE_FEATURE_NAMES: tuple[str, ...] = (
    # M×3 tensor / issue market-SP summaries
    "M",
    "mean_max_control_prob",
    "max_max_control_prob",
    "std_max_control_prob",
    "mean_probability_hhi",
    "mean_predicted_sp",
    "max_predicted_sp",
    "mean_sp_seed_std",
    "outcome_hhi",
    # frozen upstream #207 CONTROLLING K8 summaries (pre-event only)
    "up_mean_log_joint_probability",
    "up_mean_expected_pre_tax_net",
    "up_mean_predicted_sp_product",
    "up_mean_selected_probability",
    "up_mean_selected_sp",
    "up_ticket_hhi",
    "up_mean_pairwise_overlap",
    # strictly prior bankroll/path state (incumbent path, pre-issue)
    "prior_bankroll_yuan",
    "prior_trail5_bankroll_yuan",
    "prior_trail10_bankroll_yuan",
    "prior_running_drawdown_pct",
    "prior_consecutive_losses",
)


def upstream_issue_summary(
    upstream_tickets: pd.DataFrame, issue: str
) -> dict[str, float]:
    """Pre-event summaries of the frozen #207 CONTROLLING K8 bundle for an issue.

    Uses only pre-event fields (log_joint_probability, expected_pre_tax_net,
    predicted_sp_product, mean_selected_probability, mean_selected_sp,
    ticket identity HHI and pairwise overlap). No realized/outcome fields.
    """
    sub = upstream_tickets[
        (upstream_tickets["issue"] == issue)
        & (upstream_tickets["panel_role"] == "CONTROLLING")
        & (upstream_tickets["k"] == 8)
    ]
    if sub.empty:
        return {
            "up_mean_log_joint_probability": np.nan,
            "up_mean_expected_pre_tax_net": np.nan,
            "up_mean_predicted_sp_product": np.nan,
            "up_mean_selected_probability": np.nan,
            "up_mean_selected_sp": np.nan,
            "up_ticket_hhi": np.nan,
            "up_mean_pairwise_overlap": np.nan,
        }
    match_sets = [
        set(map(int, str(value).split("|")))
        for value in sub["match_indices"]
    ]
    overlaps = []
    for i in range(len(match_sets)):
        for j in range(i + 1, len(match_sets)):
            inter = len(match_sets[i] & match_sets[j])
            union = len(match_sets[i] | match_sets[j])
            overlaps.append(inter / union if union else 0.0)
    identity_counts = sub["ticket_identity"].value_counts(normalize=True)
    return {
        "up_mean_log_joint_probability": float(
            sub["log_joint_probability"].mean()
        ),
        "up_mean_expected_pre_tax_net": float(
            sub["expected_pre_tax_net"].mean()
        ),
        "up_mean_predicted_sp_product": float(sub["predicted_sp_product"].mean()),
        "up_mean_selected_probability": float(
            sub["mean_selected_probability"].mean()
        ),
        "up_mean_selected_sp": float(sub["mean_selected_sp"].mean()),
        "up_ticket_hhi": float(np.sum(identity_counts**2)),
        "up_mean_pairwise_overlap": float(np.mean(overlaps)) if overlaps else 0.0,
    }


@dataclass(frozen=True)
class PriorBankrollState:
    prior_bankroll_yuan: float
    prior_trail5_bankroll_yuan: float
    prior_trail10_bankroll_yuan: float
    prior_running_drawdown_pct: float
    prior_consecutive_losses: int


def prior_bankroll_state(
    ledger: pd.DataFrame,
    split: str,
    issue: str,
    *,
    policy: str = "MARKET_WOR",
    controller: str = "NATIVE_2_YUAN",
    k: int = 8,
) -> PriorBankrollState:
    """Strictly prior bankroll/path state from the frozen incumbent path.

    Rows are strictly before the decision issue (issue_order < current), so
    the current issue's outcome is never observed.
    """
    sub = ledger[
        (ledger["split"] == split)
        & (ledger["policy"] == policy)
        & (ledger["controller"] == controller)
        & (ledger["k"] == k)
    ].copy()
    sub = sub.sort_values("issue")
    issues = sub["issue"].tolist()
    if issue not in issues:
        # Cold start before any prior issue in this split.
        return PriorBankrollState(
            prior_bankroll_yuan=100_000.0,
            prior_trail5_bankroll_yuan=100_000.0,
            prior_trail10_bankroll_yuan=100_000.0,
            prior_running_drawdown_pct=0.0,
            prior_consecutive_losses=0,
        )
    idx = issues.index(issue)
    prior = sub.iloc[:idx]
    if prior.empty:
        return PriorBankrollState(
            prior_bankroll_yuan=100_000.0,
            prior_trail5_bankroll_yuan=100_000.0,
            prior_trail10_bankroll_yuan=100_000.0,
            prior_running_drawdown_pct=0.0,
            prior_consecutive_losses=0,
        )
    bankroll = float(prior.iloc[-1]["post_issue_bankroll_yuan"])
    trail5 = float(prior.tail(5).iloc[-1]["post_issue_bankroll_yuan"])
    trail10 = float(prior.tail(10).iloc[-1]["post_issue_bankroll_yuan"])
    running_peak = float(prior["post_issue_bankroll_yuan"].cummax().iloc[-1])
    drawdown_pct = (running_peak - bankroll) / running_peak if running_peak else 0.0
    losses = 0
    for value in reversed(prior["net_pnl_yuan"].tolist()):
        if value < 0:
            losses += 1
        else:
            break
    return PriorBankrollState(
        prior_bankroll_yuan=bankroll,
        prior_trail5_bankroll_yuan=trail5,
        prior_trail10_bankroll_yuan=trail10,
        prior_running_drawdown_pct=float(drawdown_pct),
        prior_consecutive_losses=int(losses),
    )


def build_state_vector(
    panel: IssuePanel,
    upstream_summary: dict[str, float],
    prior: PriorBankrollState,
) -> np.ndarray:
    """Assemble the pre-event state vector x (order = STATE_FEATURE_NAMES)."""
    base = issue_summary(panel)
    values: list[float] = []
    for name in STATE_FEATURE_NAMES:
        if name in base:
            values.append(float(base[name]))
        elif name in upstream_summary:
            values.append(float(upstream_summary[name]))
        elif hasattr(prior, name):
            values.append(float(getattr(prior, name)))
        else:
            raise StateError(f"unknown state feature {name}")
    return np.asarray(values, dtype=float)


def forbidden_field_check(names: Iterable[str]) -> list[str]:
    failures: list[str] = []
    for name in names:
        lowered = str(name).lower()
        if any(part in lowered for part in FORBIDDEN_INFERENCE_PARTS):
            failures.append(str(name))
    return sorted(failures)


__all__ = [
    "STATE_FEATURE_NAMES", "StateError", "PriorBankrollState",
    "build_state_vector", "forbidden_field_check", "prior_bankroll_state",
    "upstream_issue_summary",
]
