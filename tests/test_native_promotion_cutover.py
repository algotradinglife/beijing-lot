from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.adhoc_publication_attestation import sign_statement
from src.native_active_artifact import csv_bytes, file_hash, write_native_artifact
from src.native_promotion_cutover import (
    NativePromotionCutoverError,
    canonical_selection_codes_sha256,
    rollback_target_from_cutover_receipt,
    validate_native_promotion_cutover_receipt,
)
from src.structured_input_receipt import receipt_path
from src.decision_api import app as appmod


ISSUE = "26078"
FIELDS = ["issue", "match_idx", "decision_variant_id", "active_arm", "selection_codes"]


def _cutover_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "project"
    active_root = root / "results" / "structured_decision_chain_active"
    content = csv_bytes(
        [{"issue": ISSUE, "match_idx": 1, "decision_variant_id": "active_v3.3.3", "active_arm": "active_v3.3.3", "selection_codes": "3"}],
        fieldnames=FIELDS,
    )
    csv_path, _receipt, native = write_native_artifact(
        output_root=active_root,
        issue=ISSUE,
        generated_at=datetime(2026, 7, 27, 4, tzinfo=timezone.utc),
        csv_content=content,
        source={"fixture": "cutover"},
    )
    private = Ed25519PrivateKey.generate()
    private_path = root / "authority.pem"
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    registry_path = root / "config" / "keys.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": "adhoc_publication_key_registry_v1",
                "environment": "test",
                "keys": [{
                    "key_id": "cutover-test-key",
                    "status": "active",
                    "usage": "test",
                    "public_key_base64": base64.b64encode(
                        private.public_key().public_bytes(
                            serialization.Encoding.Raw,
                            serialization.PublicFormat.Raw,
                        )
                    ).decode("ascii"),
                }],
            }
        ),
        encoding="utf-8",
    )
    statement = {
        "formal_binding_schema_version": "adhoc_formal_selection_binding_v2",
        "decision_variant_id": "active_v3.3.3",
        "formal_selection_column": "selection_codes",
        "formal_structured_csv_sha256": file_hash(csv_path),
        "formal_structured_receipt_sha256": file_hash(receipt_path(csv_path)),
        "formal_selection_codes_sha256": canonical_selection_codes_sha256(native["rows"]),
    }
    attestation_path = root / "results" / "adhoc" / "publication_attestation.json"
    attestation_path.parent.mkdir(parents=True, exist_ok=True)
    attestation_path.write_text(
        json.dumps(sign_statement(private_key_path=private_path, key_id="cutover-test-key", statement=statement)),
        encoding="utf-8",
    )
    cutover_path = root / "results" / "structured_decision_chain_active" / "cutover_receipt.json"
    cutover_path.write_text(
        json.dumps(
            {
                "schema_version": "native_promotion_cutover_receipt_v1",
                "issue": ISSUE,
                "native_csv_path": str(csv_path.relative_to(root)),
                "native_csv_sha256": file_hash(csv_path),
                "native_receipt_sha256": file_hash(receipt_path(csv_path)),
                "formal_selection_codes_sha256": canonical_selection_codes_sha256(native["rows"]),
                "native_artifact_identity": f"active_v3.3.3:{ISSUE}:{file_hash(csv_path)}",
                "native_generation_identity": native["native_generation_identity"],
                "previous_native_artifact_identity": "",
                "attestation_key_id": "cutover-test-key",
                "attestation_path": str(attestation_path.relative_to(root)),
                "attestation_sha256": file_hash(attestation_path),
            }
        ),
        encoding="utf-8",
    )
    return root, active_root, registry_path, cutover_path


