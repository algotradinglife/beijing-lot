#!/usr/bin/env python3
"""Outcome-unexposed #193 P/Q structural-delete composition adapter.

The two structural controls retain their accepted #167 identities and native
1458-ticket economics.  This adapter only corrects their derived #193
compatibility and composition semantics: it reads a complete, hash-bound #137
pre-event role registry, derives the original global deletion, composes that
deletion with the already-frozen Stage-2 mask, and enumerates every surviving
ticket once at CNY 2.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Mapping, Sequence


ADAPTER_VERSION = "bj193-structural-delete-adapter-v2.1"
REGISTRY_KIND = "BJ137_COMPLETE_STRUCTURAL_DELETE_REGISTRY_V2_1"
SOURCE_PACKAGE = "bj137_gate_a_preoutcome_v2"
SOURCE_FILE = "match_vectors.csv"
SOURCE_FILE_SHA256 = (
    "d80eaedc0062eea6929c00fbfb08eef9a02445edc1f533a394a35c238ccf2b56"
)
CODES = ("3", "1", "0")
MECHANISMS = ("P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE")
LEGS = 7
UNIT_STAKE_YUAN = 2
NATIVE_STRUCTURAL_M = 1458
FORBIDDEN_FIELDS = frozenset(
    {
        "result_code",
        "target_result",
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
STRUCTURAL_FIELDS = (
    "p_min",
    "p_model3",
    "p_model1",
    "p_model0",
    "q_weight3",
    "q_weight1",
    "q_weight0",
)


def canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_sha256(value: object, field: str) -> str:
    identity = str(value)
    if len(identity) != 64 or any(
        character not in "0123456789abcdef" for character in identity.lower()
    ):
        raise ValueError(f"invalid SHA-256 identity: {field}")
    return identity.lower()


def stage3_replay_signature(
    *,
    issue: object,
    stage1_output_sha256: object,
    stage2_output_sha256: object,
    derived_stage3_action_sha256: object,
) -> str:
    """Exact accepted v2 `BJ193_STAGE3_REPLAY_SIGNATURE_V1`."""

    issue_text = str(issue)
    if not issue_text or not issue_text.isdigit():
        raise ValueError("issue must be a nonblank numeric canonical identity")
    return canonical_hash(
        {
            "contract": "BJ193_STAGE3_REPLAY_SIGNATURE_V1",
            "issue": issue_text,
            "stage1_output_sha256": _require_sha256(
                stage1_output_sha256, "stage1_output_sha256"
            ),
            "stage2_output_sha256": _require_sha256(
                stage2_output_sha256, "stage2_output_sha256"
            ),
            "derived_stage3_action_sha256": _require_sha256(
                derived_stage3_action_sha256,
                "derived_stage3_action_sha256",
            ),
        }
    )


def _assert_outcome_unexposed(row: Mapping[str, object]) -> None:
    exposed = sorted(FORBIDDEN_FIELDS & set(row))
    if exposed:
        raise ValueError(f"forbidden outcome fields supplied: {exposed}")


def _finite(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric field: {field}") from exc
    if not math.isfinite(number):
        raise ValueError(f"non-finite numeric field: {field}")
    return number


def structural_registry_row_identity(row: Mapping[str, object]) -> str:
    """Hash every pre-event field consumed by the original structural rule."""

    _assert_outcome_unexposed(row)
    return canonical_hash(
        {
            "registry_kind": REGISTRY_KIND,
            "source_package": SOURCE_PACKAGE,
            "source_file": SOURCE_FILE,
            "source_file_sha256": SOURCE_FILE_SHA256,
            "issue": str(row["issue"]),
            "fold": str(row["fold"]),
            "year": str(row["year"]),
            "issue_instance": str(row["issue_instance"]),
            "match_id": str(row["match_id"]),
            "match_idx": str(row["match_idx"]),
            "kickoff_ts": str(row["kickoff_ts"]),
            "structural_values": {
                field: str(row[field]) for field in STRUCTURAL_FIELDS
            },
        }
    )


def validate_structural_rows(
    ordered_match_ids: Sequence[str],
    registry_by_match: Mapping[str, Mapping[str, object]],
) -> tuple[list[dict[str, object]], str | None]:
    """Return exact ordered rows or an explicit fail-closed reason."""

    ordered = [str(match_id) for match_id in ordered_match_ids]
    if len(ordered) != LEGS or len(set(ordered)) != LEGS:
        return [], "INVALID_STAGE1_N7_SUPPORT"
    rows: list[dict[str, object]] = []
    issue_fold: set[tuple[str, str, str]] = set()
    for match_id in ordered:
        raw = registry_by_match.get(match_id)
        if raw is None:
            return [], "STRUCTURAL_REGISTRY_ROW_MISSING"
        row = dict(raw)
        try:
            _assert_outcome_unexposed(row)
            if str(row.get("registry_kind")) != REGISTRY_KIND:
                return [], "STRUCTURAL_REGISTRY_KIND_MISMATCH"
            if str(row.get("source_package")) != SOURCE_PACKAGE:
                return [], "STRUCTURAL_REGISTRY_SOURCE_MISMATCH"
            if str(row.get("source_file")) != SOURCE_FILE:
                return [], "STRUCTURAL_REGISTRY_SOURCE_MISMATCH"
            if str(row.get("source_file_sha256")) != SOURCE_FILE_SHA256:
                return [], "STRUCTURAL_REGISTRY_SOURCE_HASH_MISMATCH"
            if str(row.get("match_id")) != match_id:
                return [], "STRUCTURAL_REGISTRY_MATCH_ID_MISMATCH"
            expected = structural_registry_row_identity(row)
            if str(row.get("structural_registry_row_sha256")) != expected:
                return [], "STRUCTURAL_REGISTRY_ROW_IDENTITY_MISMATCH"
            for field in STRUCTURAL_FIELDS:
                _finite(row[field], field)
        except (KeyError, TypeError, ValueError):
            return [], "STRUCTURAL_REGISTRY_ROW_INVALID"
        issue_fold.add(
            (str(row["issue"]), str(row["fold"]), str(row["issue_instance"]))
        )
        rows.append(row)
    if len(issue_fold) != 1:
        return [], "STRUCTURAL_REGISTRY_MIXED_ISSUE_OR_FOLD"
    return rows, None


def derive_structural_delete(
    mechanism: str, rows: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """Reproduce #167's float/tie ordering exactly on seven ordered rows."""

    if mechanism not in MECHANISMS:
        raise ValueError(f"unknown structural mechanism: {mechanism}")
    if len(rows) != LEGS:
        raise ValueError("structural delete requires exact N7 rows")
    if mechanism == "P_MIN_GLOBAL_DELETE":
        leg_index = min(
            range(LEGS), key=lambda index: (_finite(rows[index]["p_min"], "p_min"), index)
        )
        code_index = min(
            range(3),
            key=lambda index: (
                _finite(rows[leg_index][f"p_model{CODES[index]}"], "p_model"),
                index,
            ),
        )
        ranking_value = _finite(rows[leg_index]["p_min"], "p_min")
        code_ranking_value = _finite(
            rows[leg_index][f"p_model{CODES[code_index]}"], "p_model"
        )
    else:
        leg_index, code_index = min(
            ((leg, code) for leg in range(LEGS) for code in range(3)),
            key=lambda pair: (
                _finite(
                    rows[pair[0]][f"q_weight{CODES[pair[1]]}"], "q_weight"
                ),
                pair[0],
                pair[1],
            ),
        )
        ranking_value = _finite(
            rows[leg_index][f"q_weight{CODES[code_index]}"], "q_weight"
        )
        code_ranking_value = ranking_value
    return {
        "mechanism": mechanism,
        "delete_leg_index_zero_based": leg_index,
        "delete_match_id": str(rows[leg_index]["match_id"]),
        "delete_code_index_zero_based": code_index,
        "delete_code": CODES[code_index],
        "ranking_value": format(ranking_value, ".12f"),
        "code_ranking_value": format(code_ranking_value, ".12f"),
        "tie_rule": (
            "P=(p_min,leg_index)->(model_p,code_index); "
            "Q=(q_weight,leg_index,code_index); code order 3,1,0"
        ),
    }


