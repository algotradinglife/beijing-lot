#!/usr/bin/env python3
"""Capture correct-score price history and build strict segment as-of replays."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.correct_score_price_history import (  # noqa: E402
    CAPTURE_SCHEMA,
    POLICY,
    REPLAY_SCHEMA,
    CorrectScorePriceError,
    discard_stage,
    make_stage,
    publish_immutable_bundle,
    select_latest_complete,
    sha256_file,
    snapshot_from_nowscore_crown_current,
    snapshot_from_history_row,
    utc_now,
    verify_hashed_bundle,
)
from src.multimarket_p0 import HKT, resolve_kickoff_hkt  # noqa: E402
from src.okooo_prekick_sp import (  # noqa: E402
    OkoooParseError,
    history_url,
    issue_url,
    parse_history_page,
    parse_issue_page,
)


DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_CAPTURE_ROOT = ROOT / "results/data_collection/correct_score_price_history_v1"
DEFAULT_REPLAY_ROOT = ROOT / "results/research/correct_score_price_segment_replay_v1"
DEFAULT_CHROME = Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe")
DEFAULT_AUTH_PROFILE = Path("/mnt/c/Users/hhusl/AppData/Local/OkoooCollectorProfile")
DEFAULT_NOWSCORE_PROFILE = Path("/mnt/c/Temp/BeidanNowscoreCorrectScoreCollector")
CDP_DUMP_HELPER = ROOT / "scripts/chrome_dump_via_cdp.mjs"

SNAPSHOT_FIELDS = (
    "snapshot_id", "issue", "match_idx", "provider", "provider_match_id",
    "nowscore_provider_match_id", "bookmaker_key", "provider_company_id", "market_key",
    "snapshot_ts_hkt", "source_time_raw", "timestamp_grade", "source_timestamp_scope",
    "fetched_at_utc", "kickoff_hkt",
    "relative_label", "minutes_before_kickoff", "outcome_count", "exact_score_count",
    "exact_score_complete", "tail_outcome_count",
    "missing_exact_outcomes_json", "missing_required_outcomes_json", "completeness_reason",
    "outcome_schema_sha256",
    "rejected_labels_json", "complete", "phase", "source_url", "raw_file",
    "raw_payload_sha256", "source_context_url", "source_context_file",
    "source_context_sha256", "raw_row_sha256", "capture_batch_id", "capture_classification",
)
PRICE_FIELDS = (
    "snapshot_id", "issue", "match_idx", "provider", "provider_match_id",
    "nowscore_provider_match_id", "bookmaker_key", "provider_company_id", "market_key",
    "snapshot_ts_hkt", "source_time_raw", "timestamp_grade", "source_timestamp_scope",
    "fetched_at_utc", "kickoff_hkt",
    "outcome_code", "outcome_group", "outcome_label", "sp", "raw_value", "field_index",
    "source_url", "raw_file", "raw_payload_sha256", "source_context_url",
    "source_context_file", "source_context_sha256", "raw_row_sha256", "capture_batch_id",
)
MAPPING_FIELDS = (
    "issue", "match_idx", "home", "away", "kickoff_hkt", "provider", "provider_match_id",
    "nowscore_provider_match_id", "source_home", "source_away", "source_kickoff_text",
    "mapping_status", "mapping_note",
    "mapping_source_bundle", "mapping_source_sha256s_sha256",
)
PAGE_FIELDS = (
    "issue", "match_idx", "provider", "provider_match_id", "nowscore_provider_match_id",
    "bookmaker_key", "provider_company_id", "market_key", "source_url", "raw_file",
    "raw_payload_sha256", "source_context_url", "source_context_file",
    "source_context_sha256", "fetched_at_utc", "history_rows", "complete_rows", "status", "error",
    "exact_score_complete_rows", "attempt_count", "attempts_json",
)
SELECTED_FIELDS = (
    "issue", "segment_idx", "match_idx", "provider", "provider_match_id",
    "nowscore_provider_match_id", "bookmaker_key", "provider_company_id", "market_key",
    "freeze_at_hkt", "kickoff_hkt", "snapshot_ts_hkt", "source_time_raw", "timestamp_grade",
    "source_timestamp_scope", "fetched_at_utc", "minutes_to_kickoff",
    "snapshot_staleness_minutes", "outcome_count",
    "outcome_schema_sha256", "snapshot_id", "source_url", "raw_file", "raw_payload_sha256",
    "raw_row_sha256", "capture_batch_id", "capture_bundle", "capture_bundle_sha256s_sha256",
    "capture_classification",
)
SELECTED_PRICE_FIELDS = SELECTED_FIELDS[:9] + (
    "freeze_at_hkt", "kickoff_hkt", "snapshot_ts_hkt", "source_time_raw", "timestamp_grade",
    "source_timestamp_scope", "minutes_to_kickoff", "snapshot_staleness_minutes",
    "outcome_code", "outcome_group",
    "outcome_label", "sp", "snapshot_id", "capture_bundle", "capture_bundle_sha256s_sha256",
)
MISSING_FIELDS = (
    "issue", "segment_idx", "match_idx", "provider", "provider_match_id",
    "nowscore_provider_match_id", "bookmaker_key", "provider_company_id", "market_key",
    "freeze_at_hkt", "kickoff_hkt", "minutes_to_kickoff", "missing_reason",
    "completeness_reasons_json", "missing_required_outcomes_json",
    "source_statuses_json", "timestamp_grades_json", "source_timestamp_scopes_json",
    "capture_bundles_json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--issue", required=True)
    capture.add_argument("--segment-idx", nargs="+", type=int, required=True)
    capture.add_argument("--db", type=Path, default=DEFAULT_DB)
    capture.add_argument("--output-root", type=Path, default=DEFAULT_CAPTURE_ROOT)
    capture.add_argument("--chrome", type=Path, default=DEFAULT_CHROME)
    capture.add_argument("--chrome-user-data-dir", type=Path, default=DEFAULT_AUTH_PROFILE)
    capture.add_argument("--profile-directory", default="Default")
    capture.add_argument("--provider", default="okooo")
    capture.add_argument("--bookmaker-key", default="william_hill")
    capture.add_argument("--provider-company-id", default="14")
    capture.add_argument("--match-limit", type=int)
    capture.add_argument("--page-attempts", type=int, default=3)
    capture.add_argument("--page-retry-delay", type=float, default=2.0)
    capture.add_argument("--allow-partial", action="store_true")
    capture.add_argument("--collector-checkpoint-id", default="")
    capture.add_argument(
        "--collector-trigger",
        choices=("manual", "prefreeze_observation", "prefreeze", "freeze", "late_recovery"),
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


def connect_ro(db: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{db.expanduser().resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def parse_hkt(value: str) -> datetime:
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
        raise CorrectScorePriceError(f"segment window missing: {issue}#{segment_idx}")
    return {
        "segment_idx": segment_idx,
        "freeze_at_hkt": parse_hkt(str(row["freeze_at"])),
        "match_indices": [int(value) for value in json.loads(row["match_indices_json"])],
    }


def load_matches(connection: sqlite3.Connection, issue: str, indices: Iterable[int]) -> dict[int, dict[str, Any]]:
    requested = sorted(set(indices))
    placeholders = ",".join("?" for _ in requested)
    rows = connection.execute(
        f"""
        SELECT m.match_idx,m.end_time,m.home,m.away,COALESCE(n.kickoff_time,'') kickoff_time,
               COALESCE(n.provider_match_id,'') nowscore_provider_match_id
        FROM matches m LEFT JOIN nowscore_bjdc_matches n
          ON n.issue=m.issue AND n.match_idx=m.match_idx
        WHERE m.issue=? AND m.match_idx IN ({placeholders}) ORDER BY m.match_idx
        """,
        (issue, *requested),
    ).fetchall()
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        kickoff = resolve_kickoff_hkt(str(row["end_time"] or ""), str(row["kickoff_time"] or ""))
        result[int(row["match_idx"])] = {
            "issue": issue,
            "match_idx": int(row["match_idx"]),
            "home": str(row["home"] or ""),
            "away": str(row["away"] or ""),
            "kickoff_hkt": kickoff,
            "nowscore_provider_match_id": str(row["nowscore_provider_match_id"] or ""),
        }
    missing = set(requested) - set(result)
    if missing:
        raise CorrectScorePriceError(f"local matches missing: {sorted(missing)}")
    return result


def write_csv(path: Path, rows: list[Mapping[str, Any]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def chrome_path_argument(path: Path, windows_chrome: bool) -> str:
    resolved = path.expanduser().resolve()
    if not windows_chrome:
        return str(resolved)
    converted = subprocess.run(
        ["wslpath", "-w", str(resolved)], capture_output=True, text=True, timeout=5, check=True,
    )
    return converted.stdout.strip()


class ChromeDumpFetcher:
    def __init__(self, executable: Path, user_data_dir: Path, profile_directory: str) -> None:
        self.executable = executable.expanduser().resolve()
        if not self.executable.is_file():
            raise FileNotFoundError(f"Chrome executable missing: {self.executable}")
        windows_chrome = str(self.executable).startswith("/mnt/")
        user_data_dir.expanduser().mkdir(parents=True, exist_ok=True)
        self.profile_argument = chrome_path_argument(user_data_dir, windows_chrome)
        self.profile_directory = profile_directory

    def fetch(self, url: str) -> tuple[bytes, str]:
        command = [
            str(self.executable), "--headless=new", "--disable-gpu", "--no-first-run",
            "--disable-background-networking", f"--user-data-dir={self.profile_argument}",
            f"--profile-directory={self.profile_directory}", "--dump-dom", url,
        ]
        completed = subprocess.run(command, capture_output=True, timeout=60, check=False)
        if completed.returncode != 0 or not completed.stdout.strip():
            error = completed.stderr.decode("utf-8", errors="replace")[-1000:]
            raise RuntimeError(f"Chrome dump failed rc={completed.returncode}: {error}")
        return completed.stdout, utc_now()

    def fetch_with_primes(self, url: str, prime_urls: list[str]) -> tuple[bytes, str]:
        command = [
            "node",
            str(CDP_DUMP_HELPER),
            "--chrome",
            str(self.executable),
            "--user-data-dir",
            self.profile_argument,
            "--profile-directory",
            self.profile_directory,
        ]
        for prime_url in prime_urls:
            command.extend(("--prime-url", prime_url))
        command.extend(("--url", url))
        completed = subprocess.run(command, capture_output=True, timeout=70, check=False)
        if completed.returncode != 0 or not completed.stdout.strip():
            error = completed.stderr.decode("utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"Chrome CDP dump failed rc={completed.returncode}: {error}")
        return completed.stdout, utc_now()


def load_cached_issue_matches(output_root: Path, issue: str) -> tuple[dict[int, Any], dict[str, str]]:
    issue_root = output_root.expanduser().resolve() / issue
    if not issue_root.is_dir():
        return {}, {}
    manifests = sorted(issue_root.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for manifest_path in manifests:
        raw_issue = manifest_path.parent / "raw/issue.html"
        if not raw_issue.is_file():
            continue
        try:
            verification = verify_hashed_bundle(manifest_path.parent, expected_schema=CAPTURE_SCHEMA)
            rows = parse_issue_page(raw_issue.read_bytes(), issue)
        except (OSError, CorrectScorePriceError, OkoooParseError):
            continue
        return (
            {row.match_idx: row for row in rows},
            {
                "path": str(manifest_path.parent.resolve()),
                "sha256s_sha256": verification["sha256s_sha256"],
            },
        )
    return {}, {}


def collect_nowscore_forward_observation(
    *,
    fetcher: ChromeDumpFetcher,
    raw_root: Path,
    raw_prefix: str,
    attempts: int,
    retry_delay: float,
    context_url: str,
    source_url: str,
    issue: str,
    match_idx: int,
    provider_match_id: str,
    kickoff_hkt: datetime,
    capture_batch_id: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any]]:
    """Retry one match, retaining every raw attempt and selecting the fullest vector."""
    audit: list[dict[str, Any]] = []
    best: tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]] | None = None
    for attempt in range(1, max(1, attempts) + 1):
        context_name = f"{raw_prefix}_attempt_{attempt}_analysis.html"
        odds_name = f"{raw_prefix}_attempt_{attempt}_correct_score.html"
        record: dict[str, Any] = {
            "attempt": attempt,
            "context_file": "",
            "context_sha256": "",
            "odds_file": "",
            "odds_sha256": "",
            "fetched_at_utc": "",
            "outcome_count": 0,
            "exact_score_complete": False,
            "status": "error",
            "error": "",
        }
        try:
            context_payload, _context_fetched_at = fetcher.fetch_with_primes(context_url, [])
            context_path = raw_root / context_name
            context_path.write_bytes(context_payload)
            context_sha = hashlib.sha256(context_payload).hexdigest()
            record.update(
                {
                    "context_file": f"raw/{context_name}",
                    "context_sha256": context_sha,
                }
            )

            payload, fetched_at = fetcher.fetch_with_primes(source_url, [context_url])
            raw_path = raw_root / odds_name
            raw_path.write_bytes(payload)
            payload_sha = hashlib.sha256(payload).hexdigest()
            record.update(
                {
                    "odds_file": f"raw/{odds_name}",
                    "odds_sha256": payload_sha,
                    "fetched_at_utc": fetched_at,
                }
            )
            snapshot, row_prices = snapshot_from_nowscore_crown_current(
                payload,
                context_payload,
                issue=issue,
                match_idx=match_idx,
                provider_match_id=provider_match_id,
                kickoff_hkt=kickoff_hkt,
                fetched_at_utc=fetched_at,
                source_url=source_url,
                raw_file=f"raw/{odds_name}",
                raw_payload_sha256=payload_sha,
                source_context_url=context_url,
                source_context_file=f"raw/{context_name}",
                source_context_sha256=context_sha,
                capture_batch_id=capture_batch_id,
            )
            exact_complete = bool(int(snapshot["exact_score_complete"]))
            record.update(
                {
                    "outcome_count": int(snapshot["outcome_count"]),
                    "exact_score_complete": exact_complete,
                    "status": "ok" if exact_complete else "incomplete_exact_score_vector",
                }
            )
            candidate = (snapshot, row_prices, dict(record))
            if best is None or int(snapshot["outcome_count"]) >= int(best[0]["outcome_count"]):
                best = candidate
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        audit.append(record)
        if record["exact_score_complete"]:
            break
        if attempt < max(1, attempts) and retry_delay > 0:
            time.sleep(retry_delay)

    if best is None:
        return None, [], {
            "raw_file": "",
            "raw_payload_sha256": "",
            "source_context_file": "",
            "source_context_sha256": "",
            "fetched_at_utc": "",
            "history_rows": 0,
            "exact_score_complete_rows": 0,
            "attempt_count": len(audit),
            "attempts_json": json.dumps(audit, ensure_ascii=False, sort_keys=True),
            "status": "error",
            "error": "; ".join(item["error"] for item in audit if item["error"]),
        }

    snapshot, row_prices, chosen = best
    return snapshot, row_prices, {
        "raw_file": chosen["odds_file"],
        "raw_payload_sha256": chosen["odds_sha256"],
        "source_context_file": chosen["context_file"],
        "source_context_sha256": chosen["context_sha256"],
        "fetched_at_utc": chosen["fetched_at_utc"],
        "history_rows": 1,
        "exact_score_complete_rows": int(chosen["exact_score_complete"]),
        "attempt_count": len(audit),
        "attempts_json": json.dumps(audit, ensure_ascii=False, sort_keys=True),
        "status": "pending_classification",
        "error": "",
    }


def capture(arguments: argparse.Namespace) -> dict[str, Any]:
    is_nowscore = str(arguments.provider).lower() == "nowscore"
    bookmaker_key = "crown" if is_nowscore else arguments.bookmaker_key
    provider_company_id = "3" if is_nowscore else str(arguments.provider_company_id)
    connection = connect_ro(arguments.db)
    try:
        segments = [load_segment(connection, arguments.issue, idx) for idx in arguments.segment_idx]
        indices = sorted({idx for segment in segments for idx in segment["match_indices"]})
        if arguments.match_limit is not None:
            indices = indices[: arguments.match_limit]
        matches = load_matches(connection, arguments.issue, indices)
    finally:
        connection.close()
    missing_kickoff = [idx for idx, row in matches.items() if row["kickoff_hkt"] is None]
    if missing_kickoff:
        raise CorrectScorePriceError(f"kickoff missing: {missing_kickoff}")

    created_at = utc_now()
    identity = json.dumps(
        {
            "issue": arguments.issue, "segments": sorted(set(arguments.segment_idx)),
            "indices": indices, "provider": arguments.provider, "bookmaker": bookmaker_key,
            "created_at": created_at,
        },
        sort_keys=True,
    )
    batch_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    final = arguments.output_root.expanduser().resolve() / arguments.issue / batch_id
    stage = make_stage(final)
    raw_root = stage / "raw"
    raw_root.mkdir()
    snapshots: list[dict[str, Any]] = []
    prices: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    profile_root = (
        DEFAULT_NOWSCORE_PROFILE
        if is_nowscore and arguments.chrome_user_data_dir == DEFAULT_AUTH_PROFILE
        else arguments.chrome_user_data_dir
    )
    fetcher = ChromeDumpFetcher(arguments.chrome, profile_root, arguments.profile_directory)
    source_matches, mapping_cache = (
        ({}, {}) if is_nowscore else load_cached_issue_matches(arguments.output_root, arguments.issue)
    )
    mapping_source = (
        "local_readonly_sqlite_nowscore_mapping"
        if is_nowscore else "immutable_capture_cache" if source_matches else "unavailable"
    )
    issue_error = ""
    try:
        if not is_nowscore:
            try:
                issue_payload, _issue_fetched_at = fetcher.fetch(issue_url(arguments.issue))
                (raw_root / "issue.html").write_bytes(issue_payload)
                source_matches = {row.match_idx: row for row in parse_issue_page(issue_payload, arguments.issue)}
                mapping_source = "current_issue_page"
                mapping_cache = {}
            except Exception as exc:
                issue_error = f"{type(exc).__name__}: {exc}"
                if not arguments.allow_partial:
                    raise
        for match_idx in indices:
            match = matches[match_idx]
            source_match = source_matches.get(match_idx) if not is_nowscore else None
            provider_match_id = (
                match["nowscore_provider_match_id"]
                if is_nowscore else source_match.match_id if source_match else ""
            )
            mapping_status = (
                f"mapped_by_issue_match_idx:{mapping_source}"
                if provider_match_id else "provider_match_unmapped"
            )
            mappings.append(
                {
                    "issue": arguments.issue,
                    "match_idx": match_idx,
                    "home": match["home"],
                    "away": match["away"],
                    "kickoff_hkt": match["kickoff_hkt"].astimezone(HKT).isoformat(),
                    "provider": arguments.provider,
                    "provider_match_id": provider_match_id,
                    "nowscore_provider_match_id": match["nowscore_provider_match_id"],
                    "source_home": source_match.home if source_match else match["home"] if is_nowscore else "",
                    "source_away": source_match.away if source_match else match["away"] if is_nowscore else "",
                    "source_kickoff_text": source_match.kickoff_text if source_match else "",
                    "mapping_status": mapping_status,
                    "mapping_note": "issue+match_idx is the stable cross-provider join; names retained for audit",
                    "mapping_source_bundle": mapping_cache.get("path", ""),
                    "mapping_source_sha256s_sha256": mapping_cache.get("sha256s_sha256", ""),
                }
            )
            if is_nowscore and provider_match_id:
                context_url = f"https://live.nowscore.com/analysis/{provider_match_id}cn.html"
                url = f"https://live.nowscore.com/analysis/odds/{provider_match_id}.htm"
            else:
                context_url = ""
                url = history_url(provider_match_id, "correct_score", provider_company_id) if provider_match_id else ""
            raw_name = f"{match_idx:03d}_{provider_match_id or 'unmapped'}_correct_score.html"
            context_name = f"{match_idx:03d}_{provider_match_id or 'unmapped'}_analysis.html"
            page = {
                "issue": arguments.issue,
                "match_idx": match_idx,
                "provider": arguments.provider,
                "provider_match_id": provider_match_id,
                "nowscore_provider_match_id": match["nowscore_provider_match_id"],
                "bookmaker_key": bookmaker_key,
                "provider_company_id": provider_company_id,
                "market_key": "correct_score",
                "source_url": url,
                "raw_file": "",
                "raw_payload_sha256": "",
                "source_context_url": context_url,
                "source_context_file": "",
                "source_context_sha256": "",
                "fetched_at_utc": "",
                "history_rows": 0,
                "complete_rows": 0,
                "exact_score_complete_rows": 0,
                "attempt_count": 0,
                "attempts_json": "[]",
                "status": (
                    "source_blocked"
                    if not source_match and "blocked" in issue_error
                    else "provider_match_unmapped"
                ),
                "error": issue_error if not source_match else "",
            }
            if provider_match_id:
                try:
                    if is_nowscore:
                        snapshot, row_prices, page_updates = collect_nowscore_forward_observation(
                            fetcher=fetcher,
                            raw_root=raw_root,
                            raw_prefix=f"{match_idx:03d}_{provider_match_id}",
                            attempts=int(getattr(arguments, "page_attempts", 3)),
                            retry_delay=float(getattr(arguments, "page_retry_delay", 2.0)),
                            context_url=context_url,
                            source_url=url,
                            issue=arguments.issue,
                            match_idx=match_idx,
                            provider_match_id=provider_match_id,
                            kickoff_hkt=match["kickoff_hkt"],
                            capture_batch_id=batch_id,
                        )
                        page.update(page_updates)
                        if snapshot is not None:
                            snapshots.append(snapshot)
                            prices.extend(row_prices)
                        elif not arguments.allow_partial:
                            raise CorrectScorePriceError(
                                f"Nowscore correct-score capture failed: {arguments.issue}#{match_idx}"
                            )
                    else:
                        payload, fetched_at = fetcher.fetch_with_primes(
                            url,
                            [
                                f"https://www.okooo.com/soccer/match/{provider_match_id}/",
                                f"https://www.okooo.com/soccer/match/{provider_match_id}/cs/",
                            ],
                        )
                        raw_path = raw_root / raw_name
                        raw_path.write_bytes(payload)
                        payload_sha = hashlib.sha256(payload).hexdigest()
                        page.update(
                            {
                                "raw_file": f"raw/{raw_name}",
                                "raw_payload_sha256": payload_sha,
                                "fetched_at_utc": fetched_at,
                                "attempt_count": 1,
                            }
                        )
                        history_rows = parse_history_page(payload, url)
                        page["history_rows"] = len(history_rows)
                        for history_row in history_rows:
                            snapshot, row_prices = snapshot_from_history_row(
                                history_row,
                                issue=arguments.issue,
                                match_idx=match_idx,
                                provider_match_id=provider_match_id,
                                nowscore_provider_match_id=match["nowscore_provider_match_id"],
                                kickoff_hkt=match["kickoff_hkt"],
                                fetched_at_utc=fetched_at,
                                source_url=url,
                                raw_file=f"raw/{raw_name}",
                                raw_payload_sha256=payload_sha,
                                capture_batch_id=batch_id,
                                provider=arguments.provider,
                                bookmaker_key=bookmaker_key,
                                provider_company_id=provider_company_id,
                            )
                            snapshots.append(snapshot)
                            prices.extend(row_prices)
                    match_snapshots = [
                        row for row in snapshots if int(row["match_idx"]) == match_idx
                    ]
                    page["complete_rows"] = sum(int(row["complete"]) for row in match_snapshots)
                    if match_snapshots:
                        page["status"] = "ok" if page["complete_rows"] else "no_complete_snapshot"
                    if match_snapshots and page["status"] != "ok":
                        reasons = sorted(
                            {
                                str(row.get("completeness_reason") or "")
                                for row in match_snapshots
                            }
                        )
                        page["status"] = (
                            "incomplete_outcome_schema"
                            if any(reason.startswith("missing_") for reason in reasons)
                            else "no_complete_snapshot"
                        )
                        page["error"] = ";".join(reasons) or (
                            "parsed source contains no complete pregame correct-score vector"
                        )
                except Exception as exc:
                    page["status"] = (
                        "source_blocked" if isinstance(exc, OkoooParseError) and "blocked" in str(exc) else "error"
                    )
                    page["error"] = f"{type(exc).__name__}: {exc}"
                    if not arguments.allow_partial:
                        raise
            pages.append(page)

        snapshots.sort(key=lambda row: (int(row["match_idx"]), row["snapshot_ts_hkt"], row["snapshot_id"]))
        prices.sort(key=lambda row: (int(row["match_idx"]), row["snapshot_ts_hkt"], row["outcome_code"]))
        write_csv(stage / "snapshots.csv", snapshots, SNAPSHOT_FIELDS)
        write_csv(stage / "prices.csv", prices, PRICE_FIELDS)
        write_csv(stage / "mapping_inventory.csv", mappings, MAPPING_FIELDS)
        write_csv(stage / "page_inventory.csv", pages, PAGE_FIELDS)
        manifest = {
            "schema_version": CAPTURE_SCHEMA,
            "issue": arguments.issue,
            "capture_batch_id": batch_id,
            "created_at_utc": created_at,
            "collector_checkpoint_id": arguments.collector_checkpoint_id,
            "collector_trigger": arguments.collector_trigger,
            "segment_indices": sorted(set(arguments.segment_idx)),
            "match_indices": indices,
            "provider": arguments.provider,
            "bookmaker_key": bookmaker_key,
            "provider_company_id": provider_company_id,
            "source_endpoint": (
                "live.nowscore.com/analysis/odds/{provider_match_id}.htm"
                if is_nowscore else "okooo.com/soccer/match/{provider_match_id}/cs/change/{company_id}/"
            ),
            "market": "correct_score",
            "snapshot_rows": len(snapshots),
            "price_rows": len(prices),
            "complete_snapshot_rows": sum(int(row["complete"]) for row in snapshots),
            "exact_score_complete_pages": sum(
                int(row.get("exact_score_complete_rows") or 0) > 0 for row in pages
            ),
            "operational_observation_complete": bool(pages) and all(
                int(row.get("exact_score_complete_rows") or 0) > 0 for row in pages
            ),
            "incomplete_match_indices": [
                int(row["match_idx"])
                for row in pages if int(row.get("exact_score_complete_rows") or 0) <= 0
            ],
            "page_attempts": int(getattr(arguments, "page_attempts", 3)),
            "successful_pages": sum(row["status"] == "ok" for row in pages),
            "blocked_pages": sum(row["status"] == "source_blocked" for row in pages),
            "failed_or_missing_pages": sum(row["status"] != "ok" for row in pages),
            "timestamp_grades": sorted({row["timestamp_grade"] for row in snapshots}),
            "mapping_source": mapping_source,
            "mapping_cache_bundle": mapping_cache,
            "append_only_key": "capture_batch_id; no (issue,match_idx) overwrite",
            "policy": POLICY,
            "status": "complete" if pages and all(row["status"] == "ok" for row in pages) else "partial",
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        publish_immutable_bundle(stage, final)
    finally:
        discard_stage(stage)
    verification = verify_correct_score_bundle(final, expected_schema=CAPTURE_SCHEMA)
    return {
        **manifest,
        "output_dir": str(final),
        "verification": {key: value for key, value in verification.items() if key != "manifest"},
    }


def read_capture_bundles(
    bundles: list[Path],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, Any]]]:
    snapshots: list[dict[str, str]] = []
    prices: list[dict[str, str]] = []
    pages: list[dict[str, str]] = []
    metadata: list[dict[str, Any]] = []
    for bundle in bundles:
        root = bundle.expanduser().resolve()
        verification = verify_correct_score_bundle(root, expected_schema=CAPTURE_SCHEMA)
        manifest = verification["manifest"]
        for filename, target in (("snapshots.csv", snapshots), ("prices.csv", prices), ("page_inventory.csv", pages)):
            with (root / filename).open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    row["_capture_bundle"] = str(root)
                    row["_capture_bundle_sha"] = verification["sha256s_sha256"]
                    target.append(row)
        metadata.append(
            {
                "path": str(root),
                "capture_batch_id": manifest["capture_batch_id"],
                "sha256s_sha256": verification["sha256s_sha256"],
                "provider": manifest["provider"],
                "bookmaker_key": manifest["bookmaker_key"],
                "provider_company_id": manifest["provider_company_id"],
            }
        )
    return snapshots, prices, pages, metadata


def diagnose_missing_snapshot(
    candidates: list[dict[str, str]],
    *,
    freeze_at_hkt: datetime,
    source_statuses: list[str],
    fallback_reason: str,
) -> tuple[str, dict[str, str] | None]:
    if "source_blocked" in source_statuses:
        return "source_blocked", None
    eligible: list[dict[str, str]] = []
    for row in candidates:
        value = str(row.get("snapshot_ts_hkt") or "")
        if not value or str(row.get("phase") or "") != "pregame":
            continue
        try:
            if datetime.fromisoformat(value) <= freeze_at_hkt:
                eligible.append(row)
        except ValueError:
            continue
    if not eligible:
        return fallback_reason, None
    best = max(
        eligible,
        key=lambda row: (
            int(row.get("exact_score_complete") or 0),
            int(row.get("exact_score_count") or row.get("outcome_count") or 0),
            str(row.get("snapshot_ts_hkt") or ""),
            str(row.get("fetched_at_utc") or ""),
        ),
    )
    reason = str(best.get("completeness_reason") or fallback_reason)
    return reason, best


def replay(arguments: argparse.Namespace) -> dict[str, Any]:
    connection = connect_ro(arguments.db)
    try:
        segment = load_segment(connection, arguments.issue, arguments.segment_idx)
        matches = load_matches(connection, arguments.issue, segment["match_indices"])
    finally:
        connection.close()
    snapshots, prices, pages, bundle_metadata = read_capture_bundles(arguments.capture_bundle)
    snapshots = [row for row in snapshots if row["issue"] == arguments.issue]
    pages = [row for row in pages if row["issue"] == arguments.issue]
    freeze_at = segment["freeze_at_hkt"]
    if datetime.now(timezone.utc).astimezone(HKT) < freeze_at:
        raise CorrectScorePriceError(
            f"segment freeze has not occurred: now<{freeze_at.isoformat()}"
        )
    selected_rows: list[dict[str, Any]] = []
    selected_prices: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    provider = bundle_metadata[0]["provider"] if bundle_metadata else "okooo"
    bookmaker = bundle_metadata[0]["bookmaker_key"] if bundle_metadata else "william_hill"
    company_id = bundle_metadata[0]["provider_company_id"] if bundle_metadata else "14"
    for match_idx in segment["match_indices"]:
        match = matches[match_idx]
        kickoff = match["kickoff_hkt"]
        if kickoff is None:
            raise CorrectScorePriceError(f"kickoff missing: {arguments.issue}#{match_idx}")
        countdown = round((kickoff - freeze_at).total_seconds() / 60, 3)
        candidates = [row for row in snapshots if int(row["match_idx"]) == match_idx]
        selected, reason = select_latest_complete(candidates, freeze_at)
        if selected is None or countdown <= 0:
            page_rows = [row for row in pages if int(row["match_idx"]) == match_idx]
            statuses = sorted({row["status"] for row in page_rows})
            diagnosed_reason, diagnostic = diagnose_missing_snapshot(
                candidates,
                freeze_at_hkt=freeze_at,
                source_statuses=statuses,
                fallback_reason=reason,
            )
            missing_rows.append(
                {
                    "issue": arguments.issue,
                    "segment_idx": arguments.segment_idx,
                    "match_idx": match_idx,
                    "provider": provider,
                    "provider_match_id": next((row["provider_match_id"] for row in page_rows if row["provider_match_id"]), ""),
                    "nowscore_provider_match_id": match["nowscore_provider_match_id"],
                    "bookmaker_key": bookmaker,
                    "provider_company_id": company_id,
                    "market_key": "correct_score",
                    "freeze_at_hkt": freeze_at.isoformat(),
                    "kickoff_hkt": kickoff.isoformat(),
                    "minutes_to_kickoff": countdown,
                    "missing_reason": (
                        "freeze_not_before_kickoff" if countdown <= 0 else diagnosed_reason
                    ),
                    "completeness_reasons_json": json.dumps(
                        sorted(
                            {
                                str(row.get("completeness_reason") or "")
                                for row in candidates if row.get("completeness_reason")
                            }
                        ),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "missing_required_outcomes_json": (
                        str(diagnostic.get("missing_required_outcomes_json") or "[]")
                        if diagnostic else "[]"
                    ),
                    "source_statuses_json": json.dumps(statuses, ensure_ascii=False, separators=(",", ":")),
                    "timestamp_grades_json": json.dumps(
                        sorted({row["timestamp_grade"] for row in candidates}), separators=(",", ":"),
                    ),
                    "source_timestamp_scopes_json": json.dumps(
                        sorted(
                            {
                                str(row.get("source_timestamp_scope") or "")
                                for row in candidates if row.get("source_timestamp_scope")
                            }
                        ),
                        separators=(",", ":"),
                    ),
                    "capture_bundles_json": json.dumps(bundle_metadata, ensure_ascii=False, sort_keys=True),
                }
            )
            continue
        snapshot_ts = datetime.fromisoformat(selected["snapshot_ts_hkt"])
        staleness = round((freeze_at - snapshot_ts).total_seconds() / 60, 3)
        base = {
            "issue": arguments.issue,
            "segment_idx": arguments.segment_idx,
            "match_idx": match_idx,
            "provider": selected["provider"],
            "provider_match_id": selected["provider_match_id"],
            "nowscore_provider_match_id": selected["nowscore_provider_match_id"],
            "bookmaker_key": selected["bookmaker_key"],
            "provider_company_id": selected["provider_company_id"],
            "market_key": "correct_score",
            "freeze_at_hkt": freeze_at.isoformat(),
            "kickoff_hkt": kickoff.isoformat(),
            "snapshot_ts_hkt": selected["snapshot_ts_hkt"],
            "source_time_raw": selected["source_time_raw"],
            "timestamp_grade": selected["timestamp_grade"],
            "source_timestamp_scope": selected.get("source_timestamp_scope", ""),
            "fetched_at_utc": selected["fetched_at_utc"],
            "minutes_to_kickoff": countdown,
            "snapshot_staleness_minutes": staleness,
            "outcome_count": selected["outcome_count"],
            "outcome_schema_sha256": selected["outcome_schema_sha256"],
            "snapshot_id": selected["snapshot_id"],
            "source_url": selected["source_url"],
            "raw_file": selected["raw_file"],
            "raw_payload_sha256": selected["raw_payload_sha256"],
            "raw_row_sha256": selected["raw_row_sha256"],
            "capture_batch_id": selected["capture_batch_id"],
            "capture_bundle": selected["_capture_bundle"],
            "capture_bundle_sha256s_sha256": selected["_capture_bundle_sha"],
            "capture_classification": selected["capture_classification"],
        }
        selected_rows.append(base)
        for price in prices:
            if price["snapshot_id"] != selected["snapshot_id"] or price["_capture_bundle"] != selected["_capture_bundle"]:
                continue
            selected_prices.append(
                {
                    **{key: base[key] for key in SELECTED_FIELDS[:9]},
                    "freeze_at_hkt": base["freeze_at_hkt"],
                    "kickoff_hkt": base["kickoff_hkt"],
                    "snapshot_ts_hkt": base["snapshot_ts_hkt"],
                    "source_time_raw": base["source_time_raw"],
                    "timestamp_grade": base["timestamp_grade"],
                    "source_timestamp_scope": base["source_timestamp_scope"],
                    "minutes_to_kickoff": countdown,
                    "snapshot_staleness_minutes": staleness,
                    "outcome_code": price["outcome_code"],
                    "outcome_group": price["outcome_group"],
                    "outcome_label": price["outcome_label"],
                    "sp": price["sp"],
                    "snapshot_id": selected["snapshot_id"],
                    "capture_bundle": selected["_capture_bundle"],
                    "capture_bundle_sha256s_sha256": selected["_capture_bundle_sha"],
                }
            )
    selected_rows.sort(key=lambda row: int(row["match_idx"]))
    selected_prices.sort(key=lambda row: (int(row["match_idx"]), row["outcome_code"]))
    missing_rows.sort(key=lambda row: int(row["match_idx"]))
    created_at = utc_now()
    identity = json.dumps(
        {
            "issue": arguments.issue, "segment_idx": arguments.segment_idx,
            "freeze_at": freeze_at.isoformat(), "captures": bundle_metadata, "created_at": created_at,
        },
        sort_keys=True,
    )
    replay_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    final = arguments.output_root.expanduser().resolve() / arguments.issue / f"segment_{arguments.segment_idx}" / replay_id
    stage = make_stage(final)
    try:
        write_csv(stage / "selected_snapshots.csv", selected_rows, SELECTED_FIELDS)
        write_csv(stage / "selected_prices.csv", selected_prices, SELECTED_PRICE_FIELDS)
        write_csv(stage / "missing_matches.csv", missing_rows, MISSING_FIELDS)
        staleness = [float(row["snapshot_staleness_minutes"]) for row in selected_rows]
        countdowns = [float(row["minutes_to_kickoff"]) for row in [*selected_rows, *missing_rows]]
        manifest = {
            "schema_version": REPLAY_SCHEMA,
            "issue": arguments.issue,
            "segment_idx": arguments.segment_idx,
            "replay_id": replay_id,
            "created_at_utc": created_at,
            "freeze_at_hkt": freeze_at.isoformat(),
            "freeze_source": "segment_decision_windows.freeze_at",
            "match_indices": segment["match_indices"],
            "market": "correct_score",
            "selected_snapshots": len(selected_rows),
            "selected_prices": len(selected_prices),
            "missing_matches": len(missing_rows),
            "minutes_to_kickoff_min": min(countdowns) if countdowns else None,
            "minutes_to_kickoff_max": max(countdowns) if countdowns else None,
            "snapshot_staleness_minutes_min": min(staleness) if staleness else None,
            "snapshot_staleness_minutes_max": max(staleness) if staleness else None,
            "capture_bundles": bundle_metadata,
            "selection_rule": "latest complete pregame vector with snapshot_ts_hkt <= segment freeze_at_hkt",
            "missing_data_rule": "never substitute current/static/terminal 500 correct-score SP",
            "policy": POLICY,
            "status": "complete" if not missing_rows else "partial",
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        publish_immutable_bundle(stage, final)
    finally:
        discard_stage(stage)
    verification = verify_correct_score_bundle(final, expected_schema=REPLAY_SCHEMA)
    return {
        **manifest,
        "output_dir": str(final),
        "verification": {key: value for key, value in verification.items() if key != "manifest"},
    }


def verify_correct_score_bundle(path: Path, expected_schema: str | None = None) -> dict[str, Any]:
    root = path.expanduser().resolve()
    verification = verify_hashed_bundle(root, expected_schema=expected_schema)
    manifest = verification["manifest"]
    if manifest["schema_version"] == CAPTURE_SCHEMA:
        with (root / "page_inventory.csv").open(encoding="utf-8", newline="") as handle:
            for page in csv.DictReader(handle):
                if page["raw_file"]:
                    raw = root / page["raw_file"]
                    if not raw.is_file() or sha256_file(raw) != page["raw_payload_sha256"]:
                        raise CorrectScorePriceError(f"raw payload mismatch: {page['raw_file']}")
                context_file = str(page.get("source_context_file") or "")
                if context_file:
                    context = root / context_file
                    if not context.is_file() or sha256_file(context) != page.get("source_context_sha256"):
                        raise CorrectScorePriceError(f"source context mismatch: {context_file}")
                try:
                    attempts = json.loads(page.get("attempts_json") or "[]")
                except json.JSONDecodeError as exc:
                    raise CorrectScorePriceError(
                        f"attempt audit JSON invalid: match {page.get('match_idx')}"
                    ) from exc
                for attempt in attempts:
                    for file_key, hash_key in (
                        ("context_file", "context_sha256"),
                        ("odds_file", "odds_sha256"),
                    ):
                        relative = str(attempt.get(file_key) or "")
                        expected = str(attempt.get(hash_key) or "")
                        if not relative:
                            continue
                        target = root / relative
                        if not target.is_file() or sha256_file(target) != expected:
                            raise CorrectScorePriceError(
                                f"attempt raw mismatch: match {page.get('match_idx')} {relative}"
                            )
    elif manifest["schema_version"] == REPLAY_SCHEMA:
        capture_sha = {}
        for item in manifest["capture_bundles"]:
            linked = verify_hashed_bundle(Path(item["path"]), expected_schema=CAPTURE_SCHEMA)
            if linked["sha256s_sha256"] != item["sha256s_sha256"]:
                raise CorrectScorePriceError(f"capture digest mismatch: {item['path']}")
            capture_sha[str(Path(item["path"]).expanduser().resolve())] = linked["sha256s_sha256"]
        freeze = datetime.fromisoformat(manifest["freeze_at_hkt"])
        created_at = datetime.fromisoformat(manifest["created_at_utc"]).astimezone(HKT)
        if created_at < freeze:
            raise CorrectScorePriceError("replay was published before segment freeze")
        with (root / "selected_snapshots.csv").open(encoding="utf-8", newline="") as handle:
            for selected in csv.DictReader(handle):
                snapshot_ts = datetime.fromisoformat(selected["snapshot_ts_hkt"])
                kickoff = datetime.fromisoformat(selected["kickoff_hkt"])
                if snapshot_ts > freeze:
                    raise CorrectScorePriceError(f"post-freeze snapshot: {selected['snapshot_id']}")
                if snapshot_ts >= kickoff:
                    raise CorrectScorePriceError(f"non-pregame snapshot: {selected['snapshot_id']}")
                if float(selected["snapshot_staleness_minutes"]) < 0:
                    raise CorrectScorePriceError(f"negative staleness: {selected['snapshot_id']}")
                capture = str(Path(selected["capture_bundle"]).expanduser().resolve())
                if capture_sha.get(capture) != selected["capture_bundle_sha256s_sha256"]:
                    raise CorrectScorePriceError(f"selected capture mismatch: {selected['snapshot_id']}")
    else:
        raise CorrectScorePriceError(f"unsupported schema: {manifest['schema_version']}")
    return verification


def main() -> int:
    arguments = parse_args()
    if arguments.command == "capture":
        result = capture(arguments)
    elif arguments.command == "replay":
        result = replay(arguments)
    else:
        result = verify_correct_score_bundle(arguments.bundle, expected_schema=arguments.schema)
        result.pop("manifest", None)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
