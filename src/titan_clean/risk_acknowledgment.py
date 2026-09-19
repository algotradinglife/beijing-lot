"""Explicit user risk acknowledgement for bounded low-frequency collection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .discovery import EURO_1X2_URL, SCHEDULE_URL

RISK_ACK_SCHEMA = "titan_low_frequency_risk_ack_v1"


class TitanRiskAcknowledgmentError(ValueError):
    """Raised when the operator acknowledgement is incomplete."""


@dataclass(frozen=True)
class TitanRiskAcknowledgment:
    receipt_sha256: str
    max_requests_per_minute: int
    max_fixture_ids_per_run: int


def load_risk_acknowledgment(path: Path) -> TitanRiskAcknowledgment:
    payload = Path(path).read_bytes()
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise TitanRiskAcknowledgmentError("risk acknowledgement is not valid JSON") from exc
    required = {"schema_version", "source_id", "operator_accepts_risk", "allowed_origins", "max_requests_per_minute", "max_fixture_ids_per_run"}
    if not required.issubset(document) or document["schema_version"] != RISK_ACK_SCHEMA or document["source_id"] != "titan":
        raise TitanRiskAcknowledgmentError("risk acknowledgement has an incompatible contract")
    if document["operator_accepts_risk"] is not True:
        raise TitanRiskAcknowledgmentError("operator risk acceptance is required")
    expected = {urlsplit(SCHEDULE_URL).netloc, urlsplit(EURO_1X2_URL).netloc}
    if not isinstance(document["allowed_origins"], list) or not expected.issubset(set(document["allowed_origins"])):
        raise TitanRiskAcknowledgmentError("risk acknowledgement omits a required Titan origin")
    per_minute, per_run = document["max_requests_per_minute"], document["max_fixture_ids_per_run"]
    if not isinstance(per_minute, int) or not 1 <= per_minute <= 600:
        raise TitanRiskAcknowledgmentError("max requests per minute must be between 1 and 600")
    if not isinstance(per_run, int) or not 0 <= per_run <= 600:
        raise TitanRiskAcknowledgmentError("max fixture IDs per run must be between 0 and 600")
    return TitanRiskAcknowledgment(hashlib.sha256(payload).hexdigest(), per_minute, per_run)
