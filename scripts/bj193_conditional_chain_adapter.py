#!/usr/bin/env python3
"""Outcome-unexposed #193 Stage-2/Stage-3 conditional adapters.

This module turns an immutable Stage-1 seven-match output into a direction
payload using the accepted #190 estimator fields, then turns the direction
payload plus a Stage-3 weight vector into exact ticket multiplicities using
the byte-bound #145 allocator.  It deliberately accepts no outcome, final-SP,
payout, tax, ROI, or settlement field.
"""

from __future__ import annotations

import hashlib
import json
import math
import types
from pathlib import Path
from typing import Mapping, Sequence


ADAPTER_VERSION = "bj193-conditional-chain-adapter-v3"
CODES = ("3", "1", "0")
LEGS = 7
FULL_TICKET_COUNT = 3**LEGS
WEIGHT_SOURCE_FIELDS = {
    "MODEL_P_CAL": ("p_model3", "p_model1", "p_model0"),
    "MARKET_WF_CAL": ("p_market_cal3", "p_market_cal1", "p_market_cal0"),
    "BLEND_A25": ("p_blend_a25_3", "p_blend_a25_1", "p_blend_a25_0"),
    "BLEND_A50": ("p_blend_a50_3", "p_blend_a50_1", "p_blend_a50_0"),
    "BLEND_A75": ("p_blend_a75_3", "p_blend_a75_1", "p_blend_a75_0"),
    "Q_WEIGHT": ("q_weight3", "q_weight1", "q_weight0"),
    "NA": (),
}
FORBIDDEN_INPUT_FIELDS = frozenset(
    {
        "target_result",
        "result_code",
        "final_sp",
        "winning_sp",
        "payout",
        "tax",
        "roi",
        "settlement",
        "pre_tax_net_yuan",
        "tax_net_yuan",
    }
)


def canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _assert_outcome_unexposed(row: Mapping[str, object]) -> None:
    exposed = sorted(FORBIDDEN_INPUT_FIELDS & set(row))
    if exposed:
        raise ValueError(f"forbidden outcome fields supplied: {exposed}")


def _number(value: object, *, blank: float | None = None) -> float | None:
    if value in (None, ""):
        return blank
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite estimator field")
    return parsed


def _code_features(delta: Mapping[str, float]) -> dict[str, object]:
    favored = min(CODES, key=lambda code: (-delta[code], CODES.index(code)))
    omitted = min(CODES, key=lambda code: (delta[code], CODES.index(code)))
    extreme = min(
        CODES, key=lambda code: (-abs(delta[code]), CODES.index(code))
    )
    return {
        "favored_code": favored,
        "omitted_code": omitted,
        "magnitude": abs(delta[extreme]),
        "extreme_code": extreme,
    }


def _one_probability_metric(
    row: Mapping[str, object], prefix: str, source: str
) -> dict[str, object]:
    delta = {code: float(row[f"{prefix}_delta_p{code}"]) for code in CODES}
    z = {code: float(row[f"{prefix}_z{code}"]) for code in CODES}
    probability = tuple(float(row[f"{prefix}_p{code}"]) for code in CODES)
    features = _code_features(delta)
    extreme_index = CODES.index(str(features["extreme_code"]))
    return {
        **features,
        "abs_z": abs(z[CODES[extreme_index]]),
        "estimator_source": source,
        "allocation_probability": probability,
        "delta": delta,
        "z": z,
    }


