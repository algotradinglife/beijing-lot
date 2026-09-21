#!/usr/bin/env python3
"""Capture the issues the live board advertises beyond the release's newest.

Routine discovery does not need the historical candidate walk: one request to the board's
own page yields its issue list, and each new issue then costs five pages. This writes a
capture bundle in the format `apply_settlement_issue_addition.py` consumes and never touches
the release, so capturing and appending stay separately reviewable.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.nowscore_issue_inventory import rate_limited_transport  # noqa: E402
from src.nowscore_live_issues import (  # noqa: E402
    last_kickoff,
    live_issues,
    pending_issues,
)
from src.nowscore_settlement import PLAYS, source_url  # noqa: E402

BOARD_URL = "https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5"
BUNDLE_SCHEMA = "nowscore_history_batch_v1"


def release_issues(database: Path) -> set[str]:
    """Return the issues the release carries, read-only.

    Membership decides what is pending. The newest issue alone is not enough: an issue the
    board advertises, that the applier refuses, and that a later issue overtakes would drop
    below a "newest issue" watermark and never be retried.
    """
    con = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT DISTINCT issue FROM observation").fetchall()
    finally:
        con.close()
    carried = {row[0] for row in rows}
    if not carried:
        raise ValueError("release carries no observations")
    return carried


def capture_issues(database: Path, run_root: Path, *, timeout_seconds: float,
                   interval_seconds: float, transport=None, now=None) -> dict:
    """Resolve the board's issues, capture the new ones, and write one bundle.

    Fails closed: a board page without its list, a page that is not the requested issue's
    source, or a request that never succeeds leaves raw evidence but no sealed manifest, so
    the applier's domain validation refuses it rather than appending a partial issue.
    """
    if interval_seconds < 2:
        raise ValueError("request interval must be at least two seconds")
    run_root = Path(run_root)
    if run_root.exists():
        raise FileExistsError(run_root)
    now = now or (lambda: datetime.now(timezone.utc))
    if transport is None:
        # The same per-user lock the historical inventory uses, so the two paths serialise
        # against each other instead of each keeping its own pace.
        lock = Path(tempfile.gettempdir()) / f"nowscore-inventory-{os.getuid()}.lock"

        def paced(url, timeout):
            return rate_limited_transport(url, timeout, lock_path=lock,
                                          interval=interval_seconds)
        transport = paced
    board_started = now()
    board = transport(BOARD_URL, timeout_seconds)
    if board["status"] != 200:
        raise ValueError(f"live board returned {board['status']}")
    listing = live_issues(board["payload"])
    carried = release_issues(database)
    pending = pending_issues(listing["issues"], carried)
    next_check = _serialise(last_kickoff(board["payload"]))

    # The board response authorises the decision, so it is kept either way: the advertised
    # list and the scheduling reading must be replayable without another request.
    (run_root / "raw").mkdir(parents=True)
    board_sha = hashlib.sha256(board["payload"]).hexdigest()
    (run_root / "raw" / (board_sha + ".html")).write_bytes(board["payload"])
    (run_root / "board.receipt.json").write_text(json.dumps(
        {"url": BOARD_URL, "received_at": board_started.isoformat(), "sha256": board_sha,
         "byte_count": len(board["payload"]), "advertised": listing["issues"],
         "current": listing["current"], "is_current": listing["is_current"],
         "release_carried": sorted(carried), "pending": pending,
         "next_check_after": next_check}, ensure_ascii=False), encoding="utf-8")
    if not pending:
        return {"status": "up_to_date", "bundle": str(run_root),
                "release_issues": len(carried),
                "advertised": listing["issues"], "current": listing["current"],
                "next_check_after": next_check}

    captures = []
    for issue in pending:
        for typeid in sorted(PLAYS):
            url = source_url(issue, typeid)
            response = transport(url, timeout_seconds)
            if response["status"] != 200 or not response["payload"]:
                raise ValueError(f"capture failed for {issue}/{PLAYS[typeid]}: "
                                 f"status {response['status']}")
            payload = response["payload"]
            sha = hashlib.sha256(payload).hexdigest()
            (run_root / "raw" / (sha + ".html")).write_bytes(payload)
            # Sampled after the response: a paced batch takes minutes, and these timestamps
            # become the page provenance the applier persists.
            captures.append({"issue": issue, "typeid": typeid, "url": url,
                             "received_at": now().isoformat(), "sha256": sha,
                             "classification": "data", "byte_count": len(payload)})
    manifest = {"schema": BUNDLE_SCHEMA, "source": "nowscore",
                "board_url": BOARD_URL, "board_current": listing["current"],
                "board_is_current": listing["is_current"],
                "board_sha256": board_sha,
                "release_carried_at_capture": sorted(carried),
                "batch": {"batch_id": f"live-{pending[0]}-{pending[-1]}",
                          "issues": pending},
                "controls": [], "captures": captures, "requested_issues": pending}
    (run_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False),
                                            encoding="utf-8")
    return {"status": "captured", "bundle": str(run_root), "pending": pending,
            "pages": len(captures), "next_check_after": next_check}


def _serialise(moment):
    return moment.isoformat() if moment else None


def main(argv=None):
    """Resolve, capture, and report; never write the release."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--request-interval", type=float, default=2.0)
    args = parser.parse_args(argv)
    result = capture_issues(args.database, args.run_root,
                            timeout_seconds=args.timeout,
                            interval_seconds=args.request_interval)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
