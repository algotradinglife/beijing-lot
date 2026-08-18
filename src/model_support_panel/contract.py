"""Outcome-blind, preregistered contract for Issue #216.

This module is deliberately limited to source selection, time semantics and
support thresholds.  It must be frozen before any result or settlement
namespace is opened for the Issue #216 work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final


CONTRACT_VERSION: Final = "bj216-causal-p34-model-support-v1"
UPSTREAM_CONTRACT_VERSION: Final = "bj214-decision-epoch-tensor-v1"
SOURCE_BOUNDARY_PREREGISTERED_AT_UTC: Final = "2026-08-07T11:59:52Z"
PROSPECTIVE_ACTIVATION_UTC: Final = "2026-08-07T09:35:01Z"
SOURCE_TIMEZONE: Final = "Asia/Hong_Kong"
REPRESENTATIVE_EPOCH_RULE: Final = "MEDIAN_KICKOFF_MINUS_10H"

OUTCOME_ORDER: Final = ("3", "1", "0")
CHRONOLOGICAL_ROLES: Final = (
    "development",
    "chronological_evaluation",
    "prospective_confirmation",
    "post_gate_extension",
)

ADMISSIBLE_SOURCE_COLUMNS: Final = {
    "beidan_live.matches": (
        "match_id",
        "issue",
        "match_idx",
        "kickoff_ts",
        "created_ts",
        "handicap_line",
    ),
    "beidan_live.snapshots": (
        "id",
        "match_id",
        "snapshot_ts",
        "sp_3",
        "sp_1",
        "sp_0",
        "eu_h",
        "eu_d",
        "eu_a",
        "source",
    ),
}

PROHIBITED_NAMESPACES: Final = (
    "beidan_live.settlements",
    "500_bjdc.matches.score",
    "500_bjdc.matches.result_label",
    "500_bjdc.matches.result_code",
    "500_bjdc.matches.winning_sp",
    "500_bjdc.multimarket_settlement_truth",
    "beidan_history.historical_matches",
    "beidan_features.matches",
    "beidan_xlsm.matches.score",
    "beidan_xlsm.matches.result_label",
    "beidan_xlsm.outcome_features",
)

EXCLUDED_SOURCE_CLASSES: Final = {
    "xlsm_named_snapshots": (
        "initial/10h/1h/final names have no row-level source-observed or fetch "
        "clock binding the market value to the decision epoch"
    ),
    "history_average_or_final_odds": (
        "terminal or average values have no admissible pre-decision observation clock"
    ),
    "feature_open_close_proxies": (
        "open/close values have no source observation timestamp"
    ),
    "500_live_p34_sp_only": (
        "timestamped Beijing SP lacks a same-row three-way EURO vector; cross-source "
        "clock joins are not admitted by this v1 contract"
    ),
    "sale_or_parlay_metadata": (
        "ticket-operability metadata is non-controlling for model-learning readiness"
    ),
}


@dataclass(frozen=True)
class CausalModelSupportGate:
    """Frozen support and chronology requirements inherited from #214."""

    gate_id: str = "BJ216_CAUSAL_P34_MODEL_SUPPORT_V1"
    representative_epoch_rule: str = REPRESENTATIVE_EPOCH_RULE
    minimum_complete_matches_per_issue_epoch: int = 7
    minimum_development_issues: int = 30
    minimum_chronological_evaluation_issues: int = 5
    minimum_prospective_confirmation_issues: int = 2
    minimum_n7_issue_pass_rate: float = 0.80
    minimum_core_match_coverage: float = 0.80
    require_identity_observed_by_epoch: bool = True
    require_snapshot_observed_by_epoch: bool = True
    require_match_not_started_at_epoch: bool = True
    require_same_row_complete_bj_sp_and_euro: bool = True
    require_zero_outcome_namespace_reads: bool = True

    @property
    def minimum_total_issues(self) -> int:
        return (
            self.minimum_development_issues
            + self.minimum_chronological_evaluation_issues
            + self.minimum_prospective_confirmation_issues
        )

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["minimum_total_issues"] = self.minimum_total_issues
        return value


SUPPORT_GATE: Final = CausalModelSupportGate()


def chronological_role(position: int) -> str:
    """Return the preregistered role for a zero-based eligible issue position."""

    if position < 0:
        raise ValueError("issue position must be non-negative")
    if position < SUPPORT_GATE.minimum_development_issues:
        return "development"
    position -= SUPPORT_GATE.minimum_development_issues
    if position < SUPPORT_GATE.minimum_chronological_evaluation_issues:
        return "chronological_evaluation"
    position -= SUPPORT_GATE.minimum_chronological_evaluation_issues
    if position < SUPPORT_GATE.minimum_prospective_confirmation_issues:
        return "prospective_confirmation"
    return "post_gate_extension"


__all__ = [
    "ADMISSIBLE_SOURCE_COLUMNS",
    "CHRONOLOGICAL_ROLES",
    "CONTRACT_VERSION",
    "EXCLUDED_SOURCE_CLASSES",
    "OUTCOME_ORDER",
    "PROHIBITED_NAMESPACES",
    "PROSPECTIVE_ACTIVATION_UTC",
    "REPRESENTATIVE_EPOCH_RULE",
    "SOURCE_BOUNDARY_PREREGISTERED_AT_UTC",
    "SOURCE_TIMEZONE",
    "SUPPORT_GATE",
    "UPSTREAM_CONTRACT_VERSION",
    "chronological_role",
]
