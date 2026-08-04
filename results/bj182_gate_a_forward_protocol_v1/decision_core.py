#!/usr/bin/env python3
"""Outcome-unexposed decision primitives for #182's forward paper shadow."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
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
FROZEN_SOURCE_HASHES = {
    "source_181_ledger_sha256": "3c065be028c4022d33487095f08b9838c284853614f6617646dabe5e08c31229",
    "source_181_asof_schema_sha256": "e763428d703197ec08eb2c4955ee45bc9925c84941bed8f3a9ac253edec161bd",
    "source_181_coverage_schema_sha256": "22ffbaf6ef79eb484425c48307a29c08ba73d6a0bbf743e4023b37838ed9181d",
    "source_180_gate_b_manifest_sha256": "9f48b29325d817ce873bd1430be459c9e70ad052064f8e03e02ccbc1d8bc6fcf",
    "source_180_gate_b_content_identity_sha256": "d9b41dec45c1c6215755d9dad8774e00fc0f19f564ee6ef8bf2387cb8d309108",
}
TRACE_SOURCE_HASH_KEYS = frozenset(
    (*FROZEN_SOURCE_HASHES, "baseline_package_sha256", "as_of_export_sha256")
)
FROZEN_MINIMUM_ISSUE_EXCLUSIVE = 26082
FROZEN_FALSE_AUDIT_FIELDS = (
    "outcome_accessed",
    "probability_retuned",
    "selector_retuned",
    "allocator_changed",
    "ticket_economics_changed",
)

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


def compute_decision_id(trace: Mapping[str, Any]) -> str:
    payload = dict(trace)
    payload.pop("decision_id", None)
    return sha256_json(payload)


def build_decision_trace(trace_without_id: Mapping[str, Any]) -> dict[str, Any]:
    """Content-address and validate one prospective trace before persistence."""

    trace = json.loads(canonical_json(trace_without_id))
    trace.pop("decision_id", None)
    trace["decision_id"] = compute_decision_id(trace)
    validate_frozen_constants(trace)
    validate_decision_trace(trace)
    return trace


def validate_frozen_constants(trace: Mapping[str, Any]) -> None:
    """Enforce declarative schema constants without a runtime JSON-Schema dependency."""

    if trace.get("schema_version") != SCHEMA_VERSION:
        raise DecisionContractError("schema_version does not match the frozen contract")
    if trace.get("contract") != CONTRACT:
        raise DecisionContractError("contract does not match the frozen contract")
    activation = trace.get("activation")
    if not isinstance(activation, Mapping) or (
        activation.get("minimum_issue_exclusive") != FROZEN_MINIMUM_ISSUE_EXCLUSIVE
    ):
        raise DecisionContractError("minimum_issue_exclusive must equal 26082")
    baseline = trace.get("baseline")
    if not isinstance(baseline, Mapping) or baseline.get("selector") != "B0_BEST_FULL":
        raise DecisionContractError("baseline selector does not match B0_BEST_FULL")
    evidence = trace.get("evidence")
    if not isinstance(evidence, Mapping):
        raise DecisionContractError("evidence section is missing")
    if evidence.get("ledger_schema_version") != "message_evidence_ledger_v1":
        raise DecisionContractError(
            "ledger schema version does not match the frozen contract"
        )
    if evidence.get("allowed_provenance_tiers") != list(ALLOWED_PROVENANCE_TIERS):
        raise DecisionContractError(
            "allowed provenance tiers do not match the frozen contract"
        )
    if evidence.get("required_kind_max_age_seconds") != REQUIRED_KIND_MAX_AGE_SECONDS:
        raise DecisionContractError(
            "evidence freshness limits do not match the frozen contract"
        )
    audit = trace.get("audit")
    if not isinstance(audit, Mapping):
        raise DecisionContractError("audit section is missing")
    for field in FROZEN_FALSE_AUDIT_FIELDS:
        if audit.get(field) is not False:
            raise DecisionContractError(f"audit.{field} must be false")


def _choice(value: object, allowed: Sequence[str], field: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise DecisionContractError(f"{field} must be one of {tuple(allowed)}")
    return normalized


def _timestamp(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DecisionContractError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


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
    if confidence is None:
        return "LOW"
    try:
        score = float(confidence)
    except (TypeError, ValueError) as exc:
        raise DecisionContractError("confidence must be numeric") from exc
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise DecisionContractError("confidence must be finite and between 0 and 1")
    if tier not in ALLOWED_PROVENANCE_TIERS:
        return "LOW"
    if tier in {"TIER_0_OFFICIAL", "TIER_1_PRIMARY"} and score >= 0.75:
        return "HIGH"
    if (tier == "TIER_2_RELIABLE" and score >= 0.75) or (
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
    kickoff_ts_utc: str,
    home_team_id: str,
    away_team_id: str,
    coverage_by_kind: Mapping[str, Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    """Convert cutoff-safe coverage/facts into a symmetric match-risk flag."""

    errors: list[str] = []
    try:
        kickoff = _timestamp(kickoff_ts_utc, "match kickoff")
        normalized_kickoff = kickoff.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
    except DecisionContractError:
        normalized_kickoff = str(kickoff_ts_utc)
        errors.append("MATCH_KICKOFF_INVALID")
    for kind in REQUIRED_KIND_MAX_AGE_SECONDS:
        coverage = coverage_by_kind.get(kind)
        if not isinstance(coverage, Mapping):
            errors.append("COVERAGE_REPORT_MISSING")
        else:
            if str(coverage.get("match_id") or "") != match_id:
                errors.append("COVERAGE_REPORT_IDENTITY_MISMATCH")
            if coverage.get("required_fact_kinds") != [kind]:
                errors.append("COVERAGE_POLICY_MISMATCH")
            try:
                coverage_kickoff = _timestamp(
                    coverage.get("kickoff_at_utc"), "coverage kickoff"
                )
                baseline_kickoff = _timestamp(kickoff_ts_utc, "match kickoff")
                if coverage_kickoff != baseline_kickoff:
                    errors.append("COVERAGE_KICKOFF_MISMATCH")
            except DecisionContractError:
                errors.append("COVERAGE_KICKOFF_MISMATCH")
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
            normalize_fact(fact, home_team_id=home_team_id, away_team_id=away_team_id)
            for fact in active
        ]
    except (DecisionContractError, KeyError, TypeError, ValueError):
        errors.append("FACT_EXTRACTION_SCHEMA_INVALID")
    errors = sorted(set(errors))
    if errors:
        return {
            "match_id": match_id,
            "kickoff_ts_utc": normalized_kickoff,
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
    meaningful_absence_entities = {
        str(row["entity_id"] or row["fact_id"])
        for row in normalized
        if row["consumer_confidence_band"] in {"HIGH", "MEDIUM"}
        and row["availability"] == "UNAVAILABLE"
        and row["role_class"] in {"KEY_GOALKEEPER", "KEY_STARTER", "STARTER"}
    }
    medium_signal = [
        row
        for row in normalized
        if row["consumer_confidence_band"] in {"HIGH", "MEDIUM"}
        and (
            row["availability"] in {"DOUBTFUL", "UNAVAILABLE"}
            or row["severity"] in {"MEDIUM", "HIGH"}
        )
    ]
    if high_critical or len(meaningful_absence_entities) >= 2:
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
    translation = (
        directions[0]
        if len(directions) == 1
        else ("SYMMETRIC_UNCERTAINTY" if directions else "NO_CHANGE")
    )
    return {
        "match_id": match_id,
        "kickoff_ts_utc": normalized_kickoff,
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
    validate_frozen_candidate_order(baseline_candidates)
    for rank, candidate in enumerate(baseline_candidates, start=1):
        match_ids = list(candidate["selected_match_ids"])
        if len(match_ids) != 7 or len(set(match_ids)) != 7:
            raise DecisionContractError(
                "every candidate must contain seven unique matches"
            )
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


def validate_frozen_candidate_order(
    candidates: Sequence[Mapping[str, Any]],
) -> None:
    """Prove the supplied order is the frozen B0 score/tie-break order."""

    if not candidates:
        raise DecisionContractError("candidate order must not be empty")
    keys: list[tuple[float, str]] = []
    portfolio_ids: set[str] = set()
    fingerprints: set[str] = set()
    for expected_rank, candidate in enumerate(candidates, start=1):
        if candidate.get("source_rank") != expected_rank:
            raise DecisionContractError(
                "candidate source_rank must equal list position"
            )
        try:
            score = float(candidate["b0_score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DecisionContractError("candidate b0_score must be numeric") from exc
        if not math.isfinite(score):
            raise DecisionContractError("candidate b0_score must be finite")
        portfolio_id = str(candidate.get("portfolio_id") or "")
        fingerprint = str(candidate.get("identity_fingerprint") or "")
        if not portfolio_id or portfolio_id in portfolio_ids:
            raise DecisionContractError(
                "candidate portfolio_id must be nonempty and unique"
            )
        if not fingerprint or fingerprint in fingerprints:
            raise DecisionContractError(
                "candidate identity_fingerprint must be nonempty and unique"
            )
        match_ids = [str(value) for value in candidate.get("selected_match_ids", [])]
        if len(match_ids) != 7 or len(set(match_ids)) != 7 or not all(match_ids):
            raise DecisionContractError(
                "every candidate must contain seven unique matches"
            )
        portfolio_ids.add(portfolio_id)
        fingerprints.add(fingerprint)
        keys.append((-score, portfolio_id))
    if keys != sorted(keys):
        raise DecisionContractError(
            "candidate order must be b0_score descending with portfolio_id tie break"
        )


def _selected_arm(
    *,
    arm: str,
    role: str,
    identity: tuple[str, str, list[str], object],
) -> dict[str, object]:
    return {
        "arm": arm,
        "role": role,
        "policy_status": "SELECTED_PREOUTCOME",
        "selected_portfolio_id": identity[0],
        "selected_identity_fingerprint": identity[1],
        "selected_match_ids": identity[2],
        "source_rank": identity[3],
        "planned_ticket_count": 2187,
        "planned_stake_yuan": 4374,
    }


def _abstain_arm(*, arm: str, role: str) -> dict[str, object]:
    return {
        "arm": arm,
        "role": role,
        "policy_status": "ABSTAIN_NO_ELIGIBLE_IDENTITY",
        "selected_portfolio_id": "",
        "selected_identity_fingerprint": "",
        "selected_match_ids": [],
        "source_rank": None,
        "planned_ticket_count": 0,
        "planned_stake_yuan": 0,
    }


def validate_decision_trace(trace: Mapping[str, Any]) -> None:
    """Validate cross-field invariants that JSON Schema cannot express."""

    try:
        activation = trace["activation"]
        baseline = trace["baseline"]
        evidence = trace["evidence"]
        candidates = baseline["candidate_order"]
        assessments = trace["match_assessments"]
        arms = trace["arms"]
    except (KeyError, TypeError) as exc:
        raise DecisionContractError(
            "decision trace is missing a required section"
        ) from exc
    if (
        not all(
            isinstance(value, Mapping) for value in (activation, baseline, evidence)
        )
        or not isinstance(candidates, Sequence)
        or isinstance(candidates, (str, bytes))
    ):
        raise DecisionContractError("decision trace sections have invalid shapes")
    if not isinstance(assessments, Sequence) or isinstance(assessments, (str, bytes)):
        raise DecisionContractError("match_assessments must be an array")
    if not isinstance(arms, Sequence) or isinstance(arms, (str, bytes)):
        raise DecisionContractError("arms must be an array")
    validate_frozen_candidate_order(candidates)

    try:
        issue = int(str(trace["issue"]))
        minimum_issue = int(activation["minimum_issue_exclusive"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionContractError("issue boundaries must be integers") from exc
    if minimum_issue != FROZEN_MINIMUM_ISSUE_EXCLUSIVE:
        raise DecisionContractError("minimum_issue_exclusive must equal 26082")
    if issue <= minimum_issue:
        raise DecisionContractError(
            "issue must be strictly after the activation boundary"
        )

    accepted_at = _timestamp(
        activation["gate_a_acceptance_recorded_at_utc"], "Gate-A acceptance"
    )
    package_created_at = _timestamp(
        baseline["package_created_at_utc"], "baseline package creation"
    )
    input_as_of = _timestamp(baseline["input_as_of_utc"], "baseline input as-of")
    latest_receipt = _timestamp(
        evidence["latest_receipt_recorded_at_utc"], "latest evidence receipt"
    )
    cutoff = _timestamp(evidence["cutoff_ts_utc"], "evidence cutoff")
    freeze = _timestamp(trace["freeze_ts_utc"], "decision freeze")
    if not accepted_at <= input_as_of <= package_created_at <= freeze:
        raise DecisionContractError(
            "baseline input/package chronology must be bounded by activation and freeze"
        )
    if not accepted_at <= latest_receipt <= cutoff <= freeze:
        raise DecisionContractError(
            "evidence receipt/cutoff chronology must be bounded by activation and freeze"
        )
    if input_as_of > cutoff:
        raise DecisionContractError(
            "baseline input as-of cannot follow evidence cutoff"
        )

    coverage_hashes = evidence.get("coverage_report_sha256_by_kind")
    if not isinstance(coverage_hashes, Mapping) or set(coverage_hashes) != set(
        REQUIRED_KIND_MAX_AGE_SECONDS
    ):
        raise DecisionContractError(
            "coverage report hashes must use exactly the frozen required fact kinds"
        )

    audit = trace.get("audit")
    source_hashes = audit.get("source_hashes") if isinstance(audit, Mapping) else None
    if (
        not isinstance(source_hashes, Mapping)
        or set(source_hashes) != TRACE_SOURCE_HASH_KEYS
    ):
        raise DecisionContractError(
            "audit source hashes must use exactly the frozen keys"
        )
    for key, expected_hash in FROZEN_SOURCE_HASHES.items():
        if source_hashes.get(key) != expected_hash:
            raise DecisionContractError(f"audit source hash mismatch: {key}")
    if source_hashes.get("baseline_package_sha256") != baseline.get("package_id"):
        raise DecisionContractError(
            "baseline package source hash is not bound to package_id"
        )
    if source_hashes.get("as_of_export_sha256") != evidence.get("as_of_export_sha256"):
        raise DecisionContractError("as-of export source hash is not bound to evidence")

    first = candidates[0]
    baseline_identity = (
        str(baseline.get("selected_portfolio_id") or ""),
        str(baseline.get("selected_identity_fingerprint") or ""),
        [str(value) for value in baseline.get("selected_match_ids", [])],
        1,
    )
    first_identity = (
        str(first.get("portfolio_id") or ""),
        str(first.get("identity_fingerprint") or ""),
        [str(value) for value in first.get("selected_match_ids", [])],
        first.get("source_rank"),
    )
    if baseline_identity != first_identity:
        raise DecisionContractError("B0 selected identity must equal candidate rank 1")

    assessment_by_match: dict[str, Mapping[str, Any]] = {}
    for row in assessments:
        if not isinstance(row, Mapping):
            raise DecisionContractError("match assessment must be an object")
        match_id = str(row.get("match_id") or "")
        if not match_id or match_id in assessment_by_match:
            raise DecisionContractError(
                "match assessment IDs must be nonempty and unique"
            )
        assessment_by_match[match_id] = row

    candidate_match_ids = {
        str(match_id)
        for candidate in candidates
        for match_id in candidate["selected_match_ids"]
    }
    if candidate_match_ids != set(assessment_by_match):
        raise DecisionContractError(
            "match assessments must equal the frozen candidate match universe"
        )
    for match_id in candidate_match_ids:
        kickoff = _timestamp(
            assessment_by_match[match_id].get("kickoff_ts_utc"),
            f"match {match_id} kickoff",
        )
        if freeze >= kickoff:
            raise DecisionContractError(
                "decision freeze must be strictly before every candidate kickoff"
            )

    m0 = _selected_arm(
        arm="M0_MESSAGE_ANNOTATION",
        role="DIAGNOSTIC",
        identity=baseline_identity,
    )
    m1_selection = select_message_identity(candidates, assessment_by_match)
    m1 = {
        "arm": "M1_MESSAGE_RISK_RERANK",
        "role": "PRIMARY_CHALLENGER",
        **m1_selection,
        "planned_ticket_count": (
            2187 if m1_selection["policy_status"] == "SELECTED_PREOUTCOME" else 0
        ),
        "planned_stake_yuan": (
            4374 if m1_selection["policy_status"] == "SELECTED_PREOUTCOME" else 0
        ),
    }
    expected = {
        "B0_BASELINE_SHADOW": _selected_arm(
            arm="B0_BASELINE_SHADOW",
            role="CONTROLLING_BASELINE",
            identity=baseline_identity,
        ),
        "M0_MESSAGE_ANNOTATION": m0,
        "M1_MESSAGE_RISK_RERANK": m1,
    }
    actual: dict[str, Mapping[str, Any]] = {}
    for row in arms:
        if not isinstance(row, Mapping):
            raise DecisionContractError("arm decision must be an object")
        arm = str(row.get("arm") or "")
        if arm in actual:
            raise DecisionContractError("arm names must be unique")
        actual[arm] = row
    if set(actual) != set(expected):
        raise DecisionContractError(
            "decision trace must contain exactly the frozen arms"
        )
    for arm, expected_row in expected.items():
        if dict(actual[arm]) != expected_row:
            raise DecisionContractError(f"{arm} does not match frozen policy output")
    if trace.get("decision_id") != compute_decision_id(trace):
        raise DecisionContractError(
            "decision_id must equal the canonical trace content hash"
        )