def metric_for_match(
    row: Mapping[str, object], policy: Mapping[str, object]
) -> dict[str, object] | None:
    """Reproduce the accepted #190 estimator-to-direction mapping."""

    _assert_outcome_unexposed(row)
    _assert_outcome_unexposed(policy)
    if row.get("target_safe_consensus_status") != "AVAILABLE":
        return None
    detector = str(policy["detector_family"])
    variant = str(policy["estimator_variant"])
    if detector == "LINE_RESIDUAL_MU":
        value = _number(row.get("line_residual_mu"))
        z = _number(row.get("line_residual_z"))
        if value is None or z is None or abs(value) <= 1e-15:
            return None
        return {
            "favored_code": "3" if value > 0 else "0",
            "omitted_code": "0" if value > 0 else "3",
            "magnitude": abs(value),
            "abs_z": abs(z),
            "estimator_source": "FUNDAMENTAL_T1_SCORE_DISTRIBUTION",
            "allocation_probability": tuple(
                float(row[f"fundamental_p{code}"]) for code in CODES
            ),
            "delta": {},
            "z": {},
        }
    if detector != "DELTA_P":
        return None

    fundamental = _one_probability_metric(
        row, "fundamental", "FUNDAMENTAL_T1_SCORE_DISTRIBUTION"
    )
    calibrated = _one_probability_metric(
        row, "calibrated", "CALIBRATED_MARKET_ESTIMATOR"
    )
    if variant == "FUNDAMENTAL_INDEPENDENT":
        return fundamental
    if variant == "CALIBRATED_MARKET_ESTIMATOR":
        return calibrated
    if variant == "UNION":
        return min(
            (fundamental, calibrated),
            key=lambda metric: (
                -float(metric["magnitude"]),
                0
                if metric["estimator_source"]
                == "FUNDAMENTAL_T1_SCORE_DISTRIBUTION"
                else 1,
            ),
        )
    if variant == "MODEL_AGREEMENT":
        if (
            fundamental["favored_code"] != calibrated["favored_code"]
            or fundamental["omitted_code"] != calibrated["omitted_code"]
        ):
            return None
        weaker = min(
            (fundamental, calibrated),
            key=lambda metric: (
                float(metric["magnitude"]),
                0
                if metric["estimator_source"]
                == "FUNDAMENTAL_T1_SCORE_DISTRIBUTION"
                else 1,
            ),
        )
        return {
            **weaker,
            "magnitude": min(
                float(fundamental["magnitude"]),
                float(calibrated["magnitude"]),
            ),
            "abs_z": min(
                float(fundamental["abs_z"]), float(calibrated["abs_z"])
            ),
            "estimator_source": (
                "STRICT_AGREEMENT_WEAKER::" + str(weaker["estimator_source"])
            ),
        }
    raise ValueError(f"unknown estimator variant: {variant}")


def estimator_identity_binding(
    row: Mapping[str, object],
    policy: Mapping[str, object],
    metric: Mapping[str, object],
) -> dict[str, object]:
    """Bind every immutable estimator component used to derive a direction."""

    _assert_outcome_unexposed(row)
    _assert_outcome_unexposed(policy)
    detector = str(policy["detector_family"])
    variant = str(policy["estimator_variant"])
    if detector == "LINE_RESIDUAL_MU" or variant == "FUNDAMENTAL_INDEPENDENT":
        component_names = ("t1_score_estimator_identity_sha256",)
    elif variant == "CALIBRATED_MARKET_ESTIMATOR":
        component_names = ("target_safe_consensus_identity_sha256",)
    elif variant in {"UNION", "MODEL_AGREEMENT"}:
        # Both components affect source choice/agreement, even though only one
        # component supplies the eventual probability vector.
        component_names = (
            "t1_score_estimator_identity_sha256",
            "target_safe_consensus_identity_sha256",
        )
    else:
        raise ValueError("unknown estimator identity topology")
    components: dict[str, str] = {}
    for name in component_names:
        identity = str(row.get(name, ""))
        if len(identity) != 64 or any(
            character not in "0123456789abcdef" for character in identity.lower()
        ):
            raise ValueError(f"invalid estimator component identity: {name}")
        components[name] = identity
    payload = {
        "detector_family": detector,
        "estimator_variant": variant,
        "selected_estimator_source": str(metric["estimator_source"]),
        "components": components,
    }
    return {
        "binding_sha256": canonical_hash(payload),
        "components": components,
    }


def _passes_base_gate(
    row: Mapping[str, object], policy: Mapping[str, object]
) -> tuple[bool, str]:
    if int(row["min_history_n"]) < int(policy["min_history_n"]):
        return False, "MIN_HISTORY"
    if (
        policy["coverage_gate"] == "BROAD_MARKET_AND_TARGET_SAFE_PRICE"
        and row["market_signature_breadth"] != "B05_19"
    ):
        return False, "BROAD_MARKET_COVERAGE"
    if (
        policy["uncertainty_gate"] == "MAX_0.12"
        and float(row["market_uncertainty_proxy"]) > 0.12
    ):
        return False, "UNCERTAINTY"
    return True, "PASS"