def test_cutover_receipt_binds_native_bytes_and_v2_attestation(tmp_path: Path) -> None:
    root, active_root, key_registry, cutover = _cutover_fixture(tmp_path)

    verified = validate_native_promotion_cutover_receipt(
        cutover,
        project_root=root,
        active_root=active_root,
        key_registry_path=key_registry,
    )

    assert verified["native_artifact_identity"].startswith("active_v3.3.3:26078:")
    assert verified["rollback_available"] is False
    with pytest.raises(NativePromotionCutoverError, match="rollback target is unavailable"):
        rollback_target_from_cutover_receipt(verified)


def test_cutover_receipt_rejects_attestation_or_native_identity_substitution(tmp_path: Path) -> None:
    root, active_root, key_registry, cutover = _cutover_fixture(tmp_path)
    payload = json.loads(cutover.read_text(encoding="utf-8"))
    payload["native_artifact_identity"] = "active_v3.3.3:26078:" + "0" * 64
    cutover.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(NativePromotionCutoverError, match="artifact identity mismatch"):
        validate_native_promotion_cutover_receipt(
            cutover,
            project_root=root,
            active_root=active_root,
            key_registry_path=key_registry,
        )


def test_cutover_receipt_rejects_native_path_outside_active_root(tmp_path: Path) -> None:
    root, active_root, key_registry, cutover = _cutover_fixture(tmp_path)
    payload = json.loads(cutover.read_text(encoding="utf-8"))
    payload["native_csv_path"] = "outside/structured_active_26078.csv"
    cutover.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(NativePromotionCutoverError, match="escapes structured_active_dir"):
        validate_native_promotion_cutover_receipt(
            cutover,
            project_root=root,
            active_root=active_root,
            key_registry_path=key_registry,
        )


def test_cutover_pointer_ignores_newer_unapproved_artifact_and_fails_when_pinned_bytes_corrupt(tmp_path: Path) -> None:
    root, active_root, key_registry, cutover = _cutover_fixture(tmp_path)
    payload = json.loads(cutover.read_text(encoding="utf-8"))
    pinned_csv = root / payload["native_csv_path"]
    newer_content = csv_bytes(
        [{"issue": ISSUE, "match_idx": 1, "decision_variant_id": "active_v3.3.3", "active_arm": "active_v3.3.3", "selection_codes": "1"}],
        fieldnames=FIELDS,
    )
    newer_csv, _receipt, _native = write_native_artifact(
        output_root=active_root,
        issue=ISSUE,
        generated_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
        csv_content=newer_content,
        source={"fixture": "unapproved-newer"},
    )

    verified = validate_native_promotion_cutover_receipt(
        cutover,
        project_root=root,
        active_root=active_root,
        key_registry_path=key_registry,
    )
    assert verified["native_csv_path"] == pinned_csv.resolve()
    assert verified["native_csv_path"] != newer_csv.resolve()

    pinned_csv.write_bytes(pinned_csv.read_bytes().replace(b",3\n", b",0\n"))
    with pytest.raises(NativePromotionCutoverError, match="native artifact is invalid"):
        validate_native_promotion_cutover_receipt(
            cutover,
            project_root=root,
            active_root=active_root,
            key_registry_path=key_registry,
        )


def test_rollback_requires_an_explicit_native_predecessor_identity(tmp_path: Path) -> None:
    root, active_root, key_registry, cutover = _cutover_fixture(tmp_path)
    payload = json.loads(cutover.read_text(encoding="utf-8"))
    payload["previous_native_artifact_identity"] = "active_v3.3.3:26078:" + "a" * 64
    cutover.write_text(json.dumps(payload), encoding="utf-8")

    verified = validate_native_promotion_cutover_receipt(
        cutover,
        project_root=root,
        active_root=active_root,
        key_registry_path=key_registry,
    )
    assert rollback_target_from_cutover_receipt(verified) == "active_v3.3.3:26078:" + "a" * 64


