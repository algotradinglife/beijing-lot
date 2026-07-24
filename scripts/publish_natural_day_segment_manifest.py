#!/usr/bin/env python3
"""Audit then atomically publish the BJ-SEG-DAY-001 operational contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from src.natural_day_segments import POLICY_ID, build_natural_day_segments  # noqa: E402

HKT = ZoneInfo("Asia/Hong_Kong")
DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_OUTPUT = ROOT / "results/segment_decision_forward_artifacts"


@dataclass(frozen=True)
class Match:
    match_idx: int
    kickoff: datetime


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def iso(value: datetime) -> str:
    return value.astimezone(HKT).isoformat(timespec="seconds")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--now-hkt", default="", help="test-only ISO timestamp")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now_hkt) if args.now_hkt else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=HKT)
    now = now.astimezone(HKT)
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT match_idx,end_time FROM matches WHERE issue=? ORDER BY datetime(end_time),match_idx", (args.issue,)).fetchall()
        matches = [Match(int(row["match_idx"]), datetime.fromisoformat(str(row["end_time"])).replace(tzinfo=HKT)) for row in rows]
        built = build_natural_day_segments(args.issue, matches)
        if not built.segments:
            raise SystemExit("refusing to publish an operational manifest with no eligible segments")
        old = [dict(row) for row in conn.execute("SELECT issue,segment_idx,segment_start,segment_end,freeze_at,match_indices_json,created_at,manual_frozen_at FROM segment_decision_windows WHERE issue=? ORDER BY segment_idx", (args.issue,))]
        old_hash = hashlib.sha256(canonical(old)).hexdigest()
        earliest = min(item.freeze_at for item in built.segments)
        if now >= earliest:
            raise SystemExit(f"fail closed: first freeze {iso(earliest)} has passed")
        # A freeze ledger is irrevocable evidence, so correction is prohibited.
        ledger = ROOT / "results/research/multimarket_segment_freeze_v1/ledger"
        if ledger.exists() and any(args.issue in path.read_text(encoding="utf-8", errors="ignore") for path in ledger.glob("*.json")):
            raise SystemExit("fail closed: existing research freeze ledger references issue")
        manifest = {
            "schema_version": "natural_day_segment_manifest_v1", "capability_id": "BJ-SEG-DAY-001",
            "policy": POLICY_ID, "issue": str(args.issue), "published_at_hkt": iso(now),
            "denominator_match_indices": list(built.denominator_match_indices), "skipped": list(built.skipped),
            "segments": [{"segment_idx": item.segment_idx, "hkt_dates": list(item.hkt_dates), "match_indices": list(item.match_indices), "match_count": len(item.match_indices), "segment_start": iso(item.first_kickoff), "segment_end": iso(item.last_kickoff), "freeze_at": iso(item.freeze_at), "checkpoints": {"t6h": iso(item.freeze_at - timedelta(hours=6)), "t2h": iso(item.freeze_at - timedelta(hours=2)), "t30m": iso(item.freeze_at - timedelta(minutes=30))}} for item in built.segments],
            "incident_audit": {"replaced_window_count": len(old), "pre_correction_sha256": old_hash, "pre_correction_windows": old},
        }
        manifest["manifest_sha256"] = hashlib.sha256(canonical(manifest)).hexdigest()
        destination = args.output_root / str(args.issue) / "natural_day_v1"
        destination.mkdir(parents=True, exist_ok=True)
        audit_path = destination / "incident_wrong_entire_issue_window.json"
        manifest_path = destination / "segment_manifest.json"
        audit_path.write_bytes(canonical(manifest["incident_audit"]) + b"\n")
        # Transaction keeps DB consumers from observing old/new mixed windows.
        with conn:
            conn.execute("DELETE FROM segment_decision_windows WHERE issue=?", (args.issue,))
            for item in built.segments:
                conn.execute("INSERT INTO segment_decision_windows(issue,segment_idx,segment_start,segment_end,freeze_at,match_indices_json,created_at) VALUES(?,?,?,?,?,?,?)", (args.issue, item.segment_idx, iso(item.first_kickoff), iso(item.last_kickoff), iso(item.freeze_at), json.dumps(list(item.match_indices), separators=(",", ":")), iso(now)))
        manifest_path.write_bytes(canonical(manifest) + b"\n")
        print(json.dumps({"manifest": str(manifest_path), "sha256": manifest["manifest_sha256"], "segments": [len(x.match_indices) for x in built.segments]}, sort_keys=True))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