def _passes_threshold(
    metric: Mapping[str, object], policy: Mapping[str, object]
) -> bool:
    magnitude = float(metric["magnitude"])
    if magnitude <= 1e-15:
        return False
    if policy["detector_family"] == "DELTA_P":
        if magnitude + 1e-15 < float(policy["abs_delta_p_min"]):
            return False
    elif policy["detector_family"] == "LINE_RESIDUAL_MU":
        if magnitude + 1e-15 < float(policy["abs_line_residual_mu_min"]):
            return False
    else:
        return False
    return float(metric["abs_z"]) + 1e-15 >= float(policy["abs_z_min"])


def derived_direction_identity(
    policy: Mapping[str, object], *, adapter_sha256: str
) -> str:
    """Identity of the derived conditional action, not the #190 B0 arm."""

    return canonical_hash(
        {
            "adapter_version": ADAPTER_VERSION,
            "adapter_sha256": adapter_sha256,
            "upstream_policy_id": policy["policy_id"],
            "policy": {
                key: policy.get(key, "")
                for key in (
                    "detector_family",
                    "estimator_variant",
                    "threshold_rule",
                    "abs_delta_p_min",
                    "abs_z_min",
                    "top_k",
                    "min_history_n",
                    "coverage_gate",
                    "uncertainty_gate",
                    "abs_delta_mu_min",
                    "abs_line_residual_mu_min",
                    "availability",
                )
            },
            "support": "EXACT_IMMUTABLE_STAGE1_ORDERED_MATCH_IDS",
            "protection": "NO_ADDITIONAL_PROTECTION_BEYOND_FROZEN_BASE_AND_THRESHOLD_GATES",
        }
    )


