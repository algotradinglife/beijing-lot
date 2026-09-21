#!/usr/bin/env python3
"""Append a captured bundle's new issues to the sealed settlement release.

Backs the database up before writing, then records the added issues, the capture receipts
and a content hash over the canonical order inside the database itself.
"""
import argparse
import json
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
    print(json.dumps(add_issues(args.database, args.bundle, args.backup,
                                approval_note=args.approval_note), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
