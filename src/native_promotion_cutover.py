"""Fail-closed evidence for the native ``active_v3.3.3`` registry cutover."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from src.adhoc_publication_attestation import (
    PublicationAttestationError,
    verify_attestation,
)
from src.native_active_artifact import (
    NATIVE_DECISION_VARIANT_ID,
    NativeArtifactError,
    file_hash,
    validate_native_artifact,
)
from src.structured_input_receipt import receipt_path


CUTOVER_RECEIPT_SCHEMA_VERSION = "native_promotion_cutover_receipt_v1"
FORMAL_BINDING_SCHEMA_VERSION = "adhoc_formal_selection_binding_v2"


class NativePromotionCutoverError(ValueError):
    """The native promotion evidence cannot authorize the registry cutover."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_selection_codes_sha256(rows: dict[int, dict[str, Any]]) -> str:
    """Digest the executable native selection map, ordered by match index."""

    canonical_rows = []
    for match_idx, row in sorted(rows.items()):
        codes = [part for part in str(row.get("selection_codes") or "").split("+") if part]
        canonical_rows.append({"match_idx": match_idx, "selection_codes": codes})
    return _sha256(_canonical(canonical_rows))


def _safe_project_path(value: object, *, project_root: Path, label: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise NativePromotionCutoverError(f"cutover receipt {label} is missing")
    candidate = Path(text)
    path = candidate if candidate.is_absolute() else project_root / candidate
    try:
        resolved = path.resolve()
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise NativePromotionCutoverError(
            f"cutover receipt {label} escapes project root"
        ) from exc
    return resolved


def _expected_artifact_identity(*, issue: str, csv_sha256: str) -> str:
    return f"{NATIVE_DECISION_VARIANT_ID}:{issue}:{csv_sha256}"


def validate_native_promotion_cutover_receipt(
    path: Path,
    *,
    project_root: Path,
    active_root: Path,
    key_registry_path: Path,
) -> dict[str, Any]:
    """Validate the reviewed cutover pointer and all artifacts it binds.

    The receipt is intentionally independent of the generic CSV receipt.  It
    binds registry promotion to a particular native artifact and a pinned-key
    publication attestation; without it callers must treat native resolution
    as unavailable rather than borrowing a shadow artifact.
    """

    receipt_file = _safe_project_path(path, project_root=project_root, label="path")
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativePromotionCutoverError("cutover receipt is unreadable") from exc
    if not isinstance(receipt, dict) or receipt.get("schema_version") != CUTOVER_RECEIPT_SCHEMA_VERSION:
        raise NativePromotionCutoverError("cutover receipt schema is invalid")

    issue = str(receipt.get("issue") or "")
    if not re.fullmatch(r"[0-9]+", issue):
        raise NativePromotionCutoverError("cutover receipt issue is invalid")
    csv_path = _safe_project_path(
        receipt.get("native_csv_path"), project_root=project_root, label="native_csv_path"
    )
    try:
        csv_path.relative_to(active_root.resolve())
    except ValueError as exc:
        raise NativePromotionCutoverError(
            "cutover native CSV escapes structured_active_dir"
        ) from exc
    try:
        native = validate_native_artifact(csv_path, issue=issue)
    except (NativeArtifactError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise NativePromotionCutoverError("cutover native artifact is invalid") from exc

    csv_sha256 = file_hash(csv_path)
    receipt_sha256 = file_hash(receipt_path(csv_path))
    if str(receipt.get("native_csv_sha256") or "") != csv_sha256:
        raise NativePromotionCutoverError("cutover native CSV hash mismatch")
    if str(receipt.get("native_receipt_sha256") or "") != receipt_sha256:
        raise NativePromotionCutoverError("cutover native receipt hash mismatch")
    if str(receipt.get("formal_selection_codes_sha256") or "") != canonical_selection_codes_sha256(native["rows"]):
        raise NativePromotionCutoverError("cutover formal selection digest mismatch")
    expected_identity = _expected_artifact_identity(issue=issue, csv_sha256=csv_sha256)
    if str(receipt.get("native_artifact_identity") or "") != expected_identity:
        raise NativePromotionCutoverError("cutover native artifact identity mismatch")
    if str(receipt.get("native_generation_identity") or "") != str(native["native_generation_identity"]):
        raise NativePromotionCutoverError("cutover native generation identity mismatch")

    previous = str(receipt.get("previous_native_artifact_identity") or "")
    if previous and not re.fullmatch(
        rf"{re.escape(NATIVE_DECISION_VARIANT_ID)}:{re.escape(issue)}:[0-9a-f]{{64}}", previous
    ):
        raise NativePromotionCutoverError("cutover previous native identity is invalid")

    attestation_path = _safe_project_path(
        receipt.get("attestation_path"), project_root=project_root, label="attestation_path"
    )
    if str(receipt.get("attestation_sha256") or "") != file_hash(attestation_path):
        raise NativePromotionCutoverError("cutover attestation hash mismatch")
    try:
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativePromotionCutoverError("cutover attestation is unreadable") from exc
    statement = attestation.get("statement") if isinstance(attestation, dict) else None
    if not isinstance(statement, dict):
        raise NativePromotionCutoverError("cutover attestation statement is missing")
    if str(receipt.get("attestation_key_id") or "") != str(attestation.get("key_id") or ""):
        raise NativePromotionCutoverError("cutover attestation key mismatch")
    try:
        verify_attestation(
            attestation=attestation,
            expected_statement=statement,
            registry_path=key_registry_path,
        )
    except PublicationAttestationError as exc:
        raise NativePromotionCutoverError("cutover attestation is invalid") from exc
    required_statement = {
        "formal_binding_schema_version": FORMAL_BINDING_SCHEMA_VERSION,
        "decision_variant_id": NATIVE_DECISION_VARIANT_ID,
        "formal_selection_column": "selection_codes",
        "formal_structured_csv_sha256": csv_sha256,
        "formal_structured_receipt_sha256": receipt_sha256,
        "formal_selection_codes_sha256": canonical_selection_codes_sha256(native["rows"]),
    }
    if any(statement.get(key) != value for key, value in required_statement.items()):
        raise NativePromotionCutoverError("cutover attestation does not bind native v2 input")
    return {
        "receipt": receipt,
        "receipt_path": receipt_file,
        "native_csv_path": csv_path,
        "native_artifact_identity": expected_identity,
        "native_generation_identity": native["native_generation_identity"],
        "rollback_available": bool(previous),
    }


def rollback_target_from_cutover_receipt(verified: dict[str, Any]) -> str:
    """Return the reviewed predecessor, refusing shadow or empty rollbacks."""

    receipt = verified.get("receipt") if isinstance(verified, dict) else None
    previous = str(receipt.get("previous_native_artifact_identity") or "") if isinstance(receipt, dict) else ""
    if not previous:
        raise NativePromotionCutoverError("native rollback target is unavailable; fail closed")
    return previous