def apply_direction_adapter(
    selected_match_ids: Sequence[str],
    estimator_by_match: Mapping[str, Mapping[str, object]],
    policy: Mapping[str, object],
    *,
    stage1_output_sha256: str,
    adapter_sha256: str,
) -> dict[str, object]:
    """Apply one #190 policy conditionally to an immutable Stage-1 N7 set."""

    _assert_outcome_unexposed(policy)
    ordered = tuple(str(match_id) for match_id in selected_match_ids)
    derived_id = derived_direction_identity(policy, adapter_sha256=adapter_sha256)
    base = {
        "adapter_version": ADAPTER_VERSION,
        "adapter_sha256": adapter_sha256,
        "derived_direction_action_sha256": derived_id,
        "upstream_policy_id": str(policy["policy_id"]),
        "stage1_output_sha256": stage1_output_sha256,
        "ordered_match_ids": list(ordered),
        "estimator_registry_source": (
            "bj190_gate_a_preoutcome_v3r1/estimator_match_freeze.csv.gz"
        ),
        "protection_rule": (
            "NO_ADDITIONAL_PROTECTION; exact #190 target-safe, history, "
            "breadth, uncertainty and threshold gates only"
        ),
    }

    def zero(status: str, reason: str) -> dict[str, object]:
        payload = {
            **base,
            "status": status,
            "reason_code": reason,
            "per_match": [],
            "ranked_direction_match_ids": [],
            "strongest_match_id": "",
            "delete_leg_index_zero_based": None,
            "omitted_code": "",
            "ticket_support_size": 0,
        }
        payload["direction_output_sha256"] = canonical_hash(payload)
        return payload

    if policy.get("availability") != "AVAILABLE":
        return zero("UNAVAILABLE", "UPSTREAM_POLICY_UNAVAILABLE")
    if len(ordered) != LEGS or len(set(ordered)) != LEGS:
        return zero("NO_BET", "STAGE1_NOT_EXACT_N7")
    if any(match_id not in estimator_by_match for match_id in ordered):
        return zero("UNAVAILABLE", "ESTIMATOR_ROW_MISSING")

    metrics: list[dict[str, object]] = []
    for match_id in ordered:
        source = estimator_by_match[match_id]
        _assert_outcome_unexposed(source)
        passed, failed_gate = _passes_base_gate(source, policy)
        if not passed:
            return zero("NO_BET", f"BASE_GATE_{failed_gate}")
        metric = metric_for_match(source, policy)
        if metric is None:
            return zero("NO_BET", "ESTIMATOR_DIRECTION_UNAVAILABLE")
        try:
            identity_binding = estimator_identity_binding(source, policy, metric)
        except (KeyError, ValueError):
            return zero("UNAVAILABLE", "ESTIMATOR_IDENTITY_MISSING_OR_INVALID")
        metrics.append(
            {
                "match_id": match_id,
                "match_idx": int(source["match_idx"]),
                "estimator_identity_sha256": identity_binding[
                    "binding_sha256"
                ],
                "estimator_component_identity_sha256": identity_binding[
                    "components"
                ],
                **metric,
            }
        )
    ranked = sorted(
        metrics,
        key=lambda metric: (
            -float(metric["magnitude"]),
            int(metric["match_idx"]),
            int(str(metric["match_id"])),
        ),
    )
    required = LEGS if policy["top_k"] == "ALL" else int(policy["top_k"])
    if not all(_passes_threshold(metric, policy) for metric in ranked[:required]):
        return zero("NO_BET", "THRESHOLD_NOT_MET")

    strongest = ranked[0]
    delete_leg = ordered.index(str(strongest["match_id"]))
    omitted = str(strongest["omitted_code"])
    per_match = []
    for match_id in ordered:
        metric = next(row for row in metrics if row["match_id"] == match_id)
        probabilities = tuple(float(value) for value in metric["allocation_probability"])
        allowed = [code for code in CODES]
        weights = [probabilities[index] for index in range(3)]
        if match_id == strongest["match_id"]:
            allowed = [code for code in CODES if code != omitted]
            weights[CODES.index(omitted)] = 0.0
        per_match.append(
            {
                "match_id": match_id,
                "match_idx": metric["match_idx"],
                "estimator_source": metric["estimator_source"],
                "estimator_identity_sha256": metric[
                    "estimator_identity_sha256"
                ],
                "estimator_component_identity_sha256": metric[
                    "estimator_component_identity_sha256"
                ],
                "probability_3_1_0": [format(value, ".12f") for value in probabilities],
                "allowed_codes": allowed,
                "direction_weight_3_1_0": [format(value, ".12f") for value in weights],
                "favored_code": metric["favored_code"],
                "omitted_code": metric["omitted_code"],
                "magnitude": format(float(metric["magnitude"]), ".12f"),
                "abs_z": format(float(metric["abs_z"]), ".12f"),
                "protection_flag": False,
                "threshold_pass": _passes_threshold(metric, policy),
            }
        )
    payload = {
        **base,
        "status": "ACTIVE",
        "reason_code": "DERIVED_STAGE1_CONDITIONAL_DIRECTION",
        "per_match": per_match,
        "ranked_direction_match_ids": [str(row["match_id"]) for row in ranked],
        "strongest_match_id": str(strongest["match_id"]),
        "delete_leg_index_zero_based": delete_leg,
        "omitted_code": omitted,
        "ticket_support_size": 2 * 3 ** (LEGS - 1),
    }
    payload["direction_output_sha256"] = canonical_hash(payload)
    return payload


def canonical_ticket_weight_vector(
    per_match_weights: Sequence[Sequence[float]],
) -> tuple[float, ...]:
    """Return a normalized full-ordinal vector with explicit zero support."""

    if len(per_match_weights) != LEGS:
        raise ValueError("exactly seven per-match vectors are required")
    parsed: list[tuple[float, float, float]] = []
    for leg in per_match_weights:
        if len(leg) != 3:
            raise ValueError("each per-match vector must use code order 3/1/0")
        values = tuple(float(value) for value in leg)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("ticket weights must be finite and non-negative")
        parsed.append(values)  # type: ignore[arg-type]
    raw = []
    for ordinal in range(FULL_TICKET_COUNT):
        value = ordinal
        digits = [0] * LEGS
        for index in range(LEGS - 1, -1, -1):
            digits[index] = value % 3
            value //= 3
        raw.append(math.prod(parsed[index][digit] for index, digit in enumerate(digits)))
    total = math.fsum(raw)
    if total <= 0 or not math.isfinite(total):
        raise ValueError("direction output has no positive ticket support")
    normalized = [value / total for value in raw]
    positive = [index for index, value in enumerate(normalized) if value > 0]
    # Freeze a deterministic final-positive residual correction.  The accepted
    # #145 WR engine consumes raw cumulative masses and assumes normalization.
    normalized[positive[-1]] += 1.0 - math.fsum(normalized)
    if normalized[positive[-1]] <= 0:
        raise ValueError("normalization residual invalidated positive support")
    return tuple(normalized)