def test_operational_native_resolution_fails_closed_without_a_registry_pointer(tmp_path: Path) -> None:
    release = {
        "promotion": {"native_cutover_receipts": {}},
        "artifacts": {"structured_active_dir": str(tmp_path / "active")},
    }

    path, verified, error = appmod._pinned_native_cutover_artifact(ISSUE, release)

    assert path is None
    assert verified is None
    assert error == "cutover_receipt_missing"


def test_operational_native_resolution_rejects_a_pointer_for_another_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, active_root, key_registry, cutover = _cutover_fixture(tmp_path)
    monkeypatch.setattr(appmod, "PROJECT_ROOT", root)
    monkeypatch.setattr(appmod, "ADHOC_PUBLICATION_KEY_REGISTRY", key_registry)
    release = {
        "promotion": {
            "native_cutover_receipts": {
                "26079": {
                    "mode": "active",
                    "current_receipt_path": str(cutover),
                }
            }
        },
        "artifacts": {"structured_active_dir": str(active_root)},
    }

    path, verified, error = appmod._pinned_native_cutover_artifact("26079", release)

    assert path is None
    assert verified is None
    assert error == "cutover_receipt_issue_mismatch"


def test_adhoc_formal_input_does_not_fall_back_without_a_cutover_pointer(
    tmp_path: Path,
) -> None:
    release = {
        "promotion": {"native_cutover_receipts": {}},
        "artifacts": {
            "structured_active_dir": str(tmp_path / "active"),
            "structured_shadow_dir": str(tmp_path / "shadow"),
        },
    }

    rows, metadata = appmod._adhoc_formal_structured_input(
        issue=ISSUE,
        expected_indices={1},
        request_clock=datetime(2026, 7, 27, tzinfo=timezone.utc),
        release=release,
    )

    assert rows == {}
    assert metadata["status"] == "UNAVAILABLE_FORMAL_INPUT"
    assert metadata["decision_variant_id"] == "active_v3.3.3"
    assert metadata["rejected_candidates"] == ["cutover_receipt_missing"]


def test_runtime_rollback_accepts_only_current_receipt_predecessor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current_path = tmp_path / "current.json"
    predecessor_path = tmp_path / "predecessor.json"
    arbitrary_path = tmp_path / "arbitrary.json"
    predecessor_identity = "active_v3.3.3:26078:" + "a" * 64
    current = {
        "receipt": {"issue": ISSUE, "previous_native_artifact_identity": predecessor_identity},
        "native_artifact_identity": "active_v3.3.3:26078:" + "b" * 64,
        "native_csv_path": tmp_path / "current.csv",
    }
    predecessor = {
        "receipt": {"issue": ISSUE, "previous_native_artifact_identity": ""},
        "native_artifact_identity": predecessor_identity,
        "native_csv_path": tmp_path / "predecessor.csv",
    }
    arbitrary = {**predecessor, "native_artifact_identity": "active_v3.3.3:26078:" + "c" * 64}
    verified_by_path = {current_path: current, predecessor_path: predecessor, arbitrary_path: arbitrary}
    monkeypatch.setattr(
        appmod,
        "validate_native_promotion_cutover_receipt",
        lambda path, **_kwargs: verified_by_path[path],
    )
    release = {
        "artifacts": {"structured_active_dir": str(tmp_path / "active")},
        "promotion": {
            "native_cutover_receipts": {
                ISSUE: {
                    "mode": "rollback",
                    "current_receipt_path": str(current_path),
                    "rollback_target_receipt_path": str(predecessor_path),
                }
            }
        },
    }

    resolved, _verified, error = appmod._pinned_native_cutover_artifact(ISSUE, release)
    assert resolved == predecessor["native_csv_path"]
    assert error == ""

    release["promotion"]["native_cutover_receipts"][ISSUE]["rollback_target_receipt_path"] = str(arbitrary_path)  # type: ignore[index]
    resolved, verified, error = appmod._pinned_native_cutover_artifact(ISSUE, release)
    assert resolved is None
    assert verified is None
    assert error == "rollback_target_is_not_current_receipt_predecessor"
