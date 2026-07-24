#!/usr/bin/env python3
"""Clean-checkout verifier for BJ-SEG-RECOVERY-001 packages."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.publish_segment_recovery import verify_directory  # noqa: E402
from src.segment_recovery import (  # noqa: E402
    SegmentRecoveryError,
    canonical,
    load_published_recovery,
    verify_operational_window,
)


def verify(root: Path, db: Path | None = None) -> dict[str, object]:
    receipt = verify_directory(root)
    manifest = json.loads((root / "recovery_manifest.json").read_text(encoding="utf-8"))
    if db is not None:
        conn = sqlite3.connect(db)
        try:
            published = load_published_recovery(
                conn,
                str(manifest["issue"]),
                int(manifest["parent_segment_idx"]),
            )
            if published is None:
                raise SegmentRecoveryError("SQLite recovery publication is missing")
            verify_operational_window(conn, published)
            canonical_published = {
                key: value for key, value in published.items() if key != "manifest_path"
            }
            if str(published["manifest_sha256"]) != str(
                receipt["recovery_manifest_sha256"]
            ) or canonical(canonical_published) != canonical(manifest):
                raise SegmentRecoveryError(
                    "supplied package differs from canonical SQLite recovery"
                )
        finally:
            conn.close()
    return {
        **receipt,
        "issue": str(manifest["issue"]),
        "parent_segment_idx": int(manifest["parent_segment_idx"]),
        "child_identity": str(manifest["child_identity"]),
        "parent_status": str(manifest["parent_status"]),
        "recovery_status": str(manifest["status"]),
        "included_match_count": int(manifest["included_match_count"]),
        "excluded_match_count": int(manifest["excluded_match_count"]),
        "recovery_freeze_at": str(manifest["recovery_freeze_at"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.package, args.db), sort_keys=True))
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        sqlite3.Error,
        SegmentRecoveryError,
    ) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc


if __name__ == "__main__":
    main()