def combine_stage2_and_stage3_weights(
    ordered_match_ids: Sequence[str],
    direction_per_match: Sequence[Mapping[str, object]],
    role_by_match: Mapping[str, Mapping[str, object]],
    weight_source: str,
) -> dict[str, object]:
    """Map an accepted #137 weight source through the exact Stage-2 mask."""

    def unavailable(reason_code: str) -> dict[str, object]:
        return {
            "status": "UNAVAILABLE",
            "reason_code": reason_code,
            "ordered_match_ids": list(ordered),
            "weight_source": weight_source,
            "per_match_weight_3_1_0": [],
            "role_identity_sha256_by_match": {},
            "combined_weight_input_sha256": "",
        }

    ordered = tuple(str(match_id) for match_id in ordered_match_ids)
    if len(ordered) != LEGS or len(set(ordered)) != LEGS:
        raise ValueError("Stage-3 builder requires exact ordered N7 support")
    if weight_source not in WEIGHT_SOURCE_FIELDS:
        raise ValueError(f"unknown Stage-3 weight source: {weight_source}")
    direction_by_match = {
        str(row["match_id"]): row for row in direction_per_match
    }
    if set(direction_by_match) != set(ordered):
        raise ValueError("Stage-2 direction rows do not match Stage-1 support")
    if weight_source != "NA" and any(
        match_id not in role_by_match for match_id in ordered
    ):
        return unavailable("STAGE3_ROLE_VECTOR_MISSING")
    fields = WEIGHT_SOURCE_FIELDS[weight_source]
    if weight_source != "NA":
        source_rows = [role_by_match[match_id] for match_id in ordered]
        if any(
            str(row.get("match_id", "")) != match_id
            for match_id, row in zip(ordered, source_rows, strict=True)
        ):
            return unavailable("STAGE3_MATCH_IDENTITY_MISMATCH")
        if any(any(field not in row for field in fields) for row in source_rows):
            return unavailable("STAGE3_WEIGHT_SOURCE_FIELD_MISSING")
        portfolio_ids = {str(row.get("portfolio_id", "")) for row in source_rows}
        issues = {str(row.get("issue", "")) for row in source_rows}
        if "" in portfolio_ids or len(portfolio_ids) != 1:
            return unavailable("STAGE3_PORTFOLIO_IDENTITY_MISMATCH")
        if "" in issues or len(issues) != 1:
            return unavailable("STAGE3_ISSUE_IDENTITY_MISMATCH")
    combined: list[list[float]] = []
    identities: dict[str, str] = {}
    for match_id in ordered:
        role = role_by_match.get(match_id, {})
        direction = direction_by_match[match_id]
        _assert_outcome_unexposed(role)
        _assert_outcome_unexposed(direction)
        allowed = {str(code) for code in direction["allowed_codes"]}
        if not allowed <= set(CODES):
            raise ValueError("unknown Stage-2 allowed code")
        direction_weights = tuple(
            float(value) for value in direction["direction_weight_3_1_0"]
        )
        if len(direction_weights) != 3:
            raise ValueError("Stage-2 direction weight must use 3/1/0 order")
        source_weights = (
            (1.0, 1.0, 1.0)
            if weight_source == "NA"
            else tuple(float(role[field]) for field in fields)
        )
        if any(
            not math.isfinite(value) or value < 0
            for value in (*direction_weights, *source_weights)
        ):
            raise ValueError("invalid Stage-2/Stage-3 weight")
        values = [
            source_weights[index] * direction_weights[index]
            if code in allowed
            else 0.0
            for index, code in enumerate(CODES)
        ]
        combined.append(values)
        identity_payload = {
            "source_package": (
                "CONTROL_UNIT_WEIGHT" if weight_source == "NA"
                else "bj137_gate_a_preoutcome_v2"
            ),
            "source_file": (
                "NA" if weight_source == "NA" else "n7_role_vectors.csv.gz"
            ),
            "portfolio_id": role.get("portfolio_id", "NA"),
            "issue": role.get("issue", "NA"),
            "match_id": match_id,
            "weight_source": weight_source,
            "fields": list(fields),
            "values": [format(value, ".12f") for value in source_weights],
        }
        identities[match_id] = canonical_hash(identity_payload)
    payload = {
        "status": "ACTIVE",
        "reason_code": "STAGE2_MASK_TIMES_BOUND_STAGE3_WEIGHT_SOURCE",
        "ordered_match_ids": list(ordered),
        "weight_source": weight_source,
        "source_portfolio_id": (
            "NA" if weight_source == "NA"
            else str(role_by_match[ordered[0]]["portfolio_id"])
        ),
        "source_issue": (
            "NA" if weight_source == "NA"
            else str(role_by_match[ordered[0]]["issue"])
        ),
        "per_match_weight_3_1_0": [
            [format(value, ".12f") for value in row] for row in combined
        ],
        "role_identity_sha256_by_match": identities,
    }
    payload["combined_weight_input_sha256"] = canonical_hash(payload)
    return payload


