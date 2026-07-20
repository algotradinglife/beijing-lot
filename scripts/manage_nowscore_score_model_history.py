#!/usr/bin/env python3
"""Capture immutable Nowscore odds history and build strict segment replays."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multimarket_p0 import HKT, resolve_kickoff_hkt, sha256_file  # noqa: E402
from src.nowscore_score_model_history import (  # noqa: E402
    CAPTURE_SCHEMA,
    MARKETS,
    REPLAY_SCHEMA,
    ScoreModelHistoryError,
    WILLIAM_HILL,
    euro_history_url,
    over_under_history_url,
    parse_euro_history_js,
    parse_over_under_history_json,
    select_latest_complete,
    snapshot_record,
    verify_hashed_bundle,
)


DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_CAPTURE_ROOT = ROOT / "results/data_collection/nowscore_score_model_history_v1"
DEFAULT_REPLAY_ROOT = ROOT / "results/research/nowscore_score_model_segment_replay_v1"
USER_AGENT = "Mozilla/5.0 (compatible; BeijingLotResearch/1.0)"
POLICY = {
    "execution_enabled": False,
    "roi_authorized": False,
    "formal_strategy_input": False,
    "ticket_output_enabled": False,
    "terminal_500_sp_allowed": False,
    "capture_classification": "third_party_timestamped_archive",
}
MARKET_UNAVAILABLE_ERRORS = (
    "Titan Euro company missing:",
    "Titan Euro company history missing:",
    "Titan Euro company history empty:",
    "Titan O/U history is empty",
)
SNAPSHOT_FIELDS = (
    "snapshot_id", "issue", "match_idx", "provider_match_id", "bookmaker_key",
    "provider_company_id", "provider_company_name", "market_key", "snapshot_ts_hkt",
    "source_time_raw", "time_normalization_status",
    "fetched_at_utc", "kickoff_hkt", "odds_json", "line_text", "line_value", "phase",
    "complete", "source_id", "source_url", "raw_file", "raw_payload_sha256", "raw_row_sha256",
    "capture_batch_id", "capture_classification",
)
PAGE_FIELDS = (
    "issue", "match_idx", "provider_match_id", "bookmaker_key", "market_key",
    "provider_company_id", "provider_company_name", "source_url", "raw_file",
    "raw_payload_sha256", "fetched_at_utc", "snapshot_rows", "complete_pregame_rows",
    "candidate_rows", "timestamp_rejected_rows", "incomplete_rows",
    "status", "error",
)
SELECTED_FIELDS = (
    "issue", "segment_idx", "match_idx", "provider_match_id", "bookmaker_key",
    "provider_company_id", "provider_company_name", "market_key", "freeze_at_hkt",
    "kickoff_hkt", "snapshot_ts_hkt", "fetched_at_utc",
    "minutes_to_kickoff", "snapshot_staleness_minutes", "odds_json", "line_text", "line_value",
    "source_id", "source_url", "source_time_raw", "time_normalization_status", "snapshot_id",
    "raw_file", "raw_payload_sha256", "raw_row_sha256", "capture_batch_id", "capture_bundle",
    "capture_bundle_sha256s_sha256", "capture_classification",
)
MISSING_FIELDS = (
    "issue", "segment_idx", "match_idx", "provider_match_id", "bookmaker_key",
    "provider_company_id", "market_key", "freeze_at_hkt", "kickoff_hkt",
    "minutes_to_kickoff", "missing_reason",
    "timestamp_normalization_results_json", "capture_bundles_json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture")
    capture.add_argument("--issue", required=True)
    capture.add_argument("--segment-idx", nargs="+", type=int, required=True)
    capture.add_argument("--bookmaker-key", default=WILLIAM_HILL["bookmaker_key"])
    capture.add_argument("--euro-company-id", type=int, default=WILLIAM_HILL["euro_company_id"])
    capture.add_argument("--over-under-company-id", type=int, default=WILLIAM_HILL["over_under_company_id"])
    capture.add_argument("--db", type=Path, default=DEFAULT_DB)
    capture.add_argument("--output-root", type=Path, default=DEFAULT_CAPTURE_ROOT)
    capture.add_argument("--workers", type=int, default=4)
    capture.add_argument("--timeout", type=float, default=30)
    capture.add_argument("--retries", type=int, default=2)
    capture.add_argument("--allow-partial", action="store_true")
    capture.add_argument("--collector-checkpoint-id", default="")
    capture.add_argument(
        "--collector-trigger",
        choices=("manual", "prefreeze", "freeze", "late_recovery"),
        default="manual",
    )

    replay = sub.add_parser("replay")
    replay.add_argument("--issue", required=True)
    replay.add_argument("--segment-idx", type=int, required=True)
    replay.add_argument("--capture-bundle", nargs="+", type=Path, required=True)
    replay.add_argument("--db", type=Path, default=DEFAULT_DB)
    replay.add_argument("--output-root", type=Path, default=DEFAULT_REPLAY_ROOT)

    verify = sub.add_parser("verify")
    verify.add_argument("bundle", type=Path)
    verify.add_argument("--schema", choices=(CAPTURE_SCHEMA, REPLAY_SCHEMA))
    return parser.parse_args()


def _connect_ro(db: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{db.expanduser().resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _parse_hkt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HKT)
    return parsed.astimezone(HKT)


def load_segment(connection: sqlite3.Connection, issue: str, segment_idx: int) -> dict[str, Any]:
    row = connection.execute(
        "SELECT freeze_at,match_indices_json FROM segment_decision_windows WHERE issue=? AND segment_idx=?",
        (issue, segment_idx),
    ).fetchone()
    if row is None:
        raise ScoreModelHistoryError(f"segment window missing: {issue}#{segment_idx}")
    return {
        "segment_idx": segment_idx,
        "freeze_at_hkt": _parse_hkt(str(row["freeze_at"])),
        "match_indices": [int(value) for value in json.loads(row["match_indices_json"])],
    }


def load_matches(connection: sqlite3.Connection, issue: str, indices: Iterable[int]) -> dict[int, dict[str, Any]]:
    requested = sorted(set(indices))
    if not requested:
        return {}
    placeholders = ",".join("?" for _ in requested)
    rows = connection.execute(
        f"""
        SELECT m.match_idx,m.end_time,COALESCE(n.kickoff_time,'') kickoff_time,
               COALESCE(n.provider_match_id,'') provider_match_id,m.home,m.away
        FROM matches m LEFT JOIN nowscore_bjdc_matches n
          ON n.issue=m.issue AND n.match_idx=m.match_idx
        WHERE m.issue=? AND m.match_idx IN ({placeholders}) ORDER BY m.match_idx
        """,
        (issue, *requested),
    ).fetchall()
    matches: dict[int, dict[str, Any]] = {}
    for row in rows:
        match_idx = int(row["match_idx"])
        provider_id = str(row["provider_match_id"] or "").strip()
        kickoff = resolve_kickoff_hkt(str(row["end_time"] or ""), str(row["kickoff_time"] or ""))
        matches[match_idx] = {
            "issue": issue,
            "match_idx": match_idx,
            "provider_match_id": provider_id,
            "kickoff_hkt": kickoff,
            "home": str(row["home"] or ""),
            "away": str(row["away"] or ""),
        }
    missing = set(requested) - set(matches)
    if missing:
        raise ScoreModelHistoryError(f"local matches missing: {sorted(missing)}")
    return matches


def fetch_page(
    url: str,
    timeout: float,
    retries: int,
    *,
    prime_url: str = "",
) -> tuple[bytes, str]:
    error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            session = requests.Session()
            headers = {
                "User-Agent": USER_AGENT,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            if prime_url:
                prime = session.get(prime_url, timeout=timeout, headers=headers)
                prime.raise_for_status()
                headers.update({"Referer": prime_url, "X-Requested-With": "XMLHttpRequest"})
            response = session.get(url, timeout=timeout, headers=headers)
            response.raise_for_status()
            fetched_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            return response.content, fetched_at
        except requests.RequestException as exc:
            error = exc
    raise RuntimeError(f"fetch failed after {retries + 1} attempts: {url}: {error}")


def write_csv(path: Path, rows: list[Mapping[str, Any]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify_score_model_bundle(path: Path, *, expected_schema: str | None = None) -> dict[str, Any]:
    root = path.expanduser().resolve()
    verification = verify_hashed_bundle(root, expected_schema=expected_schema)
    manifest = verification["manifest"]
    schema = manifest.get("schema_version")
    if schema == CAPTURE_SCHEMA:
        with (root / "page_inventory.csv").open(encoding="utf-8", newline="") as handle:
            pages = list(csv.DictReader(handle))
        for page in pages:
            has_raw_link = bool(page["raw_file"] and page["raw_payload_sha256"])
            if not has_raw_link and page["status"] not in {"ok", "unavailable"}:
                continue
            raw = root / page["raw_file"]
            if not raw.is_file() or sha256_file(raw) != page["raw_payload_sha256"]:
                raise ScoreModelHistoryError(f"capture raw payload link mismatch: {page['raw_file']}")
    elif schema == REPLAY_SCHEMA:
        capture_by_path: dict[str, dict[str, Any]] = {}
        for item in manifest.get("capture_bundles", []):
            capture = Path(item["path"]).expanduser().resolve()
            linked = verify_hashed_bundle(capture, expected_schema=CAPTURE_SCHEMA)
            if linked["sha256s_sha256"] != item["sha256s_sha256"]:
                raise ScoreModelHistoryError(f"replay capture digest mismatch: {capture}")
            capture_by_path[str(capture)] = linked
        freeze_at = datetime.fromisoformat(manifest["freeze_at_hkt"])
        with (root / "selected_legs.csv").open(encoding="utf-8", newline="") as handle:
            selected = list(csv.DictReader(handle))
        for leg in selected:
            capture = Path(leg["capture_bundle"]).expanduser().resolve()
            if str(capture) not in capture_by_path:
                raise ScoreModelHistoryError(f"selected leg capture is not declared: {capture}")
            if leg["capture_bundle_sha256s_sha256"] != capture_by_path[str(capture)]["sha256s_sha256"]:
                raise ScoreModelHistoryError(f"selected leg capture digest mismatch: {leg['snapshot_id']}")
            raw = capture / leg["raw_file"]
            if not raw.is_file() or sha256_file(raw) != leg["raw_payload_sha256"]:
                raise ScoreModelHistoryError(f"selected leg raw payload mismatch: {leg['snapshot_id']}")
            if datetime.fromisoformat(leg["snapshot_ts_hkt"]) > freeze_at:
                raise ScoreModelHistoryError(f"selected leg is after freeze: {leg['snapshot_id']}")
            if float(leg["snapshot_staleness_minutes"]) < 0:
                raise ScoreModelHistoryError(f"negative snapshot staleness: {leg['snapshot_id']}")
    else:
        raise ScoreModelHistoryError(f"unsupported score-model bundle schema: {schema}")
    return verification


def publish_bundle(stage: Path, final: Path) -> None:
    files = sorted(path for path in stage.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    (stage / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(path)}  {path.relative_to(stage).as_posix()}\n" for path in files),
        encoding="utf-8",
    )
    if final.exists():
        raise ScoreModelHistoryError(f"immutable bundle already exists: {final}")
    final.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(final)
    parent_fd = os.open(final.parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def is_market_unavailable_error(exc: Exception) -> bool:
    return isinstance(exc, ScoreModelHistoryError) and str(exc).startswith(MARKET_UNAVAILABLE_ERRORS)


def capture(arguments: argparse.Namespace) -> dict[str, Any]:
    connection = _connect_ro(arguments.db)
    try:
        segments = [load_segment(connection, arguments.issue, value) for value in arguments.segment_idx]
        indices = sorted({idx for segment in segments for idx in segment["match_indices"]})
        matches = load_matches(connection, arguments.issue, indices)
    finally:
        connection.close()
    missing_provider = [idx for idx, match in matches.items() if not match["provider_match_id"]]
    missing_kickoff = [idx for idx, match in matches.items() if match["kickoff_hkt"] is None]
    if missing_provider or missing_kickoff:
        raise ScoreModelHistoryError(
            f"capture prerequisites missing: provider={missing_provider}, kickoff={missing_kickoff}"
        )

    started_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    identity = json.dumps(
        {
            "issue": arguments.issue,
            "segments": sorted(set(arguments.segment_idx)),
            "bookmaker_key": arguments.bookmaker_key,
            "euro_company_id": arguments.euro_company_id,
            "over_under_company_id": arguments.over_under_company_id,
            "started_at": started_at,
        },
        sort_keys=True,
    )
    batch_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    final = arguments.output_root.expanduser().resolve() / arguments.issue / batch_id
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{batch_id}.tmp-", dir=final.parent))
    raw_root = stage / "raw"
    raw_root.mkdir()
    snapshot_rows: list[dict[str, Any]] = []
    page_rows: list[dict[str, Any]] = []
    tasks = [(match, market_key) for match in matches.values() for market_key in MARKETS]
    try:
        with ThreadPoolExecutor(max_workers=max(1, arguments.workers)) as pool:
            futures = {}
            for match, market_key in tasks:
                provider_id = str(match["provider_match_id"])
                if market_key == "euro_1x2":
                    url = euro_history_url(provider_id)
                    future = pool.submit(fetch_page, url, arguments.timeout, arguments.retries)
                else:
                    url = over_under_history_url(
                        provider_id, arguments.over_under_company_id, match["kickoff_hkt"]
                    )
                    prime_url = f"https://live.nowscore.com/odds/match/{provider_id}.htm"
                    future = pool.submit(
                        fetch_page,
                        url,
                        arguments.timeout,
                        arguments.retries,
                        prime_url=prime_url,
                    )
                futures[future] = (match, market_key, url)
            for future in as_completed(futures):
                match, market_key, url = futures[future]
                provider_id = str(match["provider_match_id"])
                company_id = (
                    arguments.euro_company_id
                    if market_key == "euro_1x2"
                    else arguments.over_under_company_id
                )
                suffix = "euro.js" if market_key == "euro_1x2" else f"ou_company_{company_id}.json"
                raw_name = f"{int(match['match_idx']):03d}_{provider_id}_{suffix}"
                base: dict[str, Any] = {
                    "issue": arguments.issue,
                    "match_idx": match["match_idx"],
                    "provider_match_id": provider_id,
                    "bookmaker_key": arguments.bookmaker_key,
                    "market_key": market_key,
                    "provider_company_id": company_id,
                    "provider_company_name": "",
                    "source_url": url,
                    "raw_file": f"raw/{raw_name}",
                    "raw_payload_sha256": "",
                    "fetched_at_utc": "",
                    "snapshot_rows": 0,
                    "complete_pregame_rows": 0,
                    "candidate_rows": 0,
                    "timestamp_rejected_rows": 0,
                    "incomplete_rows": 0,
                    "status": "error",
                    "error": "",
                }
                try:
                    payload, fetched_at = future.result()
                    raw_path = raw_root / raw_name
                    raw_path.write_bytes(payload)
                    payload_sha = hashlib.sha256(payload).hexdigest()
                    base.update(
                        {
                            "raw_payload_sha256": payload_sha,
                            "fetched_at_utc": fetched_at,
                        }
                    )
                    if market_key == "euro_1x2":
                        company_name, parsed, counters = parse_euro_history_js(
                            payload,
                            kickoff_hkt=match["kickoff_hkt"],
                            company_id=company_id,
                        )
                    else:
                        parsed, counters = parse_over_under_history_json(
                            payload,
                            kickoff_hkt=match["kickoff_hkt"],
                        )
                        company_name = "William Hill" if arguments.bookmaker_key == "william_hill" else arguments.bookmaker_key
                    records = [
                        snapshot_record(
                            item,
                            issue=arguments.issue,
                            match_idx=int(match["match_idx"]),
                            provider_match_id=provider_id,
                            bookmaker_key=arguments.bookmaker_key,
                            provider_company_id=company_id,
                            provider_company_name=company_name,
                            kickoff_hkt=match["kickoff_hkt"],
                            fetched_at_utc=fetched_at,
                            source_url=url,
                            raw_file=f"raw/{raw_name}",
                            raw_payload_sha256=payload_sha,
                            capture_batch_id=batch_id,
                        )
                        for item in parsed
                    ]
                    snapshot_rows.extend(records)
                    base.update(
                        {
                            "provider_company_name": company_name,
                            "snapshot_rows": len(records),
                            "complete_pregame_rows": sum(row["complete"] == 1 for row in records),
                            **counters,
                            "status": "ok",
                        }
                    )
                except Exception as exc:
                    unavailable = is_market_unavailable_error(exc)
                    base["status"] = "unavailable" if unavailable else "error"
                    prefix = "market_unavailable" if unavailable else type(exc).__name__
                    base["error"] = f"{prefix}: {exc}"
                    if not arguments.allow_partial:
                        raise
                page_rows.append(base)

        snapshot_rows.sort(
            key=lambda row: (
                int(row["match_idx"]), row["bookmaker_key"], row["market_key"],
                row["snapshot_ts_hkt"], row["snapshot_id"],
            )
        )
        page_rows.sort(key=lambda row: (int(row["match_idx"]), row["market_key"]))
        if not snapshot_rows:
            raise ScoreModelHistoryError("capture produced no parsed history snapshots")
        write_csv(stage / "snapshots.csv", snapshot_rows, SNAPSHOT_FIELDS)
        write_csv(stage / "page_inventory.csv", page_rows, PAGE_FIELDS)
        manifest = {
            "schema_version": CAPTURE_SCHEMA,
            "issue": arguments.issue,
            "capture_batch_id": batch_id,
            "created_at_utc": started_at,
            "collector_checkpoint_id": arguments.collector_checkpoint_id,
            "collector_trigger": arguments.collector_trigger,
            "segment_indices": sorted(set(arguments.segment_idx)),
            "match_indices": indices,
            "bookmaker_key": arguments.bookmaker_key,
            "provider_company_ids": {
                "euro_1x2": arguments.euro_company_id,
                "over_under": arguments.over_under_company_id,
            },
            "source_endpoints": {
                "euro_1x2": "1x2d.titan007.com/{provider_match_id}.js",
                "over_under": "m.titan007.com/HandicapDataInterface.ashx?oddskind=1",
            },
            "markets": list(MARKETS),
            "requested_pages": len(tasks),
            "successful_pages": sum(row["status"] == "ok" for row in page_rows),
            "unavailable_pages": sum(row["status"] == "unavailable" for row in page_rows),
            "failed_pages": sum(row["status"] == "error" for row in page_rows),
            "snapshot_rows": len(snapshot_rows),
            "complete_pregame_rows": sum(row["complete"] == 1 for row in snapshot_rows),
            "append_only_key": "capture_batch_id; no (issue,match_idx) overwrite",
            "policy": POLICY,
            "status": (
                "complete"
                if all(row["status"] == "ok" for row in page_rows)
                else "complete_with_exclusions"
                if all(row["status"] in {"ok", "unavailable"} for row in page_rows)
                else "partial"
            ),
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        publish_bundle(stage, final)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    verification = verify_score_model_bundle(final, expected_schema=CAPTURE_SCHEMA)
    return {**manifest, "output_dir": str(final), "verification": {key: value for key, value in verification.items() if key != "manifest"}}


def _read_capture_rows(bundles: list[Path]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    rows: list[dict[str, str]] = []
    bundle_metadata: list[dict[str, Any]] = []
    for bundle in bundles:
        root = bundle.expanduser().resolve()
        verification = verify_hashed_bundle(root, expected_schema=CAPTURE_SCHEMA)
        manifest = verification["manifest"]
        with (root / "snapshots.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                row["_capture_bundle"] = str(root)
                row["_capture_bundle_sha"] = verification["sha256s_sha256"]
                rows.append(row)
        bundle_metadata.append(
            {
                "path": str(root),
                "capture_batch_id": manifest["capture_batch_id"],
                "sha256s_sha256": verification["sha256s_sha256"],
                "bookmaker_key": manifest["bookmaker_key"],
                "provider_company_ids": manifest["provider_company_ids"],
            }
        )
    return rows, bundle_metadata


def replay(arguments: argparse.Namespace) -> dict[str, Any]:
    connection = _connect_ro(arguments.db)
    try:
        segment = load_segment(connection, arguments.issue, arguments.segment_idx)
        matches = load_matches(connection, arguments.issue, segment["match_indices"])
    finally:
        connection.close()
    capture_rows, bundle_metadata = _read_capture_rows(arguments.capture_bundle)
    capture_rows = [row for row in capture_rows if row["issue"] == arguments.issue]
    bookmaker_keys = sorted({row["bookmaker_key"] for row in capture_rows})
    company_by_market = {
        market: int(metadata["provider_company_ids"][market])
        for metadata in bundle_metadata
        for market in MARKETS
    }
    freeze_at = segment["freeze_at_hkt"]
    selected_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    for match_idx in segment["match_indices"]:
        match = matches[match_idx]
        kickoff = match["kickoff_hkt"]
        if kickoff is None:
            raise ScoreModelHistoryError(f"kickoff missing: {arguments.issue}#{match_idx}")
        countdown = round((kickoff - freeze_at).total_seconds() / 60, 3)
        for bookmaker_key in bookmaker_keys:
            for market_key in MARKETS:
                provider_company_id = company_by_market[market_key]
                candidates = [
                    row
                    for row in capture_rows
                    if int(row["match_idx"]) == match_idx
                    and row["bookmaker_key"] == bookmaker_key
                    and row["market_key"] == market_key
                ]
                selected, reason = select_latest_complete(candidates, freeze_at)
                if selected is None or countdown <= 0:
                    missing_rows.append(
                        {
                            "issue": arguments.issue,
                            "segment_idx": arguments.segment_idx,
                            "match_idx": match_idx,
                            "provider_match_id": match["provider_match_id"],
                            "bookmaker_key": bookmaker_key,
                            "provider_company_id": provider_company_id,
                            "market_key": market_key,
                            "freeze_at_hkt": freeze_at.isoformat(),
                            "kickoff_hkt": kickoff.isoformat(),
                            "minutes_to_kickoff": countdown,
                            "missing_reason": "freeze_not_before_kickoff" if countdown <= 0 else reason,
                            "timestamp_normalization_results_json": json.dumps(
                                sorted({row["time_normalization_status"] for row in candidates}),
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            "capture_bundles_json": json.dumps(bundle_metadata, ensure_ascii=False, sort_keys=True),
                        }
                    )
                    continue
                snapshot_ts = datetime.fromisoformat(selected["snapshot_ts_hkt"])
                selected_rows.append(
                    {
                        "issue": arguments.issue,
                        "segment_idx": arguments.segment_idx,
                        "match_idx": match_idx,
                        "provider_match_id": selected["provider_match_id"],
                        "bookmaker_key": selected["bookmaker_key"],
                        "provider_company_id": selected["provider_company_id"],
                        "provider_company_name": selected["provider_company_name"],
                        "market_key": market_key,
                        "freeze_at_hkt": freeze_at.isoformat(),
                        "kickoff_hkt": kickoff.isoformat(),
                        "snapshot_ts_hkt": selected["snapshot_ts_hkt"],
                        "fetched_at_utc": selected["fetched_at_utc"],
                        "minutes_to_kickoff": countdown,
                        "snapshot_staleness_minutes": round((freeze_at - snapshot_ts).total_seconds() / 60, 3),
                        "odds_json": selected["odds_json"],
                        "line_text": selected["line_text"],
                        "line_value": selected["line_value"],
                        "source_id": selected["source_id"],
                        "source_url": selected["source_url"],
                        "source_time_raw": selected["source_time_raw"],
                        "time_normalization_status": selected["time_normalization_status"],
                        "snapshot_id": selected["snapshot_id"],
                        "raw_file": selected["raw_file"],
                        "raw_payload_sha256": selected["raw_payload_sha256"],
                        "raw_row_sha256": selected["raw_row_sha256"],
                        "capture_batch_id": selected["capture_batch_id"],
                        "capture_bundle": selected["_capture_bundle"],
                        "capture_bundle_sha256s_sha256": selected["_capture_bundle_sha"],
                        "capture_classification": selected["capture_classification"],
                    }
                )
    selected_rows.sort(key=lambda row: (int(row["match_idx"]), row["bookmaker_key"], row["market_key"]))
    missing_rows.sort(key=lambda row: (int(row["match_idx"]), row["bookmaker_key"], row["market_key"]))
    created_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    identity = json.dumps(
        {
            "issue": arguments.issue,
            "segment_idx": arguments.segment_idx,
            "freeze_at": freeze_at.isoformat(),
            "captures": bundle_metadata,
            "created_at": created_at,
        },
        sort_keys=True,
    )
    replay_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    final = (
        arguments.output_root.expanduser().resolve()
        / arguments.issue
        / f"segment_{arguments.segment_idx}"
        / replay_id
    )
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{replay_id}.tmp-", dir=final.parent))
    try:
        write_csv(stage / "selected_legs.csv", selected_rows, SELECTED_FIELDS)
        write_csv(stage / "missing_legs.csv", missing_rows, MISSING_FIELDS)
        countdowns = sorted(
            {
                float(row["minutes_to_kickoff"])
                for row in [*selected_rows, *missing_rows]
            }
        )
        staleness = [float(row["snapshot_staleness_minutes"]) for row in selected_rows]
        manifest = {
            "schema_version": REPLAY_SCHEMA,
            "issue": arguments.issue,
            "segment_idx": arguments.segment_idx,
            "replay_id": replay_id,
            "created_at_utc": created_at,
            "freeze_at_hkt": freeze_at.isoformat(),
            "freeze_source": "segment_decision_windows.freeze_at",
            "match_indices": segment["match_indices"],
            "bookmaker_keys": bookmaker_keys,
            "provider_company_ids": company_by_market,
            "markets": list(MARKETS),
            "selected_legs": len(selected_rows),
            "missing_legs": len(missing_rows),
            "minutes_to_kickoff_min": min(countdowns) if countdowns else None,
            "minutes_to_kickoff_max": max(countdowns) if countdowns else None,
            "snapshot_staleness_minutes_min": min(staleness) if staleness else None,
            "snapshot_staleness_minutes_max": max(staleness) if staleness else None,
            "capture_bundles": bundle_metadata,
            "selection_rule": "latest complete pregame snapshot with snapshot_ts_hkt <= freeze_at_hkt",
            "timestamp_normalization": "Titan explicit year/timestamp normalized to timezone-aware HKT",
            "policy": POLICY,
            "status": "complete" if not missing_rows else "partial",
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        publish_bundle(stage, final)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    verification = verify_score_model_bundle(final, expected_schema=REPLAY_SCHEMA)
    return {**manifest, "output_dir": str(final), "verification": {key: value for key, value in verification.items() if key != "manifest"}}


def main() -> int:
    arguments = parse_args()
    if arguments.command == "capture":
        result: Any = capture(arguments)
    elif arguments.command == "replay":
        result = replay(arguments)
    else:
        result = verify_score_model_bundle(arguments.bundle, expected_schema=arguments.schema)
        result.pop("manifest", None)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
