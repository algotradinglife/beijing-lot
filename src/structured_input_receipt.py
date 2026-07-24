"""Content-bound generation receipts for operational structured decision inputs."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "structured_decision_input_receipt_v1"


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt_path(csv_path: Path) -> Path:
    return csv_path.with_suffix(".input_receipt.json")


def write_receipt(
    csv_path: Path,
    *,
    issue: str,
    generated_at: datetime | None = None,
    source: dict[str, Any] | None = None,
) -> Path:
    """Atomically bind the just-generated CSV bytes to their generation clock."""
    observed = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "issue": str(issue),
        "structured_csv_name": csv_path.name,
        "structured_csv_sha256": file_hash(csv_path),
        "structured_csv_size_bytes": csv_path.stat().st_size,
        "generated_at_utc": observed.isoformat(timespec="microseconds"),
        "source": source or {},
    }
    payload["sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
    target = receipt_path(csv_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(payload) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target


def verify_receipt(
    csv_path: Path, receipt: Path, *, issue: str
) -> dict[str, Any]:
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    claimed = str(payload.pop("sha256", ""))
    actual = hashlib.sha256(canonical(payload)).hexdigest()
    if claimed != actual:
        raise ValueError("structured input receipt sha256 mismatch")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or str(payload.get("issue")) != str(issue)
        or payload.get("structured_csv_name") != csv_path.name
        or payload.get("structured_csv_sha256") != file_hash(csv_path)
        or int(payload.get("structured_csv_size_bytes", -1)) != csv_path.stat().st_size
    ):
        raise ValueError("structured input receipt does not bind selected CSV")
    generated = datetime.fromisoformat(str(payload["generated_at_utc"]))
    if generated.tzinfo is None:
        raise ValueError("structured input receipt clock lacks timezone")
    return {**payload, "sha256": claimed, "generated_at": generated}
