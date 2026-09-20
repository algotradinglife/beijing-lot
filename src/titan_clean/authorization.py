"""Authorization receipts required for non-probe Titan collection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .discovery import EURO_1X2_URL, SCHEDULE_URL

AUTHORIZATION_SCHEMA = "titan_collection_authorization_v1"


class TitanAuthorizationError(ValueError):
    """Raised when a collection authorization receipt is incomplete or unsafe."""


@dataclass(frozen=True)
class TitanAuthorization:
    receipt_sha256: str
    authorization_basis: str
    evidence_uri: str
    allowed_origins: tuple[str, ...]


def load_titan_authorization(path: Path) -> TitanAuthorization:
    """Load a user-provided authorization receipt without storing any credential."""
    payload = Path(path).read_bytes()
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise TitanAuthorizationError("authorization receipt is not valid JSON") from exc
    required = {"schema_version", "source_id", "automation_permitted", "authorization_basis", "evidence_uri", "allowed_origins"}
    if not required.issubset(document):
        raise TitanAuthorizationError("authorization receipt lacks required fields")
    if document["schema_version"] != AUTHORIZATION_SCHEMA or document["source_id"] != "titan":
        raise TitanAuthorizationError("authorization receipt has an incompatible source contract")
    if document["automation_permitted"] is not True:
        raise TitanAuthorizationError("authorization receipt does not permit automation")
    if not isinstance(document["authorization_basis"], str) or not document["authorization_basis"].strip():
        raise TitanAuthorizationError("authorization basis is required")
    if not isinstance(document["evidence_uri"], str) or not document["evidence_uri"].strip():
        raise TitanAuthorizationError("authorization evidence URI is required")
    origins = document["allowed_origins"]
    if not isinstance(origins, list) or not all(isinstance(item, str) and item for item in origins):
        raise TitanAuthorizationError("allowed origins must be a non-empty string list")
    expected = {urlsplit(SCHEDULE_URL).netloc, urlsplit(EURO_1X2_URL).netloc}
    if not expected.issubset(set(origins)):
        raise TitanAuthorizationError("authorization receipt omits a required Titan origin")
    return TitanAuthorization(
        receipt_sha256=hashlib.sha256(payload).hexdigest(),
        authorization_basis=document["authorization_basis"].strip(),
        evidence_uri=document["evidence_uri"].strip(),
        allowed_origins=tuple(sorted(set(origins))),
    )
