"""Versioned contract for the #214 decision-epoch data interface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Final

from unified_tensor.contract import FEATURE_NAMES, FEATURE_SPECS, OUTCOME_ORDER


CONTRACT_VERSION: Final = "bj214-decision-epoch-tensor-v1"
UPSTREAM_CONTRACT_VERSION: Final = "bj203-causal-tensor-v2"
ACTIVATION_UTC: Final = "2026-08-07T09:35:01Z"
SOURCE_TIMEZONE: Final = "Asia/Hong_Kong"

EPOCH_RULES: Final = (
    "ISSUE_START",
    "FIRST_KICKOFF_MINUS_10H",
    "MEDIAN_KICKOFF_MINUS_10H",
    "LAST_KICKOFF_MINUS_10H",
    "FIRST_KICKOFF_MINUS_1H",
    "MEDIAN_KICKOFF_MINUS_1H",
    "LAST_KICKOFF_MINUS_1H",
    "PUBLISHED_SEGMENT_FREEZE",
    "PROSPECTIVE_ACTIVATION",
)

COHORTS: Final = (
    "development",
    "historical_model_unseen",
    "post_203_operational_observational",
    "prospective_post_activation",
)

CORE_FEATURES: Final = (
    "devig_euro_probability",
    "euro_1h_odds",
    "bj_sp_snapshot",
)

REPRESENTATIVE_EPOCH_RULE: Final = "MEDIAN_KICKOFF_MINUS_10H"
REPRESENTATIVE_RULE_RATIONALE: Final = (
    "Schedule-only median-kickoff anchor with a ten-hour operational planning "
    "lead; common to every cohort and frozen without using outcomes or observed "
    "coverage. All other epoch rules are sensitivity evidence only."
)

FORBIDDEN_INFERENCE_PARTS: Final = (
    "result",
    "score",
    "settlement",
    "winning_sp",
    "official_sp",
    "final_observed_sp",
    "payout",
    "tax",
    "roi",
    "profit",
    "hit",
)


@dataclass(frozen=True)
class ModelLearningSupportGate:
    """Predeclared causal feature-support gate for #204 model learning."""

    gate_id: str = "BJ214_MODEL_LEARNING_N7_SUPPORT_V2"
    representative_epoch_rule: str = REPRESENTATIVE_EPOCH_RULE
    minimum_complete_matches_per_epoch: int = 7
    minimum_evaluated_issues_development: int = 30
    minimum_evaluated_issues_historical_model_unseen: int = 5
    minimum_evaluated_issues_prospective_post_activation: int = 2
    minimum_epoch_pass_rate: float = 0.80
    minimum_core_cell_coverage: float = 0.80
    require_timestamped_identity: bool = True
    require_no_post_epoch_observations: bool = True
    require_no_started_matches: bool = True
    require_all_three_bj_sp_and_euro: bool = True

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TicketOperabilityGate:
    """Separate ticket-operability gate; it is not model feature support."""

    gate_id: str = "BJ214_TICKET_OPERABILITY_N7_V1"
    representative_epoch_rule: str = REPRESENTATIVE_EPOCH_RULE
    minimum_complete_matches_per_epoch: int = 7
    minimum_evaluated_issues_development: int = 30
    minimum_evaluated_issues_historical_model_unseen: int = 5
    minimum_evaluated_issues_prospective_post_activation: int = 2
    minimum_epoch_pass_rate: float = 0.80
    minimum_ticket_eligible_coverage: float = 0.80
    require_open_sale_evidence: bool = True
    require_parlay_allowed_evidence: bool = True
    require_timestamped_identity: bool = True
    require_no_post_epoch_observations: bool = True
    require_no_started_matches: bool = True
    require_all_three_bj_sp_and_euro: bool = True

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


MODEL_SUPPORT_GATE: Final = ModelLearningSupportGate()
TICKET_OPERABILITY_GATE: Final = TicketOperabilityGate()


def epoch_id(issue: str, rule: str, decision_epoch_utc: str, ordinal: int) -> str:
    payload = (
        f"{CONTRACT_VERSION}|{issue}|{rule}|{decision_epoch_utc}|{ordinal}"
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def epoch_cell_key(
    epoch_identity: str,
    match_id: str,
    outcome_code: str,
) -> str:
    if outcome_code not in OUTCOME_ORDER:
        raise ValueError(f"unsupported outcome code: {outcome_code}")
    payload = (
        f"{CONTRACT_VERSION}|{epoch_identity}|{match_id}|{outcome_code}"
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def forbidden_inference_names(values: object) -> list[str]:
    failures: list[str] = []
    for value in values:  # type: ignore[union-attr]
        name = str(value).lower()
        if name == "predicted_final_sp":
            continue
        if any(part in name for part in FORBIDDEN_INFERENCE_PARTS):
            failures.append(str(value))
    return sorted(failures)


FEATURE_DICTIONARY: Final = tuple(asdict(spec) for spec in FEATURE_SPECS)

__all__ = [
    "ACTIVATION_UTC",
    "COHORTS",
    "CONTRACT_VERSION",
    "CORE_FEATURES",
    "EPOCH_RULES",
    "FEATURE_DICTIONARY",
    "FEATURE_NAMES",
    "OUTCOME_ORDER",
    "MODEL_SUPPORT_GATE",
    "REPRESENTATIVE_EPOCH_RULE",
    "REPRESENTATIVE_RULE_RATIONALE",
    "SOURCE_TIMEZONE",
    "UPSTREAM_CONTRACT_VERSION",
    "TICKET_OPERABILITY_GATE",
    "epoch_cell_key",
    "epoch_id",
    "forbidden_inference_names",
]
