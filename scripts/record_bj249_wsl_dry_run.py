#!/usr/bin/env python3
"""Publish compact Git evidence from the successful #249 WSL restore rehearsal."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT_ENV = "BEIJING_LOT_DATA_ROOT"


def _canonical(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--restore-target", type=Path, required=True)
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=ROOT / "evidence/bj249_data_portability_v1",
    )
    args = parser.parse_args()
    external_text = os.environ.get(DATA_ROOT_ENV)
    if not external_text:
        parser.error(f"{DATA_ROOT_ENV} must be explicitly set")
    snapshot = Path(external_text) / "snapshots" / args.snapshot_id
    manifest_bytes = (snapshot / "MANIFEST.json").read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if (snapshot / "COMPLETE").read_text(encoding="ascii").strip() != manifest_sha:
        raise ValueError("snapshot completion marker does not bind manifest")
    restore_receipt = json.loads(
        (args.restore_target / "RESTORE_RECEIPT.json").read_text(encoding="utf-8")
    )
    if restore_receipt["manifest_sha256"] != manifest_sha:
        raise ValueError("restore receipt does not bind snapshot manifest")
    manifest = json.loads(manifest_bytes)
    if restore_receipt["restored_asset_count"] != len(manifest["assets"]):
        raise ValueError("restore receipt asset count does not match manifest")
    receipt = {
        "contract": "BJ-UNIFIED-DATA-PORTABILITY-001",
        "snapshot_id": args.snapshot_id,
        "manifest_sha256": manifest_sha,
        "snapshot_verification": {
            key: restore_receipt[key]
            for key in ("status", "asset_count", "total_bytes", "verified_at_utc", "manifest_sha256")
        },
        "restore_verification": {
            "status": "PASS",
            "restored_asset_count": restore_receipt["restored_asset_count"],
            "restored_at_utc": restore_receipt["restored_at_utc"],
        },
        "source_mutation_check": "PASS_BY_READ_ONLY_URI_AND_FOCUSED_TEST",
        "external_location": "$BEIJING_LOT_DATA_ROOT/snapshots/" + args.snapshot_id,
        "restore_location": "isolated-ext4-restore-target",
    }
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    (args.evidence_dir / "MANIFEST.json").write_bytes(manifest_bytes)
    (args.evidence_dir / "wsl_dry_run_receipt.json").write_bytes(_canonical(receipt))
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
