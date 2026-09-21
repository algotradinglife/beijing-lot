#!/usr/bin/env python3
"""Apply the approved issue-recovery ledger to the sealed settlement release.

Backs the database up before writing, then records the recovered issues, the archive
evidence manifest and the original build receipt inside the database itself.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.settlement_issue_recovery import recover_issues  # noqa: E402
from src.settlement_storage import validate_settlement_storage  # noqa: E402


def main(argv=None):
    """Validate explicit storage, then apply one approved archive-recovery ledger."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'ledger', 'backup', 'data-root'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--mountpoint', type=Path)
    parser.add_argument('--approval-note', required=True)
    args = parser.parse_args(argv)
    validate_settlement_storage(args.data_root, [args.database, args.backup],
                                mountpoint=args.mountpoint)
    print(json.dumps(recover_issues(args.database, args.ledger, args.backup,
                                    approval_note=args.approval_note),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
