"""Strict, immutable correct-score bookmaker price assets."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from bs4 import BeautifulSoup

from src.multimarket_p0 import HKT
from src.okooo_prekick_sp import HistoryRow, outcome_values


CAPTURE_SCHEMA = "correct_score_price_history_capture_v1"
REPLAY_SCHEMA = "correct_score_price_segment_replay_v1"
POLICY = {
    "execution_enabled": False,
    "frontend_selectable": False,
    "roi_authorized": False,
    "formal_strategy_input": False,
    "ticket_output_enabled": False,
    "release_manifest_enabled": False,
    "terminal_500_sp_allowed": False,
    "post_sale_500_backfill_role": "settlement_or_coverage_audit_only",
}
REQUIRED_TAIL_OUTCOMES = frozenset({"home_other", "draw_other", "away_other"})
NOWSCORE_REQUIRED_EXACT_OUTCOMES = frozenset(
    f"{home}-{away}" for home in range(5) for away in range(5)
)

ABSOLUTE_TIME_RE = re.compile(
    r"(?P<year>20\d{2})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})"
    r"\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?"
)
SHORT_TIME_RE = re.compile(
    r"(?<!\d)(?P<month>\d{1,2})[-/.](?P<day>\d{1,2})"
    r"\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?"
)
SCORE_RE = re.compile(r"(?<!\d)(?P<home>\d+)\s*[:：-]\s*(?P<away>\d+)(?!\d)")


class CorrectScorePriceError(ValueError):
    """Raised when a correct-score asset violates the strict replay contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_score_outcome(label: str) -> tuple[str, str] | None:
    """Return a stable outcome code and home/draw/away group."""
    compact = "".join(label.split()).replace("：", ":")
    match = SCORE_RE.search(compact)
    if match:
        home = int(match.group("home"))
        away = int(match.group("away"))
        group = "home" if home > away else "draw" if home == away else "away"
        return f"{home}-{away}", group
    if "其他" not in compact:
        return None
    if any(token in compact for token in ("主胜", "胜其他", "胜其它")):
        return "home_other", "home"
    if any(token in compact for token in ("平局", "平其他", "平其它", "和其他", "和其它")):
        return "draw_other", "draw"
    if any(token in compact for token in ("客胜", "负其他", "负其它")):
        return "away_other", "away"
    return None


def normalize_source_time(
    row: HistoryRow,
    *,
    kickoff_hkt: datetime,
) -> tuple[datetime | None, str, str]:
    """Normalize explicit source time, otherwise derive it from source countdown."""
    kickoff = kickoff_hkt.astimezone(HKT)
    joined = " | ".join(row.cells)
    absolute = ABSOLUTE_TIME_RE.search(joined)
    if absolute:
        values = {key: int(value or 0) for key, value in absolute.groupdict().items()}
        parsed = datetime(
            values["year"], values["month"], values["day"], values["hour"],
            values["minute"], values["second"], tzinfo=HKT,
        )
        return parsed, absolute.group(0), "source_explicit_hkt"
    short = SHORT_TIME_RE.search(joined)
    if short:
        values = {key: int(value or 0) for key, value in short.groupdict().items()}
        candidates = [
            datetime(
                year, values["month"], values["day"], values["hour"],
                values["minute"], values["second"], tzinfo=HKT,
            )
            for year in (kickoff.year - 1, kickoff.year, kickoff.year + 1)
        ]
        parsed = min(candidates, key=lambda value: abs((kickoff - value).total_seconds()))
        return parsed, short.group(0), "source_month_day_inferred_year"
    if row.minutes_before_kickoff >= 0:
        return (
            kickoff - timedelta(minutes=row.minutes_before_kickoff),
            row.relative_label,
            "source_relative_to_kickoff_derived",
        )
    return None, row.relative_label, "source_time_unparseable"


