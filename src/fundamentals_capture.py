"""Bounded immutable HTTP capture for Nowscore, Titan and audit evidence.

Fetching is separate from parsing and persistence. The batch output is created
atomically, stores every attempt's original entity bytes in transport receipts,
and records transport failures without converting them to empty source data. No
import-time network or filesystem activity occurs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from src.fundamentals_census import canonical

CAPTURE_SCHEMA = "bj408_capture_batch_v1"
MAX_BYTES = 10 * 1024 * 1024
TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})
SOURCE_HOSTS = {"nowscore": frozenset({"cp.nowscore.com", "live.nowscore.com"}),
                "titan": frozenset({"zq.titan007.com"})}


def capture_documents(documents: list[dict], output_dir: str | Path, *, fetch=None,
                      timeout_seconds: float = 20, max_attempts: int = 3,
                      source_intervals: dict[str, float] | None = None,
                      clock=None, monotonic=None, sleeper=None) -> dict:
    """Capture a declared batch into a new immutable directory.

    Each document requires source, HTTPS URL and a safe JSON filename. Nowscore
    and Titan hosts are exact; independent evidence may use any explicit HTTPS
    host because its independence is assessed during adjudication. Retries apply
    only to transport exceptions and bounded transient HTTP statuses. Injected
    adapters make routine tests fully offline.
    """
    if not isinstance(documents, list) or not documents:
        raise ValueError("capture batch must be non-empty")
    if type(max_attempts) is not int or max_attempts < 1 or max_attempts > 5:
        raise ValueError("max_attempts must be between 1 and 5")
    if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 60:
        raise ValueError("timeout_seconds must be in (0, 60]")
    intervals = {"nowscore": 5.0, "titan": 5.0, "independent": 2.0}
    if source_intervals is not None:
        if set(source_intervals) - set(intervals) or any(not isinstance(value, (int, float)) or value < 0
                                                        for value in source_intervals.values()):
            raise ValueError("invalid source intervals")
        intervals.update(source_intervals)
    names = set()
    normalized = []
    for document in documents:
        if not isinstance(document, dict) or document.get("source") not in intervals:
            raise ValueError("invalid capture source")
        name = document.get("filename")
        url = document.get("url")
        if (not isinstance(name, str) or
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.json", name) or
                name == "capture-manifest.json" or name in names):
            raise ValueError("invalid or duplicate capture filename")
        parsed = urlparse(str(url))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("capture URL must be credential-free HTTPS")
        if document["source"] in SOURCE_HOSTS and parsed.hostname not in SOURCE_HOSTS[document["source"]]:
            raise ValueError("capture URL does not match source host")
        names.add(name)
        normalized.append({"source": document["source"], "url": str(url), "filename": name})
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(output)
    current_time = clock or (lambda: datetime.now(timezone.utc))
    monotonic_time = monotonic or time.monotonic
    pause = sleeper or time.sleep
    session = None
    if fetch is None:
        session = requests.Session()
        fetch = session.get
    implementation_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    last_started = {}
    rows = []
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=output.parent, prefix=".fundamentals-capture-") as temp:
            stage = Path(temp) / "capture"
            stage.mkdir()
            for document in normalized:
                result = None
                attempt_receipts = []
                for attempt in range(1, max_attempts + 1):
                    elapsed = monotonic_time() - last_started.get(document["source"], float("-inf"))
                    if elapsed < intervals[document["source"]]:
                        pause(intervals[document["source"]] - elapsed)
                    started = current_time()
                    if started.utcoffset() is None:
                        raise ValueError("capture clock requires timezone")
                    last_started[document["source"]] = monotonic_time()
                    response = None
                    try:
                        response = fetch(document["url"], timeout=timeout_seconds, stream=True)
                        raw_parts = []
                        size = 0
                        chunks = response.iter_content(chunk_size=65536) if hasattr(response, "iter_content") else [response.content]
                        for chunk in chunks:
                            if not chunk:
                                continue
                            size += len(chunk)
                            if size > MAX_BYTES:
                                raise ValueError("response exceeds 10 MiB")
                            raw_parts.append(bytes(chunk))
                        raw = b"".join(raw_parts)
                        received = current_time()
                        if received.utcoffset() is None or received < started:
                            raise ValueError("invalid capture chronology")
                        status = response.status_code
                        if type(status) is not int or not 100 <= status <= 599:
                            raise ValueError("invalid HTTP status")
                        result = {"url": document["url"], "final_url": str(response.url), "status": status,
                                  "content_type": str(response.headers.get("content-type", "")),
                                  "started_at_utc": started.isoformat(), "received_at_utc": received.isoformat(),
                                  "byte_count": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                                  "body_base64": base64.b64encode(raw).decode("ascii"), "attempts": attempt}
                        attempt_receipts.append({**result, "attempt": attempt})
                        if status not in TRANSIENT_STATUSES or attempt == max_attempts:
                            break
                    except requests.RequestException as exc:
                        received = current_time()
                        if received.utcoffset() is None or received < started:
                            raise ValueError("invalid capture chronology") from exc
                        result = {"url": document["url"], "started_at_utc": started.isoformat(),
                                  "received_at_utc": received.isoformat(), "attempts": attempt,
                                  "error": f"{type(exc).__name__}: {exc}"}
                        attempt_receipts.append({**result, "attempt": attempt})
                        if attempt == max_attempts:
                            break
                    finally:
                        if response is not None and hasattr(response, "close"):
                            response.close()
                if result is None:
                    raise RuntimeError("capture attempt produced no result")
                result["attempt_receipts"] = attempt_receipts
                (stage / document["filename"]).write_text(canonical(result) + "\n", encoding="utf-8")
                rows.append({"source": document["source"], "url": document["url"],
                             "filename": document["filename"], "attempts": result["attempts"],
                             "state": "TRANSPORT_FAILURE" if "error" in result else
                                      "HTTP_OK" if result["status"] == 200 else "HTTP_FAILURE",
                             "sha256": result.get("sha256", ""), "error": result.get("error", "")})
            if implementation_hash != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
                raise ValueError("capture implementation changed during batch")
            file_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(stage.glob("*.json"))}
            manifest = {"schema": CAPTURE_SCHEMA, "historical_learning": "NONE", "timeout_seconds": timeout_seconds,
                        "max_attempts": max_attempts, "source_intervals": intervals,
                        "implementation_sha256": implementation_hash, "documents": rows, "file_hashes": file_hashes}
            (stage / "capture-manifest.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
            os.rename(stage, output)
        return manifest
    finally:
        if session is not None:
            session.close()
