"""Immutable native artifacts for the formal ``active_v3.3.3`` contract."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.structured_input_receipt import receipt_path, verify_receipt, write_receipt


NATIVE_ARTIFACT_SCHEMA_VERSION = "structured_active_artifact_v1"
NATIVE_DECISION_VARIANT_ID = "active_v3.3.3"
NATIVE_CSV_PREFIX = "structured_active_"


class NativeArtifactError(ValueError):
    """A native artifact is malformed, mutable, or not independently bound."""


def _validated_issue(issue: str) -> str:
    """Return a numeric issue identifier safe for a filename and identity."""

    if not isinstance(issue, str) or not re.fullmatch(r"[0-9]+", issue):
        raise NativeArtifactError("native issue identifier is unsafe")
    return issue


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def native_generation_id(*, issue: str, generated_at: datetime, csv_sha256: str) -> str:
    issue = _validated_issue(issue)
    observed = generated_at.astimezone(timezone.utc)
    clock = observed.strftime("%Y%m%dT%H%M%S%fZ")
    return f"{NATIVE_DECISION_VARIANT_ID}:{issue}:{clock}:{csv_sha256}"


def native_path_component(*, issue: str, generated_at: datetime, csv_sha256: str) -> str:
    issue = _validated_issue(issue)
    observed = generated_at.astimezone(timezone.utc)
    clock = observed.strftime("%Y%m%dT%H%M%S%fZ")
    return f"{issue}_{clock}_{csv_sha256}_{NATIVE_DECISION_VARIANT_ID}"


def csv_bytes(records: Iterable[dict[str, Any]], *, fieldnames: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    return stream.getvalue().encode("utf-8")


def write_native_artifact(
    *,
    output_root: Path,
    issue: str,
    generated_at: datetime,
    csv_content: bytes,
    source: dict[str, Any],
) -> tuple[Path, Path, dict[str, Any]]:
    """Create one content-addressed native artifact; never overwrite a path."""

    issue = _validated_issue(issue)
    csv_sha256 = hashlib.sha256(csv_content).hexdigest()
    identity = native_generation_id(
        issue=issue, generated_at=generated_at, csv_sha256=csv_sha256
    )
    component = native_path_component(
        issue=issue, generated_at=generated_at, csv_sha256=csv_sha256
    )
    resolved_root = output_root.resolve()
    target_dir = resolved_root / component
    try:
        target_dir.resolve().relative_to(resolved_root)
    except ValueError as exc:
        raise NativeArtifactError("native artifact path escapes output root") from exc
    csv_path = target_dir / f"{NATIVE_CSV_PREFIX}{issue}.csv"
    receipt = receipt_path(csv_path)
    output_root.mkdir(parents=True, exist_ok=True)
    try:
        target_dir.mkdir()
    except FileExistsError as exc:
        # Same identity may be retried, but any incomplete or byte-different
        # directory is evidence of a collision and must remain untouched.
        if not csv_path.is_file() or not receipt.is_file() or csv_path.read_bytes() != csv_content:
            raise NativeArtifactError("native artifact path collision") from exc
        verified = validate_native_artifact(csv_path, issue=issue)
        if verified["native_generation_identity"] != identity:
            raise NativeArtifactError("native artifact identity collision")
        return csv_path, receipt, verified

    try:
        with csv_path.open("xb") as stream:
            stream.write(csv_content)
            stream.flush()
            os.fsync(stream.fileno())
        receipt = write_receipt(
            csv_path,
            issue=issue,
            generated_at=generated_at,
            source={
                **source,
                "native_artifact_schema_version": NATIVE_ARTIFACT_SCHEMA_VERSION,
                "native_generation_identity": identity,
                "native_generation_path_component": component,
                "native_csv_sha256": csv_sha256,
            },
        )
        return csv_path, receipt, validate_native_artifact(csv_path, issue=issue)
    except BaseException:
        # Never delete a partially-created directory: it is collision evidence
        # and must not silently become reusable under the same identity.
        raise


def validate_native_artifact(path: Path, *, issue: str) -> dict[str, Any]:
    """Verify bytes, immutable identity, and v2-native CSV semantics."""

    issue = _validated_issue(issue)
    if path.name != f"{NATIVE_CSV_PREFIX}{issue}.csv":
        raise NativeArtifactError("native CSV filename does not bind issue")
    try:
        receipt = verify_receipt(path, receipt_path(path), issue=issue)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise NativeArtifactError("native artifact receipt is invalid") from exc
    source = receipt.get("source")
    if not isinstance(source, dict):
        raise NativeArtifactError("native artifact receipt source is missing")
    csv_sha256 = file_hash(path)
    if source.get("native_artifact_schema_version") != NATIVE_ARTIFACT_SCHEMA_VERSION:
        raise NativeArtifactError("native artifact schema is invalid")
    if str(source.get("native_csv_sha256") or "") != csv_sha256:
        raise NativeArtifactError("native artifact receipt hash mismatch")
    component = str(source.get("native_generation_path_component") or "")
    if path.parent.name != component:
        raise NativeArtifactError("native artifact path identity mismatch")
    generated_at = receipt.get("generated_at")
    if not isinstance(generated_at, datetime):
        raise NativeArtifactError("native artifact receipt clock is invalid")
    expected_identity = native_generation_id(
        issue=issue, generated_at=generated_at, csv_sha256=csv_sha256
    )
    if str(source.get("native_generation_identity") or "") != expected_identity:
        raise NativeArtifactError("native artifact generation identity mismatch")
    expected_component = native_path_component(
        issue=issue, generated_at=generated_at, csv_sha256=csv_sha256
    )
    if component != expected_component:
        raise NativeArtifactError("native artifact generation path is ambiguous")

    rows: dict[int, dict[str, Any]] = {}
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            required = {
                "issue",
                "match_idx",
                "decision_variant_id",
                "active_arm",
                "selection_codes",
            }
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise NativeArtifactError("native CSV lacks required v2 columns")
            if {"shadow_arm", "shadow_selection_codes"}.intersection(reader.fieldnames):
                raise NativeArtifactError("native CSV contains legacy shadow columns")
            for row in reader:
                if str(row.get("issue") or "") != issue:
                    raise NativeArtifactError("native CSV row issue mismatch")
                if str(row.get("decision_variant_id") or "") != NATIVE_DECISION_VARIANT_ID:
                    raise NativeArtifactError("native CSV variant is not active_v3.3.3")
                if str(row.get("active_arm") or "") != NATIVE_DECISION_VARIANT_ID:
                    raise NativeArtifactError("native CSV arm is not active")
                try:
                    idx = int(row.get("match_idx") or 0)
                except (TypeError, ValueError) as exc:
                    raise NativeArtifactError("native CSV match index is invalid") from exc
                if idx <= 0 or idx in rows:
                    raise NativeArtifactError("native CSV match index is duplicated")
                codes = [part for part in str(row.get("selection_codes") or "").split("+") if part]
                if not codes or any(code not in {"3", "1", "0"} for code in codes):
                    raise NativeArtifactError("native CSV selection codes are invalid")
                if len(codes) != len(set(codes)):
                    raise NativeArtifactError("native CSV selection codes are duplicated")
                rows[idx] = dict(row)
    except OSError as exc:
        raise NativeArtifactError("native CSV cannot be read") from exc
    if not rows:
        raise NativeArtifactError("native CSV has no rows")
    return {
        "rows": rows,
        "receipt": receipt,
        "native_generation_identity": expected_identity,
        "csv_sha256": csv_sha256,
        "receipt_sha256": file_hash(receipt_path(path)),
    }
