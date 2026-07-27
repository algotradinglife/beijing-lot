from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.adhoc_publication_attestation import (
    PublicationAttestationError,
    sign_statement,
    verify_attestation,
)


def _private_key(path: Path) -> Ed25519PrivateKey:
    key = Ed25519PrivateKey.generate()
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return key


def _registry(
    path: Path,
    *,
    key: Ed25519PrivateKey,
    key_id: str = "reviewed-test-key",
    status: str = "active",
    environment: str = "test",
    usage: str = "test",
) -> None:
    public_bytes = key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": "adhoc_publication_key_registry_v1",
                "environment": environment,
                "keys": [
                    {
                        "key_id": key_id,
                        "status": status,
                        "usage": usage,
                        "public_key_base64": base64.b64encode(public_bytes).decode(
                            "ascii"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_reviewed_key_signs_and_pinned_registry_verifies(tmp_path: Path) -> None:
    private_path = tmp_path / "authority.pem"
    registry_path = tmp_path / "registry.json"
    key = _private_key(private_path)
    _registry(registry_path, key=key)
    statement = {
        "unsigned_package_content_sha256": "a" * 64,
        "request_id": "request-1",
    }

    attestation = sign_statement(
        private_key_path=private_path,
        key_id="reviewed-test-key",
        statement=statement,
    )

    verify_attestation(
        attestation=attestation,
        expected_statement=statement,
        registry_path=registry_path,
    )
    assert "private_key" not in json.dumps(attestation)
    assert "public_key" not in json.dumps(attestation)


def test_package_supplied_attacker_key_is_ignored(tmp_path: Path) -> None:
    reviewed_private_path = tmp_path / "reviewed.pem"
    attacker_private_path = tmp_path / "attacker.pem"
    registry_path = tmp_path / "registry.json"
    reviewed_key = _private_key(reviewed_private_path)
    attacker_key = _private_key(attacker_private_path)
    _registry(registry_path, key=reviewed_key)
    statement = {"unsigned_package_content_sha256": "b" * 64}
    attestation = sign_statement(
        private_key_path=attacker_private_path,
        key_id="attacker-key",
        statement=statement,
    )
    attestation["public_key_base64"] = base64.b64encode(
        attacker_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    ).decode("ascii")

    with pytest.raises(
        PublicationAttestationError, match="unknown or revoked"
    ):
        verify_attestation(
            attestation=attestation,
            expected_statement=statement,
            registry_path=registry_path,
        )


@pytest.mark.parametrize("status", ["retired", "revoked"])
def test_non_active_registry_key_fails_closed(
    tmp_path: Path, status: str
) -> None:
    private_path = tmp_path / "authority.pem"
    registry_path = tmp_path / "registry.json"
    key = _private_key(private_path)
    _registry(registry_path, key=key, status=status)
    statement = {"unsigned_package_content_sha256": "c" * 64}
    attestation = sign_statement(
        private_key_path=private_path,
        key_id="reviewed-test-key",
        statement=statement,
    )

    with pytest.raises(PublicationAttestationError, match="not active"):
        verify_attestation(
            attestation=attestation,
            expected_statement=statement,
            registry_path=registry_path,
        )


def test_test_key_cannot_be_smuggled_into_production_registry(
    tmp_path: Path,
) -> None:
    private_path = tmp_path / "authority.pem"
    registry_path = tmp_path / "registry.json"
    key = _private_key(private_path)
    _registry(
        registry_path,
        key=key,
        environment="production",
        usage="test",
    )
    statement = {"unsigned_package_content_sha256": "d" * 64}
    attestation = sign_statement(
        private_key_path=private_path,
        key_id="reviewed-test-key",
        statement=statement,
    )

    with pytest.raises(
        PublicationAttestationError, match="usage does not match"
    ):
        verify_attestation(
            attestation=attestation,
            expected_statement=statement,
            registry_path=registry_path,
        )


def test_altered_signature_and_statement_fail_closed(tmp_path: Path) -> None:
    private_path = tmp_path / "authority.pem"
    registry_path = tmp_path / "registry.json"
    key = _private_key(private_path)
    _registry(registry_path, key=key)
    statement = {"unsigned_package_content_sha256": "e" * 64}
    attestation = sign_statement(
        private_key_path=private_path,
        key_id="reviewed-test-key",
        statement=statement,
    )

    altered_signature = dict(attestation)
    altered_signature["signature_base64"] = base64.b64encode(b"x" * 64).decode(
        "ascii"
    )
    with pytest.raises(PublicationAttestationError, match="signature is invalid"):
        verify_attestation(
            attestation=altered_signature,
            expected_statement=statement,
            registry_path=registry_path,
        )

    altered_statement = {
        "unsigned_package_content_sha256": "f" * 64,
    }
    with pytest.raises(
        PublicationAttestationError, match="does not bind package content"
    ):
        verify_attestation(
            attestation=attestation,
            expected_statement=altered_statement,
            registry_path=registry_path,
        )


def test_missing_private_key_reports_authority_unavailable(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        PublicationAttestationError, match="PUBLICATION_AUTHORITY_UNAVAILABLE"
    ):
        sign_statement(
            private_key_path=tmp_path / "missing.pem",
            key_id="reviewed-test-key",
            statement={"unsigned_package_content_sha256": "0" * 64},
        )