def snapshot_from_history_row(
    row: HistoryRow,
    *,
    issue: str,
    match_idx: int,
    provider_match_id: str,
    nowscore_provider_match_id: str,
    kickoff_hkt: datetime,
    fetched_at_utc: str,
    source_url: str,
    raw_file: str,
    raw_payload_sha256: str,
    capture_batch_id: str,
    provider: str = "okooo",
    bookmaker_key: str = "william_hill",
    provider_company_id: str = "14",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    snapshot_ts, source_time_raw, time_grade = normalize_source_time(row, kickoff_hkt=kickoff_hkt)
    prices: list[dict[str, Any]] = []
    rejected_labels: list[str] = []
    for value in outcome_values(row):
        canonical = canonical_score_outcome(str(value["outcome_label"]))
        if canonical is None:
            rejected_labels.append(str(value["outcome_label"]))
            continue
        outcome_code, outcome_group = canonical
        prices.append(
            {
                "outcome_code": outcome_code,
                "outcome_group": outcome_group,
                "outcome_label": value["outcome_label"],
                "sp": value["sp"],
                "raw_value": value["raw_value"],
                "field_index": value["field_index"],
            }
        )
    codes = [str(item["outcome_code"]) for item in prices]
    groups = {str(item["outcome_group"]) for item in prices}
    numeric = all(isinstance(item["sp"], (int, float)) and float(item["sp"]) > 1 for item in prices)
    missing_required = sorted(REQUIRED_TAIL_OUTCOMES - set(codes))
    complete = (
        snapshot_ts is not None
        and snapshot_ts < kickoff_hkt.astimezone(HKT)
        and len(prices) >= 18
        and len(codes) == len(set(codes))
        and groups == {"home", "draw", "away"}
        and not missing_required
        and numeric
    )
    row_payload = json.dumps(
        {
            "headers": row.headers,
            "cells": row.cells,
            "row_order": row.row_order,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    raw_row_sha256 = hashlib.sha256(row_payload.encode("utf-8")).hexdigest()
    identity = "|".join(
        (
            issue, str(match_idx), provider, provider_match_id, bookmaker_key,
            snapshot_ts.isoformat() if snapshot_ts else source_time_raw, raw_row_sha256,
        )
    )
    snapshot_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    snapshot = {
        "snapshot_id": snapshot_id,
        "issue": str(issue),
        "match_idx": match_idx,
        "provider": provider,
        "provider_match_id": provider_match_id,
        "nowscore_provider_match_id": nowscore_provider_match_id,
        "bookmaker_key": bookmaker_key,
        "provider_company_id": provider_company_id,
        "market_key": "correct_score",
        "snapshot_ts_hkt": snapshot_ts.isoformat() if snapshot_ts else "",
        "source_time_raw": source_time_raw,
        "timestamp_grade": time_grade,
        "source_timestamp_scope": "market_history_row",
        "fetched_at_utc": fetched_at_utc,
        "kickoff_hkt": kickoff_hkt.astimezone(HKT).isoformat(),
        "relative_label": row.relative_label,
        "minutes_before_kickoff": row.minutes_before_kickoff,
        "outcome_count": len(prices),
        "exact_score_count": sum("-" in code for code in codes),
        "exact_score_complete": "",
        "tail_outcome_count": len(REQUIRED_TAIL_OUTCOMES & set(codes)),
        "missing_exact_outcomes_json": "[]",
        "missing_required_outcomes_json": json.dumps(missing_required, separators=(",", ":")),
        "completeness_reason": "complete" if complete else (
            "missing_tail_outcomes" if missing_required else "invalid_vector_or_timestamp"
        ),
        "outcome_schema_sha256": hashlib.sha256("|".join(sorted(codes)).encode("utf-8")).hexdigest(),
        "rejected_labels_json": json.dumps(rejected_labels, ensure_ascii=False, separators=(",", ":")),
        "complete": int(complete),
        "phase": "pregame" if snapshot_ts is not None and snapshot_ts < kickoff_hkt.astimezone(HKT) else "invalid_or_postkickoff",
        "source_url": source_url,
        "raw_file": raw_file,
        "raw_payload_sha256": raw_payload_sha256,
        "raw_row_sha256": raw_row_sha256,
        "capture_batch_id": capture_batch_id,
        "capture_classification": "third_party_timestamped_bookmaker_archive",
    }
    normalized_prices = [
        {
            "snapshot_id": snapshot_id,
            "issue": str(issue),
            "match_idx": match_idx,
            "provider": provider,
            "provider_match_id": provider_match_id,
            "nowscore_provider_match_id": nowscore_provider_match_id,
            "bookmaker_key": bookmaker_key,
            "provider_company_id": provider_company_id,
            "market_key": "correct_score",
            "snapshot_ts_hkt": snapshot["snapshot_ts_hkt"],
            "source_time_raw": source_time_raw,
            "timestamp_grade": time_grade,
            "source_timestamp_scope": "market_history_row",
            "fetched_at_utc": fetched_at_utc,
            "kickoff_hkt": snapshot["kickoff_hkt"],
            **price,
            "source_url": source_url,
            "raw_file": raw_file,
            "raw_payload_sha256": raw_payload_sha256,
            "raw_row_sha256": raw_row_sha256,
            "capture_batch_id": capture_batch_id,
        }
        for price in prices
    ]
    return snapshot, normalized_prices


def snapshot_from_nowscore_crown_current(
    odds_payload: bytes,
    context_payload: bytes,
    *,
    issue: str,
    match_idx: int,
    provider_match_id: str,
    kickoff_hkt: datetime,
    fetched_at_utc: str,
    source_url: str,
    raw_file: str,
    raw_payload_sha256: str,
    source_context_url: str,
    source_context_file: str,
    source_context_sha256: str,
    capture_batch_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize Nowscore's current Crown 波胆 panel as a forward observation.

    The panel exposes 25 exact scores but currently no other-home/draw/away
    buckets. Such observations are retained immutably but fail completeness.
    """
    context_text = BeautifulSoup(
        context_payload.decode("utf-8", errors="replace"), "html.parser"
    ).get_text(" ", strip=True)
    marker = re.search(r"最后更新\s*(20\d{2}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}:\d{2})", context_text)
    snapshot_ts: datetime | None = None
    source_time_raw = marker.group(1) if marker else ""
    if marker:
        snapshot_ts = datetime.strptime(source_time_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=HKT)

    soup = BeautifulSoup(odds_payload.decode("utf-8", errors="replace"), "html.parser")
    title = soup.find("b", string=lambda value: bool(value and value.strip() == "波胆"))
    if title is None or title.find_parent("table") is None:
        raise CorrectScorePriceError("Nowscore Crown correct-score table missing")
    rows = title.find_parent("table").find_all("tr")
    if len(rows) < 3:
        raise CorrectScorePriceError("Nowscore Crown correct-score rows incomplete")
    labels = [cell.get_text(" ", strip=True) for cell in rows[0].find_all(["td", "th"])][1:]
    home_values = [cell.get_text(" ", strip=True) for cell in rows[1].find_all(["td", "th"])][1:]
    away_values = [cell.get_text(" ", strip=True) for cell in rows[2].find_all(["td", "th"])][1:]
    if len(labels) < 15 or len(home_values) < 15 or len(away_values) < 10:
        raise CorrectScorePriceError(
            f"Nowscore Crown correct-score vector truncated: labels={len(labels)} "
            f"home={len(home_values)} away={len(away_values)}"
        )

    raw_entries: list[tuple[str, str]] = []
    raw_entries.extend(zip(labels[:10], home_values[:10]))
    raw_entries.extend(zip(labels[10:15], home_values[10:15]))
    for label, value in zip(labels[:10], away_values[:10]):
        score = canonical_score_outcome(label)
        if score is None or "-" not in score[0]:
            continue
        home, away = score[0].split("-", 1)
        raw_entries.append((f"{away}:{home}", value))

    prices: list[dict[str, Any]] = []
    rejected_labels: list[str] = []
    for field_index, (label, raw_value) in enumerate(raw_entries):
        canonical = canonical_score_outcome(label)
        try:
            price = float(raw_value)
        except ValueError:
            price = 0.0
        if canonical is None or price <= 1:
            rejected_labels.append(label)
            continue
        outcome_code, outcome_group = canonical
        prices.append(
            {
                "outcome_code": outcome_code,
                "outcome_group": outcome_group,
                "outcome_label": label,
                "sp": price,
                "raw_value": raw_value,
                "field_index": field_index,
            }
        )

    codes = [str(item["outcome_code"]) for item in prices]
    missing_exact = sorted(NOWSCORE_REQUIRED_EXACT_OUTCOMES - set(codes))
    missing_tail = sorted(REQUIRED_TAIL_OUTCOMES - set(codes))
    missing_required = sorted({*missing_exact, *missing_tail})
    fetched_at_hkt = datetime.fromisoformat(fetched_at_utc).astimezone(HKT)
    phase = (
        "pregame"
        if snapshot_ts is not None and snapshot_ts < kickoff_hkt.astimezone(HKT)
        and fetched_at_hkt < kickoff_hkt.astimezone(HKT)
        else "invalid_or_postkickoff"
    )
    timestamp_scope = "analysis_page_global"
    complete = (
        phase == "pregame"
        and len(codes) == len(set(codes))
        and {str(item["outcome_group"]) for item in prices} == {"home", "draw", "away"}
        and not missing_exact
        and not missing_tail
        and timestamp_scope == "market_specific"
    )
    row_payload = json.dumps(raw_entries, ensure_ascii=False, separators=(",", ":"))
    raw_row_sha256 = hashlib.sha256(row_payload.encode("utf-8")).hexdigest()
    identity = "|".join(
        (
            issue, str(match_idx), "nowscore", provider_match_id, "crown",
            snapshot_ts.isoformat() if snapshot_ts else source_time_raw,
            raw_row_sha256, fetched_at_utc,
        )
    )
    snapshot_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    snapshot = {
        "snapshot_id": snapshot_id,
        "issue": str(issue),
        "match_idx": match_idx,
        "provider": "nowscore",
        "provider_match_id": provider_match_id,
        "nowscore_provider_match_id": provider_match_id,
        "bookmaker_key": "crown",
        "provider_company_id": "3",
        "market_key": "correct_score",
        "snapshot_ts_hkt": snapshot_ts.isoformat() if snapshot_ts else "",
        "source_time_raw": source_time_raw,
        "timestamp_grade": (
            "source_page_global_explicit_hkt" if snapshot_ts else "source_time_unparseable"
        ),
        "source_timestamp_scope": timestamp_scope,
        "fetched_at_utc": fetched_at_utc,
        "kickoff_hkt": kickoff_hkt.astimezone(HKT).isoformat(),
        "relative_label": "",
        "minutes_before_kickoff": (
            round((kickoff_hkt.astimezone(HKT) - snapshot_ts).total_seconds() / 60, 3)
            if snapshot_ts else -1
        ),
        "outcome_count": len(prices),
        "exact_score_count": len(NOWSCORE_REQUIRED_EXACT_OUTCOMES & set(codes)),
        "exact_score_complete": int(not missing_exact),
        "tail_outcome_count": len(REQUIRED_TAIL_OUTCOMES & set(codes)),
        "missing_exact_outcomes_json": json.dumps(missing_exact, separators=(",", ":")),
        "missing_required_outcomes_json": json.dumps(missing_required, separators=(",", ":")),
        "completeness_reason": "complete" if complete else (
            "missing_exact_score_outcomes" if missing_exact else
            "missing_tail_outcomes" if missing_tail else
            "source_timestamp_not_market_specific" if timestamp_scope != "market_specific" else
            "invalid_vector_or_timestamp"
        ),
        "outcome_schema_sha256": hashlib.sha256("|".join(sorted(codes)).encode("utf-8")).hexdigest(),
        "rejected_labels_json": json.dumps(rejected_labels, ensure_ascii=False, separators=(",", ":")),
        "complete": int(complete),
        "phase": phase,
        "source_url": source_url,
        "raw_file": raw_file,
        "raw_payload_sha256": raw_payload_sha256,
        "source_context_url": source_context_url,
        "source_context_file": source_context_file,
        "source_context_sha256": source_context_sha256,
        "raw_row_sha256": raw_row_sha256,
        "capture_batch_id": capture_batch_id,
        "capture_classification": "forward_observed_current_bookmaker_snapshot",
    }
    normalized_prices = [
        {
            "snapshot_id": snapshot_id,
            "issue": str(issue),
            "match_idx": match_idx,
            "provider": "nowscore",
            "provider_match_id": provider_match_id,
            "nowscore_provider_match_id": provider_match_id,
            "bookmaker_key": "crown",
            "provider_company_id": "3",
            "market_key": "correct_score",
            "snapshot_ts_hkt": snapshot["snapshot_ts_hkt"],
            "source_time_raw": source_time_raw,
            "timestamp_grade": snapshot["timestamp_grade"],
            "source_timestamp_scope": timestamp_scope,
            "fetched_at_utc": fetched_at_utc,
            "kickoff_hkt": snapshot["kickoff_hkt"],
            **price,
            "source_url": source_url,
            "raw_file": raw_file,
            "raw_payload_sha256": raw_payload_sha256,
            "source_context_url": source_context_url,
            "source_context_file": source_context_file,
            "source_context_sha256": source_context_sha256,
            "raw_row_sha256": raw_row_sha256,
            "capture_batch_id": capture_batch_id,
        }
        for price in prices
    ]
    return snapshot, normalized_prices


def select_latest_complete(
    rows: Sequence[Mapping[str, Any]],
    freeze_at_hkt: datetime,
) -> tuple[Mapping[str, Any] | None, str]:
    if not rows:
        return None, "no_persisted_snapshot"
    timestamped = [row for row in rows if row.get("snapshot_ts_hkt")]
    if not timestamped:
        return None, "source_timestamp_unavailable"
    complete = [
        row for row in timestamped
        if str(row.get("complete")) in {"1", "True", "true"}
        and str(row.get("phase")) == "pregame"
    ]
    if not complete:
        return None, "no_complete_snapshot"
    freeze = freeze_at_hkt.astimezone(HKT)
    eligible = [row for row in complete if datetime.fromisoformat(str(row["snapshot_ts_hkt"])) <= freeze]
    if not eligible:
        return None, "no_complete_snapshot_at_or_before_freeze"
    return max(eligible, key=lambda row: (str(row["snapshot_ts_hkt"]), str(row["snapshot_id"]))), ""


def verify_hashed_bundle(path: Path, expected_schema: str | None = None) -> dict[str, Any]:
    root = path.expanduser().resolve()
    sums = root / "SHA256SUMS"
    if not sums.is_file():
        raise CorrectScorePriceError(f"SHA256SUMS missing: {root}")
    entries: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise CorrectScorePriceError(f"invalid SHA256SUMS line: {line!r}") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or Path(name).is_absolute() or ".." in Path(name).parts:
            raise CorrectScorePriceError(f"invalid SHA256SUMS entry: {line!r}")
        if name in entries:
            raise CorrectScorePriceError(f"duplicate SHA256SUMS entry: {name}")
        target = root / name
        if not target.is_file() or sha256_file(target) != digest:
            raise CorrectScorePriceError(f"checksum mismatch: {target}")
        entries[name] = digest
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if set(entries) != actual_files:
        raise CorrectScorePriceError(
            "SHA256SUMS does not bind the complete capture bundle file set"
        )
    manifest_path = root / "manifest.json"
    if "manifest.json" not in entries:
        raise CorrectScorePriceError("manifest.json is not hash-bound")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if expected_schema and manifest.get("schema_version") != expected_schema:
        raise CorrectScorePriceError(
            f"unexpected schema: {manifest.get('schema_version')} != {expected_schema}"
        )
    policy = manifest.get("policy", {})
    for key in (
        "execution_enabled", "frontend_selectable", "roi_authorized",
        "ticket_output_enabled", "release_manifest_enabled",
    ):
        if policy.get(key) is not False:
            raise CorrectScorePriceError(f"unsafe policy flag: {key}")
    return {
        "status": "valid",
        "files": len(entries),
        "sha256s_sha256": sha256_file(sums),
        "manifest": manifest,
    }


def publish_immutable_bundle(stage: Path, final: Path) -> None:
    files = sorted(path for path in stage.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    (stage / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(path)}  {path.relative_to(stage).as_posix()}\n" for path in files),
        encoding="utf-8",
    )
    if final.exists():
        raise CorrectScorePriceError(f"immutable bundle already exists: {final}")
    final.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(final)
    parent_fd = os.open(final.parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def make_stage(final: Path) -> Path:
    final.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f".{final.name}.tmp-", dir=final.parent))


def discard_stage(stage: Path) -> None:
    if stage.exists():
        shutil.rmtree(stage)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
