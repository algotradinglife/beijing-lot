"""Immutable Titan007/Nowscore Euro 1X2 and over/under history primitives."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.multimarket_p0 import HKT, sha256_file


CAPTURE_SCHEMA = "nowscore_score_model_history_capture_v1"
REPLAY_SCHEMA = "nowscore_score_model_segment_replay_v1"
MARKETS = ("euro_1x2", "over_under")
SOURCE_CLASSIFICATION = "third_party_timestamped_archive"
WILLIAM_HILL = {
    "bookmaker_key": "william_hill",
    "euro_company_id": 115,
    "over_under_company_id": 9,
}
from packages.beidan.inst.python.beidan_backend.market_capture.history import (
    EURO_TIME_RE, OU_TIME_RE, ScoreModelHistoryError, ParsedSnapshot,
    euro_history_url, over_under_history_url, _float, parse_line, _js_array,
    parse_euro_history_js, parse_over_under_history_json,
)


def snapshot_record(
    parsed: ParsedSnapshot,
    *,
    issue: str,
    match_idx: int,
    provider_match_id: str,
    bookmaker_key: str,
    provider_company_id: int,
    provider_company_name: str,
    kickoff_hkt: datetime,
    fetched_at_utc: str,
    source_url: str,
    raw_file: str,
    raw_payload_sha256: str,
    capture_batch_id: str,
) -> dict[str, Any]:
    identity = "|".join(
        (
            issue,
            str(match_idx),
            provider_match_id,
            bookmaker_key,
            parsed.market_key,
            str(provider_company_id),
            parsed.snapshot_ts_hkt,
            parsed.raw_row_sha256,
        )
    )
    return {
        "snapshot_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "issue": issue,
        "match_idx": match_idx,
        "provider_match_id": provider_match_id,
        "bookmaker_key": bookmaker_key,
        "provider_company_id": provider_company_id,
        "provider_company_name": provider_company_name,
        "market_key": parsed.market_key,
        "snapshot_ts_hkt": parsed.snapshot_ts_hkt,
        "source_time_raw": parsed.source_time_raw,
        "time_normalization_status": parsed.time_normalization_status,
        "fetched_at_utc": fetched_at_utc,
        "kickoff_hkt": kickoff_hkt.isoformat(),
        "odds_json": json.dumps(parsed.odds, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "line_text": parsed.line_text,
        "line_value": parsed.line_value,
        "phase": parsed.phase,
        "complete": int(parsed.complete),
        "source_id": f"titan007:{parsed.market_key}:company:{provider_company_id}",
        "source_url": source_url,
        "raw_file": raw_file,
        "raw_payload_sha256": raw_payload_sha256,
        "raw_row_sha256": parsed.raw_row_sha256,
        "capture_batch_id": capture_batch_id,
        "capture_classification": SOURCE_CLASSIFICATION,
    }


def verify_hashed_bundle(path: Path, *, expected_schema: str | None = None) -> dict[str, Any]:
    root = path.expanduser().resolve()
    sums = root / "SHA256SUMS"
    manifest_path = root / "manifest.json"
    if not sums.is_file() or not manifest_path.is_file():
        raise ScoreModelHistoryError(f"bundle control files missing: {root}")
    count = 0
    for line in sums.read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise ScoreModelHistoryError(f"invalid checksum line: {line!r}") from exc
        relative = Path(name)
        target = root / relative
        if relative.is_absolute() or ".." in relative.parts or not target.is_file():
            raise ScoreModelHistoryError(f"invalid bundle path: {name}")
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or sha256_file(target) != digest:
            raise ScoreModelHistoryError(f"bundle checksum mismatch: {name}")
        count += 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if expected_schema and manifest.get("schema_version") != expected_schema:
        raise ScoreModelHistoryError("bundle schema mismatch")
    policy = manifest.get("policy", {})
    if policy.get("execution_enabled") is not False or policy.get("roi_authorized") is not False:
        raise ScoreModelHistoryError("bundle safety policy mismatch")
    return {"status": "valid", "files": count, "manifest": manifest, "sha256s_sha256": sha256_file(sums)}


def select_latest_complete(
    rows: Iterable[Mapping[str, str]], freeze_at_hkt: datetime
) -> tuple[Mapping[str, str] | None, str]:
    all_rows = list(rows)
    if not all_rows:
        return None, "market_history_missing"
    at_or_before = [
        row for row in all_rows if datetime.fromisoformat(row["snapshot_ts_hkt"]) <= freeze_at_hkt
    ]
    if not at_or_before:
        return None, "all_snapshots_after_freeze"
    pregame = [row for row in at_or_before if row.get("phase") == "pregame"]
    if not pregame:
        return None, "only_non_pregame_snapshots_at_or_before_freeze"
    complete = [row for row in pregame if row.get("complete") in {"1", "true", "True"}]
    if not complete:
        return None, "only_incomplete_snapshots_at_or_before_freeze"
    selected = max(
        complete,
        key=lambda row: (
            datetime.fromisoformat(row["snapshot_ts_hkt"]),
            row.get("fetched_at_utc", ""),
            row.get("snapshot_id", ""),
        ),
    )
    return selected, "selected"
