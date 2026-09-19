#!/usr/bin/env python3
"""Collect Titan historical Euro 1X2 payloads for every candidate bridge ID.

No-agent bounded collector: reads the opaque Titan candidate bridge exported by
the discovery ledger, then fetches each `1x2d.titan007.com/{id}.js` payload into
the isolated Titan control store with pre-network reservation, per-minute
rolling limit, resumable progress and failure quarantine.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.titan_clean.discovery import EURO_1X2_URL  # noqa: E402
from src.titan_clean.fundamentals import parse_analysis_fundamentals  # noqa: E402
from src.titan_clean.risk_acknowledgment import load_risk_acknowledgment  # noqa: E402
from src.titan_clean.store import TitanRosterStore, TitanStoreError  # noqa: E402

HISTORICAL_PARSER_VERSION = "titan_historical_1x2_v1"
AUX_PARSER_VERSION = "titan_historical_aux_v1"
MAX_ATTEMPTS = 5
RETRY_BASE_SECONDS = 15


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_fixture(fixture_id: str, timeout: float = 30) -> bytes:
    request = urllib.request.Request(
        EURO_1X2_URL.format(fixture_id=fixture_id),
        headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _fetch_aux(url: str, timeout: float = 30) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "Accept-Encoding": "identity"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _capture_aux(store: TitanRosterStore, fixture_batch_id: str, fixture_id: str) -> None:
    """Capture analysis and handicap raw pages plus parsed fundamentals (best effort)."""
    try:
        analysis_payload = _fetch_aux(f"https://zq.titan007.com/analysis/{fixture_id}cn.htm")
        store.record_historical_aux(
            batch_id=f"{fixture_batch_id}:analysis",
            fixture_batch_id=fixture_batch_id,
            endpoint_kind="analysis",
            source_fixture_id=fixture_id,
            source_url=f"https://zq.titan007.com/analysis/{fixture_id}cn.htm",
            payload=analysis_payload,
            requested_at_utc=now_utc(),
            trusted_received_at_utc=now_utc(),
            parser_version=AUX_PARSER_VERSION,
        )
        fundamentals = parse_analysis_fundamentals(analysis_payload)
        store.record_historical_fundamental(
            fixture_batch_id=fixture_batch_id,
            source_fixture_id=fixture_id,
            parser_version=AUX_PARSER_VERSION,
            venue=fundamentals.venue,
            weather=fundamentals.weather,
            temperature=fundamentals.temperature,
            home_form_json=fundamentals.home_form,
            away_form_json=fundamentals.away_form,
            h2h_json=fundamentals.h2h,
            home_season_stats_json=fundamentals.home_season_stats,
            away_season_stats_json=fundamentals.away_season_stats,
            standings_link=fundamentals.standings_link,
            fundamentals_available=fundamentals.venue is not None or bool(fundamentals.home_form),
        )
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError, OSError) as exc:
        print({"aux_failed": fixture_id, "kind": "analysis", "error": type(exc).__name__}, flush=True)
    try:
        handicap_payload = _fetch_aux(f"https://vip.titan007.com/AsianOdds_n.aspx?id={fixture_id}")
        store.record_historical_aux(
            batch_id=f"{fixture_batch_id}:handicap",
            fixture_batch_id=fixture_batch_id,
            endpoint_kind="handicap",
            source_fixture_id=fixture_id,
            source_url=f"https://vip.titan007.com/AsianOdds_n.aspx?id={fixture_id}",
            payload=handicap_payload,
            requested_at_utc=now_utc(),
            trusted_received_at_utc=now_utc(),
            parser_version=AUX_PARSER_VERSION,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        print({"aux_failed": fixture_id, "kind": "handicap", "error": type(exc).__name__}, flush=True)


def load_bridge_candidates(path: Path) -> list[str]:
    document = json.loads(path.read_text())
    if document.get("schema_version") != "titan_historical_candidate_bridge_v1":
        raise ValueError("unsupported candidate bridge schema")
    candidates = document.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidate bridge is empty")
    ids: list[str] = []
    for item in candidates:
        fixture_id = item.get("nowscore_provider_match_id")
        if not isinstance(fixture_id, str) or not fixture_id.isdecimal():
            raise ValueError("candidate bridge contains an invalid provider id")
        ids.append(fixture_id)
    if len(ids) != len(set(ids)):
        raise ValueError("candidate bridge contains duplicate provider ids")
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--risk-acknowledgment", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=60)
    parser.add_argument("--issues", help="comma-separated 500 issue codes to limit the run (trial batches)")
    parser.add_argument("--limit", type=int, default=0, help="max candidates to process this run (0 = all)")
    parser.add_argument("--skip-aux", action="store_true", help="only fetch 1x2d fixture payload, skip analysis/handicap aux")
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 600:
        parser.error("--batch-size must be between 1 and 600")
    if args.limit < 0:
        parser.error("--limit must be >= 0")

    risk = load_risk_acknowledgment(args.risk_acknowledgment)
    candidates = load_bridge_candidates(args.bridge)
    if args.issues:
        import sqlite3
        connection = sqlite3.connect(args.data_root / "control/external_id_discovery/discovery.sqlite")
        placeholders = ",".join("?" * len(args.issues.split(",")))
        rows = connection.execute(
            f"SELECT DISTINCT nowscore_provider_match_id FROM issue_slot_nowscore_map WHERE issue_code IN ({placeholders})",
            tuple(args.issues.split(",")),
        ).fetchall()
        connection.close()
        allowed = {str(row[0]) for row in rows}
        candidates = [fixture_id for fixture_id in candidates if fixture_id in allowed]
        print({"trial_issues": args.issues, "trial_candidates": len(candidates)})
    if args.limit:
        candidates = candidates[: args.limit]
        print({"limit": args.limit, "candidates_after_limit": len(candidates)})
    store = TitanRosterStore.open(args.data_root)
    try:
        captured = store.historical_captured_ids()
        failed = store.historical_failed_ids(min_attempts=MAX_ATTEMPTS)
        pending = [fixture_id for fixture_id in candidates if fixture_id not in captured and fixture_id not in failed]

        def needs_aux(fixture_id: str) -> bool:
            row = store.connection.execute(
                "SELECT 1 FROM historical_aux_capture WHERE source_fixture_id=? AND endpoint_kind='analysis' LIMIT 1",
                (fixture_id,),
            ).fetchone()
            return row is None

        aux_pending = [] if args.skip_aux else [
            fixture_id for fixture_id in candidates if fixture_id in captured and needs_aux(fixture_id)
        ]
        print({"pending": len(pending), "aux_pending": len(aux_pending), "captured": len(captured), "failed": len(failed), "skip_aux": args.skip_aux})

        def reserve_n(count: int, key: str) -> None:
            while True:
                try:
                    store.reserve_low_frequency_capture(
                        batch_id=f"reserve:{now_utc()}:{key}",
                        receipt_sha256=risk.receipt_sha256,
                        reserved_at_utc=now_utc(),
                        request_count=count,
                        max_requests_per_minute=risk.max_requests_per_minute,
                    )
                    return
                except TitanStoreError:
                    time.sleep(2)

        while pending or aux_pending:
            work = (pending + aux_pending)[: args.batch_size]
            batch_done = 0
            for fixture_id in work:
                attempts = store.connection.execute(
                    "SELECT COUNT(*) FROM historical_fixture_failure WHERE source_fixture_id=?", (fixture_id,)
                ).fetchone()[0]
                try:
                    existing_batch = store.connection.execute(
                        "SELECT batch_id FROM historical_fixture_capture WHERE source_fixture_id=? ORDER BY trusted_received_at_utc LIMIT 1",
                        (fixture_id,),
                    ).fetchone()
                    if existing_batch is not None:
                        if args.skip_aux:
                            continue
                        reserve_n(2, f"{fixture_id}:aux")
                        _capture_aux(store, existing_batch[0], fixture_id)
                        continue
                    reserve_n(1, f"{fixture_id}:fixture")
                    payload = fetch_fixture(fixture_id)
                    requested = now_utc()
                    fixture_batch_id = f"historical:{requested}:{fixture_id}"
                    store.record_historical_fixture(
                        batch_id=fixture_batch_id,
                        admission_bridge_sha256=args.bridge.resolve().name[:-5],
                        source_fixture_id=fixture_id,
                        payload=payload,
                        requested_at_utc=requested,
                        trusted_received_at_utc=now_utc(),
                        parser_version=HISTORICAL_PARSER_VERSION,
                    )
                    batch_done += 1
                    if not args.skip_aux:
                        reserve_n(2, f"{fixture_id}:aux")
                        _capture_aux(store, fixture_batch_id, fixture_id)
                except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError, OSError) as exc:
                    store.record_historical_failure(
                        source_fixture_id=fixture_id, attempted_at_utc=now_utc(), error=exc
                    )
                    if int(attempts) + 1 >= MAX_ATTEMPTS:
                        print({"fixture": fixture_id, "status": "FAILED", "attempts": int(attempts) + 1, "error": type(exc).__name__})
                    else:
                        time.sleep(RETRY_BASE_SECONDS * (int(attempts) + 1))
            progress = store.historical_progress()
            print({"batch_done": batch_done, "captured": progress["captured"], "failed_ids": progress["failed_ids"], "remaining": len(candidates) - progress["captured"] - progress["failed_ids"]})
            captured = store.historical_captured_ids()
            failed = store.historical_failed_ids(min_attempts=MAX_ATTEMPTS)
            pending = [fixture_id for fixture_id in candidates if fixture_id not in captured and fixture_id not in failed]
            aux_pending = [] if args.skip_aux else [
                fixture_id for fixture_id in candidates if fixture_id in captured and needs_aux(fixture_id)
            ]
        print({"status": "ALL_HISTORICAL_CANDIDATES_DONE", "progress": store.historical_progress()})
    finally:
        store.close()


if __name__ == "__main__":
    main()
