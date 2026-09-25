"""Explicit persistence of raw responses and the derived metadata receipt.

Persistence is never implicit: the caller passes the directory, and this module
writes exactly four things per issue — the untouched raw HTML of each source, one metadata receipt (including parsed per-source rows) — and nothing else.

Two rules drive that shape:

* **Raw bytes are written before anything is parsed.** A parser failure must
  never destroy the evidence that explains it, so a failed parse is still
  replayable offline and still leaves the observation on disk.
* **No CSV is written here.** The canonical table's CSV is a *user action*
  through ``readr::write_csv`` ; a fetch has
  no business choosing a tabular serialization on the user's behalf.

No database is opened and no other directory is created.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PersistError(RuntimeError):
    """Persistence was requested without an explicit, usable directory."""


def new_fetch_directory(raw_dir: str | Path, issue_id: str, fetch_id: str) -> Path:
    """Create and return one immutable per-fetch observation directory.

    @param raw_dir Explicit parent directory.
    @param issue_id Issue identifier.
    @param fetch_id Caller identifier; a numeric suffix disambiguates a repeat
        with the same id so an existing observation is never overwritten.
    @return The created directory path.
    """
    return _fetch_directory(raw_dir, issue_id, fetch_id)


def persist_issue_raw(
    *,
    directory: str | Path,
    issue_id: str,
    bodies: dict[str, bytes],
) -> dict[str, str]:
    """Write the untouched response bodies for one issue into a fresh directory.

    @param directory The immutable per-fetch directory from
        ``new_fetch_directory()``; never derived here, so the raw bytes always
        land beside the receipt that describes them.
    @param issue_id Issue identifier used in filenames.
    @param bodies Mapping logical source name -> raw response bytes.
    @return Mapping ``"<source>_raw"`` -> written path.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    prefix = f"{issue_id}."
    written: dict[str, str] = {}
    for source, body in bodies.items():
        path = directory / f"{prefix}{source}.raw.html"
        path.write_bytes(body)
        written[f"{source}_raw"] = str(path)
    return written


def persist_issue_meta(
    *,
    directory: str | Path,
    issue_id: str,
    bodies: dict[str, bytes],
    rows: dict[str, list[Any]],
    meta: dict[str, Any],
) -> dict[str, str]:
    """Write the parsed per-source rows and one metadata receipt.

    @param directory The same immutable per-fetch directory the raw bytes were
        written to, so the receipt always lands beside its observation.
    @param issue_id Issue identifier used in filenames.
    @param bodies The same raw bytes that were persisted, used for their hashes.
    @param rows Mapping ``"500"``/``"nowscore"`` -> parsed provider rows.
    @param meta JSON-shaped metadata: issue id, both URLs, observation instants,
        byte hashes, parser outcome (parsed or failed) and diagnostics.
    @return Mapping of logical name -> written path.
    @raises PersistError when ``directory`` is empty.
    @details A failed parse still gets a receipt: ``meta["parse"]["failed"]``
        names the exception, so the on-disk record distinguishes "the source
        returned nothing" from "our parser broke".
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    prefix = f"{issue_id}."
    written: dict[str, str] = {}
    for source, source_rows in rows.items():
        path = directory / f"{prefix}{source}.rows.json"
        _write_json(path, [_jsonable(row) for row in source_rows])
        written[f"{source}_rows"] = str(path)
    payload = dict(meta)
    payload["raw_sha256"] = {
        source: hashlib.sha256(body).hexdigest() for source, body in bodies.items()
    }
    payload["recorded_at"] = datetime.now(timezone.utc).isoformat()
    meta_path = directory / f"{prefix}source.json"
    _write_json(meta_path, payload)
    written["source_meta"] = str(meta_path)
    return written


def _fetch_directory(raw_dir: str | Path, issue_id: str, fetch_id: str) -> Path:
    """Return (and create) the immutable per-fetch directory.

    @param raw_dir Explicit parent directory.
    @param issue_id Issue identifier.
    @param fetch_id Caller identifier; a numeric suffix disambiguates a repeat
        with the same id, so an existing observation is never overwritten.
    """
    parent = _prepare(raw_dir)
    if not fetch_id or not str(fetch_id).strip():
        raise PersistError("fetch_id must be a non-empty string")
    safe = str(fetch_id).replace(":", "").replace("+", "")
    base = parent / issue_id / safe
    directory = base
    suffix = 1
    while directory.exists():
        directory = parent / issue_id / f"{safe}.{suffix}"
        suffix += 1
    directory.mkdir(parents=True)
    return directory


def _prepare(raw_dir: str | Path) -> Path:
    if raw_dir is None or (isinstance(raw_dir, str) and not raw_dir.strip()):
        raise PersistError("raw_dir must be given explicitly; there is no default")
    directory = Path(raw_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
