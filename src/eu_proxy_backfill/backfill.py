"""Fail-closed acquisition primitives for Issue #268 full proxy recovery.

Every logical HTTP request returns a terminal receipt, including retry exhaustion.
Payload identity is checked before issue-page rows can enter the fixture namespace.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import pandas as pd
import requests

from scripts.update_beidan_nowscore_sqlite import parse_cp_issue_html
from src.source_schema import publication


@dataclass(frozen=True)
class AcquisitionReceipt:
    source_kind: str
    source_key: str
    source_url: str
    requested_at_utc: str
    received_at_utc: str
    parser_version: str
    acquisition_result: str
    status_code: int | None
    payload_bytes: int | None
    payload_sha256: str | None
    error_class: str | None
    error_detail: str | None
    attempt_count: int


@dataclass(frozen=True)
class AcquisitionResult:
    payload: bytes | None
    receipt: AcquisitionReceipt


@dataclass(frozen=True)
class ParsedIssuePayload:
    declared_issue_code: str
    rows: list[dict[str, object]]


class ByteClient(Protocol):
    def get(self, url: str, timeout: float) -> bytes: ...


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _response_bytes(value: object) -> tuple[bytes, int | None]:
    if isinstance(value, bytes):
        return value, 200
    content = getattr(value, "content", None)
    if not isinstance(content, bytes):
        raise TypeError("network client returned neither bytes nor a response with bytes content")
    raise_for_status = getattr(value, "raise_for_status", None)
    if callable(raise_for_status):
        raise_for_status()
    status = getattr(value, "status_code", None)
    return content, int(status) if status is not None else None


def acquire_terminal(
    client: ByteClient,
    *,
    source_kind: str,
    source_key: str,
    source_url: str,
    timeout: float,
    attempts: int = 4,
    parser_version: str = "bj268_v1",
    retry_delay_seconds: float = 0.0,
) -> AcquisitionResult:
    """Acquire one logical source item with exactly one terminal receipt.

    Failures deliberately retain nullable byte/hash fields: no fake payload hash
    may make a failed request look like a successful immutable receipt.
    """
    if attempts < 1:
        raise ValueError("attempts must be positive")
    requested = _now()
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            payload, status_code = _response_bytes(client.get(source_url, timeout=timeout))
            receipt = AcquisitionReceipt(
                source_kind=source_kind,
                source_key=str(source_key),
                source_url=source_url,
                requested_at_utc=requested,
                received_at_utc=_now(),
                parser_version=parser_version,
                acquisition_result="SUCCESS",
                status_code=status_code,
                payload_bytes=len(payload),
                payload_sha256=hashlib.sha256(payload).hexdigest(),
                error_class=None,
                error_detail=None,
                attempt_count=attempt,
            )
            return AcquisitionResult(payload=payload, receipt=receipt)
        except Exception as exc:  # terminal request accounting; never catches BaseException
            last_error = exc
            if attempt < attempts and retry_delay_seconds:
                time.sleep(retry_delay_seconds * attempt)
    assert last_error is not None
    receipt = AcquisitionReceipt(
        source_kind=source_kind,
        source_key=str(source_key),
        source_url=source_url,
        requested_at_utc=requested,
        received_at_utc=_now(),
        parser_version=parser_version,
        acquisition_result="REQUEST_ERROR",
        status_code=None,
        payload_bytes=None,
        payload_sha256=None,
        error_class=type(last_error).__name__,
        error_detail=str(last_error)[:500],
        attempt_count=attempts,
    )
    return AcquisitionResult(payload=None, receipt=receipt)


def receipt_record(result: AcquisitionResult) -> dict[str, object]:
    """Return a CSV/JSON-friendly complete terminal acquisition receipt."""
    return asdict(result.receipt)


def _declared_issue(text: str) -> str | None:
    # Nowscore has used both hidden input and JavaScript declaration forms.
    input_match = re.search(
        r"<input[^>]+(?:id|name)=[\"'](?:issueNum|IssueNum)[\"'][^>]+value=[\"'](\d+)[\"']",
        text,
        flags=re.I,
    )
    if input_match:
        return input_match.group(1)
    script_match = re.search(r"\b(?:issueNum|IssueNum)\s*[:=]\s*[\"']?(\d+)", text)
    return script_match.group(1) if script_match else None


def parse_declared_issue_payload(payload: bytes, *, requested_issue: str) -> ParsedIssuePayload:
    """Validate Nowscore's embedded issue identity before parsing fixture rows."""
    text = payload.decode("utf-8", errors="replace")
    declared = _declared_issue(text)
    if declared is None:
        raise ValueError("missing payload-declared issue identity")
    requested = str(requested_issue).strip()
    if declared != requested:
        raise ValueError(f"payload-declared issue {declared} differs from requested issue {requested}")
    rows = parse_cp_issue_html(text, requested)
    if not rows:
        raise ValueError(f"issue {requested} payload declared identity but contains no parsable fixtures")
    return ParsedIssuePayload(declared_issue_code=declared, rows=rows)


