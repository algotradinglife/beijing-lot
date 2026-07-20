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
EURO_TIME_RE = re.compile(r"^(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$")
OU_TIME_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$")


class ScoreModelHistoryError(ValueError):
    """Raised when a score-model history or replay invariant is violated."""


@dataclass(frozen=True)
class ParsedSnapshot:
    market_key: str
    source_time_raw: str
    snapshot_ts_hkt: str
    time_normalization_status: str
    phase: str
    odds: Mapping[str, float | None]
    line_text: str
    line_value: float | None
    complete: bool
    raw_row_sha256: str


def euro_history_url(provider_match_id: str) -> str:
    return f"https://1x2d.titan007.com/{provider_match_id}.js"


def over_under_history_url(provider_match_id: str, company_id: int, kickoff_hkt: datetime) -> str:
    matchtime = kickoff_hkt.astimezone(HKT).strftime("%Y%m%d%H%M%S")
    return (
        "https://m.titan007.com/HandicapDataInterface.ashx?"
        f"scheid={provider_match_id}&type=3&oddskind=1&companyid={company_id}"
        f"&matchtime={matchtime}&isHalf=0"
    )


def _float(value: str) -> float | None:
    try:
        result = float(value.strip())
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def parse_line(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    if "/" in text:
        parts = text.split("/")
        if len(parts) != 2:
            return None
        try:
            return sum(float(part) for part in parts) / 2
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def _js_array(text: str, name: str) -> list[str]:
    match = re.search(rf"var\s+{re.escape(name)}\s*=\s*Array\((.*?)\);", text, re.S)
    if not match:
        raise ScoreModelHistoryError(f"Titan Euro JS array missing: {name}")
    return re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1), re.S)


def parse_euro_history_js(
    payload: bytes,
    *,
    kickoff_hkt: datetime,
    company_id: int,
) -> tuple[str, list[ParsedSnapshot], dict[str, int]]:
    text = payload.decode("utf-8-sig", errors="replace")
    games = _js_array(text, "game")
    details = _js_array(text, "gameDetail")
    company_name = ""
    record_id = ""
    for entry in games:
        parts = entry.split("|")
        if len(parts) >= 3 and parts[0] == str(company_id):
            record_id = parts[1]
            company_name = parts[2]
            break
    if not record_id:
        raise ScoreModelHistoryError(f"Titan Euro company missing: {company_id}")
    history = next((entry.split("^", 1)[1] for entry in details if entry.startswith(f"{record_id}^")), "")
    if not history:
        raise ScoreModelHistoryError(f"Titan Euro company history missing: {company_id}")
    snapshots: list[ParsedSnapshot] = []
    counters = {"candidate_rows": 0, "timestamp_rejected_rows": 0, "incomplete_rows": 0}
    for raw in history.split(";"):
        if not raw.strip():
            continue
        counters["candidate_rows"] += 1
        parts = raw.split("|")
        if len(parts) < 8:
            counters["incomplete_rows"] += 1
            continue
        match = EURO_TIME_RE.fullmatch(parts[3].strip())
        try:
            year = int(parts[7])
            if not match:
                raise ValueError
            month, day, hour, minute = (int(value) for value in match.groups())
            source_time = datetime(year, month, day, hour, minute, tzinfo=HKT)
        except ValueError:
            counters["timestamp_rejected_rows"] += 1
            continue
        odds: Mapping[str, float | None] = {
            "home": _float(parts[0]),
            "draw": _float(parts[1]),
            "away": _float(parts[2]),
        }
        phase = "pregame" if source_time <= kickoff_hkt else "live_or_postkickoff"
        complete = phase == "pregame" and all(value is not None for value in odds.values())
        if not complete:
            counters["incomplete_rows"] += 1
        snapshots.append(
            ParsedSnapshot(
                market_key="euro_1x2",
                source_time_raw=f"{parts[7]}-{parts[3]}",
                snapshot_ts_hkt=source_time.isoformat(timespec="minutes"),
                time_normalization_status="explicit_titan_year_and_hkt",
                phase=phase,
                odds=odds,
                line_text="",
                line_value=None,
                complete=complete,
                raw_row_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            )
        )
    if not snapshots:
        raise ScoreModelHistoryError(f"Titan Euro company history empty: {company_id}")
    snapshots.sort(key=lambda row: (row.snapshot_ts_hkt, row.raw_row_sha256))
    return company_name, snapshots, counters


def parse_over_under_history_json(
    payload: bytes,
    *,
    kickoff_hkt: datetime,
) -> tuple[list[ParsedSnapshot], dict[str, int]]:
    try:
        rows = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        text = payload.decode("utf-8", errors="replace")
        if "WAF" in text or "访问" in text or "频" in text:
            raise ScoreModelHistoryError("Titan O/U WAF response") from exc
        raise ScoreModelHistoryError("Titan O/U payload is not JSON") from exc
    if not isinstance(rows, list):
        raise ScoreModelHistoryError("Titan O/U history root is not a list")
    snapshots: list[ParsedSnapshot] = []
    counters = {"candidate_rows": 0, "timestamp_rejected_rows": 0, "incomplete_rows": 0}
    for item in rows:
        if not isinstance(item, dict):
            continue
        counters["candidate_rows"] += 1
        source_time_raw = str(item.get("ModifyTime") or "")
        match = OU_TIME_RE.fullmatch(source_time_raw)
        if not match:
            counters["timestamp_rejected_rows"] += 1
            continue
        try:
            source_time = datetime(*(int(value) for value in match.groups()), tzinfo=HKT)
        except ValueError:
            counters["timestamp_rejected_rows"] += 1
            continue
        happen_time = str(item.get("HappenTime") or "").strip()
        score_status = str(item.get("Score") or "").strip()
        phase = "pregame" if not happen_time and score_status in {"", "即", "早"} else "live_or_postkickoff"
        odds: Mapping[str, float | None] = {
            "over": _float(str(item.get("HomeOdds") or "")),
            "under": _float(str(item.get("AwayOdds") or "")),
        }
        line_text = str(item.get("PanKou") or "").strip()
        line_value = parse_line(line_text)
        complete = (
            phase == "pregame"
            and source_time <= kickoff_hkt
            and line_value is not None
            and all(value is not None for value in odds.values())
        )
        if not complete:
            counters["incomplete_rows"] += 1
        raw = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        snapshots.append(
            ParsedSnapshot(
                market_key="over_under",
                source_time_raw=source_time_raw,
                snapshot_ts_hkt=source_time.isoformat(timespec="seconds"),
                time_normalization_status="explicit_titan_yyyymmddhhmmss_hkt",
                phase=phase,
                odds=odds,
                line_text=line_text,
                line_value=line_value,
                complete=complete,
                raw_row_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            )
        )
    if not snapshots:
        raise ScoreModelHistoryError("Titan O/U history is empty")
    snapshots.sort(key=lambda row: (row.snapshot_ts_hkt, row.raw_row_sha256))
    return snapshots, counters


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
