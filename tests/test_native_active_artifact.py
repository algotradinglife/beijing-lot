from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.native_active_artifact import (
    NativeArtifactError,
    csv_bytes,
    validate_native_artifact,
    write_native_artifact,
)


ISSUE = "99156"
NOW = datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc)
FIELDS = [
    "issue",
    "match_idx",
    "decision_variant_id",
    "active_arm",
    "selection_codes",
]


def _records(*, code: str = "3") -> list[dict[str, object]]:
    return [
        {
            "issue": ISSUE,
            "match_idx": 1,
            "decision_variant_id": "active_v3.3.3",
            "active_arm": "active_v3.3.3",
            "selection_codes": code,
        }
    ]


def test_native_artifact_is_content_addressed_and_retry_safe(tmp_path) -> None:
    content = csv_bytes(_records(), fieldnames=FIELDS)
    csv_path, receipt, verified = write_native_artifact(
        output_root=tmp_path,
        issue=ISSUE,
        generated_at=NOW,
        csv_content=content,
        source={"fixture": "native"},
    )

    assert receipt.is_file()
    assert verified["rows"][1]["selection_codes"] == "3"
    assert ":99156:20260727T040000000000Z:" in verified["native_generation_identity"]
    retry_csv, retry_receipt, retry_verified = write_native_artifact(
        output_root=tmp_path,
        issue=ISSUE,
        generated_at=NOW,
        csv_content=content,
        source={"fixture": "native"},
    )
    assert (retry_csv, retry_receipt) == (csv_path, receipt)
    assert retry_verified["native_generation_identity"] == verified["native_generation_identity"]


def test_existing_native_path_with_different_bytes_fails_closed(tmp_path) -> None:
    content = csv_bytes(_records(), fieldnames=FIELDS)
    csv_path, _receipt, _verified = write_native_artifact(
        output_root=tmp_path,
        issue=ISSUE,
        generated_at=NOW,
        csv_content=content,
        source={"fixture": "native"},
    )
    csv_path.write_bytes(content.replace(b",3\n", b",1\n"))

    with pytest.raises(NativeArtifactError, match="path collision"):
        write_native_artifact(
            output_root=tmp_path,
            issue=ISSUE,
            generated_at=NOW,
            csv_content=content,
            source={"fixture": "native"},
        )


def test_native_validator_rejects_legacy_shadow_columns(tmp_path) -> None:
    legacy_fields = [*FIELDS, "shadow_selection_codes"]
    with pytest.raises(NativeArtifactError, match="legacy shadow columns"):
        write_native_artifact(
            output_root=tmp_path,
            issue=ISSUE,
            generated_at=NOW,
            csv_content=csv_bytes(
                [{**_records()[0], "shadow_selection_codes": "3"}],
                fieldnames=legacy_fields,
            ),
            source={"fixture": "bad-legacy"},
        )


def test_native_validator_rejects_mutated_receipt_bytes(tmp_path) -> None:
    content = csv_bytes(_records(), fieldnames=FIELDS)
    csv_path, receipt, _verified = write_native_artifact(
        output_root=tmp_path,
        issue=ISSUE,
        generated_at=NOW,
        csv_content=content,
        source={"fixture": "native"},
    )
    receipt.write_bytes(receipt.read_bytes().replace(b"structured_active_artifact_v1", b"structured_active_artifact_bad"))

    with pytest.raises(NativeArtifactError, match="receipt is invalid"):
        validate_native_artifact(csv_path, issue=ISSUE)