def write_content_addressed_payload(root: Path, receipt: AcquisitionReceipt, payload: bytes) -> Path:
    """Persist successful bytes under a receipt-bound content address only."""
    if receipt.acquisition_result != "SUCCESS" or receipt.payload_sha256 is None or receipt.payload_bytes is None:
        raise ValueError("only successful receipts with a hash and byte count can write raw payloads")
    safe_component = re.compile(r"^[A-Za-z0-9_.:-]+$")
    if not safe_component.fullmatch(receipt.source_kind) or not safe_component.fullmatch(receipt.source_key):
        raise ValueError("unsafe receipt path component")
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != receipt.payload_sha256 or len(payload) != receipt.payload_bytes:
        raise ValueError("payload hash mismatch with terminal receipt")
    suffix = ".html" if receipt.source_kind == "issue_page" else ".js"
    target = root / "raw" / receipt.source_kind / f"{receipt.source_key}.{receipt.payload_sha256}{suffix}"
    if target.exists():
        existing = target.read_bytes()
        if hashlib.sha256(existing).hexdigest() != receipt.payload_sha256 or existing != payload:
            raise ValueError(f"existing content-addressed payload hash mismatch: {target}")
        return target
    publication.atomic_write_bytes(target, payload)
    return target


def resolve_duplicate_quotes(quotes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Resolve exact duplicates, quarantine conflicting duplicates with a ledger.

    Exact duplicate payloads select the lexical lowest payload digest. Different
    quote values are never silently chosen: the entire key is quarantined.
    """
    keys = ["issue_code", "match_idx", "snapshot_kind", "bookmaker_id"]
    required = {*keys, "v1", "v2", "v3", "payload_sha256"}
    missing = required - set(quotes.columns)
    if missing:
        raise ValueError(f"quotes missing required columns: {sorted(missing)}")
    selected: list[pd.DataFrame] = []
    ledger: list[dict[str, object]] = []
    for key, group in quotes.groupby(keys, dropna=False, sort=True):
        ordered = group.sort_values("payload_sha256", kind="stable")
        values = ordered[["v1", "v2", "v3"]].astype(str).drop_duplicates()
        if len(ordered) == 1:
            selected.append(ordered)
        elif len(values) == 1:
            selected.append(ordered.iloc[[0]])
            ledger.append(dict(zip(keys, key)) | {
                "reason": "EXACT_DUPLICATE_SOURCE_QUOTE",
                "payload_sha256": ",".join(ordered.payload_sha256.astype(str)),
            })
        else:
            ledger.append(dict(zip(keys, key)) | {
                "reason": "CONFLICTING_DUPLICATE_SOURCE_QUOTE",
                "payload_sha256": ",".join(ordered.payload_sha256.astype(str)),
            })
    selected_frame = pd.concat(selected, ignore_index=True) if selected else quotes.iloc[0:0].copy()
    ledger_columns = [*keys, "reason", "payload_sha256"]
    return selected_frame, pd.DataFrame(ledger, columns=ledger_columns)
