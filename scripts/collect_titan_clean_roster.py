#!/usr/bin/env python3
"""Capture a fresh Titan roster and optional Titan fixture payloads.

This collector deliberately has no Nowscore or legacy-database input. It writes
only beneath an explicit clean data root and never fetches 500 settlement data.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.titan_clean.authorization import load_titan_authorization  # noqa: E402
from src.titan_clean.discovery import SCHEDULE_URL, euro_1x2_url  # noqa: E402
from src.titan_clean.risk_acknowledgment import load_risk_acknowledgment  # noqa: E402
from src.titan_clean.store import TitanRosterStore  # noqa: E402

PARSER_VERSION = "titan-clean-v1"
USER_AGENT = "beijing-lot-titan-clean/1.0"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/javascript,application/javascript,*/*;q=0.1"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP status {response.status} for {url}")
        return response.read()


def collect(
    root: Path,
    *,
    capture_key: str,
    fixture_ids: tuple[str, ...],
    fetch: Callable[[str], bytes] = fetch_bytes,
    clock: Callable[[], str] = now_utc,
    authorization_mode: str = "PROBE",
    authorization_receipt_sha256: str | None = None,
    max_requests_per_minute: int | None = None,
    max_fixture_ids_per_run: int | None = None,
    next_unseen_fixture: bool = False,
) -> dict[str, object]:
    """Record an observed Titan roster and explicitly requested fixture details."""
    store = TitanRosterStore.open(root)
    try:
        if authorization_mode == "USER_RISK_ACKNOWLEDGED":
            if authorization_receipt_sha256 is None or max_requests_per_minute is None or max_fixture_ids_per_run is None:
                raise ValueError("risk-acknowledged collection requires explicit low-frequency limits")
            planned_fixture_count = len(fixture_ids) + int(next_unseen_fixture)
            if planned_fixture_count > max_fixture_ids_per_run:
                raise ValueError("risk acknowledgement fixture-per-run limit exceeded")
            store.reserve_low_frequency_capture(
                batch_id=f"{capture_key}:roster", receipt_sha256=authorization_receipt_sha256,
                reserved_at_utc=clock(), request_count=1 + planned_fixture_count,
                max_requests_per_minute=max_requests_per_minute,
            )
        requested = clock()
        schedule = fetch(SCHEDULE_URL)
        received = clock()
        roster_result = store.record_schedule(
            batch_id=f"{capture_key}:roster",
            payload=schedule,
            source_url=SCHEDULE_URL,
            requested_at_utc=requested,
            trusted_received_at_utc=received,
            parser_version=PARSER_VERSION,
            authorization_mode=authorization_mode,
            authorization_receipt_sha256=authorization_receipt_sha256,
        )
        admitted = tuple(
            row[0]
            for row in store.connection.execute(
                "SELECT source_fixture_id FROM roster_observation WHERE batch_id=? ORDER BY ordinal",
                (f"{capture_key}:roster",),
            )
        )
        selected_fixture_ids = fixture_ids
        if next_unseen_fixture:
            captured_ids = {
                row[0] for row in store.connection.execute("SELECT DISTINCT source_fixture_id FROM fixture_capture")
            }
            selected_fixture_ids = tuple(fixture_id for fixture_id in admitted if fixture_id not in captured_ids)[:1]
        captured: list[str] = []
        for fixture_id in selected_fixture_ids:
            if fixture_id not in admitted:
                raise ValueError(f"requested fixture id is absent from this Titan roster: {fixture_id}")
            requested = clock()
            payload = fetch(euro_1x2_url(fixture_id))
            received = clock()
            store.record_fixture(
                batch_id=f"{capture_key}:fixture:{fixture_id}",
                roster_batch_id=f"{capture_key}:roster",
                source_fixture_id=fixture_id,
                payload=payload,
                requested_at_utc=requested,
                trusted_received_at_utc=received,
                parser_version=PARSER_VERSION,
            )
            captured.append(fixture_id)
        return {
            "capture_key": capture_key,
            "roster_inserted": roster_result.inserted,
            "roster_fixture_count": roster_result.fixture_count,
            "fixture_ids_captured": captured,
            "authorization_mode": authorization_mode,
            "authorization_receipt_sha256": authorization_receipt_sha256,
            "manifest_sha256": hashlib.sha256(store.manifest()).hexdigest(),
        }
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--capture-key", required=True)
    parser.add_argument("--fixture-id", action="append", default=[])
    parser.add_argument("--next-unseen-fixture", action="store_true")
    parser.add_argument("--probe", action="store_true", help="allow one unauthenticated read-only probe fixture")
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--risk-acknowledgment", type=Path)
    args = parser.parse_args()
    if args.next_unseen_fixture and args.fixture_id:
        parser.error("--next-unseen-fixture and --fixture-id are mutually exclusive")
    if sum(bool(item) for item in (args.probe, args.authorization_receipt, args.risk_acknowledgment)) > 1:
        parser.error("--probe, --authorization-receipt and --risk-acknowledgment are mutually exclusive")
    if args.probe:
        if len(args.fixture_id) > 1:
            parser.error("a probe can request at most one fixture")
        authorization_mode, receipt_sha256 = "PROBE", None
    elif args.authorization_receipt:
        authorization = load_titan_authorization(args.authorization_receipt)
        authorization_mode, receipt_sha256 = "AUTHORIZED", authorization.receipt_sha256
        max_requests_per_minute = max_fixture_ids_per_run = None
    elif args.risk_acknowledgment:
        risk = load_risk_acknowledgment(args.risk_acknowledgment)
        authorization_mode, receipt_sha256 = "USER_RISK_ACKNOWLEDGED", risk.receipt_sha256
        max_requests_per_minute, max_fixture_ids_per_run = risk.max_requests_per_minute, risk.max_fixture_ids_per_run
    else:
        parser.error("operational collection requires --authorization-receipt or --risk-acknowledgment")
    if args.probe:
        max_requests_per_minute = max_fixture_ids_per_run = None
    result = collect(
        args.data_root,
        capture_key=args.capture_key,
        fixture_ids=tuple(args.fixture_id),
        authorization_mode=authorization_mode,
        authorization_receipt_sha256=receipt_sha256,
        max_requests_per_minute=max_requests_per_minute,
        max_fixture_ids_per_run=max_fixture_ids_per_run,
        next_unseen_fixture=args.next_unseen_fixture,
    )
    print(result)


if __name__ == "__main__":
    main()
