"""Pinned-key Ed25519 attestations for operational adhoc packages.

Package hashes make a directory self-consistent.  They do not identify the
authority that is allowed to publish it.  This module supplies that separate
authority proof; the private key is API-service-only and is never serialized
into a package.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature


ATTESTATION_SCHEMA_VERSION = "adhoc_publication_attestation_v1"
KEY_REGISTRY_SCHEMA_VERSION = "adhoc_publication_key_registry_v1"


class PublicationAttestationError(ValueError):
    """The operational publication authority is missing or invalid."""


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _registry_key(registry_path: Path, key_id: str) -> dict[str, Any]:
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationAttestationError("publication key registry is unavailable") from exc
    if registry.get("schema_version") != KEY_REGISTRY_SCHEMA_VERSION:
        raise PublicationAttestationError("publication key registry schema is invalid")
    for item in registry.get("keys", []):
        if isinstance(item, dict) and item.get("key_id") == key_id:
            if item.get("status") != "active":
                raise PublicationAttestationError("publication key is not active")
            return item
    raise PublicationAttestationError("publication key is unknown or revoked")


def sign_statement(
    *, private_key_path: Path, key_id: str, statement: dict[str, Any]
) -> dict[str, Any]:
    try:
        private_key = serialization.load_pem_private_key(
            private_key_path.read_bytes(), password=None
        )
    except (OSError, ValueError, TypeError) as exc:
        raise PublicationAttestationError("PUBLICATION_AUTHORITY_UNAVAILABLE") from exc
    if not isinstance(private_key, Ed25519PrivateKey):
        raise PublicationAttestationError("publication private key is not Ed25519")
    return {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "key_id": key_id,
        "statement": statement,
        "signature_base64": base64.b64encode(private_key.sign(canonical(statement))).decode("ascii"),
    }


def verify_attestation(
    *, attestation: object, expected_statement: dict[str, Any], registry_path: Path
) -> None:
    if not isinstance(attestation, dict):
        raise PublicationAttestationError("operational package lacks publication attestation")
    if attestation.get("schema_version") != ATTESTATION_SCHEMA_VERSION:
        raise PublicationAttestationError("publication attestation schema is invalid")
    if attestation.get("statement") != expected_statement:
        raise PublicationAttestationError("publication attestation statement does not bind package content")
    key = _registry_key(registry_path, str(attestation.get("key_id") or ""))
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(str(key.get("public_key_base64") or ""), validate=True)
        )
        signature = base64.b64decode(
            str(attestation.get("signature_base64") or ""), validate=True
        )
        public_key.verify(signature, canonical(expected_statement))
    except (ValueError, InvalidSignature) as exc:
        raise PublicationAttestationError("publication attestation signature is invalid") from exc