def _stage2_rows(
    ordered_match_ids: Sequence[str], stage2_output: Mapping[str, object]
) -> tuple[list[list[float]], str | None, str]:
    _assert_outcome_unexposed(stage2_output)
    upstream_status = str(stage2_output.get("status"))
    if upstream_status == "NO_BET":
        return [], "STAGE2_NO_BET_ZERO_FLOW", "NO_BET"
    if upstream_status == "UNAVAILABLE":
        return [], "STAGE2_UNAVAILABLE_ZERO_FLOW", "UNAVAILABLE"
    if upstream_status != "ACTIVE":
        return [], "INVALID_STAGE2_STATUS", "UNAVAILABLE"
    supplied = stage2_output.get("per_match")
    if not isinstance(supplied, list) or len(supplied) != LEGS:
        return [], "INVALID_STAGE2_PER_MATCH_ROWS", "UNAVAILABLE"
    weights: list[list[float]] = []
    for expected_match, raw in zip(ordered_match_ids, supplied, strict=True):
        if not isinstance(raw, Mapping) or str(raw.get("match_id")) != str(expected_match):
            return [], "STAGE2_MATCH_ORDER_MISMATCH", "UNAVAILABLE"
        values = raw.get("direction_weight_3_1_0")
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            return [], "INVALID_STAGE2_WEIGHT_VECTOR", "UNAVAILABLE"
        try:
            parsed = [_finite(value, "direction_weight") for value in values]
        except ValueError:
            return [], "INVALID_STAGE2_WEIGHT_VECTOR", "UNAVAILABLE"
        if any(value < 0 for value in parsed) or not any(value > 0 for value in parsed):
            return [], "INVALID_STAGE2_WEIGHT_VECTOR", "UNAVAILABLE"
        weights.append(parsed)
    return weights, None, "ACTIVE"


def _normalized(values: Sequence[float]) -> list[str]:
    total = sum(value for value in values if value > 0)
    if total <= 0:
        raise ValueError("zero support leg")
    return [format(value / total if value > 0 else 0.0, ".12f") for value in values]


