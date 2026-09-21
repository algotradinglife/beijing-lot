#!/usr/bin/env python3
"""Append a captured bundle's new issues to the sealed settlement release.

Backs the database up before writing, then records the added issues, the capture receipts
and a content hash over the canonical order inside the database itself.

The receipt is also written next to the bundle's own evidence as ``applied.json``. A replay
needs the exact pre-write snapshot of its batch to derive which issues were owed, so the
backup has to be named durably somewhere a retention pass can read; the bundle is the batch's
own evidence directory and outlives the snapshots.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.settlement_issue_addition import add_issues  # noqa: E402
from src.settlement_storage import validate_settlement_storage  # noqa: E402


def main(argv=None):
    """Validate explicit storage, then append one captured bundle's new issues."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'bundle', 'backup', 'data-root'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--mountpoint', type=Path)
    parser.add_argument('--approval-note', required=True)
    args = parser.parse_args(argv)
    validate_settlement_storage(args.data_root, [args.database, args.backup],
                                mountpoint=args.mountpoint)
    receipt = add_issues(args.database, args.bundle, args.backup,
                         approval_note=args.approval_note)
    receipt["approval_note"] = args.approval_note
    receipt["applied_at"] = datetime.now(timezone.utc).isoformat()
    (args.bundle / "applied.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
