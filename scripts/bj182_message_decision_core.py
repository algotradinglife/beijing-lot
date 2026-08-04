#!/usr/bin/env python3
"""Outcome-unexposed decision primitives for #182's forward paper shadow."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


CONTRACT = "BJ-FWD-MESSAGE-CHAIN-N7-001"
SCHEMA_VERSION = "bj182-message-decision-v1"

ALLOWED_PROVENANCE_TIERS = (
    "TIER_0_OFFICIAL",
    "TIER_1_PRIMARY",
    "TIER_2_RELIABLE",
)
REQUIRED_KIND_MAX_AGE_SECONDS = {
    "injury": 7 * 24 * 3600,
    "suspension": 7 * 24 * 3600,
    "expected_lineup": 24 * 3600,
    "coach_change": 7 * 24 * 3600,
    "motivation": 72 * 3600,
}
OPTIONAL_FACT_KINDS = ("confirmed_lineup", "schedule", "travel")

AVAILABILITY_STATES = ("AVAILABLE", "DOUBTFUL", "UNAVAILABLE", "UNKNOWN")
ROLE_CLASSES = (
    "KEY_GOALKEEPER",
    "KEY_STARTER",
    "STARTER",
    "ROTATION",
    "TEAM_LEVEL",
    "UNKNOWN",
)
SEVERITY_BANDS = ("LOW", "MEDIUM", "HIGH", "UNKNOWN")
DIRECTIONS = (
    "HOME_NEGATIVE",
    "AWAY_NEGATIVE",
    "SYMMETRIC_UNCERTAINTY",
    "NO_DIRECTION",
)


class DecisionContractError(ValueError):
    """Raised when a prospective decision input violates the frozen contract."""


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _choice(value: object, allowed: Sequence[str], field: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise DecisionContractError(f"{field} must be one of {tuple(allowed)}")
    return normalized


def consumer_confidence_band(fact: Mapping[str, Any]) -> str:
    """Classify causal evidence without treating provenance tier as truth."""

    if not bool(fact.get("active")):
        return "NOT_ACTIONABLE"
    if fact.get("assertion_state") != "affirmed":
        return "NOT_ACTIONABLE"
    if fact.get("conflicts_with"):
        return "NOT_ACTIONABLE"
    tier = str(fact.get("provenance_tier", ""))
    confidence = fact.get("confidence")
    if tier not in ALLOWED_PROVENANCE_TIERS or confidence is None:
        return "LOW"
    score = float(confidence)
    if tier in {"TIER_0_OFFICIAL", "TIER_1_PRIMARY"} and score >= 0.75:
        return "HIGH"
    if (
        tier == "TIER_2_RELIABLE" and score >= 0.75
    ) or (
        tier in {"TIER_0_OFFICIAL", "TIER_1_PRIMARY"} and score >= 0.50
    ):
        return "MEDIUM"
    return "LOW"


def normalize_fact(
    fact: Mapping[str, Any], *, home_team_id: str, away_team_id: str
) -> dict[str, object]:
    """Validate the strategy-owned structured extraction from one ledger fact."""

    value = fact.get("value")
    if not isinstance(value, Mapping):
        raise DecisionContractError("fact.value must be an object")
    entity_id = str(fact.get("entity_id") or "")
    if entity_id == home_team_id:
        entity_side = "HOME"
    elif entity_id == away_team_id:
        entity_side = "AWAY"
    elif entity_id:
        entity_side = "RELATED_ENTITY"
    else:
        entity_side = "MATCH"
    direction = _choice(value.get("direction", "NO_DIRECTION"), DIRECTIONS, "direction")
    if entity_side == "HOME" and direction == "AWAY_NEGATIVE":
        raise DecisionContractError("home entity cannot declare AWAY_NEGATIVE")
    if entity_side == "AWAY" and direction == "HOME_NEGATIVE":
        raise DecisionContractError("away entity cannot declare HOME_NEGATIVE")
    return {
        "fact_id": str(fact["fact_id"]),
        "fact_kind": str(fact["fact_kind"]),
        "entity_id": entity_id,
        "entity_side": entity_side,
        "availability": _choice(
            value.get("availability", "UNKNOWN"),
            AVAILABILITY_STATES,
            "availability",
        ),
        "role_class": _choice(
            value.get("role_class", "UNKNOWN"), ROLE_CLASSES, "role_class"
        ),
        "severity": _choice(
            value.get("severity", "UNKNOWN"), SEVERITY_BANDS, "severity"
        ),
        "direction": direction,
        "consumer_confidence_band": consumer_confidence_band(fact),
        "producer_confidence": fact.get("confidence"),
        "provenance_tier": str(fact.get("provenance_tier", "")),
        "raw_sha256": str(fact.get("raw_sha256", "")),
        "effective_cutoff_utc": str(fact.get("effective_cutoff_utc", "")),
    }


def coverage_failure_codes(coverage: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not bool(coverage.get("cutoff_strictly_before_kickoff")):
        reasons.append("CUTOFF_NOT_BEFORE_KICKOFF")
    if coverage.get("missing_fact_kinds"):
        reasons.append("MISSING_REQUIRED_FACT")
    if coverage.get("incomplete_observation_fact_kinds"):
        reasons.append("INCOMPLETE_COLLECTION")
    if coverage.get("stale_observation_fact_kinds") or coverage.get("stale_fact_kinds"):
        reasons.append("STALE_EVIDENCE")
    if coverage.get("uncovered_entity_ids_by_kind"):
        reasons.append("INCOMPLETE_ENTITY_COVERAGE")
    if coverage.get("explicit_missing_fact_kinds"):
        reasons.append("EXPLICIT_MISSINGNESS")
    if coverage.get("unresolved_conflict_fact_ids"):
        reasons.append("UNRESOLVED_CONTRADICTION")
    if not bool(coverage.get("decision_chain_eligible")) and not reasons:
        reasons.append("COVERAGE_INELIGIBLE_OTHER")
    return sorted(set(reasons))


def assess_match(
    *,
    match_id: str,
    home_team_id: str,
    away_team_id: str,
    coverage_by_kind: Mapping[str, Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    """Convert cutoff-safe coverage/facts into a symmetric match-risk flag."""

    errors: list[str] = []
    for kind in REQUIRED_KIND_MAX_AGE_SECONDS:
        coverage = coverage_by_kind.get(kind)
        if coverage is None:
            errors.append("COVERAGE_REPORT_MISSING")
        else:
            errors.extend(coverage_failure_codes(coverage))
    active = [
        fact
        for fact in facts
        if fact.get("active")
        and fact.get("fact_kind")
        in {*REQUIRED_KIND_MAX_AGE_SECONDS, *OPTIONAL_FACT_KINDS}
    ]
    if any(fact.get("conflicts_with") for fact in active):
        errors.append("UNRESOLVED_CONTRADICTION")
    normalized: list[dict[str, object]] = []
    try:
        normalized = [
            normalize_fact(
                fact, home_team_id=home_team_id, away_team_id=away_team_id
            )
            for fact in active
        ]
    except (DecisionContractError, KeyError, TypeError, ValueError):
        errors.append("FACT_EXTRACTION_SCHEMA_INVALID")
    errors = sorted(set(errors))
    if errors:
        return {
            "match_id": match_id,
            "decision_status": "ABSTAIN",
            "risk_flag": "NOT_EVALUATED",
            "protection_action": "NO_MESSAGE_DECISION",
            "handicap_translation": "NO_CHANGE",
            "error_codes": errors,
            "fact_ids": sorted(str(fact.get("fact_id", "")) for fact in active),
            "extractions": normalized,
        }

    high_critical = [
        row
        for row in normalized
        if row["consumer_confidence_band"] == "HIGH"
        and (
            row["severity"] == "HIGH"
            or (
                row["availability"] == "UNAVAILABLE"
                and row["role_class"] in {"KEY_GOALKEEPER", "KEY_STARTER"}
            )
        )
    ]
    meaningful_absences = [
        row
        for row in normalized
        if row["consumer_confidence_band"] in {"HIGH", "MEDIUM"}
        and row["availability"] == "UNAVAILABLE"
        and row["role_class"] in {"KEY_GOALKEEPER", "KEY_STARTER", "STARTER"}
    ]
    medium_signal = [
        row
        for row in normalized
        if row["consumer_confidence_band"] in {"HIGH", "MEDIUM"}
        and (
            row["availability"] in {"DOUBTFUL", "UNAVAILABLE"}
            or row["severity"] in {"MEDIUM", "HIGH"}
        )
    ]
    if high_critical or len(meaningful_absences) >= 2:
        flag = "HIGH"
        action = "REJECT_IDENTITY"
    elif medium_signal:
        flag = "MEDIUM"
        action = "ANNOTATE_ONLY"
    else:
        flag = "CLEAR"
        action = "KEEP_BASELINE_ORDER"
    directions = sorted(
        {
            str(row["direction"])
            for row in normalized
            if row["direction"] != "NO_DIRECTION"
        }
    )
    translation = directions[0] if len(directions) == 1 else (
        "SYMMETRIC_UNCERTAINTY" if directions else "NO_CHANGE"
    )
    return {
        "match_id": match_id,
        "decision_status": "ELIGIBLE",
        "risk_flag": flag,
        "protection_action": action,
        # Diagnostic only: no probability/handicap/ticket mutation is allowed.
        "handicap_translation": translation,
        "error_codes": [],
        "fact_ids": sorted(str(fact["fact_id"]) for fact in active),
        "extractions": normalized,
    }


def select_message_identity(
    baseline_candidates: Sequence[Mapping[str, Any]],
    assessments: Mapping[str, Mapping[str, Any]],
) -> dict[str, object]:
    """Filter the frozen B0 order; never rescore or synthesize candidates."""

    if not baseline_candidates:
        return {
            "policy_status": "ABSTAIN_BASELINE_UNAVAILABLE",
            "selected_portfolio_id": "",
            "selected_identity_fingerprint": "",
            "selected_match_ids": [],
            "source_rank": None,
        }
    for rank, candidate in enumerate(baseline_candidates, start=1):
        match_ids = list(candidate["selected_match_ids"])
        if len(match_ids) != 7 or len(set(match_ids)) != 7:
            raise DecisionContractError("every candidate must contain seven unique matches")
        rows = [assessments.get(str(match_id)) for match_id in match_ids]
        if any(row is None or row.get("decision_status") != "ELIGIBLE" for row in rows):
            continue
        if any(row.get("protection_action") == "REJECT_IDENTITY" for row in rows):
            continue
        return {
            "policy_status": "SELECTED_PREOUTCOME",
            "selected_portfolio_id": str(candidate["portfolio_id"]),
            "selected_identity_fingerprint": str(candidate["identity_fingerprint"]),
            "selected_match_ids": match_ids,
            "source_rank": rank,
        }
    return {
        "policy_status": "ABSTAIN_NO_ELIGIBLE_IDENTITY",
        "selected_portfolio_id": "",
        "selected_identity_fingerprint": "",
        "selected_match_ids": [],
        "source_rank": None,
    }
