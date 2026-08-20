#!/usr/bin/env python3
"""Create, verify, or restore a #249 external data snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_portability import (  # noqa: E402
    DATA_ROOT_ENV,
    create_snapshot,
    restore_snapshot,
    snapshot_summary,
    verify_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("snapshot")
    create.add_argument("--config", type=Path, required=True)
    create.add_argument("--source-root", type=Path, default=ROOT)
    create.add_argument("--snapshot-id", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--snapshot-id", required=True)

    restore = subparsers.add_parser("restore")
    restore.add_argument("--snapshot-id", required=True)
    restore.add_argument("--target", type=Path, required=True)

    args = parser.parse_args()
    root_text = os.environ.get(DATA_ROOT_ENV)
    if not root_text:
        parser.error(f"{DATA_ROOT_ENV} must be explicitly set")
    external_root = Path(root_text)
    snapshot_path = external_root / "snapshots" / args.snapshot_id

    if args.command == "snapshot":
        snapshot_path = create_snapshot(
            config_path=args.config,
            source_root=args.source_root,
            external_root=external_root,
            snapshot_id=args.snapshot_id,
        )
        result = snapshot_summary(snapshot_path)
    elif args.command == "verify":
        result = verify_snapshot(snapshot_path)
    else:
        result = restore_snapshot(snapshot_path=snapshot_path, target=args.target)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