def ticket_weight_sha256(weights: Sequence[float]) -> str:
    return canonical_hash([format(float(value), ".17g") for value in weights])


def allocate_conditional_tickets(
    mechanism: str,
    per_match_weights: Sequence[Sequence[float]],
    m: int,
    *,
    allocation_engine: object,
    seed: str = "NA",
    identity_signature: str = "",
    cap: int | None = None,
) -> dict[str, object]:
    """Freeze reduced-support behavior before calling the accepted engine."""

    try:
        weights = canonical_ticket_weight_vector(per_match_weights)
    except ValueError as error:
        return {
            "status": "NO_BET",
            "reason_code": "NO_POSITIVE_TICKET_SUPPORT",
            "requested_M": int(m),
            "effective_M": 0,
            "positive_support_count": 0,
            "requested_ticket_count": 0,
            "requested_stake_yuan": 0,
            "ticket_weight_sha256": "",
            "counts_sha256": "",
            "counts": (),
            "detail": str(error),
        }
    positive = sum(value > 0 for value in weights)
    if mechanism in {"WOR_DISTINCT", "DETERMINISTIC_TOP_MASS"} and m > positive:
        status = "NO_BET"
        reason = "M_EXCEEDS_DISTINCT_POSITIVE_SUPPORT"
        counts: tuple[int, ...] = tuple()
        effective_m = 0
    elif mechanism == "CAPPED_REPEAT" and (
        cap is None or m > positive * int(cap)
    ):
        status = "NO_BET"
        reason = "M_EXCEEDS_POSITIVE_SUPPORT_CAPACITY"
        counts = tuple()
        effective_m = 0
    elif mechanism == "FULL_ENUMERATED":
        # FULL means each allowed upstream ticket exactly once.  On reduced
        # support this is the explicit enumerate-support fallback rather than
        # reintroducing deleted/zero-weight tickets.
        counts = tuple(1 if value > 0 else 0 for value in weights)
        status = "ACTIVE"
        reason = (
            "FULL_ALLOW_ALL" if positive == FULL_TICKET_COUNT
            else "ENUMERATE_UPSTREAM_SUPPORT_FALLBACK"
        )
        effective_m = positive
    else:
        counts = allocation_engine.allocate(
            mechanism,
            weights,
            int(m),
            seed=str(seed),
            identity_signature=identity_signature,
            cap=cap,
        )
        if any(count and weights[index] <= 0 for index, count in enumerate(counts)):
            raise RuntimeError("accepted allocator selected zero-weight ordinal")
        status = "ACTIVE"
        reason = "ALLOCATED_ON_POSITIVE_UPSTREAM_SUPPORT"
        effective_m = sum(counts)
    if status == "NO_BET":
        fingerprint = {
            "counts_sha256": "",
            "draw_count": 0,
            "unique_count": 0,
            "duplicate_count": 0,
            "max_multiplicity": 0,
        }
    else:
        fingerprint = allocation_engine.counts_fingerprint(counts)
    return {
        "status": status,
        "reason_code": reason,
        "requested_M": int(m),
        "effective_M": effective_m,
        "positive_support_count": positive,
        "requested_ticket_count": int(fingerprint["draw_count"]),
        "requested_stake_yuan": 2 * int(fingerprint["draw_count"]),
        "ticket_weight_sha256": ticket_weight_sha256(weights),
        **fingerprint,
        "counts": counts,
    }


def load_frozen_allocation_engine(path: Path) -> object:
    module = types.ModuleType("bj145_frozen_allocator")
    module.__file__ = str(path)
    source = path.read_bytes()
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module