def _ticket_ordinals(weights: Sequence[Sequence[float]]) -> list[int]:
    ordinals: list[int] = []
    for ordinal in range(3**LEGS):
        value = ordinal
        indices = [0] * LEGS
        for leg in range(LEGS - 1, -1, -1):
            indices[leg] = value % 3
            value //= 3
        if all(weights[leg][indices[leg]] > 0 for leg in range(LEGS)):
            ordinals.append(ordinal)
    return ordinals


def compose_structural_delete(
    mechanism: str,
    ordered_match_ids: Sequence[str],
    stage2_output: Mapping[str, object],
    registry_by_match: Mapping[str, Mapping[str, object]],
    *,
    issue: str,
    stage1_output_sha256: str,
    stage2_output_sha256: str,
    derived_stage3_action_sha256: str,
) -> dict[str, object]:
    """Compose one exact structural zero mask and enumerate positive tickets."""

    issue_text = str(issue)
    stage1_identity = _require_sha256(
        stage1_output_sha256, "stage1_output_sha256"
    )
    stage2_identity = _require_sha256(
        stage2_output_sha256, "stage2_output_sha256"
    )
    action_identity = _require_sha256(
        derived_stage3_action_sha256, "derived_stage3_action_sha256"
    )
    replay_signature = stage3_replay_signature(
        issue=issue_text,
        stage1_output_sha256=stage1_identity,
        stage2_output_sha256=stage2_identity,
        derived_stage3_action_sha256=action_identity,
    )
    base = {
        "adapter_version": ADAPTER_VERSION,
        "mechanism": mechanism,
        "weight_source": "NA",
        "repeat_mode": mechanism,
        "replicate_mode": "DETERMINISTIC_SINGLETON",
        "native_M": NATIVE_STRUCTURAL_M,
        "issue": issue_text,
        "stage1_output_sha256": stage1_identity,
        "stage2_output_sha256": stage2_identity,
        "derived_stage3_action_sha256": action_identity,
        "ordered_match_ids": [str(value) for value in ordered_match_ids],
    }
    if mechanism not in MECHANISMS:
        raise ValueError(f"unknown structural mechanism: {mechanism}")
    rows, registry_reason = validate_structural_rows(
        ordered_match_ids, registry_by_match
    )
    if rows and str(rows[0]["issue"]) != issue_text:
        rows = []
        registry_reason = "STRUCTURAL_REGISTRY_TRACE_ISSUE_MISMATCH"
    weights, stage2_reason, stage2_status = _stage2_rows(
        ordered_match_ids, stage2_output
    )
    reason = registry_reason or stage2_reason
    if reason is not None:
        output = {
            **base,
            "status": "UNAVAILABLE" if registry_reason else stage2_status,
            "reason_code": reason,
            "requested_ticket_count": 0,
            "requested_stake_yuan": 0,
            "ticket_ordinal_set_sha256": canonical_hash([]),
            "per_match": [],
            "counts": tuple([0] * (3**LEGS)),
        }
        output["stage3_replay_signature_sha256"] = replay_signature
        output["structural_output_identity_sha256"] = canonical_hash(
            {
                key: value
                for key, value in output.items()
                if key not in {"counts", "structural_output_identity_sha256"}
            }
        )
        return output

    deletion = derive_structural_delete(mechanism, rows)
    leg = int(deletion["delete_leg_index_zero_based"])
    code = int(deletion["delete_code_index_zero_based"])
    already_absent = weights[leg][code] <= 0
    if not already_absent:
        weights[leg][code] = 0.0
    ordinals = _ticket_ordinals(weights)
    counts = [0] * (3**LEGS)
    for ordinal in ordinals:
        counts[ordinal] = 1
    per_match = [
        {
            "leg_index_zero_based": index,
            "match_id": str(match_id),
            "final_weight_3_1_0": _normalized(values),
            "allowed_codes": [
                CODES[code_index]
                for code_index, value in enumerate(values)
                if value > 0
            ],
            "structural_registry_row_sha256": str(
                rows[index]["structural_registry_row_sha256"]
            ),
        }
        for index, (match_id, values) in enumerate(
            zip(ordered_match_ids, weights, strict=True)
        )
    ]
    output = {
        **base,
        "status": "ACTIVE",
        "reason_code": (
            "STRUCTURAL_DELETE_ALREADY_ABSENT"
            if already_absent
            else "STRUCTURAL_DELETE_ADDITIONAL_ZERO_MASK"
        ),
        **deletion,
        "requested_ticket_count": len(ordinals),
        "requested_stake_yuan": len(ordinals) * UNIT_STAKE_YUAN,
        "ticket_ordinal_set_sha256": canonical_hash(ordinals),
        "per_match": per_match,
        "counts": tuple(counts),
    }
    output["stage3_replay_signature_sha256"] = replay_signature
    output["structural_output_identity_sha256"] = canonical_hash(
        {
            key: value
            for key, value in output.items()
            if key not in {"counts", "structural_output_identity_sha256"}
        }
    )
    return output
